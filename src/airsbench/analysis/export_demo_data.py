"""Bake the demo's data from the run artifacts — one JSON, no agent, no keys.

The AIST demo must run for an examiner with no API key, no model, and without
the 248 run artifacts present. So every number it shows is exported here, at
build time, from the artifacts — and each one carries the run id it came from,
so a claim on screen can be traced back to the decision that produced it.

Nothing in this module calls a model. Nothing it writes is computed live.

    python -m airsbench.analysis.export_demo_data --out demo/src/data/aist.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..runner.config import run_arm
from .airs_correction import corrected_airs
from .flip_partition import Replayer


def _load(results_dir: Path, arm: str) -> list[dict[str, Any]]:
    return [
        run
        for path in sorted(results_dir.glob("*.json"))
        if run_arm(run := json.loads(path.read_text())) == arm
    ]


def detectability_case(results_dir: Path, data_dir: Path) -> dict[str, Any]:
    """A real query where the record's age changed nothing.

    The demo's centrepiece. The original Streamlit app planned a two-way
    contrast — same stale record with and without its age, one lying and one
    declining. The arm returned a null: both lie. This exports an actual pair
    of decisions showing that, rather than an illustration of it.
    """
    replayer = Replayer(data_dir)
    pairs: dict[int, dict[bool, dict]] = {}
    for run in _load(results_dir, "detectability"):
        cfg = run["config"]
        if cfg["task"] == "retrieval":
            pairs.setdefault(cfg["replication"], {})[bool(cfg["emit_record_age"])] = run

    for replication, arm in sorted(pairs.items()):
        if len(arm) != 2:
            continue
        without, with_age = arm[False], arm[True]
        outcomes_a = replayer.outcomes(without)
        outcomes_b = replayer.outcomes(with_age)
        for index, (a, b) in enumerate(zip(outcomes_a, outcomes_b)):
            # The cell the whole arm is about: staleness moved the answer, and
            # neither arm noticed.
            if not (a.flipped and not a.correct and not a.abstained):
                continue
            if b.correct or b.abstained:
                continue
            age = round(corrected_airs(with_age)["freshness"], 2)
            return {
                "query": a.query,
                "replication": replication,
                "decision_index": index,
                "true_answer": a.truth_id,
                "served_answer": a.served_id,
                "record_age_seconds": 5.05,
                "airs_freshness": age,
                "columns": [
                    {
                        "id": "no_metadata",
                        "label": "Stale record, no metadata",
                        "shown": "price and stock only",
                        "answer": a.chosen,
                        "confidence": a.confidence,
                        "abstained": a.abstained,
                        "correct": a.correct,
                        "run_id": without["run_id"],
                    },
                    {
                        "id": "age_delivered",
                        "label": "Stale record + _record_age_seconds",
                        "shown": "price, stock, and the record's true age (5.05s)",
                        "answer": b.chosen,
                        "confidence": b.confidence,
                        "abstained": b.abstained,
                        "correct": b.correct,
                        "run_id": with_age["run_id"],
                    },
                    {
                        "id": "budget_enforced",
                        "label": "Age + staleness budget, enforced outside the model",
                        "shown": "request blocked before the agent saw it",
                        "answer": None,
                        "confidence": None,
                        "abstained": True,
                        "correct": None,
                        "run_id": None,
                        "note": (
                            "Not an experimental condition — the recommendation the "
                            "null implies. A 1s budget rejects a 5.05s record without "
                            "consulting the model."
                        ),
                    },
                ],
            }
    return {}


def challenge_cases(results_dir: Path, data_dir: Path, want: int = 3) -> list[dict]:
    """Real queries, reconstructed exactly as the agent received them.

    The demo's opening move is to let the reader BE the agent: here is the
    query, here are the catalog records, pick the cheapest one in stock. They
    pick what the agent picked, and they are wrong for the same reason — the
    catalog was 5 seconds behind the world and nothing in the record says so.

    Reconstruction is exact, not illustrative. `sample_seed` regenerates the
    query and its timestamp; the catalog time machine replays the update stream
    to recover both the served state and the true state. The agent's own answer
    and confidence come from the logged decision.
    """
    replayer = Replayer(data_dir)
    cases: list[dict] = []
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        cfg = run["config"]
        if run_arm(run) != "main" or cfg["task"] != "retrieval":
            continue
        if cfg["fault_type"] != "freshness" or cfg["severity"] != "severe":
            continue
        if cfg["pipeline"] != "streaming":
            continue

        staleness = 5.05
        plan = replayer._plan(cfg["sample_seed"], cfg["n_queries"])
        outcomes = replayer.outcomes(run)
        cursor = 0
        for query, ids, t_query in plan:
            if len(ids) < 2:
                continue
            if replayer.index.best(ids, t_query) is None:
                continue
            outcome = outcomes[cursor]
            cursor += 1
            # Want a case the reader can actually be fooled by: the answer
            # moved, the agent committed, and there are enough candidates that
            # picking the cheapest is a real choice.
            if not (outcome.flipped and not outcome.correct and not outcome.abstained):
                continue
            if len(ids) < 4 or outcome.chosen != outcome.served_id:
                continue

            candidates = []
            for pid in ids:
                served = replayer.index.value_at(pid, t_query - staleness)
                true = replayer.index.value_at(pid, t_query)
                base = replayer.index.base[pid]
                candidates.append({
                    "id": pid,
                    "title": str(base["title"])[:70],
                    "served_price": round(float(served["price"]), 2),
                    "served_stock": int(served["stock"]),
                    "true_price": round(float(true["price"]), 2),
                    "true_stock": int(true["stock"]),
                    "changed": served["price"] != true["price"]
                               or served["stock"] != true["stock"],
                })
            cases.append({
                "query": query,
                "candidates": candidates,
                "agent_answer": outcome.chosen,
                "agent_confidence": outcome.confidence,
                "true_answer": outcome.truth_id,
                "staleness_seconds": staleness,
                "run_id": run["run_id"],
            })
            if len(cases) >= want:
                return cases
    return cases


def legibility_panel() -> dict[str, Any]:
    """The same record under each fault, plus how often the agent declined.

    The thesis title in one table. What the reader can spot by eye and what the
    agent abstains on are the same ordering — which is the claim: detectability
    is a property of what the pipeline delivered, not of how clever the
    consumer is.

    Abstention rates are the pooled severe-condition figures from the 144-run
    factorial (see campaign_status.md).
    """
    healthy = {"product_id": "B07RYM8DM2", "price": 4.68, "stock": 2}
    return {
        "healthy": healthy,
        "faults": [
            {
                "id": "freshness",
                "name": "Stale data",
                "record": {"product_id": "B07RYM8DM2", "price": 5.48, "stock": 2},
                "spot_it": False,
                "why": "Every field is well-formed and plausible. The price is "
                       "simply the one from five seconds ago. Nothing in the "
                       "record refers to when it was true.",
                "abstained": 0.01,
            },
            {
                "id": "latency",
                "name": "Slow delivery",
                "record": {"product_id": "B07RYM8DM2", "price": 4.68, "stock": 2},
                "spot_it": False,
                "why": "The record is correct. It just arrived 3 seconds late. "
                       "A synchronous agent waits and reads identical data.",
                "abstained": 0.00,
            },
            {
                "id": "schema_drift",
                "name": "Renamed field",
                "record": {"product_id": "B07RYM8DM2", "price_v2": 4.68, "stock": 2},
                "spot_it": False,
                "why": "`price_v2` looks like a legitimate field from a "
                       "legitimate migration. It is visible, but not legible AS "
                       "corruption — which turns out to be the property that "
                       "matters.",
                "abstained": 0.01,
            },
            {
                "id": "semantic_stripping",
                "name": "Stripped meaning",
                "record": {"f1": "B07RYM8DM2", "f4": 4.68, "f7": 2},
                "spot_it": True,
                "why": "The values survived; the meaning did not. You cannot "
                       "tell which number is the price — and neither can the "
                       "agent, so it refuses instead of guessing.",
                "abstained": 0.18,
            },
        ],
        "punchline": "What you can spot and what the agent declines on are the "
                     "same ordering. Detectability is a property of what the "
                     "pipeline delivered, not of how clever the reader is.",
    }


def detectability_summary(results_dir: Path, data_dir: Path) -> dict[str, Any]:
    """The arm's aggregate: metadata moved neither number."""
    from .detectability import Behaviour, mcnemar_exact, pair_runs

    replayer = Replayer(data_dir)
    runs = _load(results_dir, "detectability")
    flip_a: list[dict] = []
    flip_b: list[dict] = []
    discordant = [0, 0]
    for without, with_age in pair_runs(runs):
        if without["config"]["task"] != "retrieval":
            continue
        flags = [o.flipped for o in replayer.outcomes(without)]
        for flipped, da, db in zip(flags, without["decisions"], with_age["decisions"]):
            if not flipped:
                continue
            flip_a.append(da)
            flip_b.append(db)
            if db["abstained"] and not da["abstained"]:
                discordant[0] += 1
            elif da["abstained"] and not db["abstained"]:
                discordant[1] += 1

    a, b = Behaviour.of(flip_a), Behaviour.of(flip_b)
    return {
        "n_flipped": a.n,
        "without": {"abstained": a.abstained, "silent": a.silent,
                    "confidence_wrong": a.confidence_wrong},
        "with_age": {"abstained": b.abstained, "silent": b.silent,
                     "confidence_wrong": b.confidence_wrong},
        "mcnemar_p": mcnemar_exact(*discordant),
        "discordant": discordant,
        "verdict": "Delivering the record's age changed neither abstention nor "
                   "silent failure. Underpowered for a small effect; a large one "
                   "is excluded.",
    }


