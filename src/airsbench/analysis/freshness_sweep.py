"""Freshness sweep — RQ1: is degradation monotonic in data age, and where is
the threshold?

The main factorial tests freshness at two severities, and two points always look
monotonic. Shisher & Sun (MobiHoc 2022) prove prediction error need not be
monotone in age, so the claim needs more levels than the factorial provides.

**The outcome variable is not accuracy.** The flip partition established that
freshness does not impair the agent at all — it moves the answer key, and raw
accuracy under staleness traces the answer-flip rate, which is a property of the
catalog's velocity rather than of the agent. Sweeping accuracy against staleness
would therefore chart the dataset. The monotonicity claim is tested on the
**flip-conditioned silent-failure rate**: of the queries staleness made
unanswerable, the share the agent answers confidently anyway.

Raw accuracy is still reported, decomposed into its mechanical and residual
parts, because RQ1's threshold is defined operationally on the observable an
engineer would actually watch.

Methods follow `research_questions_v2.md` §5 (RQ1):

- **Monotonicity** — Spearman's rho on staleness vs outcome at the run level,
  plus an isotonic fit compared against the unconstrained per-level means. If
  the monotone constraint costs little error, monotonicity is consistent with
  the data; if it costs a lot, the response is not monotone.
- **Threshold** — first crossing of the 10-point band, reported with the full
  curve rather than alone.
- **Changepoint** — exhaustive single-changepoint search. At six levels this is
  exact, so `ruptures` buys nothing here.

    python -m airsbench.analysis.freshness_sweep
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..pipelines.loader import DEP_DELAY_KNOWLEDGE_HORIZON_S
from ..runner.config import RunConfig, run_arm
from ..runner.execute import value_staleness_s
from .flip_partition import Replayer

# Degradation of this many points defines the operational threshold (RQ1).
THRESHOLD_BAND = 0.10


@dataclass
class Level:
    """One staleness level, pooled over replications."""

    staleness_s: float
    n_runs: int
    n_decisions: int
    accuracy: float
    abstained: float
    silent: float
    # Retrieval only — requires the flip partition.
    flip_rate: float | None = None
    unflipped_accuracy: float | None = None
    flip_silent: float | None = None
    flip_abstained: float | None = None
    n_flipped: int = 0
    # Per-run values, for the run-level monotonicity tests.
    run_accuracy: list[float] = None
    run_flip_silent: list[float] = None

    @property
    def saturated_classification(self) -> bool:
        """Past the horizon the delay feature is clamped to zero for every
        flight, so the arm is measuring an absent feature rather than a stale
        one. See CLAUDE.md's note on the horizon collision."""
        return self.staleness_s >= DEP_DELAY_KNOWLEDGE_HORIZON_S


def load_sweep(results_dir: Path) -> list[dict[str, Any]]:
    runs = []
    for path in sorted(results_dir.glob("*.json")):
        data = json.loads(path.read_text())
        if run_arm(data) == "freshness_sweep":
            runs.append(data)
    return runs


def _config(run: dict[str, Any]) -> RunConfig:
    return RunConfig(
        **{k: v for k, v in run["config"].items() if k in RunConfig.__dataclass_fields__}
    )


def _rates(decisions: list[dict[str, Any]]) -> tuple[float, float, float]:
    n = len(decisions)
    if not n:
        return (float("nan"),) * 3
    silent = sum(
        1 for d in decisions
        if not d["correct"] and not d["abstained"] and not d["parse_failed"]
    )
    return (
        sum(d["correct"] for d in decisions) / n,
        sum(d["abstained"] for d in decisions) / n,
        silent / n,
    )


