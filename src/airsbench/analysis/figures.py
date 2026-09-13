"""Chapter 4 figures 4.1–4.5, drawn through the modules that own each result.

Every number in these figures is recomputed by the same code that produced its
findings document — never copied — and printed as the figure is built. Where a
published value exists to check against (the held-out Spearman stored in
`calibrated_weights.json`, the AUCs in `airs_calibration_findings.md`), the
recomputed value is printed beside it, so a figure that silently disagrees with
its own findings doc is caught before it reaches a chapter.

Figures 4.6–4.8 are produced by `interaction`, `curve_sensitivity` and
`fragility` themselves; `make figures` builds all of them.

    python -m airsbench.analysis.figures
    python -m airsbench.analysis.figures --only 4.4
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

RESULTS = Path("results/runs")
DATA = Path("data/ecommerce")
OUT = Path("docs/figures")
MODEL = "gpt-4o-mini"
FAULTS = ("freshness", "latency", "schema_drift", "semantic_stripping")
TASKS = ("retrieval", "classification")
TEAL, AMBER, GREY, SLATE, MIST = "#0e6f7a", "#b45309", "#8a96a3", "#5a6675", "#c9d6e0"
WEIGHTS_FILE = Path(__file__).parents[1] / "airs" / "calibrated_weights.json"
# Published AUCs (airs_calibration_findings.md §2), silent-failure target, held out.
PUBLISHED_AUC = {"retrieval": (0.580, 0.501), "classification": (0.557, 0.608)}


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _style(ax) -> None:
    ax.grid(color="#eef2f5", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def _save(fig, name: str) -> Path:
    plt = _plt()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _legend_below(fig, ax, ncols: int, offset: float = -0.08) -> None:
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, ncols=ncols,
               loc="lower center", bbox_to_anchor=(0.5, offset))


@lru_cache(maxsize=1)
def _replayer():
    from .flip_partition import Replayer
    return Replayer(DATA)


@lru_cache(maxsize=1)
def _calibration_frame():
    from .airs_calibration import build_frame
    frame = build_frame(RESULTS, DATA)
    return frame[(frame["model"] == MODEL) & (frame["arm"] != "cross_model")]


def _check(label: str, got: float, expected: float, tolerance: float) -> None:
    status = "OK" if abs(got - expected) <= tolerance else "MISMATCH"
    print(f"    {label}: recomputed {got:+.3f}, published {expected:+.3f}  [{status}]")


# ---- 4.1 -------------------------------------------------------------------------

def fig4_1() -> Path:
    """RQ1: freshness is monotone, and retrieval decomposes into exposure x rate."""
    from .freshness_sweep import build_levels, load_sweep

    plt = _plt()
    runs = load_sweep(RESULTS)
    retrieval = build_levels(runs, "retrieval", _replayer())
    classification = build_levels(runs, "classification", None)

    fig, (left, right) = plt.subplots(1, 2, figsize=(11.8, 4.3))
    xs = [lv.staleness_s for lv in retrieval]
    nan = float("nan")
    left.plot(xs, [100 * (lv.flip_rate if lv.flip_rate is not None else nan) for lv in retrieval],
              marker="o", color=AMBER, linewidth=2, label="exposure: correct answer changed")
    left.plot(xs, [100 * (lv.flip_silent if lv.flip_silent is not None else nan)
                   for lv in retrieval],
              marker="s", color=TEAL, linewidth=2, label="silent failure, given it changed")
    left.plot(xs, [100 * lv.silent for lv in retrieval], marker="^", color=SLATE,
              linewidth=1.3, linestyle="--", label="silent failure, all decisions")
    for lv in retrieval:
        left.scatter([lv.staleness_s] * len(lv.run_flip_rate),
                     [100 * v for v in lv.run_flip_rate], color=AMBER, s=9, alpha=0.3, lw=0)
        values = [v for v in lv.run_flip_silent if v == v]
        left.scatter([lv.staleness_s] * len(values), [100 * v for v in values],
                     color=TEAL, s=9, alpha=0.3, lw=0)
    left.set_title("retrieval", fontsize=11)

    xc = [lv.staleness_s for lv in classification]
    right.plot(xc, [100 * lv.accuracy for lv in classification], marker="o", color=TEAL,
               linewidth=2, label="accuracy")
    right.plot(xc, [100 * lv.silent for lv in classification], marker="s", color=AMBER,
               linewidth=2, label="silent failure")
    saturated = [lv.staleness_s for lv in classification if lv.saturated_classification]
    if saturated:
        right.axvspan(min(saturated) * 0.92, max(xc) * 1.1, color=MIST, alpha=0.45, lw=0,
                      label="past the delay-knowledge horizon")
    right.set_title("classification", fontsize=11)

    for ax in (left, right):
        ax.set_xscale("log")
        ax.set_xticks(xs or xc)
        ax.set_xticklabels([f"{x:g}" for x in (xs or xc)])
        ax.set_xlabel("age of the served values (s, log scale)")
        ax.set_ylabel("%")
        _style(ax)
        ax.legend(frameon=False, fontsize=8.5, loc="best")
    fig.suptitle("Degradation is monotone in data age — and on retrieval it is exposure, "
                 "not impairment", fontsize=12, y=1.02)
    fig.tight_layout()

    print("  4.1  staleness  exposure  silent|changed  silent-all   (retrieval)")
    for lv in retrieval:
        print(f"       {lv.staleness_s:>7.2f}  {lv.flip_rate or 0:>8.1%}  "
              f"{lv.flip_silent if lv.flip_silent is not None else nan:>14.1%}  {lv.silent:>10.1%}")
    return _save(fig, "fig4_1_freshness_sweep.png")


# ---- 4.2 -------------------------------------------------------------------------

def fig4_2() -> Path:
    """RQ2: raw accuracy change against residual impairment, retrieval.

    Pooled over BOTH pipelines, exactly as `flip_partition_findings.md` publishes
    RQ2. An earlier version plotted streaming only, which gave different numbers
    (−19.7 pp severe drift against the published −0.173) for the same claim.
    """
    from ..runner.config import run_arm

    plt = _plt()
    replayer = _replayer()
    cells = defaultdict(list)
    for path in sorted(RESULTS.glob("*.json")):
        run = json.loads(path.read_text())
        c = run["config"]
        if run_arm(run) == "main" and c["model"] == MODEL and c["task"] == "retrieval":
            cells[(c["fault_type"], c["severity"])].extend(replayer.outcomes(run))

    def accuracy(outcomes):
        return sum(o.correct for o in outcomes) / len(outcomes)

    def unflipped(outcomes):
        kept = [o for o in outcomes if not o.flipped]
        return accuracy(kept) if kept else float("nan")

    base = cells[("none", "none")]
    base_raw, base_residual = accuracy(base), unflipped(base)
    rows, residual, raw_accuracy = [], {}, {}
    for fault in FAULTS:
        for severity in ("mild", "severe"):
            outcomes = cells.get((fault, severity))
            if not outcomes:
                continue
            residual[(fault, severity)] = unflipped(outcomes) - base_residual
            raw_accuracy[(fault, severity)] = accuracy(outcomes)
            rows.append((f"{fault.replace('_', ' ')} · {severity}",
                         100 * (accuracy(outcomes) - base_raw),
                         100 * residual[(fault, severity)]))

    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    positions = list(range(len(rows)))[::-1]
    height = 0.38
    ax.barh([p + height / 2 for p in positions], [r[1] for r in rows], height=height,
            color=MIST, edgecolor=SLATE, linewidth=0.6, label="raw accuracy change")
    ax.barh([p - height / 2 for p in positions], [r[2] for r in rows], height=height,
            color=TEAL, label="residual impairment (questions whose answer did not change)")
    ax.axvline(0, color=SLATE, linewidth=0.8)
    ax.set_yticks(positions)
    ax.set_yticklabels([r[0] for r in rows], fontsize=9)
    ax.set_xlabel("change against the fault-free baseline, both pipelines pooled (pp)")
    _style(ax)
    _legend_below(fig, ax, ncols=1, offset=-0.16)
    fig.suptitle("Freshness lowers accuracy without impairing the agent; drift and "
                 "stripping impair it", fontsize=12, y=1.02)
    fig.tight_layout()

    print(f"  4.2  baseline raw accuracy {base_raw:.3f}, unflipped {base_residual:.3f} (pooled)")
    print("       condition                       raw Δ   residual Δ   (pp)")
    for label, raw, res in rows:
        print(f"       {label:<30}{raw:>+7.1f}{res:>+12.1f}")
    published_residual = {("freshness", "mild"): -0.003, ("freshness", "severe"): -0.003,
                          ("schema_drift", "severe"): -0.173,
                          ("semantic_stripping", "severe"): -0.128}
    published_raw = {("freshness", "mild"): 0.812, ("freshness", "severe"): 0.774,
                     ("schema_drift", "severe"): 0.689, ("semantic_stripping", "severe"): 0.729}
    for key, expected in published_residual.items():
        _check(f"{key[0]}/{key[1]} residual", residual[key], expected, 0.0015)
    for key, expected in published_raw.items():
        _check(f"{key[0]}/{key[1]} raw accuracy", raw_accuracy[key], expected, 0.0015)
    return _save(fig, "fig4_2_flip_partition.png")


# ---- 4.3 -------------------------------------------------------------------------

def fig4_3() -> Path:
    """RQ4: AIRS ranks pipelines by total error, on runs it was not fitted on."""
    from ..airs import DIMENSIONS
    from ..gate.replay import load_weights
    from .airs_calibration import run_level_ranking, split_by_run

    plt = _plt()
    frame = _calibration_frame()
    stored = json.loads(WEIGHTS_FILE.read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4))
    print("  4.3  held-out Spearman, AIRS composite vs run total error")
    for ax, task in zip(axes, TASKS):
        train, held = split_by_run(frame[frame["task"] == task])
        weights = load_weights(task)
        rho, _, n_runs = run_level_ranking(held, weights, "wrong")
        _check(task, rho, stored["validation"][task]["held_out_spearman"], 1e-3)
        for part, colour, alpha, size, label in ((train, GREY, 0.35, 12, "fitting runs"),
                                                 (held, TEAL, 0.95, 26, "held-out runs")):
            runs = part.groupby("run_id").agg(
                rate=("wrong", "mean"), **{d: (d, "first") for d in DIMENSIONS})
            composite = sum(weights[d] * runs[d] for d in DIMENSIONS)
            ax.scatter(composite, 100 * runs["rate"], s=size, color=colour, alpha=alpha,
                       linewidth=0, label=label)
        ax.set_title(f"{task}   held-out ρ = {rho:+.2f} (n = {n_runs} runs)", fontsize=11)
        ax.set_xlabel("AIRS composite (calibrated weights)")
        ax.set_ylabel("run total error (%)")
        _style(ax)
    _legend_below(fig, axes[0], ncols=2, offset=-0.07)
    fig.suptitle("AIRS ranks pipelines it was never fitted on", fontsize=12, y=1.02)
    fig.tight_layout()
    return _save(fig, "fig4_3_airs_ranking.png")


# ---- 4.4 -------------------------------------------------------------------------

def fig4_4() -> Path:
    """RQ4 headline: agent confidence cannot see its own silent failures."""
    from sklearn.metrics import roc_curve

    from ..airs import DIMENSIONS
    from .airs_calibration import delong_test, fit_weights, normalised_weights, split_by_run

    plt = _plt()
    frame = _calibration_frame()
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.8))
    print("  4.4  held-out decision-level AUC, silent failure")
    for ax, task in zip(axes, TASKS):
        train, held = split_by_run(frame[frame["task"] == task])
        weights = normalised_weights(fit_weights(train, "silent"))
        labels = held["silent"].to_numpy()
        airs_score = (-sum(weights[d] * held[d] for d in DIMENSIONS)).to_numpy()
        confidence_score = (-held["confidence"]).to_numpy()
        airs_auc, confidence_auc, p = delong_test(labels, airs_score, confidence_score)
        published_airs, published_conf = PUBLISHED_AUC[task]
        _check(f"{task} AIRS", airs_auc, published_airs, 2e-3)
        _check(f"{task} confidence", confidence_auc, published_conf, 2e-3)
        for score, colour, name, value in (
            (airs_score, TEAL, "AIRS", airs_auc),
            (confidence_score, AMBER, "agent confidence", confidence_auc),
        ):
            fpr, tpr, _ = roc_curve(labels, score)
            ax.plot(100 * fpr, 100 * tpr, color=colour, linewidth=2,
                    label=f"{name} — AUC {value:.3f}")
        ax.plot([0, 100], [0, 100], color="#dfe5ea", linewidth=1, zorder=0)
        p_text = "< 0.0001" if p < 1e-4 else f"= {p:.4f}"
        ax.set_title(f"{task} · held-out decisions\nDeLong p {p_text}", fontsize=10.5)
        ax.set_xlabel("false positive rate (%)")
        ax.set_ylabel("true positive rate (%)")
        ax.set_aspect("equal")
        _style(ax)
        # Labels kept short so the legend fits lower right, which is empty in both
        # panels. Long labels spanned the whole axis and struck through the curves
        # in whichever corner they were placed.
        ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.suptitle("On retrieval, the agent's confidence about its own silent failures is a "
                 "coin flip", fontsize=12, y=1.0)
    fig.tight_layout()
    return _save(fig, "fig4_4_confidence_roc.png")


# ---- 4.5 -------------------------------------------------------------------------

def fig4_5() -> Path:
    """The gate: every policy trades coverage for residual silent failure."""
    from ..gate.policy import Policy
    from ..gate.replay import SWEEPS, load_batches, load_weights, replay

    plt = _plt()
    batches = load_batches(RESULTS)
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 4.5), sharey=True)
    print("  4.5  coverage and residual silent failure per policy")
    for ax, task in zip(axes, TASKS):
        selected = [b for b in batches if b.task == task]
        weights = load_weights(task)
        base = replay(selected, Policy(name="no gate"), weights)
        healthy = [b for b in selected if b.fault == "none"]
        floor = sum(b.silent for b in healthy) / sum(b.n for b in healthy)
        for sweep, colour, marker, joined in (("age", AMBER, "o", True),
                                              ("airs", TEAL, "s", True),
                                              ("dimension", SLATE, "^", False)):
            points = []
            for policy in SWEEPS[sweep](task):
                if not policy.checks_anything:
                    continue
                out = replay(selected, policy, weights)
                points.append((100 * out.coverage, 100 * out.residual_silent_rate, policy.name))
            points.sort()
            ax.plot([x for x, _, _ in points], [y for _, y, _ in points], marker=marker,
                    color=colour, linewidth=1.5 if joined else 0, markersize=5.5,
                    label=f"{sweep} policies")
            for x, y, name in points:
                print(f"       {task:<15}{sweep:<10}{name:<34}"
                      f"coverage {x:5.1f}%  residual {y:5.1f}%")
        ax.axhline(100 * base.baseline_silent_rate, color=GREY, linestyle="--", linewidth=1,
                   label="no gate")
        ax.axhline(100 * floor, color=MIST, linewidth=2.5, label="fault-free baseline")
        ax.set_title(task, fontsize=11)
        ax.set_xlabel("coverage: decisions still answered (%)")
        ax.set_xlim(0, 103)
        _style(ax)
    axes[0].set_ylabel("residual silent failure among admitted decisions (%)")
    _legend_below(fig, axes[0], ncols=5, offset=-0.08)
    # Several AIRS policies land BELOW the fault-free line. That is selection, not
    # success: they admit a handful of pipelines, and clean pipelines alone range
    # 6-24% (gate_findings.md). The title must not deny what the plot shows.
    fig.suptitle("A gate trades coverage for residual silent failure — points below the "
                 "fault-free line admit only a handful of pipelines", fontsize=12, y=1.02)
    fig.tight_layout()
    return _save(fig, "fig4_5_gate_tradeoff.png")


FIGURES = {"4.1": fig4_1, "4.2": fig4_2, "4.3": fig4_3, "4.4": fig4_4, "4.5": fig4_5}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", choices=sorted(FIGURES))
    args = parser.parse_args(argv)
    for key in args.only or sorted(FIGURES):
        print(f"  figure: {FIGURES[key]()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