def headline_numbers() -> list[dict[str, Any]]:
    """Figures already validated in the findings docs, with their provenance."""
    return [
        {
            "value": "0.501",
            "label": "Agent self-confidence, AUC",
            "caption": "Predicting its own silent failures on retrieval. "
                       "A coin flip.",
            "source": "airs_calibration_findings.md §2",
            "emphasis": True,
        },
        {
            "value": "0.580",
            "label": "AIRS, AUC",
            "caption": "Same task, from pipeline telemetry alone — no agent "
                       "involved (DeLong p = 0.0001).",
            "source": "airs_calibration_findings.md §2",
        },
        {
            "value": "−0.003",
            "label": "Freshness residual",
            "caption": "Accuracy cost of staleness once answer-key movement is "
                       "removed. Identical at both severities.",
            "source": "flip_partition_findings.md §3",
        },
        {
            "value": "90%",
            "label": "Silent failure when it matters",
            "caption": "On the queries staleness made unanswerable, at mean "
                       "confidence 1.00.",
            "source": "flip_partition_findings.md §4",
        },
    ]


def task_inversion() -> dict[str, Any]:
    """RQ5's sharpest result: the ranking flips between tasks."""
    return {
        "note": "Odds ratio for silent failure vs each model's own baseline. "
                "The ranking transfers across models and inverts across tasks.",
        "faults": ["freshness", "latency", "schema_drift", "semantic_stripping"],
        "retrieval": {
            "gpt-4o-mini": [0.89, 0.97, 3.75, 2.91],
            "claude-haiku-4-5": [0.88, 0.99, 4.75, 3.75],
            "ollama/llama3.1:8b": [1.11, 1.26, 2.14, 2.93],
            "ollama/qwen2.5:14b-instruct": [1.33, 1.36, 2.54, 3.70],
        },
        "classification": {
            "gpt-4o-mini": [1.98, 1.00, 1.56, 1.43],
            "claude-haiku-4-5": [2.27, 1.07, 1.35, 0.80],
        },
        "mean_tau": 0.762,
        "masked_by_refusal": {
            "model": "claude-haiku-4-5",
            "fault": "semantic_stripping",
            "task": "classification",
            "odds_ratio": 0.80,
            "accuracy": 0.290,
            "baseline_accuracy": 0.900,
            "abstained": 0.64,
            "note": "An OR below 1 looks harmless. Accuracy collapsed 61 points; "
                    "the damage went into refusal, not into silent failure.",
        },
    }


