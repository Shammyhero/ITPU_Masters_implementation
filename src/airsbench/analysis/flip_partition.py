"""Flip-partition analysis — free, retroactive, no API calls.

Raw accuracy under a freshness fault is close to arithmetic: staleness
mechanically changes the correct answer on some share of queries, and an agent
reasoning perfectly on what it was served must be wrong on exactly those. So
"freshness lowers accuracy" measures the answer-flip rate with an expensive
language model, and is not by itself a finding.

This module partitions every logged retrieval decision by whether staleness
changed the correct answer, which separates two very different questions:

  answer did NOT flip  — accuracy should equal baseline. If it does not,
                         staleness is doing something beyond changing the
                         right answer (e.g. confusing the agent outright).
  answer DID flip      — the agent cannot be right. The measurement is
                         whether it ABSTAINS or COMMITS CONFIDENTLY. This
                         cell is the actual finding, and it is where silent
                         failure lives.

The reconstruction is exact rather than statistical. Query sampling and query
timestamps derive from ``RunConfig.sample_seed`` (invariant 2), so replaying
that seed regenerates the identical queries at the identical simulated times;
the flip status is then joined to the decisions already on disk. Every replay
is checked against the logged ``ground_truth`` before it is used — see
``verify`` — so a drift between this module and the runner surfaces as a
failure rather than as quietly wrong numbers.

Retrieval only. The classification task's label (ArrDel15) is a property of the
flight, not of the catalog, so staleness there attenuates a feature rather than
moving the correct answer; there is no flip to partition on.

    python -m airsbench.analysis.flip_partition
    python -m airsbench.analysis.flip_partition --verify-only
"""

from __future__ import annotations

import argparse
import bisect
import json
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agents.retrieval import RetrievalAgent
from ..pipelines.loader import CatalogTimeMachine
from ..runner.config import NEVER_POOLED, RunConfig, run_arm
from ..runner.execute import N_CANDIDATES, value_staleness_s


class CatalogIndex:
    """Per-product update timelines — ``state_at`` for a handful of products.

    ``CatalogTimeMachine.state_at`` materialises all 20k products per call,
    which is fine once per run but not for the ~5.7k lookups this analysis
    needs. This index answers the same question for a named product in log
    time, and is checked against the time machine in
    ``tests/test_flip_partition.py``.
    """

    def __init__(self, machine: CatalogTimeMachine) -> None:
        self.base = machine.base
        timelines: dict[str, tuple[list[float], list[tuple[float, int]]]] = {}
        for update in machine.updates:
            pid = update["product_id"]
            row = self.base.get(pid)
            if row is None:
                continue
            ts_list, snapshots = timelines.setdefault(pid, ([], []))
            price, stock = snapshots[-1] if snapshots else (row["price"], row["stock"])
            ts_list.append(update["ts"])
            snapshots.append(
                (update.get("price", price), update.get("stock", stock))
            )
        self.timelines = timelines

    def value_at(self, pid: str, ts: float) -> dict[str, Any] | None:
        """Price/stock of one product after replaying updates with u.ts <= ts."""
        row = self.base.get(pid)
        if row is None:
            return None
        timeline = self.timelines.get(pid)
        price, stock = row["price"], row["stock"]
        if timeline is not None:
            ts_list, snapshots = timeline
            idx = bisect.bisect_right(ts_list, ts)
            if idx:
                price, stock = snapshots[idx - 1]
        return {"product_id": pid, "price": price, "stock": stock}

    def best(self, pids: list[str], ts: float) -> str | None:
        """Cheapest in-stock product among ``pids`` at ``ts``, or None."""
        products = [p for pid in pids if (p := self.value_at(pid, ts)) is not None]
        winner = RetrievalAgent.ground_truth(products)
        return winner["product_id"] if winner else None


