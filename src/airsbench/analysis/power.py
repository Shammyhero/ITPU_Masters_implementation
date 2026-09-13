"""Was the design able to detect the effects it reports? Power under clustering.

RQs v2 §6 gave a closed-form minimum detectable effect — "roughly 8–10
percentage points" at 320 decisions per condition — and marked a simulation
that accounts for run-level clustering as required before the results chapter.
The closed form treats 320 decisions as 320 independent observations. They are
not: decisions within a run share a query sample and a fault realisation, which
is why every analysis in the study clusters its standard errors by run. The
simulation was never run. This is it.

§6 also justified its bound as conservative "because the mixed-effects model
borrows strength across conditions". No mixed-effects model exists in the
repository; the analyses fit logistic GLMs with cluster-robust errors. So the
simulation tests the model the study actually uses.

Per task and outcome (total error, silent failure), on the main factorial:

  ICC            intraclass correlation between replicate runs of one
                 condition (one-way ANOVA estimator; bootstrap interval over
                 runs, approximate with four runs per condition).
  design effect  1 + (m − 1) · ICC.
  MDE            smallest increase over the fault-free baseline detectable with
                 80% power at α = 0.05 — closed form without clustering (what §6
                 computed), closed form with the design effect, and simulated
                 by generating the study's own design and fitting its own test.

The simulation also measures the test's EMPIRICAL type-I error. A single cell
comparison has four runs per group — eight clusters — and cluster-robust
standard errors are anti-conservative with few clusters, so the nominal 0.05 is
checked rather than assumed. It was not achieved (REVIEW F-C7): the cluster-
robust logistic test rejected a true null 11–12% of the time per cell. Cell and
pooled comparisons therefore use CR2 errors with Bell–McCaffrey degrees of
freedom, chosen because they held nominal size in simulation BEFORE they were
applied to any observed cell. The uncorrected test is still simulated on the
same datasets and reported beside it, so the size of the correction stays
visible.

    python -m airsbench.analysis.power
    python -m airsbench.analysis.power --figure docs/figures/fig3_1_power.png
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..runner.config import run_arm
from ..runner.scoring import is_silent_failure

MODEL = "gpt-4o-mini"
ALPHA = 0.05
TARGET_POWER = 0.80
DELTAS = tuple(round(0.02 * k, 2) for k in range(16))  # 0.00 … 0.30
TASKS = ("retrieval", "classification")
OUTCOMES = ("wrong", "silent")
OUTCOME_LABEL = {"wrong": "total error", "silent": "silent failure"}
SIMS = 2000
BOOTSTRAP = 1000
SEED = 20260913
BASELINE = ("streaming", "none", "none")
# (treated runs, control runs).
#   cell   — one fault x severity on one pipeline against that pipeline's baseline
#   pooled — one fault type over both pipelines and severities against both baselines
DESIGNS = {"cell": (4, 4), "pooled": (16, 8)}


@dataclass(frozen=True)
class RunCount:
    condition: tuple[str, str, str]  # (pipeline, fault_type, severity)
    n: int
    k: int


def outcome_count(decisions: list[dict], outcome: str) -> int:
    if outcome == "silent":
        return sum(1 for d in decisions if is_silent_failure(d))
    if outcome == "wrong":
        return sum(1 for d in decisions if not d.get("correct"))
    raise ValueError(f"unknown outcome {outcome!r}")


def load_counts(runs: list[dict[str, Any]], task: str, outcome: str) -> list[RunCount]:
    return [
        RunCount((r["config"]["pipeline"], r["config"]["fault_type"], r["config"]["severity"]),
                 len(r["decisions"]), outcome_count(r["decisions"], outcome))
        for r in runs
        if run_arm(r) == "main" and r["config"].get("model") == MODEL
        and r["config"]["task"] == task
    ]


def icc_anova(counts: list[RunCount]) -> float:
    """One-way ANOVA ICC between replicate runs, nested within condition.

    Only conditions with at least two runs contribute. Clamped to [0, 1]: a
    negative estimate means between-run variation is below binomial noise.
    """
    groups: dict[tuple, list[RunCount]] = defaultdict(list)
    for rc in counts:
        groups[rc.condition].append(rc)
    groups = {c: v for c, v in groups.items() if len(v) >= 2}
    if not groups:
        return float("nan")
    N = sum(rc.n for v in groups.values() for rc in v)
    R = sum(len(v) for v in groups.values())
    C = len(groups)
    if R - C <= 0 or N - R <= 0:
        return float("nan")
    ss_between = ss_within = sum_sq = 0.0
    for v in groups.values():
        n_condition = sum(rc.n for rc in v)
        mean = sum(rc.k for rc in v) / n_condition
        sum_sq += sum(rc.n ** 2 for rc in v) / n_condition
        for rc in v:
            y = rc.k / rc.n
            ss_between += rc.n * (y - mean) ** 2
            ss_within += rc.n * y * (1 - y)
    ms_between = ss_between / (R - C)
    ms_within = ss_within / (N - R)
    n0 = (N - sum_sq) / (R - C)
    denominator = ms_between + (n0 - 1) * ms_within
    if denominator <= 0:
        return 0.0
    return float(min(1.0, max(0.0, (ms_between - ms_within) / denominator)))


def icc_interval(counts: list[RunCount], rng: np.random.Generator,
                 reps: int = BOOTSTRAP) -> tuple[float, float]:
    groups: dict[tuple, list[RunCount]] = defaultdict(list)
    for rc in counts:
        groups[rc.condition].append(rc)
    values = []
    for _ in range(reps):
        sample = []
        for v in groups.values():
            sample.extend(v[i] for i in rng.integers(0, len(v), len(v)))
        values.append(icc_anova(sample))
    arr = np.array([x for x in values if not math.isnan(x)])
    if not arr.size:
        return float("nan"), float("nan")
    return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))


def design_effect(m: float, icc: float) -> float:
    return 1.0 + (m - 1.0) * icc


def closed_form_mde(p0: float, n_treat: float, n_control: float,
                    alpha: float = ALPHA, power: float = TARGET_POWER) -> float:
    """Two-proportion MDE, iterated so the treated variance uses p0 + MDE."""
    from scipy.stats import norm

    z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    delta = z * math.sqrt(p0 * (1 - p0) * (1 / n_treat + 1 / n_control))
    for _ in range(100):
        p1 = min(p0 + delta, 0.999)
        updated = z * math.sqrt(p0 * (1 - p0) / n_control + p1 * (1 - p1) / n_treat)
        if abs(updated - delta) < 1e-12:
            break
        delta = updated
    return delta


def cluster_pvalues(k_treat, n_treat, k_control, n_control) -> np.ndarray:
    """Two-sided p for `treat` in `y ~ treat`, logistic, cluster-robust by run.

    The UNCORRECTED test — what the study used before REVIEW F-C7, kept so its
    empirical size can be reported beside the corrected one. Arrays are
    (studies, runs). It reproduces statsmodels' default small-sample correction
    G/(G-1) · (N-1)/(N-K) applied at DECISION level. With one binary covariate
    both the MLE and the sandwich have closed forms, which is what makes
    thousands of simulated studies cheap. `tests/test_power.py` pins this
    against statsmodels fitted on the expanded decision-level data.
    """
    from scipy.stats import norm

    kt = np.atleast_2d(np.asarray(k_treat, dtype=float))
    kc = np.atleast_2d(np.asarray(k_control, dtype=float))
    nt = np.broadcast_to(np.asarray(n_treat, dtype=float), kt.shape)
    nc = np.broadcast_to(np.asarray(n_control, dtype=float), kc.shape)
    Nt, Nc = nt.sum(axis=1), nc.sum(axis=1)
    pt, pc = kt.sum(axis=1) / Nt, kc.sum(axis=1) / Nc
    valid = (pt > 0) & (pt < 1) & (pc > 0) & (pc < 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        coefficient = np.log(pt / (1 - pt)) - np.log(pc / (1 - pc))
        var_t = ((kt - nt * pt[:, None]) ** 2).sum(axis=1) / (Nt * pt * (1 - pt)) ** 2
        var_c = ((kc - nc * pc[:, None]) ** 2).sum(axis=1) / (Nc * pc * (1 - pc)) ** 2
        G = kt.shape[1] + kc.shape[1]
        N = Nt + Nc
        variance = (var_t + var_c) * (G / (G - 1)) * ((N - 1) / (N - 2))
        p = 2 * norm.sf(np.abs(coefficient / np.sqrt(variance)))
    return np.where(valid & np.isfinite(p) & (variance > 0), p, 1.0)


def bell_mccaffrey_df(n_treat, n_control) -> np.ndarray:
    """Bell–McCaffrey degrees of freedom for `treat` in `y ~ treat`, CR2 by run.

    Satterthwaite's (Σλ)² / Σλ² over the eigenvalues of the CR2 variance's
    quadratic form, under a homoskedastic working model. It depends on the
    design alone — how many runs, of what size — never on the outcomes. The two
    groups do not interact, so each contributes a block with trace 1/N and
    entries (δ·n_g − n_g·n_h/N) / (N² · √((1 − n_g/N)(1 − n_h/N))). With equal
    run sizes this is Welch–Satterthwaite applied to 1/N per group: 6 for 4 v 4
    runs, 14.1 for 16 v 8.
    """
    def block(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        N = n.sum(axis=-1, keepdims=True)
        a = 1.0 - n / N
        diagonal = np.eye(n.shape[-1]) * n[..., :, None]
        outer = n[..., :, None] * n[..., None, :] / N[..., None]
        B = (diagonal - outer) / (N[..., None] ** 2 * np.sqrt(a[..., :, None] * a[..., None, :]))
        return 1.0 / N[..., 0], (B ** 2).sum(axis=(-2, -1))

    trace_t, square_t = block(np.atleast_2d(np.asarray(n_treat, dtype=float)))
    trace_c, square_c = block(np.atleast_2d(np.asarray(n_control, dtype=float)))
    return (trace_t + trace_c) ** 2 / (square_t + square_c)


def cr2_pvalues(k_treat, n_treat, k_control, n_control) -> np.ndarray:
    """Two-sided p for a difference in proportions: CR2 errors, Bell–McCaffrey df.

    The study's cell and pooled test since REVIEW F-C7. The linear probability
    model `y ~ treat` at decision level, clustered by run. With a binary
    covariate the design is constant within a run, so CR2's bias-reduced
    linearisation collapses to one term per run, (k − n·p)² / (1 − n/N), and
    the reference distribution is t with `bell_mccaffrey_df`.

    The scale is the risk difference, not the log-odds: CR2 is defined for the
    linear model, and the cell comparisons report percentage-point effects.
    `tests/test_power.py` pins both closed forms against the matrix definitions.
    A comparison with no within-group variation has no estimable variance and
    returns p = 1, never a spurious 0.
    """
    from scipy.stats import t as student_t

    kt = np.atleast_2d(np.asarray(k_treat, dtype=float))
    kc = np.atleast_2d(np.asarray(k_control, dtype=float))
    nt = np.broadcast_to(np.asarray(n_treat, dtype=float), kt.shape)
    nc = np.broadcast_to(np.asarray(n_control, dtype=float), kc.shape)
    Nt, Nc = nt.sum(axis=1), nc.sum(axis=1)
    pt, pc = kt.sum(axis=1) / Nt, kc.sum(axis=1) / Nc
    with np.errstate(divide="ignore", invalid="ignore"):
        var_t = (((kt - nt * pt[:, None]) ** 2) / (1 - nt / Nt[:, None])).sum(axis=1) / Nt ** 2
        var_c = (((kc - nc * pc[:, None]) ** 2) / (1 - nc / Nc[:, None])).sum(axis=1) / Nc ** 2
        variance = var_t + var_c
        df = bell_mccaffrey_df(nt, nc)
        p = 2 * student_t.sf(np.abs((pt - pc) / np.sqrt(variance)), df)
    return np.where(np.isfinite(p) & (variance > 0), p, 1.0)


def _run_rates(rng: np.random.Generator, p, icc: float, shape) -> np.ndarray:
    """Per-run success probabilities with the given mean and ICC (beta-binomial).

    `p` may be a scalar or an array broadcastable to `shape`.
    """
    if icc <= 1e-9:
        return np.broadcast_to(np.asarray(p, dtype=float), shape).copy()
    a = np.asarray(p, dtype=float) * (1 - icc) / icc
    b = (1 - np.asarray(p, dtype=float)) * (1 - icc) / icc
    return rng.beta(a, b, size=shape)


def simulate_power(p0: float, icc: float, m: int, runs_treat: int, runs_control: int,
                   deltas=DELTAS, sims: int = SIMS, seed: int = SEED,
                   test=None) -> dict[float, float]:
    """Rejection rate at α for each true effect.

    `test` defaults to the corrected CR2 test. The simulated datasets depend on
    the seed only, so two tests run with one seed see identical studies — which
    is what makes their sizes directly comparable.
    """
    test = test or cr2_pvalues
    rng = np.random.default_rng(seed)
    curve = {}
    for delta in deltas:
        p1 = min(p0 + delta, 0.999)
        kt = rng.binomial(m, _run_rates(rng, p1, icc, (sims, runs_treat)))
        kc = rng.binomial(m, _run_rates(rng, p0, icc, (sims, runs_control)))
        curve[delta] = float((test(kt, m, kc, m) < ALPHA).mean())
    return curve


def mde_from_curve(curve: dict[float, float], target: float = TARGET_POWER) -> float | None:
    for delta in sorted(curve):
        if delta > 0 and curve[delta] >= target:
            return delta
    return None


def observed_cells(counts: list[RunCount]) -> list[dict[str, Any]]:
    """Each streaming fault x severity cell against the streaming baseline, as the
    study's corrected test sees it — with the uncorrected p kept beside it."""
    base = [rc for rc in counts if rc.condition == BASELINE]
    kc = np.array([[rc.k for rc in base]])
    nc = np.array([[rc.n for rc in base]])
    rows = []
    cells = sorted({rc.condition for rc in counts
                    if rc.condition[0] == "streaming" and rc.condition[1] != "none"})
    for condition in cells:
        treat = [rc for rc in counts if rc.condition == condition]
        kt = np.array([[rc.k for rc in treat]])
        nt = np.array([[rc.n for rc in treat]])
        rows.append({"condition": condition,
                     "effect": float(kt.sum() / nt.sum() - kc.sum() / nc.sum()),
                     "p": float(cr2_pvalues(kt, nt, kc, nc)[0]),
                     "p_uncorrected": float(cluster_pvalues(kt, nt, kc, nc)[0])})
    return rows