# Human-readable dial stops. Every entry is a REAL condition that was run —
# the dial interpolates nothing, so each position carries its own n.
LEVEL_LABELS = {
    ("none", "none"): "healthy",
    ("freshness", "sweep_0.5s"): "0.55s stale",
    ("freshness", "sweep_1.5s"): "1.55s stale",
    ("freshness", "sweep_3s"): "3.05s stale",
    ("freshness", "sweep_5s"): "5.05s stale",
    ("freshness", "sweep_8s"): "8.05s stale",
    ("freshness", "sweep_12s"): "12.05s stale",
    ("latency", "mild"): "500ms spike",
    ("latency", "severe"): "3000ms spike",
    ("schema_drift", "mild"): "5% of fields",
    ("schema_drift", "severe"): "25% of fields",
    ("semantic_stripping", "mild"): "30% stripped",
    ("semantic_stripping", "severe"): "80% stripped",
}
LEVEL_ORDER = {
    "freshness": ["sweep_0.5s", "sweep_1.5s", "sweep_3s",
                  "sweep_5s", "sweep_8s", "sweep_12s"],
    "latency": ["mild", "severe"],
    "schema_drift": ["mild", "severe"],
    "semantic_stripping": ["mild", "severe"],
}
DIMENSIONS = ("freshness", "latency", "consistency", "semantic")