@dataclass
class QueryOutcome:
    """One logged decision joined to its replayed flip status."""

    query: str
    truth_id: str
    served_id: str | None
    chosen: str | None
    correct: bool
    confidence: float
    abstained: bool
    parse_failed: bool

    @property
    def flipped(self) -> bool:
        """Staleness made the served-optimal answer differ from the true one."""
        return self.served_id != self.truth_id

    @property
    def served_faithful(self) -> bool:
        """Agent picked the best answer available in the data it was shown.

        Under a flip this is the signature of correct reasoning over corrupt
        input: the agent is wrong, but not confused.
        """
        return self.chosen is not None and self.chosen == self.served_id


class Replayer:
    """Regenerates the exact query sample and timestamps of a retrieval run."""

    def __init__(self, data_dir: Path) -> None:
        import pandas as pd

        machine = CatalogTimeMachine.load(data_dir)
        self.max_ts = machine.max_ts
        self.index = CatalogIndex(machine)
        queries = pd.read_parquet(data_dir / "queries.parquet").to_dict("records")
        self.usable = [q for q in queries if len(q["relevant_product_ids"]) >= 2]
        self._plans: dict[tuple[int, int], list[tuple[str, list[str], float]]] = {}

    def _plan(self, sample_seed: int, n_queries: int) -> list[tuple[str, list[str], float]]:
        """The (query, candidate ids, query time) sequence for a sample seed.

        Cached: the paired design gives every condition within a replication
        the same seed, so this is computed once per replication rather than
        once per run.
        """
        key = (sample_seed, n_queries)
        if key in self._plans:
            return self._plans[key]

        rng = random.Random(sample_seed)
        sampled = rng.sample(self.usable, min(n_queries, len(self.usable)))
        plan = []
        for query in sampled:
            # Drawn for every sampled query, including ones later skipped —
            # the runner draws before it filters, so the RNG stream must too.
            t_query = rng.uniform(self.max_ts * 0.5, self.max_ts)
            ids = [str(pid) for pid in query["relevant_product_ids"]][:N_CANDIDATES]
            ids = [pid for pid in ids if pid in self.index.base]
            plan.append((query["query"], ids, t_query))
        self._plans[key] = plan
        return plan

    def outcomes(self, run: dict[str, Any]) -> list[QueryOutcome]:
        """Join a run's logged decisions to their replayed flip status.

        Raises ValueError if the replay disagrees with the run artifact, which
        means this module and the runner have drifted apart and no number
        below it can be trusted.
        """
        config = RunConfig(
            **{k: v for k, v in run["config"].items() if k in RunConfig.__dataclass_fields__}
        )
        staleness = value_staleness_s(config)
        decisions = run["decisions"]

        outcomes: list[QueryOutcome] = []
        for query, ids, t_query in self._plan(config.sample_seed, config.n_queries):
            if len(ids) < 2:
                continue
            truth_id = self.index.best(ids, t_query)
            if truth_id is None:
                continue  # nothing in stock: no well-defined answer
            served_id = self.index.best(ids, max(0.0, t_query - staleness))

            if len(outcomes) >= len(decisions):
                raise ValueError(
                    f"{run['run_id']}: replay produced more evaluated queries "
                    f"than the run logged ({len(decisions)})"
                )
            decision = decisions[len(outcomes)]
            if decision["query"] != query or decision["ground_truth"] != truth_id:
                raise ValueError(
                    f"{run['run_id']}: replay diverged at decision {len(outcomes)} — "
                    f"logged ({decision['query']!r}, {decision['ground_truth']}) "
                    f"vs replayed ({query!r}, {truth_id})"
                )
            outcomes.append(
                QueryOutcome(
                    query=query,
                    truth_id=truth_id,
                    served_id=served_id,
                    chosen=decision["chosen"],
                    correct=decision["correct"],
                    confidence=decision["confidence"],
                    abstained=decision["abstained"],
                    parse_failed=decision["parse_failed"],
                )
            )

        if len(outcomes) != len(decisions):
            raise ValueError(
                f"{run['run_id']}: replay produced {len(outcomes)} evaluated "
                f"queries, run logged {len(decisions)}"
            )
        return outcomes


