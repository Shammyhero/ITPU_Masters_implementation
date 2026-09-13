"""Tests for the clustered power analysis.

`test_closed_form_matches_statsmodels_at_decision_level` is the load-bearing
one. The simulation fits tens of thousands of studies using a closed-form
logistic MLE and sandwich instead of calling statsmodels. That is only a
simulation of THE STUDY'S test if the closed form reproduces what statsmodels
returns for `y ~ treat`, cluster-robust by run, on decision-level data — with
unequal run sizes, and the default small-sample correction.
"""

from __future__ import annotations

import numpy as np
import pytest

from airsbench.analysis.power import (
    RunCount,
    _run_rates,
    closed_form_mde,
    cluster_pvalues,
    design_effect,
    icc_anova,
    mde_from_curve,
    observed_cells,
    simulate_power,
)


def _clustered_counts(icc, rng, conditions=(0.15, 0.25, 0.40), runs=60, m=80):
    out = []
    for c, p in enumerate(conditions):
        rates = _run_rates(rng, p, icc, runs)
        for k in rng.binomial(m, rates):
            out.append(RunCount(("streaming", f"f{c}", "severe"), m, int(k)))
    return out


def test_icc_recovers_a_planted_value():
    estimate = icc_anova(_clustered_counts(0.05, np.random.default_rng(1)))
    assert 0.03 <= estimate <= 0.07


def test_icc_is_near_zero_without_clustering():
    assert icc_anova(_clustered_counts(0.0, np.random.default_rng(2))) < 0.01


def test_closed_form_matches_statsmodels_at_decision_level():
    import pandas as pd
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    rng = np.random.default_rng(3)
    nt, nc = np.array([78, 80, 79, 80]), np.array([80, 77, 80, 79])
    kt, kc = rng.binomial(nt, 0.30), rng.binomial(nc, 0.20)

    rows = []
    for treat, ks, ns in ((1, kt, nt), (0, kc, nc)):
        for r, (k, n) in enumerate(zip(ks, ns)):
            zeros = [(treat, f"{treat}-{r}", 0)] * int(n - k)
            rows += [(treat, f"{treat}-{r}", 1)] * int(k) + zeros
    frame = pd.DataFrame(rows, columns=["treat", "run", "y"])
    fitted = smf.glm("y ~ treat", data=frame, family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": frame["run"]})

    closed = cluster_pvalues(kt[None], nt[None], kc[None], nc[None])[0]
    assert closed == pytest.approx(float(fitted.pvalues["treat"]), rel=1e-6)


def test_power_is_low_without_an_effect_and_near_one_with_a_large_one():
    curve = simulate_power(0.2, 0.01, 80, 16, 8, deltas=(0.0, 0.25), sims=400, seed=1)
    assert curve[0.0] < 0.2
    assert curve[0.25] > 0.95


def test_mde_is_the_smallest_positive_effect_reaching_target():
    assert mde_from_curve({0.0: 0.05, 0.02: 0.30, 0.04: 0.81, 0.06: 0.95}) == 0.04
    assert mde_from_curve({0.0: 0.05, 0.02: 0.50}) is None


def test_naive_closed_form_reproduces_the_rqs_v2_claim():
    """§6: 'roughly 8–10 percentage points' at 320 decisions per condition."""
    assert 0.08 <= closed_form_mde(0.2, 320, 320) <= 0.10


def test_design_effect():
    assert design_effect(80, 0.0) == 1.0
    assert design_effect(80, 0.1) == pytest.approx(8.9)


def test_observed_cells_compare_against_the_streaming_baseline_only():
    counts = [RunCount(("streaming", "none", "none"), 100, 10) for _ in range(4)]
    counts += [RunCount(("batch", "none", "none"), 100, 90) for _ in range(4)]
    counts += [RunCount(("streaming", "freshness", "severe"), 100, 30) for _ in range(4)]
    (cell,) = observed_cells(counts)
    assert cell["condition"] == ("streaming", "freshness", "severe")
    assert cell["effect"] == pytest.approx(0.20)
