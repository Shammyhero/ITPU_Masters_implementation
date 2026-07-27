"""Phase-1 go/no-go report.

Reads completed run artifacts and answers the one question the checkpoint
exists to answer: **is this design capable of producing the study's results?**

Four checks, each of which has already caught a real defect:

1. Coverage      — is the replication complete and balanced?
2. Floors        — is any arm pinned at chance or at a ceiling, so severity
                   cannot move it? (caught the 10 s batch staleness collision)
3. Coherence     — does any faulted condition outscore its own baseline by
                   more than sampling noise allows? (caught the unpaired design)
4. Effects       — do faults actually degrade accuracy, and does the
                   abstention/silent-failure split behave as H3 predicts?

Usage:
    python -m airsbench.analysis.phase1_check
    python -m airsbench.analysis.phase1_check --results results/runs
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..runner.config import run_arm

# A faulted condition scoring this far ABOVE its own baseline is not
# noise — it indicates the comparison is not controlled.
COHERENCE_TOLERANCE = 0.10
# Binary tasks sit at 0.5 by chance; retrieval with 6 candidates at ~0.17.
CHANCE = {"classification": 0.50, "retrieval": 1.0 / 6.0}
FLOOR_MARGIN = 0.08


def load_runs(
    results_dir: Path, include_other_arms: bool = False
) -> list[dict[str, Any]]:
    """Main-factorial runs. Other arms are excluded by default — the
    detectability arm and the freshness sweep contain conditions that also
    appear here, and pooling them would distort the checkpoint's own numbers."""
    runs = []
    for path in sorted(results_dir.glob("*.json")):
        data = json.loads(path.read_text())
        if not include_other_arms and run_arm(data) != "main":
            continue
        cfg, met = data["config"], data["metrics"]
        runs.append(
            {
                "pipeline": cfg["pipeline"],
                "task": cfg["task"],
                "fault": cfg["fault_type"],
                "severity": cfg["severity"],
                "replication": cfg["replication"],
                "n": met["n"],
                "accuracy": met["accuracy"],
                "abstention": met.get("abstention_rate", 0.0),
                "silent": met.get("silent_failure_rate", 0.0),
                "parse_failures": met["parse_failures"],
                "airs": data["airs"]["total"],
                "cost": data["usage"]["cost_usd"],
                "decisions": data.get("decisions", []),
            }
        )
    return runs


def wilson_halfwidth(p: float, n: int) -> float:
    """Half-width of a 95% Wilson interval — honest error bars at small n."""
    if n == 0:
        return 0.0
    z = 1.96
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(abs(centre + margin - p), abs(p - (centre - margin)))