def build_levels(
    runs: list[dict[str, Any]], task: str, replayer: Replayer | None
) -> list[Level]:
    by_staleness: dict[float, list[dict]] = defaultdict(list)
    for run in runs:
        if run["config"]["task"] == task:
            by_staleness[round(value_staleness_s(_config(run)), 4)].append(run)

    levels: list[Level] = []
    for staleness in sorted(by_staleness):
        group = by_staleness[staleness]
        decisions = [d for run in group for d in run["decisions"]]
        accuracy, abstained, silent = _rates(decisions)
        level = Level(
            staleness_s=staleness,
            n_runs=len(group),
            n_decisions=len(decisions),
            accuracy=accuracy,
            abstained=abstained,
            silent=silent,
            run_accuracy=[_rates(run["decisions"])[0] for run in group],
            run_flip_silent=[],
        )

        if task == "retrieval" and replayer is not None:
            flipped_all: list[dict] = []
            unflipped_all: list[dict] = []
            for run in group:
                outcomes = replayer.outcomes(run)
                flipped = [
                    d for o, d in zip(outcomes, run["decisions"]) if o.flipped
                ]
                unflipped = [
                    d for o, d in zip(outcomes, run["decisions"]) if not o.flipped
                ]
                flipped_all += flipped
                unflipped_all += unflipped
                level.run_flip_silent.append(
                    _rates(flipped)[2] if flipped else float("nan")
                )
            level.n_flipped = len(flipped_all)
            level.flip_rate = len(flipped_all) / max(len(decisions), 1)
            level.unflipped_accuracy = _rates(unflipped_all)[0]
            if flipped_all:
                _, level.flip_abstained, level.flip_silent = _rates(flipped_all)
        levels.append(level)
    return levels


# ---- monotonicity ----------------------------------------------------------

def spearman(xs: list[float], ys: list[float]) -> tuple[float, float]:
    from scipy.stats import spearmanr

    if len(xs) < 3:
        return float("nan"), float("nan")
    result = spearmanr(xs, ys)
    return float(result.statistic), float(result.pvalue)


def isotonic_cost(xs: list[float], ys: list[float], increasing: bool) -> tuple[float, float]:
    """SSE of a monotone fit vs the unconstrained per-level means.

    The unconstrained model is the per-level mean — six free parameters against
    the isotonic fit's monotone-constrained ones. If the constraint costs little
    extra error the data are consistent with monotonicity; a large cost is
    evidence against it.

    Returns (isotonic SSE, unconstrained SSE).
    """
    from sklearn.isotonic import IsotonicRegression

    fit = IsotonicRegression(increasing=increasing, out_of_bounds="clip").fit(xs, ys)
    iso_sse = float(sum((y - p) ** 2 for y, p in zip(ys, fit.predict(xs))))

    means: dict[float, list[float]] = defaultdict(list)
    for x, y in zip(xs, ys):
        means[x].append(y)
    free_sse = float(
        sum((y - statistics.fmean(means[x])) ** 2 for x, y in zip(xs, ys))
    )
    return iso_sse, free_sse


def changepoint(values: list[float]) -> tuple[int | None, float]:
    """Exhaustive single-changepoint search: the split minimising within-segment
    SSE. Exact at six levels, so no approximation and no extra dependency.

    Returns (index of the first point after the change, variance explained).
    """
    n = len(values)
    if n < 4:
        return None, 0.0
    total = sum((v - statistics.fmean(values)) ** 2 for v in values)
    best, best_sse = None, total
    for split in range(1, n):
        left, right = values[:split], values[split:]
        if not left or not right:
            continue
        sse = sum((v - statistics.fmean(left)) ** 2 for v in left) + sum(
            (v - statistics.fmean(right)) ** 2 for v in right
        )
        if sse < best_sse:
            best, best_sse = split, sse
    explained = 1 - best_sse / total if total > 0 else 0.0
    return best, explained


def first_crossing(levels: list[Level], values: list[float], rising: bool) -> float | None:
    """Staleness at which the outcome first degrades past the band."""
    if not values:
        return None
    reference = values[0]
    for level, value in zip(levels, values):
        delta = value - reference if rising else reference - value
        if delta >= THRESHOLD_BAND:
            return level.staleness_s
    return None


# ---- reporting -------------------------------------------------------------

def _fmt(value: float | None, pct: bool = True) -> str:
    if value is None or value != value:
        return f"{'—':>9}"
    return f"{value:>8.0%} " if pct else f"{value:>9.3f}"