def load_retrieval_runs(
    results_dir: Path, include_other_arms: bool = False
) -> list[dict[str, Any]]:
    """Retrieval runs from the main factorial.

    Other arms are excluded by default. The detectability arm contains
    streaming/freshness/severe retrieval runs too, half of them delivering
    record age — pooling those into the main factorial's freshness cell would
    quietly mix a different treatment into the headline table.
    """
    runs = []
    for path in sorted(results_dir.glob("*.json")):
        data = json.loads(path.read_text())
        if data["config"]["task"] != "retrieval":
            continue
        if run_arm(data) in NEVER_POOLED:
            # Live Analyst traffic is never data, whatever the caller asked for:
            # unpaired, unreplicated, and chosen by whoever was holding the mouse
            # (invariant 7). The refetch arm is data, but from a different
            # instrument, so it is never pooled with this one either.
            # → tests/test_live_quarantine.py, tests/test_refetch_quarantine.py
            continue
        if not include_other_arms and run_arm(data) != "main":
            continue
        runs.append(data)
    return runs


def _cell(outcomes: list[QueryOutcome]) -> dict[str, float]:
    n = len(outcomes)
    if n == 0:
        return {"n": 0}
    confident_wrong = [
        o for o in outcomes if not o.correct and not o.abstained and not o.parse_failed
    ]
    return {
        "n": n,
        "accuracy": sum(o.correct for o in outcomes) / n,
        "abstained": sum(o.abstained for o in outcomes) / n,
        "silent": len(confident_wrong) / n,
        "faithful": sum(o.served_faithful for o in outcomes) / n,
        "confidence": statistics.fmean([o.confidence for o in outcomes]),
        "confidence_wrong": (
            statistics.fmean([o.confidence for o in confident_wrong])
            if confident_wrong
            else float("nan")
        ),
    }


COLUMN_LABELS = {
    "n": "n",
    "accuracy": "acc",
    "abstained": "abstain",
    "silent": "silent",
    "faithful": "faithful",
    "confidence_wrong": "conf|wrong",
}
COL = 11


def _header(keys: tuple[str, ...]) -> str:
    return (
        f"     {'condition':<34}"
        + "".join(f"{COLUMN_LABELS[k]:>{COL}}" for k in keys)
        + "\n     "
        + "-" * (34 + COL * len(keys))
    )


def _fmt(cell: dict[str, float], keys: tuple[str, ...]) -> str:
    if not cell["n"]:
        return f"{'—':>{COL}}" * len(keys)
    out = []
    for key in keys:
        value = cell[key]
        if value != value:  # NaN
            out.append(f"{'—':>{COL}}")
        elif key == "n":
            out.append(f"{int(value):>{COL}}")
        elif key.startswith("confidence"):
            out.append(f"{value:>{COL}.2f}")
        else:
            out.append(f"{value:>{COL - 1}.0%} ")
    return "".join(out)