def report(runs: list[dict[str, Any]]) -> int:
    if not runs:
        print("No runs found.")
        return 1

    problems: list[str] = []
    total_cost = sum(r["cost"] for r in runs)
    print(f"Phase-1 go/no-go — {len(runs)} runs, ${total_cost:.3f} spent\n")

    # ---- 1. coverage -----------------------------------------------------
    conditions = {(r["pipeline"], r["task"], r["fault"], r["severity"]) for r in runs}
    print(f"1. COVERAGE — {len(conditions)} distinct conditions")
    by_arm: dict[tuple[str, str], int] = defaultdict(int)
    for r in runs:
        by_arm[(r["pipeline"], r["task"])] += 1
    for (pipe, task), count in sorted(by_arm.items()):
        print(f"     {pipe:>9} / {task:<15} {count:>2} runs")
    if len(conditions) < 36:
        print(f"   ! incomplete: {36 - len(conditions)} conditions not yet run")
    print()

    # ---- 2. floors -------------------------------------------------------
    print("2. FLOORS — is any arm pinned so severity cannot move it?")
    for (pipe, task) in sorted(by_arm):
        arm = [r for r in runs if r["pipeline"] == pipe and r["task"] == task]
        base = [r for r in arm if r["fault"] == "none"]
        if not base:
            continue
        b = base[0]["accuracy"]
        floor = CHANCE[task] + FLOOR_MARGIN
        flag = ""
        if b <= floor:
            flag = f"  <-- FLOORED (chance={CHANCE[task]:.2f})"
            problems.append(f"{pipe}/{task} baseline {b:.3f} at or below chance")
        print(f"     {pipe:>9} / {task:<15} baseline {b:.3f}{flag}")
    print()

    # ---- 3. coherence ----------------------------------------------------
    print("3. COHERENCE — faulted conditions must not beat their own baseline")
    baselines = {
        (r["pipeline"], r["task"]): r["accuracy"] for r in runs if r["fault"] == "none"
    }
    violations = []
    for r in runs:
        if r["fault"] == "none":
            continue
        base = baselines.get((r["pipeline"], r["task"]))
        if base is None:
            continue
        gain = r["accuracy"] - base
        if gain > COHERENCE_TOLERANCE:
            violations.append((r, base, gain))
    if violations:
        for r, base, gain in violations:
            line = (f"{r['pipeline']}/{r['task']}/{r['fault']}/{r['severity']}")
            print(f"     ! {line:<48} {r['accuracy']:.3f} vs base {base:.3f} (+{gain:.3f})")
            problems.append(f"{line} scores {gain:+.3f} above baseline")
    else:
        print("     ok — no faulted condition exceeds its baseline beyond tolerance")
    print()

    # ---- 4. effects ------------------------------------------------------
    print("4. EFFECTS — degradation and failure mode by fault (pooled over arms)")
    print(f"     {'fault / severity':<32} {'acc':>13} {'abstain':>9} {'silent':>9}")
    print("     " + "-" * 66)

    def pooled(fault: str, severity: str) -> dict[str, float] | None:
        sel = [r for r in runs if r["fault"] == fault and r["severity"] == severity]
        if not sel:
            return None
        n = sum(r["n"] for r in sel)
        return {
            "accuracy": sum(r["accuracy"] * r["n"] for r in sel) / n,
            "abstention": sum(r["abstention"] * r["n"] for r in sel) / n,
            "silent": sum(r["silent"] * r["n"] for r in sel) / n,
            "n": n,
        }

    base = pooled("none", "none")
    rows = [("none", "none")] + [
        (f, s)
        for f in ("freshness", "latency", "schema_drift", "semantic_stripping")
        for s in ("mild", "severe")
    ]
    effects = {}
    for fault, severity in rows:
        p = pooled(fault, severity)
        if p is None:
            continue
        hw = wilson_halfwidth(p["accuracy"], p["n"])
        delta = "" if fault == "none" else f" ({p['accuracy'] - base['accuracy']:+.3f})"
        label = f"{fault}/{severity}"
        print(
            f"     {label:<32} {p['accuracy']:.3f}±{hw:.3f}{delta:<9}"
            f" {p['abstention']:>8.0%} {p['silent']:>8.0%}"
        )
        effects[(fault, severity)] = p

    # H3: detectability split
    print()
    print("     H3 (detectability) — visible faults should drive abstention,")
    print("     invisible faults should drive silent failure:")
    for fault, visibility in [
        ("semantic_stripping", "VISIBLE   (opaque names)"),
        ("schema_drift", "VISIBLE   (renamed/retyped fields)"),
        ("freshness", "INVISIBLE (well-formed, just wrong)"),
        ("latency", "INVISIBLE (well-formed, on time)"),
    ]:
        p = effects.get((fault, "severe"))
        if p is None:
            continue
        print(
            f"       {fault:<20} {visibility:<36} "
            f"abstain {p['abstention']:>4.0%}  silent {p['silent']:>4.0%}"
        )

    # ---- verdict ---------------------------------------------------------
    print()
    degraded = [
        f for f in ("freshness", "latency", "schema_drift", "semantic_stripping")
        if (p := effects.get((f, "severe"))) and base["accuracy"] - p["accuracy"] > 0.05
    ]
    print("=" * 72)
    if problems:
        print("VERDICT: NO-GO — resolve before phase 2:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if not degraded:
        print("VERDICT: NO-GO — no fault degrades accuracy by >5 points at severe.")
        print("  The instrument cannot detect what the study is designed to measure.")
        return 1
    print(f"VERDICT: GO — {len(degraded)} of 4 faults degrade accuracy at severe "
          f"({', '.join(degraded)}).")
    print("  No floored arm, no incoherent comparison. Proceed to phase 2:")
    print("    python -m airsbench.runner.run --main --n-queries 80 --offset 36 "
          "--max-cost 2.00")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    args = parser.parse_args(argv)
    return report(load_runs(args.results))


if __name__ == "__main__":
    raise SystemExit(main())
