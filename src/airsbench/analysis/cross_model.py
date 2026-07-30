"""RQ5 — does the fault RANKING hold across model classes?

Only the ranking is claimed to generalise, never the absolute thresholds. A
model with a lower ceiling will fail more at everything; what would make the
AIRS framework useful is if the *ordering* of infrastructure properties by
damage is a property of the pipeline rather than of the consumer.

Three things this has to get right to be honest:

1. **Compare like with like.** The cross-model subset is streaming-only and
   severe-only, so the primary model is restricted to that same slice rather
   than compared against its full factorial.
2. **Measure each model against its own ceiling.** Every model brings its own
   baseline runs, and effects are odds ratios against that baseline — a
   weaker model failing more everywhere must not be read as a fault effect.
3. **Refuse to rank a floored arm.** If a model sits at chance on the baseline
   it has no headroom, its ordering is noise, and a rank correlation computed
   from it would be worse than no answer at all.

Retrieval effects use answerable decisions only, so freshness is not credited
with damage that is really answer-key movement (see flip_partition).

    python -m airsbench.analysis.cross_model
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..runner.config import run_arm
from .decision_models import fit_logit
from .flip_partition import Replayer
from .phase1_check import CHANCE, FLOOR_MARGIN

FAULTS = ("freshness", "latency", "schema_drift", "semantic_stripping")
PRIMARY_MODEL = "gpt-4o-mini"


def build_frame(results_dir: Path, data_dir: Path):
    """Decision-level frame across every model, restricted to the comparable slice.

    The comparable slice is streaming pipeline, severe severity, plus each
    model's own baseline — the intersection of what the main factorial and the
    cross-model subset both contain.
    """
    import pandas as pd

    replayer = Replayer(data_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        arm = run_arm(run)
        if arm not in ("main", "cross_model"):
            continue
        cfg = run["config"]
        if cfg["pipeline"] != "streaming":
            continue
        if cfg["severity"] not in ("severe", "none"):
            continue

        flags = (
            [o.flipped for o in replayer.outcomes(run)]
            if cfg["task"] == "retrieval"
            else [False] * len(run["decisions"])
        )
        for decision, flipped in zip(run["decisions"], flags):
            rows.append({
                "run_id": run["run_id"],
                "model": cfg["model"],
                "task": cfg["task"],
                "fault": cfg["fault_type"],
                "correct": int(decision["correct"]),
                "abstained": int(decision["abstained"]),
                "silent": int(
                    not decision["correct"]
                    and not decision["abstained"]
                    and not decision["parse_failed"]
                ),
                "parse_failed": int(decision["parse_failed"]),
                "flipped": bool(flipped),
            })
    frame = pd.DataFrame(rows)
    frame["condition"] = frame["fault"].map(
        lambda f: "baseline" if f == "none" else f
    )
    return frame


def baseline_health(frame, model: str) -> dict[str, dict[str, Any]]:
    """Per-task baseline accuracy, and whether the arm has room to degrade."""
    health = {}
    for task in ("retrieval", "classification"):
        sel = frame[(frame["model"] == model) & (frame["task"] == task)
                    & (frame["fault"] == "none")]
        if sel.empty:
            continue
        accuracy = sel["correct"].mean()
        health[task] = {
            "accuracy": accuracy,
            "n": len(sel),
            "parse_failure_rate": sel["parse_failed"].mean(),
            "floored": accuracy <= CHANCE[task] + FLOOR_MARGIN,
        }
    return health


def fault_effects(frame, model: str, task: str) -> dict[str, float]:
    """Odds ratio for silent failure vs this model's own baseline, per fault."""
    import numpy as np

    sel = frame[(frame["model"] == model) & (frame["task"] == task)]
    if task == "retrieval":
        sel = sel[~sel["flipped"]]
    if sel.empty or sel["fault"].nunique() < 2:
        return {}

    result = fit_logit(sel, "silent", "C(condition)")
    effects = {}
    for fault in FAULTS:
        term = f"C(condition)[T.{fault}]"
        if term in result.params.index:
            effects[fault] = float(np.exp(result.params[term]))
    return effects


def rank(effects: dict[str, float]) -> dict[str, int]:
    """Rank 1 = most damaging."""
    ordered = sorted(effects, key=lambda f: -effects[f])
    return {fault: i + 1 for i, fault in enumerate(ordered)}


