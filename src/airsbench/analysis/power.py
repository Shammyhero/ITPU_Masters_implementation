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
checked rather than assumed.

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

    Arrays are (studies, runs). This is the model every analysis in the study
    fits, including statsmodels' default small-sample correction
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


def _run_rates(rng: np.random.Generator, p: float, icc: float, shape) -> np.ndarray:
    """Per-run success probabilities with the given mean and ICC (beta-binomial)."""
    if icc <= 1e-9:
        return np.full(shape, p)
    a = p * (1 - icc) / icc
    b = (1 - p) * (1 - icc) / icc
    return rng.beta(a, b, size=shape)


def simulate_power(p0: float, icc: float, m: int, runs_treat: int, runs_control: int,
                   deltas=DELTAS, sims: int = SIMS, seed: int = SEED) -> dict[float, float]:
    rng = np.random.default_rng(seed)
    curve = {}
    for delta in deltas:
        p1 = min(p0 + delta, 0.999)
        kt = rng.binomial(m, _run_rates(rng, p1, icc, (sims, runs_treat)))
        kc = rng.binomial(m, _run_rates(rng, p0, icc, (sims, runs_control)))
        curve[delta] = float((cluster_pvalues(kt, m, kc, m) < ALPHA).mean())
    return curve


def mde_from_curve(curve: dict[float, float], target: float = TARGET_POWER) -> float | None:
    for delta in sorted(curve):
        if delta > 0 and curve[delta] >= target:
            return delta
    return None


def observed_cells(counts: list[RunCount]) -> list[dict[str, Any]]:
    """Each streaming fault x severity cell against the streaming baseline, as the
    study's own clustered test sees it."""
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
                     "p": float(cluster_pvalues(kt, nt, kc, nc)[0])})
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
                curve = simulate_power(p0, icc, m, runs_treat, runs_control,
                                       sims=sims, seed=seed + 97 * offset)
                designs[name] = {
                    "runs": (runs_treat, runs_control),
                    "naive": closed_form_mde(p0, runs_treat * m, runs_control * m),
                    "adjusted": closed_form_mde(p0, runs_treat * m / de, runs_control * m / de),
                    "curve": curve, "mde": mde_from_curve(curve), "alpha": curve[0.0],
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
    print("simulated = the study's own design and test (cluster-robust logistic GLM),")
    print("            smallest effect on a 2 pp grid reaching 80% power")
    print("α emp.    = how often that test rejects when there is no effect\n")
    for (task, outcome), r in results.items():
        lo, hi = r["icc_ci"]
        print(f"  {task} · {OUTCOME_LABEL[outcome]}   baseline {r['p0']:.1%}   "
              f"{r['m']} decisions/run   ICC {r['icc']:.3f} [{lo:.3f}, {hi:.3f}]   "
              f"design effect {r['design_effect']:.2f}")
        print(f"    {'design':<22}{'naive':>10}{'clustered':>12}{'simulated':>12}{'α emp.':>9}")
        for name, d in r["designs"].items():
            label = f"{name} ({d['runs'][0]} v {d['runs'][1]} runs)"
            print(f"    {label:<22}{_pp(d['naive']):>10}{_pp(d['adjusted']):>12}"
                  f"{_pp(d['mde']):>12}{d['alpha']:>9.3f}")
        cell_mde = r["designs"]["cell"]["mde"]
        print("    observed streaming cells against the streaming baseline:")
        for row in r["cells"]:
            _, fault, severity = row["condition"]
            size = abs(row["effect"])
            verdict = ("above the simulated MDE" if cell_mde is not None and size >= cell_mde
                       else "below the simulated MDE")
            print(f"      {fault + '/' + severity:<30}{100 * row['effect']:>+7.1f} pp   "
                  f"p {row['p']:.3f}   {verdict}")
        print()
    return 0


def figure(results: dict, out_path: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

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
                ys = [d["curve"][x] for x in sorted(d["curve"])]
                ax.plot(xs, ys, marker="o", markersize=3.5, linewidth=1.6, color=colours[name],
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
    fig.legend(handles, labels, frameon=False, fontsize=9, ncols=2,
               loc="lower center", bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Power of the study's clustered test, simulated from the observed ICC",
                 fontsize=12, y=1.01)
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
