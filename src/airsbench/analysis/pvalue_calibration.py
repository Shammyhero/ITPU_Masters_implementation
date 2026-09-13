"""Are the decision-model p-values as small as they claim? Calibration by simulation.

`decision_models.py` reports odds ratios from logistic GLMs with cluster-robust
(CR1) errors grouped by run. The W2 power simulation found that kind of test
anti-conservative when a comparison rests on few clusters — 11–12% false
positives per cell instead of 5% (REVIEW F-C7). Each condition coefficient in
the decision models rests on only eight or sixteen runs against as many
baseline runs, even though a model as a whole has 72 or 144, so the same
problem may apply. It was never measured. This measures it.

For every condition coefficient in every published model:

  α at 0.05     how often the model's own test rejects that coefficient when its
                true value is zero. Studies are simulated from the fitted model
                with that one coefficient removed (a parametric bootstrap under
                the restricted null), keeping the real design — the same runs,
                run sizes, pipelines and tasks — and the observed run-level ICC.
  calibrated p  the share of those null studies with a p-value at least as
                small as the one observed: what the test would have reported had
                it held its nominal size.

The logistic models are not rebuilt; their coefficients and intervals stand.
Only the strength of the evidence is re-read. Task and pipeline terms are
nuisance covariates and are not calibrated.

Fitting tens of thousands of GLMs through statsmodels takes far too long, so
the fits run as a batched IRLS over run-level binomial counts with the same
sandwich and small-sample correction. `tests/test_pvalue_calibration.py` pins
it against statsmodels on decision-level data, and `report` refuses to print a
verdict unless it also reproduces statsmodels on the real data.

    python -m airsbench.analysis.pvalue_calibration
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Any

import numpy as np

from .decision_models import MODELS, build_frame, fit_logit, select
from .power import RunCount, _run_rates, icc_anova

ALPHA = 0.05
SIMS = 2000
SEED = 20260914
CONDITION = "C(condition)[T."
# A logit coefficient beyond this has run off towards infinity: the cell it
# identifies has no events (or no non-events) and no finite MLE exists.
SEPARATED = 15.0
REPRODUCTION_TOLERANCE = 1e-6


def run_design(frame, outcome: str, formula: str):
    """One row per run — covariates, decisions `n`, events `k` — and its design.

    Every decision in a run shares its covariates, so the run-level binomial
    likelihood has the decision-level MLE and Hessian, and each run's summed
    score is exactly the cluster score the sandwich needs.
    """
    import patsy

    runs = (
        frame.groupby("run_id", sort=True)
        .agg(condition=("condition", "first"), task=("task", "first"),
             pipeline=("pipeline", "first"), n=(outcome, "size"), k=(outcome, "sum"))
        .reset_index()
    )
    design = patsy.dmatrix(formula, runs, return_type="dataframe")
    return runs, design


def fit_batch(X, k, n, max_iter: int = 100, tol: float = 1e-10):
    """Logistic MLE and cluster-robust p-values for many outcomes on one design.

    `X` is (runs, K); `k` and `n` are (studies, runs). Mirrors statsmodels'
    `GLM(Binomial).fit(cov_type="cluster")` on the decision-level data, each run
    its own cluster, with the default correction G/(G−1)·(N−1)/(N−K) and N
    counted in decisions. Returns (beta, p), both (studies, K). A coefficient
    that did not converge or separated gets p = NaN — not evidence either way —
    so callers must decide what an inestimable study means, never a silent 0.
    """
    from scipy.special import expit
    from scipy.stats import norm

    X = np.asarray(X, dtype=float)
    k = np.atleast_2d(np.asarray(k, dtype=float))
    n = np.broadcast_to(np.asarray(n, dtype=float), k.shape)
    studies, (runs, K) = k.shape[0], X.shape
    ridge = 1e-10 * np.eye(K)

    def hessian(beta):
        mu = expit(beta @ X.T)
        return mu, np.swapaxes((n * mu * (1 - mu))[..., None] * X, 1, 2) @ X + ridge

    beta = np.zeros((studies, K))
    step = np.full((studies, K), np.inf)
    for _ in range(max_iter):
        mu, H = hessian(beta)
        step = np.linalg.solve(H, ((k - n * mu) @ X)[..., None])[..., 0]
        beta = beta + step
        if ((np.abs(step) < tol) | (np.abs(beta) > SEPARATED)).all():
            break

    mu, H = hessian(beta)
    bread = np.linalg.inv(H)
    scores = (k - n * mu)[..., None] * X
    meat = np.swapaxes(scores, 1, 2) @ scores
    N = n.sum(axis=1)
    correction = (runs / (runs - 1)) * ((N - 1) / (N - K))
    covariance = bread @ meat @ bread * correction[:, None, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        se = np.sqrt(np.diagonal(covariance, axis1=1, axis2=2))
        p = 2 * norm.sf(np.abs(beta / se))
    usable = (np.abs(step) < 1e-6) & (np.abs(beta) < SEPARATED) & np.isfinite(p)
    return beta, np.where(usable, p, np.nan)


def calibrated_pvalue(observed: float, null: np.ndarray) -> float:
    """(1 + #{null p ≤ observed}) / (1 + #estimable null studies).

    The observed study counts as one of its own null draws, so the result is
    never exactly zero; its floor is 1 / (1 + sims).
    """
    null = np.asarray(null, dtype=float)
    null = null[np.isfinite(null)]
    return float((1 + np.count_nonzero(null <= observed)) / (1 + null.size))


def calibrate(frame, sims: int = SIMS, seed: int = SEED) -> list[dict[str, Any]]:
    from scipy.special import expit

    rng = np.random.default_rng(seed)
    results = []
    for key, outcome, formula, population in MODELS:
        data = select(frame, population)
        runs, design = run_design(data, outcome, formula)
        X = design.to_numpy()
        k = runs["k"].to_numpy(dtype=float)
        n = runs["n"].to_numpy(dtype=float)

        reference = fit_logit(data, outcome, formula)
        _, p_batched = fit_batch(X, k, n)
        discrepancy = max(abs(float(p_batched[0, j]) - float(reference.pvalues[name]))
                          for j, name in enumerate(design.columns))

        icc = icc_anova([
            RunCount((row.task, row.pipeline, row.condition), int(row.n), int(row.k))
            for row in runs.itertuples()
        ])
        icc = 0.0 if math.isnan(icc) else icc

        terms = []
        for j, name in enumerate(design.columns):
            if not name.startswith(CONDITION):
                continue
            restricted = np.delete(X, j, axis=1)
            beta0, _ = fit_batch(restricted, k, n)
            rates = _run_rates(rng, expit(restricted @ beta0[0]), icc, (sims, len(n)))
            k_null = rng.binomial(n.astype(int), rates)
            _, p_null = fit_batch(X, k_null, n)
            null = p_null[:, j]
            estimable = np.isfinite(null)
            observed = float(reference.pvalues[name])
            terms.append({
                "term": name[len(CONDITION):-1],
                "odds_ratio": float(np.exp(reference.params[name])),
                "p": observed,
                "alpha": float((null[estimable] < ALPHA).mean()) if estimable.any()
                         else float("nan"),
                "calibrated_p": calibrated_pvalue(observed, null),
                "estimable": float(estimable.mean()),
            })
        results.append({
            "model": key, "outcome": outcome, "population": population,
            "decisions": int(n.sum()), "runs": len(n), "icc": icc, "sims": sims,
            "discrepancy": discrepancy, "terms": terms,
        })
    return results


def verdict(p: float, calibrated: float) -> str:
    if p < ALPHA and calibrated < ALPHA:
        return "survives"
    if p < ALPHA:
        return "DOES NOT SURVIVE"
    if calibrated < ALPHA:
        return "significant only after calibration"
    return ""


def report(results: list[dict[str, Any]]) -> int:
    print("Calibrated p-values for the decision models — REVIEW F-C7\n")
    print("p (CR1)     = the published cluster-robust logistic p-value")
    print("α at .05    = how often that test rejects this coefficient when it is truly")
    print("              zero: studies simulated from the fitted model with the")
    print("              coefficient removed, on the real runs, run sizes and ICC")
    print("calibrated  = share of those null studies with a p-value at least as small")
    print("estimable   = share of null studies where the coefficient had a finite MLE\n")
    status = 0
    for model in results:
        print(f"  {model['model']} — {model['outcome']} on {model['population']}: "
              f"{model['decisions']:,} decisions, {model['runs']} runs, "
              f"ICC {model['icc']:.3f}, {model['sims']} null studies per term")
        print(f"    batched fit vs statsmodels on the real data: max |Δp| = "
              f"{model['discrepancy']:.1e}")
        if model["discrepancy"] > REPRODUCTION_TOLERANCE:
            print("    ✗ the batched fit does not reproduce statsmodels — no verdict given\n")
            status = 1
            continue
        floor = 1 / (1 + model["sims"])
        print(f"    {'term':<28}{'OR':>7}{'p (CR1)':>10}{'α at .05':>10}"
              f"{'calibrated':>12}{'estimable':>11}   verdict")
        for t in model["terms"]:
            calibrated = (f"≤{floor:.4f}" if t["calibrated_p"] <= floor + 1e-12
                          else f"{t['calibrated_p']:.4f}")
            print(f"    {t['term']:<28}{t['odds_ratio']:>7.2f}{t['p']:>10.4f}"
                  f"{t['alpha']:>10.3f}{calibrated:>12}{t['estimable']:>11.0%}   "
                  f"{verdict(t['p'], t['calibrated_p'])}")
        print()
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    parser.add_argument("--sims", type=int, default=SIMS)
    args = parser.parse_args(argv)
    return report(calibrate(build_frame(args.results, args.data_dir), sims=args.sims))


if __name__ == "__main__":
    raise SystemExit(main())
