"""Tests for the decision-model p-value calibration (REVIEW F-C7).

The calibration fits tens of thousands of logistic GLMs with a batched IRLS
instead of statsmodels. It is only a calibration of THE PUBLISHED tests if that
fit reproduces statsmodels' cluster-robust GLM — coefficients and p-values —
on decision-level data. `test_batched_fit_matches_statsmodels_on_decision_level_data`
pins it; `calibrate` re-checks it on the real data every time it runs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from airsbench.analysis.pvalue_calibration import (
    calibrate,
    calibrated_pvalue,
    fit_batch,
    run_design,
)

RESULTS_DIR = Path("results/runs")
DATA_DIR = Path("data/ecommerce")

needs_runs = pytest.mark.skipif(
    not list(RESULTS_DIR.glob("*.json")) or not (DATA_DIR / "updates.jsonl").exists(),
    reason="no completed runs",
)


def _frame(rng, rates: dict[str, float], reps: int = 3):
    import pandas as pd

    rows, run = [], 0
    for condition, p in rates.items():
        for pipeline, shift in (("batch", 0.0), ("streaming", 0.03)):
            for _ in range(reps):
                run += 1
                n = int(rng.integers(70, 81))
                k = int(rng.binomial(n, min(p + shift, 1.0))) if p > 0 else 0
                rows += [{"run_id": f"r{run:03d}", "condition": condition,
                          "task": "retrieval", "pipeline": pipeline,
                          "silent": int(i < k)} for i in range(n)]
    return pd.DataFrame(rows)


def test_batched_fit_matches_statsmodels_on_decision_level_data():
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    frame = _frame(np.random.default_rng(7),
                   {"baseline": 0.12, "drift_mild": 0.18, "drift_severe": 0.30})
    formula = "C(condition) + C(pipeline)"
    reference = smf.glm(f"silent ~ {formula}", data=frame,
                        family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": frame["run_id"]})

    runs, design = run_design(frame, "silent", formula)
    beta, p = fit_batch(design.to_numpy(), runs["k"].to_numpy(), runs["n"].to_numpy())
    for j, name in enumerate(design.columns):
        assert beta[0, j] == pytest.approx(float(reference.params[name]), rel=1e-6, abs=1e-9)
        assert p[0, j] == pytest.approx(float(reference.pvalues[name]), rel=1e-5)


def test_a_separated_coefficient_is_inestimable_not_evidence():
    """A condition with no events has no finite MLE. Its p must be NaN, never a
    spurious 0 — and the coefficients that ARE estimable must still be reported."""
    frame = _frame(np.random.default_rng(8),
                   {"baseline": 0.15, "empty": 0.0, "drift_severe": 0.30})
    runs, design = run_design(frame, "silent", "C(condition) + C(pipeline)")
    _, p = fit_batch(design.to_numpy(), runs["k"].to_numpy(), runs["n"].to_numpy())
    by_name = dict(zip(design.columns, p[0]))
    assert np.isnan(by_name["C(condition)[T.empty]"])
    assert np.isfinite(by_name["C(condition)[T.drift_severe]"])


def test_calibrated_pvalue_counts_the_observed_study_and_skips_inestimable_ones():
    null = np.array([0.001, 0.01, 0.2, np.nan, 0.9])
    assert calibrated_pvalue(0.01, null) == pytest.approx((1 + 2) / (1 + 4))
    assert calibrated_pvalue(0.0, null) == pytest.approx(1 / 5)


@needs_runs
def test_every_published_model_is_calibrated_against_its_own_fit():
    from airsbench.analysis.decision_models import MODELS, build_frame

    results = calibrate(build_frame(RESULTS_DIR, DATA_DIR), sims=20, seed=1)
    assert [r["model"] for r in results] == [key for key, *_ in MODELS]
    for model in results:
        assert model["discrepancy"] < 1e-6, model["model"]
        assert len(model["terms"]) == 8, "one term per fault x severity condition"