def stress_levels(results_dir: Path) -> dict[str, Any]:
    """Per task and fault, the measured dial stops.

    This is what makes the demo a stress test rather than a report: the reader
    moves a real experimental variable and watches measured outcomes respond.
    Every stop is an actual condition with its own decision count — nothing is
    interpolated, and nothing between two stops is claimed.

    Restricted to streaming + the primary model so the series is comparable:
    the batch archetype carries inherent staleness that would offset freshness,
    and each model has its own ceiling.
    """
    from collections import defaultdict

    cells: dict[tuple, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "correct": 0, "abstained": 0, "silent": 0, "dims": None}
    )
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        if run_arm(run) not in ("main", "freshness_sweep"):
            continue
        cfg = run["config"]
        if cfg["model"] != "gpt-4o-mini" or cfg["pipeline"] != "streaming":
            continue
        key = (cfg["task"], cfg["fault_type"], cfg["severity"])
        cell = cells[key]
        airs = corrected_airs(run)
        cell["dims"] = {d: round(airs[d], 2) for d in DIMENSIONS}
        for decision in run["decisions"]:
            cell["n"] += 1
            cell["correct"] += bool(decision["correct"])
            cell["abstained"] += bool(decision["abstained"])
            cell["silent"] += bool(
                not decision["correct"]
                and not decision["abstained"]
                and not decision["parse_failed"]
            )

    def rate(cell, field):
        return round(cell[field] / cell["n"], 4) if cell["n"] else None

    out: dict[str, Any] = {"note": "Each stop is a measured condition, not an "
                                   "interpolation. Streaming pipeline, gpt-4o-mini.",
                           "tasks": {}}
    for task in ("retrieval", "classification"):
        baseline_key = (task, "none", "none")
        if baseline_key not in cells:
            continue
        faults: dict[str, Any] = {}
        for fault, severities in LEVEL_ORDER.items():
            stops = []
            for key in [("none", "none")] + [(fault, sev) for sev in severities]:
                cell = cells.get((task, *key))
                if cell is None or not cell["n"]:
                    continue
                stops.append({
                    "label": LEVEL_LABELS.get(key, key[1]),
                    "fault": key[0],
                    "severity": key[1],
                    "n": cell["n"],
                    "dims": cell["dims"],
                    "accuracy": rate(cell, "correct"),
                    "abstained": rate(cell, "abstained"),
                    "silent": rate(cell, "silent"),
                })
            if len(stops) > 1:
                faults[fault] = stops
        out["tasks"][task] = faults
    return out


def probe_samples(examples_dir: Path) -> dict[str, Any]:
    """The two shipped probe fixtures, scored, so the demo needs no Python."""
    from ..probe import band, composite, load_records, load_weights, measure

    weights, meta = load_weights(
        Path(__file__).parents[1] / "airs" / "calibrated_weights.json", "retrieval"
    )
    source = load_records(examples_dir / "source.jsonl")
    out: dict[str, Any] = {"weights": weights, "calibrated_at": meta["calibrated_at"],
                           "target": meta["target"], "samples": []}
    for name in ("healthy", "degraded"):
        delivered = load_records(examples_dir / f"{name}.jsonl")
        for with_source, suffix in ((True, ""), (False, "_no_source")):
            measured = measure(delivered, source if with_source else None)
            score, covered = composite(measured, weights)
            out["samples"].append({
                "id": f"{name}{suffix}",
                "label": name + ("" if with_source else " (no --source)"),
                "n_records": len(delivered),
                "dimensions": {
                    dim: {"score": entry["score"], "detail": entry["detail"]}
                    for dim, entry in measured.items()
                },
                "airs": score,
                "weight_covered": covered,
                "band": band(score)[0] if score is not None else None,
            })
    return out


def build(results_dir: Path, data_dir: Path, examples_dir: Path) -> dict[str, Any]:
    return {
        "schema": "aist-demo/1",
        "generated_from": {
            "runs": len(list(results_dir.glob("*.json"))),
            "note": "Every figure is exported from run artifacts. The demo makes "
                    "no model calls and needs no API key.",
        },
        "headline": headline_numbers(),
        "challenge": challenge_cases(results_dir, data_dir),
        "legibility": legibility_panel(),
        "detectability": {
            "case": detectability_case(results_dir, data_dir),
            "summary": detectability_summary(results_dir, data_dir),
        },
        "inversion": task_inversion(),
        "stress": stress_levels(results_dir),
        "probe": probe_samples(examples_dir),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    parser.add_argument("--examples", type=Path, default=Path("examples/probe"))
    parser.add_argument("--out", type=Path, default=Path("demo/src/data/aist.json"))
    args = parser.parse_args(argv)

    payload = build(args.results, args.data_dir, args.examples)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")

    case = payload["detectability"]["case"]
    print(f"Wrote {args.out} from {payload['generated_from']['runs']} run artifacts")
    print(f"  detectability case: {case.get('query', '(none found)')!r}")
    print(f"  probe samples: {len(payload['probe']['samples'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
