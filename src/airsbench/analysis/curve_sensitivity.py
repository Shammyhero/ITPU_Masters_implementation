"""Is AIRS one metric, or one arbitrary parameterisation of a family of them?

RQ4 fits the AIRS weights rather than assuming them, and the calibration reports
that as a methodological commitment. The commitment holds one level up and is
skipped one level down: the weights are estimated, but they are estimated *on
top of* four constants nobody derived —

    src/airsbench/airs/calculator.py
        DEFAULT_FRESHNESS_TARGET_S = 1.0      # why one second?
        DEFAULT_LATENCY_TARGET_MS  = 500.0    # why half a second?
        score = 100 * target / observed       # why a hyperbola?

Change any of them and every freshness and latency score in the study moves, the
weights are refitted against different predictors, and the composite reports a
different number for the same pipeline. A metric whose values depend on
undocumented choices is not measured, it is declared — so this module measures
how much depends on them.

## Design

**Physical quantities are recovered from the run configuration, never inverted
from the recorded score.** Inversion is tempting (`age = 100·T/score`) and wrong:
`latency_score` returns exactly 100 for everything at or below target, so a
baseline run at 0 ms and a mild-latency run at 500 ms both invert to 500 ms. An
earlier draft of this analysis did precisely that and silently treated every
fault-free pipeline as degraded. `value_staleness_s` and the injector's
`spike_ms` give the true values.

**Every curve is anchored at the same two points** — 100 at the target and 10 at
ten times the target — so the comparison isolates the *shape* of the decay and
not incidental steepness. Without the anchor a reviewer could fairly say the
alternatives were chosen to flatter the shipped one.

**Everything else is held identical to the published calibration**: same frame,
same run-level split, same seed, same estimator, same target variable. Only the
two dimension transforms move.

    python -m airsbench.analysis.curve_sensitivity
    python -m airsbench.analysis.curve_sensitivity --figure docs/figures/fig4_7.png
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..airs import DIMENSIONS
from ..runner.config import RunConfig, fault_components
from ..runner.execute import value_staleness_s

# The calibration is fitted on one model; mixing models here would confound
# curve shape with model identity.
CALIBRATION_MODEL = "gpt-4o-mini"
# The calibration doc recommends total error over silent failure as the target,
# because whether pipeline harm surfaces as a lie or a refusal belongs to the
# agent (H3), not the pipeline.
TARGET = "wrong"
# Anchor: every curve reads 100 at the target and 10 at ANCHOR_RATIO x target.
ANCHOR_RATIO = 10.0

CurveFn = Callable[[float, float], float]


def _hyperbolic(x: float, target: float) -> float:
    """The shipped curve. Already passes through both anchors."""
    return 100.0 if x <= target else 100.0 * target / x


def _exponential(x: float, target: float) -> float:
    if x <= target:
        return 100.0
    rate = math.log(ANCHOR_RATIO) / (ANCHOR_RATIO - 1.0)
    return 100.0 * math.exp(-rate * (x / target - 1.0))


def _linear(x: float, target: float) -> float:
    if x <= target:
        return 100.0
    slope = 90.0 / (ANCHOR_RATIO - 1.0)
    return max(0.0, 100.0 - slope * (x / target - 1.0))


def _logarithmic(x: float, target: float) -> float:
    if x <= target:
        return 100.0
    scale = 90.0 / math.log(ANCHOR_RATIO)
    return max(0.0, 100.0 - scale * math.log(x / target))


CURVES: dict[str, CurveFn] = {
    "hyperbolic": _hyperbolic,
    "exponential": _exponential,
    "linear": _linear,
    "logarithmic": _logarithmic,
}

SHIPPED_FRESHNESS_TARGET_S = 1.0
SHIPPED_LATENCY_TARGET_MS = 500.0
SHIPPED_SHAPE = "hyperbolic"


@dataclass(frozen=True)
class Variant:
    """One parameterisation of the two target-based AIRS dimensions."""

    label: str
    shape: str
    freshness_target_s: float
    latency_target_ms: float
    family: str  # "shipped" | "shape" | "target"

    @property
    def shipped(self) -> bool:
        return self.family == "shipped"

    def score(self, age_s: float, latency_ms: float) -> tuple[float, float]:
        curve = CURVES[self.shape]
        return (curve(max(age_s, 1e-9), self.freshness_target_s),
                curve(max(latency_ms, 1.0), self.latency_target_ms))


def build_variants() -> list[Variant]:
    """The shipped parameterisation, then shape held fixed, then target held fixed."""
    variants = [Variant("SHIPPED  hyperbolic, 1.0 s / 500 ms", SHIPPED_SHAPE,
                        SHIPPED_FRESHNESS_TARGET_S, SHIPPED_LATENCY_TARGET_MS,
                        "shipped")]
    for shape in CURVES:
        if shape == SHIPPED_SHAPE:
            continue
        variants.append(Variant(f"shape: {shape}", shape,
                                SHIPPED_FRESHNESS_TARGET_S,
                                SHIPPED_LATENCY_TARGET_MS, "shape"))
    for fresh_s, lat_ms in ((0.5, 250.0), (2.0, 1000.0), (5.0, 2000.0)):
        variants.append(Variant(f"target: {fresh_s} s / {lat_ms:.0f} ms",
                                SHIPPED_SHAPE, fresh_s, lat_ms, "target"))
    return variants


# ---- physical quantities ---------------------------------------------------

def physical_quantities(run: dict[str, Any]) -> tuple[float, float]:
    """(mean record age in seconds, mean delivery latency in ms) for a run.

    Both are exact functions of the configuration. Recovering them by inverting
    the recorded AIRS score cannot work: `latency_score` saturates at 100 for
    everything at or below target, so a fault-free run (0 ms) and a mild-latency
    run (500 ms) are indistinguishable after scoring.
    """
    config = RunConfig(
        **{k: v for k, v in run["config"].items()
           if k in RunConfig.__dataclass_fields__}
    )
    age_s = value_staleness_s(config)
    components = fault_components(config.fault_type)
    if "latency" in components:
        params = config.injector_params
        entry = params.get("latency", params) if len(components) > 1 else params
        # spike_probability defaults to 1.0, so mean injected latency == spike_ms
        latency_ms = float(entry.get("spike_ms", 0.0))
    else:
        latency_ms = 0.0
    return age_s, latency_ms


def attach_physical(frame, results_dir: Path):
    """Add exact `age_s` and `latency_ms` columns to a calibration frame."""
    import json

    import pandas as pd

    rows = []
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        age_s, latency_ms = physical_quantities(run)
        rows.append({"run_id": run["run_id"], "age_s": age_s,
                     "latency_ms": latency_ms})
    return frame.merge(pd.DataFrame(rows), on="run_id", how="left")


# ---- refitting -------------------------------------------------------------

def refit(frame, variant: Variant, task: str) -> dict[str, Any]:
    """Refit the RQ4 weights under one parameterisation.

    Identical to `airs_calibration` in every respect except the two transforms:
    same split seed, same estimator, same cluster-robust SEs, same target.
    """
    from .airs_calibration import fit_weights, normalised_weights, run_level_ranking, split_by_run

    selected = frame[(frame["task"] == task)
                     & (frame["model"] == CALIBRATION_MODEL)].copy()
    scored = [variant.score(a, ms) for a, ms
              in zip(selected["age_s"], selected["latency_ms"])]
    selected["freshness"] = [f for f, _ in scored]
    selected["latency"] = [ms for _, ms in scored]

    train, held = split_by_run(selected)
    weights = normalised_weights(fit_weights(train, TARGET))
    rho, p_value, n_runs = run_level_ranking(held, weights, TARGET)
    return {"weights": weights, "rho": rho, "p": p_value, "n": n_runs,
            "top": max(weights, key=weights.get)}


def sensitivity(frame, task: str) -> list[tuple[Variant, dict[str, Any]]]:
    return [(v, refit(frame, v, task)) for v in build_variants()]


# ---- reporting -------------------------------------------------------------

def report_task(frame, task: str) -> list[tuple[Variant, dict[str, Any]]]:
    results = sensitivity(frame, task)
    print(f"\n{task.upper()}   target = total error, model = {CALIBRATION_MODEL}")
    print(f"  {'parameterisation':<34}" + "".join(f"{d[:9]:>10}" for d in DIMENSIONS)
          + f"{'held-out p':>12}{'top':>14}")
    print("  " + "-" * 100)
    for variant, out in results:
        marker = " *" if variant.shipped else "  "
        print(f"{marker}{variant.label:<34}"
              + "".join(f"{out['weights'][d]:>9.1%} " for d in DIMENSIONS)
              + f"{out['rho']:>+11.3f}{out['top']:>14}")

    shipped = next(o for v, o in results if v.shipped)
    print("\n  dimension        shipped      range across parameterisations   verdict")
    print("  " + "-" * 78)
    for dim in DIMENSIONS:
        values = [o["weights"][dim] for _, o in results]
        low, high = min(values), max(values)
        spread_pp = 100.0 * (high - low)
        if high < 0.005:
            verdict = "zero everywhere — robust"
        elif spread_pp < 10.0:
            verdict = "stable"
        else:
            verdict = "PARAMETERISATION-DEPENDENT"
        print(f"  {dim:<16}{shipped['weights'][dim]:>7.1%}"
              f"{low:>14.1%} – {high:<8.1%}{spread_pp:>7.1f}pp   {verdict}")

    tops = {o["top"] for _, o in results}
    if len(tops) == 1:
        print(f"\n  Dominant dimension is {tops.pop().upper()} under every "
              f"parameterisation tested.")
    else:
        flippers = [v.label for v, o in results if o["top"] != shipped["top"]]
        print(f"\n  ⚠ The dominant dimension CHANGES: {shipped['top']} under the "
              f"shipped curve,\n    but {', '.join(sorted(tops - {shipped['top']}))} "
              f"under — {'; '.join(flippers)}.")
    return results


def report(frame) -> int:
    print("AIRS curve sensitivity — do the conclusions depend on the "
          "undocumented constants?\n")
    print("Every curve is anchored at 100 at its target and 10 at ten times its")
    print("target, so what varies is the SHAPE of the decay, not its steepness.")
    print("Split seed, estimator and target variable are identical to the")
    print("published calibration; only the freshness and latency transforms move.")
    for task in ("retrieval", "classification"):
        report_task(frame, task)
    print("\n  * = the parameterisation shipped in airs/calculator.py")
    return 0


def figure(frame, out_path: Path) -> Path:
    """Tornado plot: weight range per dimension, shipped value marked."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharex=True)
    for ax, task in zip(axes, ("retrieval", "classification")):
        results = sensitivity(frame, task)
        shipped = next(o for v, o in results if v.shipped)
        for row, dim in enumerate(reversed(DIMENSIONS)):
            values = [o["weights"][dim] * 100 for _, o in results]
            low, high = min(values), max(values)
            ax.barh(row, high - low, left=low, height=0.5,
                    color="#c9d6e0", edgecolor="#5a6675", linewidth=0.6)
            ax.plot([shipped["weights"][dim] * 100], [row], marker="D",
                    color="#0e6f7a", markersize=7, zorder=3)
        ax.set_yticks(range(len(DIMENSIONS)))
        ax.set_yticklabels([d for d in reversed(DIMENSIONS)])
        ax.set_title(task, fontsize=11)
        ax.set_xlabel("fitted weight (%)")
        ax.grid(axis="x", color="#e3eaee", linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
    # Legend goes OUTSIDE the axes: placed inside, the sample marker sits at a
    # plausible x position on a dimension's row and reads as a data point.
    handles = [
        plt.Line2D([], [], marker="D", color="#0e6f7a", linestyle="none",
                   markersize=7, label="shipped parameterisation"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#c9d6e0", edgecolor="#5a6675",
                      linewidth=0.6, label="range across 7 parameterisations"),
    ]
    fig.legend(handles=handles, frameon=False, fontsize=9, ncols=2,
               loc="lower center", bbox_to_anchor=(0.5, -0.10))
    fig.suptitle("AIRS weight sensitivity to the undocumented scoring curves",
                 fontsize=12, y=1.04)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    parser.add_argument("--figure", type=Path, default=None,
                        help="also write the tornado plot here")
    args = parser.parse_args(argv)

    from .airs_calibration import build_frame

    frame = attach_physical(build_frame(args.results, args.data_dir), args.results)
    status = report(frame)
    if args.figure is not None:
        print(f"\n  figure: {figure(frame, args.figure)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