def kendall(a: dict[str, int], b: dict[str, int]) -> tuple[float, float]:
    from scipy.stats import kendalltau

    shared = sorted(set(a) & set(b))
    if len(shared) < 3:
        return float("nan"), float("nan")
    result = kendalltau([a[f] for f in shared], [b[f] for f in shared])
    return float(result.statistic), float(result.pvalue)


def report(frame) -> int:
    models = sorted(frame["model"].unique(),
                    key=lambda m: (m != PRIMARY_MODEL, m))
    if len(models) < 2:
        print("Only one model present. Run the cross-model arm:")
        print("  python -m airsbench.runner.run --cross-model ollama/llama3.1:8b "
              "--n-queries 100 --max-cost 0.01")
        return 1

    print(f"RQ5 — fault ranking across {len(models)} models "
          f"({len(frame):,} decisions)\n")
    print("Comparable slice only: streaming pipeline, severe severity, each model")
    print("against its OWN baseline. Retrieval uses answerable decisions only.\n")

    # ---- 1. can each arm bear a ranking? ---------------------------------
    print("1. BASELINE HEALTH — an arm at chance cannot be ranked")
    print(f"   {'model':<30}{'task':<16}{'baseline acc':>13}{'parse fail':>12}   note")
    print("   " + "-" * 78)
    usable: dict[str, list[str]] = {}
    for model in models:
        for task, health in baseline_health(frame, model).items():
            note = ""
            if health["floored"]:
                note = f"<- FLOORED (chance {CHANCE[task]:.2f}), not ranked"
            elif health["parse_failure_rate"] > 0.10:
                note = "<- high parse-failure rate"
            else:
                usable.setdefault(model, []).append(task)
            print(f"   {model:<30}{task:<16}{health['accuracy']:>13.3f}"
                  f"{health['parse_failure_rate']:>12.1%}   {note}")
    print()

    # ---- 2. effects and rankings -----------------------------------------
    rankings: dict[tuple[str, str], dict[str, int]] = {}
    print("2. SILENT-FAILURE ODDS RATIO vs each model's own baseline")
    for task in ("retrieval", "classification"):
        eligible = [m for m in models if task in usable.get(m, [])]
        if not eligible:
            print(f"\n   {task}: no model has a rankable baseline")
            continue
        print(f"\n   {task}")
        print(f"   {'model':<30}" + "".join(f"{f[:13]:>15}" for f in FAULTS))
        print("   " + "-" * (30 + 15 * len(FAULTS)))
        for model in eligible:
            effects = fault_effects(frame, model, task)
            if not effects:
                continue
            rankings[(model, task)] = rank(effects)
            cells = "".join(
                f"{effects[f]:>14.2f} " if f in effects else f"{'—':>15}"
                for f in FAULTS
            )
            print(f"   {model:<30}{cells}")
        print(f"   {'rank order (1 = worst)':<30}")
        for model in eligible:
            if (model, task) in rankings:
                order = sorted(rankings[(model, task)],
                               key=lambda f: rankings[(model, task)][f])
                print(f"     {model:<28} {' > '.join(order)}")

    # ---- 3. does the ranking hold? ---------------------------------------
    print("\n3. RANK AGREEMENT — Kendall's tau on the fault ordering")
    pairs = []
    for task in ("retrieval", "classification"):
        eligible = [m for m in models if (m, task) in rankings]
        for i, a in enumerate(eligible):
            for b in eligible[i + 1:]:
                tau, p = kendall(rankings[(a, task)], rankings[(b, task)])
                pairs.append(tau)
                print(f"   {task:<16}{a} vs {b}")
                print(f"   {'':<16}tau = {tau:+.3f}  (p = {p:.4f})")
    if not pairs:
        print("   no comparable pairs")
        return 0

    mean_tau = sum(pairs) / len(pairs)
    print("\n" + "=" * 78)
    print(f"Mean Kendall's tau across {len(pairs)} model pairs: {mean_tau:+.3f}")
    if mean_tau >= 0.5:
        print("=> The RANKING generalises across model classes. Which "
              "infrastructure\n   property hurts most is a property of the "
              "pipeline, not of the consumer.")
    elif mean_tau <= -0.5:
        print("=> The ranking INVERTS across models — a strong negative result: "
              "the\n   damage ordering is model-specific and AIRS weights cannot "
              "transfer.")
    else:
        print("=> The ranking does NOT clearly generalise. AIRS weights are "
              "model-specific\n   and must be recalibrated per deployment — "
              "report as a limitation.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    args = parser.parse_args(argv)
    return report(build_frame(args.results, args.data_dir))


if __name__ == "__main__":
    raise SystemExit(main())
