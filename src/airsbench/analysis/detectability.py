"""Detectability arm — does delivering a record's age change how it fails?

Design: docs/detectability_arm.md. The fault is held constant (freshness,
severe, streaming) and one thing varies: whether the delivered record carries
`_record_age_seconds`. So any behavioural difference is attributable to
legibility rather than to the fault, the queries, or the prompt.

The comparison is paired at the query level. A and B share `sample_seed`, so
decision *i* of the A run and decision *i* of its B partner are the same query
at the same simulated time under the same fault realization. That permits
McNemar's test on the discordant pairs — far more powerful at n=240 than
comparing two independent rates, and the correct test for the design.

Three quantities, in descending order of interest:

1. **Flip-conditioned behaviour** (retrieval). On queries where staleness moved
   the correct answer, the agent cannot be right; the question is whether it
   abstains or commits. Condition A's values are already established by the
   main factorial: 5% abstention, 89% silent failure, confidence 1.00 when
   wrong (docs/flip_partition_findings.md).
2. **Overall behaviour**, both tasks.
3. **Over-caution.** Shown an age of ~0.05 s on fresh data, does the agent
   start abstaining anyway? If it does, the metadata is not free.

    python -m airsbench.analysis.detectability
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..runner.config import DETECTABILITY_SEED_RANGE, run_arm
from .flip_partition import Replayer
from .phase1_check import wilson_halfwidth

# Runs are identified by their seed block rather than by condition, because the
# main factorial also contains streaming/freshness/severe runs without the
# metadata — those belong to a different arm and must not be pooled in.
ARM_SEED_RANGE = DETECTABILITY_SEED_RANGE


def in_arm(run: dict[str, Any]) -> bool:
    return run_arm(run) == "detectability"


def load_arm(results_dir: Path) -> list[dict[str, Any]]:
    runs = []
    for path in sorted(results_dir.glob("*.json")):
        data = json.loads(path.read_text())
        if in_arm(data):
            runs.append(data)
    return runs


@dataclass
class Behaviour:
    """What the agent did over a set of decisions."""

    n: int
    accuracy: float
    abstained: float
    silent: float
    confidence_wrong: float

    @classmethod
    def of(cls, decisions: list[dict[str, Any]]) -> "Behaviour":
        n = len(decisions)
        if not n:
            return cls(0, float("nan"), float("nan"), float("nan"), float("nan"))
        wrong = [
            d for d in decisions
            if not d["correct"] and not d["abstained"] and not d["parse_failed"]
        ]
        return cls(
            n=n,
            accuracy=sum(d["correct"] for d in decisions) / n,
            abstained=sum(d["abstained"] for d in decisions) / n,
            silent=len(wrong) / n,
            confidence_wrong=(
                statistics.fmean([d["confidence"] for d in wrong])
                if wrong else float("nan")
            ),
        )


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p for discordant counts b and c.

    b = pairs where only B abstained, c = pairs where only A did. Under the
    null the metadata changes nothing, so each discordant pair is a fair coin.
    Exact rather than chi-square: the discordant counts here are small.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def min_discordant_for_significance(alpha: float = 0.05) -> int:
    """Fewest one-directional discordant pairs that could reach significance.

    Under McNemar's exact test the p-value depends on the discordant pairs
    alone, not on how many concordant pairs surround them. So a null result
    with few discordant pairs is uninformative *by construction*, and this
    number is what separates "no effect" from "no power" — it must be reported
    alongside any null this arm produces.
    """
    k = 1
    while mcnemar_exact(k, 0) >= alpha:
        k += 1
    return k


def rule_of_three(n: int) -> float:
    """95% upper bound on a rate after observing zero events in n trials.

    The only honest way to report "it never happened": with n=240 and no
    abstentions, the rate is not 0 — it is below roughly 1.25%.
    """
    return 3.0 / n if n else 1.0


def pair_runs(runs: list[dict[str, Any]]) -> list[tuple[dict, dict]]:
    """Match each A run to its B partner by (task, replication, fault)."""
    keyed: dict[tuple, dict[bool, dict]] = {}
    for run in runs:
        cfg = run["config"]
        if cfg["fault_type"] != "freshness":
            continue
        key = (cfg["task"], cfg["replication"])
        keyed.setdefault(key, {})[bool(cfg["emit_record_age"])] = run
    pairs = []
    for key, arms in sorted(keyed.items()):
        if len(arms) == 2:
            pairs.append((arms[False], arms[True]))
        else:
            print(f"     ! incomplete pair {key} — skipped")
    return pairs


def _row(label: str, behaviour: Behaviour) -> str:
    if not behaviour.n:
        return f"     {label:<28}{'—':>8}"
    conf = (
        "—" if behaviour.confidence_wrong != behaviour.confidence_wrong
        else f"{behaviour.confidence_wrong:.2f}"
    )
    hw = wilson_halfwidth(behaviour.abstained, behaviour.n)
    return (
        f"     {label:<28}{behaviour.n:>6}{behaviour.accuracy:>9.0%}"
        f"{behaviour.abstained:>9.0%} ±{hw:<5.0%}{behaviour.silent:>8.0%}{conf:>11}"
    )


HEADER = (
    f"     {'condition':<28}{'n':>6}{'acc':>9}{'abstain':>9}"
    f"{'  95% ci':<7}{'silent':>8}{'conf|wrong':>11}\n     " + "-" * 71
)


def report(runs: list[dict[str, Any]], data_dir: Path) -> int:
    if not runs:
        print("No detectability-arm runs found. Run:")
        print("  python -m airsbench.runner.run --detectability "
              "--n-queries 80 --max-cost 0.30")
        return 1

    cost = sum(r["usage"]["cost_usd"] for r in runs)
    print(f"Detectability arm — {len(runs)} runs, ${cost:.3f}\n")
    print("Fault held constant (freshness/severe/streaming). The only difference")
    print("between A and B is that B's records carry `_record_age_seconds`.\n")

    pairs = pair_runs(runs)
    if not pairs:
        print("No complete A/B pairs yet.")
        return 1

    # ---- 1. flip-conditioned, retrieval ----------------------------------
    replayer = Replayer(data_dir)
    flip_a: list[dict] = []
    flip_b: list[dict] = []
    discordant_flip = [0, 0]  # [only B abstained, only A abstained]

    for run_a, run_b in pairs:
        if run_a["config"]["task"] != "retrieval":
            continue
        flags = [o.flipped for o in replayer.outcomes(run_a)]
        assert flags == [o.flipped for o in replayer.outcomes(run_b)], (
            "paired design broken: A and B saw different queries"
        )
        for flipped, da, db in zip(flags, run_a["decisions"], run_b["decisions"]):
            if not flipped:
                continue
            flip_a.append(da)
            flip_b.append(db)
            if db["abstained"] and not da["abstained"]:
                discordant_flip[0] += 1
            elif da["abstained"] and not db["abstained"]:
                discordant_flip[1] += 1

    print("1. FLIP-CONDITIONED — queries where staleness moved the correct answer")
    print("   The agent cannot be right here. Does the age field make it say so?")
    print(HEADER)
    print(_row("A  age absent", Behaviour.of(flip_a)))
    print(_row("B  age delivered", Behaviour.of(flip_b)))
    if flip_a:
        p = mcnemar_exact(*discordant_flip)
        print(f"\n     McNemar on abstention: {discordant_flip[0]} pairs where only B "
              f"abstained,\n     {discordant_flip[1]} where only A did — exact p = {p:.4f}")
    print()

    # ---- 2. overall, per task --------------------------------------------
    print("2. OVERALL — all queries, both tasks")
    for task in ("retrieval", "classification"):
        task_pairs = [p for p in pairs if p[0]["config"]["task"] == task]
        if not task_pairs:
            continue
        a = [d for run, _ in task_pairs for d in run["decisions"]]
        b = [d for _, run in task_pairs for d in run["decisions"]]
        discordant = [0, 0]
        for run_a, run_b in task_pairs:
            for da, db in zip(run_a["decisions"], run_b["decisions"]):
                if db["abstained"] and not da["abstained"]:
                    discordant[0] += 1
                elif da["abstained"] and not db["abstained"]:
                    discordant[1] += 1
        print(f"\n   {task}")
        print(HEADER)
        print(_row("A  age absent", Behaviour.of(a)))
        print(_row("B  age delivered", Behaviour.of(b)))
        print(f"     McNemar on abstention: b={discordant[0]} c={discordant[1]} "
              f"exact p = {mcnemar_exact(*discordant):.4f}")
    print()

    # ---- 3. over-caution --------------------------------------------------
    print("3. OVER-CAUTION — baseline data, age delivered (~0.05 s)")
    print("   If abstention rises here, the metadata is not free: the agent")
    print("   declines on data that was perfectly good.")
    print(HEADER)
    baselines = [r for r in runs if r["config"]["fault_type"] == "none"]
    for run in sorted(baselines, key=lambda r: r["config"]["task"]):
        label = f"baseline+age  {run['config']['task'][:9]}"
        print(_row(label, Behaviour.of(run["decisions"])))
    print()

    # ---- verdict ----------------------------------------------------------
    print("=" * 78)
    if not flip_a:
        print("No flipped retrieval queries yet — cannot judge the headline cell.")
        return 0

    a_beh, b_beh = Behaviour.of(flip_a), Behaviour.of(flip_b)
    d_abstain = b_beh.abstained - a_beh.abstained
    d_silent = b_beh.silent - a_beh.silent
    p = mcnemar_exact(*discordant_flip)
    print(f"On flipped queries: abstention {a_beh.abstained:.0%} -> "
          f"{b_beh.abstained:.0%} ({d_abstain:+.0%}), silent failure "
          f"{a_beh.silent:.0%} -> {b_beh.silent:.0%} ({d_silent:+.0%})")

    over_caution = max(
        (Behaviour.of(r["decisions"]).abstained for r in baselines), default=0.0
    )
    needed = min_discordant_for_significance()
    observed = sum(discordant_flip)
    print()

    if p < 0.05 and d_abstain > 0 and over_caution < 0.15:
        print("=> SILENT FAILURE FROM STALENESS IS A PIPELINE DESIGN DEFECT.")
        print("   Shipping record age with the record measurably converts silent")
        print("   failure into abstention. Direct, actionable recommendation.")
        return 0
    if p < 0.05 and d_abstain > 0:
        print("=> Metadata raises abstention, BUT it also raises it on fresh data")
        print(f"   ({over_caution:.0%} at baseline). Calibration problem in how age")
        print("   is presented — the agent distrusts the field, not the staleness.")
        return 0

    print("=> NO DETECTABLE EFFECT. Delivering the record's age did not change")
    print("   what the agent did with it.")
    print()
    print("   What this rules out, and what it does not:")
    print(f"     - the flip-conditioned cell has {observed} discordant pair(s); "
          f"at least {needed}\n       in one direction are needed for significance, so it "
          "cannot resolve a\n       small effect. The point estimate moves as predicted "
          "but is not evidence.")

    for task in ("retrieval", "classification"):
        decisions = [
            d for pair in pairs for run in pair
            if run["config"]["task"] == task for d in run["decisions"]
        ]
        if decisions and not any(d["abstained"] for d in decisions):
            bound = rule_of_three(len(decisions))
            print(f"     - {task}: ZERO abstentions in {len(decisions)} decisions "
                  f"across both arms.\n       A real abstention rate above "
                  f"{bound:.1%} is ruled out. This is a strong null:\n       the agent "
                  "is offered the option, shown the age, and never takes it.")

    if over_caution < 0.05:
        print(f"     - the metadata is not merely being over-applied: abstention on "
              f"fresh\n       data stays at {over_caution:.0%}. The agent is not "
              "reacting to the field at all.")
    print()
    print("   Reading: metadata alone is insufficient. An age is not actionable")
    print("   without a freshness policy — the agent is told the record is 5.05 s")
    print("   old but never what age is acceptable, and every record in a run")
    print("   carries the same age, so there is nothing to discriminate against.")
    print("   The freshness guard has to be enforced outside the model.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    args = parser.parse_args(argv)
    return report(load_arm(args.results), args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