def analyse(runs: list[dict[str, Any]], sims: int = SIMS, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    results = {}
    offset = 0
    for task in TASKS:
        for outcome in OUTCOMES:
            counts = load_counts(runs, task, outcome)
            base = [rc for rc in counts if rc.condition == BASELINE]
            if not counts or not base:
                continue
            p0 = sum(rc.k for rc in base) / sum(rc.n for rc in base)
            m = int(np.median([rc.n for rc in counts]))
            icc = icc_anova(counts)
            de = design_effect(m, icc)
            designs = {}
            for name, (runs_treat, runs_control) in DESIGNS.items():
                offset += 1
                args = (p0, icc, m, runs_treat, runs_control)
                curve = simulate_power(*args, sims=sims, seed=seed + 97 * offset)
                uncorrected = simulate_power(*args, sims=sims, seed=seed + 97 * offset,
                                             test=cluster_pvalues)
                designs[name] = {
                    "runs": (runs_treat, runs_control),
                    "df": float(bell_mccaffrey_df(np.full(runs_treat, m),
                                                  np.full(runs_control, m))[0]),
                    "naive": closed_form_mde(p0, runs_treat * m, runs_control * m),
                    "adjusted": closed_form_mde(p0, runs_treat * m / de, runs_control * m / de),
                    "curve": curve, "mde": mde_from_curve(curve), "alpha": curve[0.0],
                    "curve_uncorrected": uncorrected,
                    "mde_uncorrected": mde_from_curve(uncorrected),
                    "alpha_uncorrected": uncorrected[0.0],
                }
            results[(task, outcome)] = {
                "p0": p0, "m": m, "icc": icc, "icc_ci": icc_interval(counts, rng),
                "design_effect": de, "designs": designs, "cells": observed_cells(counts),
                "sims": sims,
            }
    return results


def _pp(value: float | None) -> str:
    return "  >30 pp" if value is None else f"{100 * value:>6.1f} pp"


def report(results: dict) -> int:
    print(f"Power under run-level clustering — {MODEL}, main factorial\n")
    print("naive     = closed form ignoring clustering (what RQs v2 §6 computed)")
    print("clustered = closed form with the design effect 1 + (m-1)·ICC")
    print("simulated = the study's own design and test, smallest effect on a 2 pp grid")
    print("            reaching 80% power — CR2 errors, Bell–McCaffrey df (REVIEW F-C7)")
    print("α CR2     = how often that test rejects when there is no effect")
    print("α CR1     = the same for the uncorrected cluster-robust logistic test, on the")
    print("            same simulated studies — why the correction was needed\n")
    for (task, outcome), r in results.items():
        lo, hi = r["icc_ci"]
        print(f"  {task} · {OUTCOME_LABEL[outcome]}   baseline {r['p0']:.1%}   "
              f"{r['m']} decisions/run   ICC {r['icc']:.3f} [{lo:.3f}, {hi:.3f}]   "
              f"design effect {r['design_effect']:.2f}")
        print(f"    {'design':<22}{'naive':>10}{'clustered':>12}{'simulated':>12}"
              f"{'df':>6}{'α CR2':>8}{'α CR1':>8}")
        for name, d in r["designs"].items():
            label = f"{name} ({d['runs'][0]} v {d['runs'][1]} runs)"
            print(f"    {label:<22}{_pp(d['naive']):>10}{_pp(d['adjusted']):>12}"
                  f"{_pp(d['mde']):>12}{d['df']:>6.1f}{d['alpha']:>8.3f}"
                  f"{d['alpha_uncorrected']:>8.3f}")
        cell_mde = r["designs"]["cell"]["mde"]
        print("    observed streaming cells against the streaming baseline:")
        for row in r["cells"]:
            _, fault, severity = row["condition"]
            size = abs(row["effect"])
            verdict = ("above the simulated MDE" if cell_mde is not None and size >= cell_mde
                       else "below the simulated MDE")
            print(f"      {fault + '/' + severity:<30}{100 * row['effect']:>+7.1f} pp   "
                  f"p {row['p']:.3f}   (uncorrected {row['p_uncorrected']:.3f})   {verdict}")
        print()
    return 0


def figure(results: dict, out_path: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(len(TASKS), len(OUTCOMES), figsize=(10.5, 6.8),
                             sharex=True, sharey=True)
    colours = {"cell": "#0e6f7a", "pooled": "#b45309"}
    for i, task in enumerate(TASKS):
        for j, outcome in enumerate(OUTCOMES):
            ax = axes[i][j]
            r = results.get((task, outcome))
            if r is None:
                ax.set_visible(False)
                continue
            for name, d in r["designs"].items():
                xs = [100 * x for x in sorted(d["curve"])]
                ax.plot(xs, [d["curve_uncorrected"][x] for x in sorted(d["curve"])],
                        linewidth=1.0, linestyle="--", alpha=0.45, color=colours[name])
                ax.plot(xs, [d["curve"][x] for x in sorted(d["curve"])],
                        marker="o", markersize=3.5, linewidth=1.6, color=colours[name],
                        label=f"{name} ({d['runs'][0]} v {d['runs'][1]} runs)")
                if d["mde"] is not None:
                    ax.axvline(100 * d["mde"], color=colours[name], linewidth=0.7, linestyle=":")
            ax.axhline(TARGET_POWER, color="#5a6675", linewidth=0.8, linestyle="--")
            ax.axhline(ALPHA, color="#c9d6e0", linewidth=0.8)
            ax.set_title(f"{task} · {OUTCOME_LABEL[outcome]}  (ICC {r['icc']:.3f})", fontsize=10)
            ax.grid(color="#eef2f5", linewidth=0.8)
            ax.set_axisbelow(True)
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
            if i == len(TASKS) - 1:
                ax.set_xlabel("true increase over the fault-free baseline (pp)")
            if j == 0:
                ax.set_ylabel("power")
    handles, labels = axes[0][0].get_legend_handles_labels()
    handles.append(Line2D([], [], color="#5a6675", linewidth=1.0, linestyle="--", alpha=0.6))
    labels.append("uncorrected CR1 test (anti-conservative)")
    fig.legend(handles, labels, frameon=False, fontsize=9, ncols=3,
               loc="lower center", bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Power of the study's clustered test with the small-cluster correction "
                 "(CR2, Bell–McCaffrey df)", fontsize=12, y=1.01)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--sims", type=int, default=SIMS)
    parser.add_argument("--figure", type=Path, default=None)
    args = parser.parse_args(argv)
    runs = [json.loads(p.read_text()) for p in sorted(args.results.glob("*.json"))]
    results = analyse(runs, sims=args.sims)
    status = report(results)
    if args.figure is not None:
        print(f"  figure: {figure(results, args.figure)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