def report_task(task: str, levels: list[Level]) -> None:
    print(f"\n{'=' * 78}\n{task.upper()}\n")
    if not levels:
        print("  no runs")
        return

    if task == "retrieval":
        print(f"  {'stale':>7}{'runs':>6}{'n':>7}{'raw acc':>10}{'flip%':>9}"
              f"{'unflip acc':>12}{'silent|flip':>12}{'abst|flip':>11}")
        print("  " + "-" * 74)
        for lv in levels:
            print(f"  {lv.staleness_s:>6.2f}s{lv.n_runs:>6}{lv.n_decisions:>7}"
                  f"{lv.accuracy:>10.3f}{_fmt(lv.flip_rate)}"
                  f"{lv.unflipped_accuracy:>12.3f}"
                  f"{_fmt(lv.flip_silent):>12}{_fmt(lv.flip_abstained):>11}")
    else:
        print(f"  {'stale':>7}{'runs':>6}{'n':>7}{'accuracy':>10}{'abstain':>10}"
              f"{'silent':>9}   note")
        print("  " + "-" * 74)
        for lv in levels:
            note = "<- feature zeroed by the horizon" if lv.saturated_classification else ""
            print(f"  {lv.staleness_s:>6.2f}s{lv.n_runs:>6}{lv.n_decisions:>7}"
                  f"{lv.accuracy:>10.3f}{lv.abstained:>10.0%}{lv.silent:>9.0%}   {note}")

    # ---- monotonicity on the primary outcome -----------------------------
    if task == "retrieval":
        outcome_name = "flip-conditioned silent failure"
        pooled = [lv.flip_silent for lv in levels]
        run_x = [lv.staleness_s for lv in levels for v in lv.run_flip_silent if v == v]
        run_y = [v for lv in levels for v in lv.run_flip_silent if v == v]
        rising = True
    else:
        usable = [lv for lv in levels if not lv.saturated_classification]
        if len(usable) < len(levels):
            print(f"\n  Levels at or beyond the {DEP_DELAY_KNOWLEDGE_HORIZON_S:.0f}s "
                  "knowledge horizon are EXCLUDED from the tests below:")
            print("  the delay feature is clamped to zero there, so the arm measures")
            print("  an absent feature rather than a stale one. Reported, not tested.")
        levels = usable
        outcome_name = "accuracy"
        pooled = [lv.accuracy for lv in levels]
        run_x = [lv.staleness_s for lv in levels for _ in lv.run_accuracy]
        run_y = [v for lv in levels for v in lv.run_accuracy]
        rising = False

    pooled = [v for v in pooled if v is not None and v == v]
    if len(pooled) < 3:
        print("\n  too few usable levels for a monotonicity test")
        return

    print(f"\n  MONOTONICITY — outcome: {outcome_name}")
    rho, p = spearman(run_x, run_y)
    direction = "increasing" if rising else "decreasing"
    print(f"    Spearman rho = {rho:+.3f} (p = {p:.4f}) over {len(run_y)} runs "
          f"[expected {direction}]")

    iso_sse, free_sse = isotonic_cost(run_x, run_y, increasing=rising)
    cost = (iso_sse - free_sse) / free_sse if free_sse > 0 else 0.0
    print(f"    isotonic SSE {iso_sse:.4f} vs unconstrained {free_sse:.4f} "
          f"({cost:+.1%} cost)")
    if cost < 0.05:
        print("    => monotone constraint costs almost nothing: response is")
        print("       consistent with monotonicity in data age.")
    else:
        print("    => the monotone constraint costs real error: the response is")
        print("       NOT monotone in age (cf. Shisher & Sun). Report the curve.")

    split, explained = changepoint(pooled)
    if split is not None:
        print(f"    changepoint between {levels[split - 1].staleness_s:.2f}s and "
              f"{levels[split].staleness_s:.2f}s (explains {explained:.0%} of variance)")

    crossing = first_crossing(levels, pooled, rising=rising)
    if crossing is None:
        print(f"    threshold: never crosses the {THRESHOLD_BAND:.0%} band "
              f"within the sweep")
    else:
        print(f"    threshold: {outcome_name} crosses the {THRESHOLD_BAND:.0%} band "
              f"at {crossing:.2f}s")


def report(runs: list[dict[str, Any]], data_dir: Path) -> int:
    if not runs:
        print("No freshness-sweep runs found. Run:")
        print("  python -m airsbench.runner.run --freshness-sweep --n-queries 60 "
              "--max-cost 0.50")
        return 1

    cost = sum(r["usage"]["cost_usd"] for r in runs)
    print(f"Freshness sweep — {len(runs)} runs, ${cost:.3f}\n")
    print("RQ1: is degradation monotone in data age, and where is the threshold?")
    print("Outcome for retrieval is the FLIP-CONDITIONED silent-failure rate, not")
    print("accuracy — raw accuracy under staleness traces the answer-flip rate,")
    print("which is a property of the catalog rather than of the agent.")

    replayer = Replayer(data_dir)
    for task in ("retrieval", "classification"):
        report_task(task, build_levels(runs, task, replayer))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    args = parser.parse_args(argv)
    return report(load_sweep(args.results), args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