def report(runs: list[dict[str, Any]], data_dir: Path) -> int:
    if not runs:
        print("No retrieval runs found.")
        return 1

    replayer = Replayer(data_dir)
    by_condition: dict[tuple[str, str, str], list[QueryOutcome]] = defaultdict(list)
    for run in runs:
        cfg = run["config"]
        key = (cfg["pipeline"], cfg["fault_type"], cfg["severity"])
        by_condition[key].extend(replayer.outcomes(run))

    print(f"Flip-partition analysis — {len(runs)} retrieval runs, "
          f"{sum(len(v) for v in by_condition.values())} decisions, $0 spent\n")
    print("Replay verified against every logged ground truth.\n")

    order = [("none", "none")] + [
        (f, s)
        for f in ("freshness", "latency", "schema_drift", "semantic_stripping")
        for s in ("mild", "severe")
    ]

    # ---- 1. how much of the accuracy drop is mechanical? -----------------
    print("1. MECHANICAL CEILING — share of queries whose correct answer moved")
    print(f"     {'condition':<34} {'flip rate':>10} {'ceiling acc':>13}")
    print("     " + "-" * 59)
    for pipeline in ("streaming", "batch"):
        for fault, severity in order:
            outcomes = by_condition.get((pipeline, fault, severity))
            if not outcomes:
                continue
            flip = sum(o.flipped for o in outcomes) / len(outcomes)
            print(f"     {pipeline + '/' + fault + '/' + severity:<34} "
                  f"{flip:>9.1%} {1 - flip:>12.1%}")
    print()

    # ---- 2. the partition ------------------------------------------------
    keys = ("n", "accuracy", "abstained", "silent")
    for label, predicate in (
        ("2. ANSWER DID NOT FLIP — accuracy here should match baseline",
         lambda o: not o.flipped),
        ("3. ANSWER DID FLIP — the agent cannot be right; does it abstain?",
         lambda o: o.flipped),
    ):
        print(label)
        print(_header(keys))
        for pipeline in ("streaming", "batch"):
            for fault, severity in order:
                outcomes = by_condition.get((pipeline, fault, severity))
                if not outcomes:
                    continue
                cell = _cell([o for o in outcomes if predicate(o)])
                print(f"     {pipeline + '/' + fault + '/' + severity:<34}"
                      f"{_fmt(cell, keys)}")
        print()

    # ---- 4. the headline -------------------------------------------------
    print("4. THE FINDING — behaviour on flipped queries, freshness vs baseline")
    print("     Of the queries staleness made unanswerable, what did the agent do?")
    print()
    keys2 = ("n", "abstained", "silent", "faithful", "confidence_wrong")
    print(_header(keys2))
    for pipeline in ("streaming", "batch"):
        for fault, severity in (("none", "none"), ("freshness", "mild"),
                                ("freshness", "severe")):
            outcomes = by_condition.get((pipeline, fault, severity))
            if not outcomes:
                continue
            flipped = [o for o in outcomes if o.flipped]
            print(f"     {pipeline + '/' + fault + '/' + severity:<34}"
                  f"{_fmt(_cell(flipped), keys2)}")
    print()
    print("     'faithful' = chose the best answer present in the data it was shown.")
    print("     High faithful + low abstained = the agent reasoned correctly over")
    print("     corrupt input and reported the result with confidence. That is")
    print("     silent failure caused by the pipeline, not by the model.")

    # ---- verdict ---------------------------------------------------------
    print()
    print("=" * 78)
    base = _cell([o for o in by_condition.get(("streaming", "none", "none"), [])
                  if not o.flipped])
    fresh = _cell([o for o in by_condition.get(("streaming", "freshness", "severe"), [])
                   if not o.flipped])
    if not base["n"] or not fresh["n"]:
        print("Not enough runs to judge; need streaming baseline and freshness/severe.")
        return 0
    residual = base["accuracy"] - fresh["accuracy"]
    print(f"Unflipped-query accuracy, streaming: baseline {base['accuracy']:.3f} "
          f"vs freshness/severe {fresh['accuracy']:.3f} ({residual:+.3f})")
    if abs(residual) < 0.05:
        print("=> Freshness costs accuracy ONLY where it moved the correct answer.")
        print("   Report the flip-conditioned failure mode, not the raw accuracy drop.")
    else:
        print("=> Freshness degrades accuracy BEYOND the mechanical flip — staleness")
        print("   is confusing the agent, not just changing the answer. Report both.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="only check that the replay reproduces every logged ground truth",
    )
    args = parser.parse_args(argv)

    runs = load_retrieval_runs(args.results)
    if args.verify_only:
        replayer = Replayer(args.data_dir)
        for run in runs:
            replayer.outcomes(run)
        print(f"Replay verified for {len(runs)} retrieval runs.")
        return 0
    return report(runs, args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
