"""Tests for the clustered power analysis.

`test_closed_form_matches_statsmodels_at_decision_level` and
`test_cr2_closed_form_matches_the_matrix_definition` are the load-bearing ones.
The simulation fits tens of thousands of studies using closed forms instead of
fitting models. That is only a simulation of THE STUDY'S tests if the closed
forms reproduce the real estimators — statsmodels' cluster-robust logistic fit
for the uncorrected test, and CR2 with Bell–McCaffrey degrees of freedom, built
from their matrix definitions, for the corrected one — with unequal run sizes.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from airsbench.analysis.power import (
    RunCount,
    _run_rates,
    bell_mccaffrey_df,
    closed_form_mde,
    cluster_pvalues,
    cr2_pvalues,
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


def _cr2_reference(kt, nt, kc, nc):
    """CR2 and Bell–McCaffrey df from their matrix definitions, at decision level.

    Slow and obviously correct: the linear probability model `y ~ treat`,
    adjustment A_g = (I − H_gg)^(−1/2) per run, and Satterthwaite's df over the
    eigenvalues of PᵀP with P_g = (I − H)_{·g} A_g X_g (XᵀX)⁻¹ c.
    """
    y, treat, cluster = [], [], []
    for offset, (ks, ns, flag) in enumerate(((kt, nt, 1), (kc, nc, 0))):
        for g, (k, n) in enumerate(zip(ks, ns)):
            y += [1.0] * int(k) + [0.0] * int(n - k)
            treat += [flag] * int(n)
            cluster += [f"{offset}-{g}"] * int(n)
    y, cluster = np.array(y), np.array(cluster)
    X = np.column_stack([np.ones(len(y)), treat])
    bread = np.linalg.inv(X.T @ X)
    residual_maker = np.eye(len(y)) - X @ bread @ X.T
    residuals = residual_maker @ y
    contrast = np.array([0.0, 1.0])
    variance, columns = 0.0, []
    for g in np.unique(cluster):
        idx = cluster == g
        values, vectors = np.linalg.eigh(residual_maker[np.ix_(idx, idx)])
        adjust = vectors @ np.diag(values ** -0.5) @ vectors.T
        weights = contrast @ bread @ X[idx].T @ adjust
        variance += float(weights @ residuals[idx]) ** 2
        columns.append(residual_maker[:, idx] @ adjust @ X[idx] @ bread @ contrast)
    P = np.column_stack(columns)
    eigenvalues = np.linalg.eigvalsh(P.T @ P)
    df = eigenvalues.sum() ** 2 / (eigenvalues ** 2).sum()
    coefficient = (bread @ X.T @ y)[1]
    return coefficient, variance, df


@pytest.mark.parametrize("runs_treat,runs_control", [(4, 4), (5, 3)])
def test_cr2_closed_form_matches_the_matrix_definition(runs_treat, runs_control):
    rng = np.random.default_rng(5 + runs_treat)
    nt, nc = rng.integers(70, 81, runs_treat), rng.integers(70, 81, runs_control)
    kt, kc = rng.binomial(nt, 0.18), rng.binomial(nc, 0.11)

    coefficient, variance, df = _cr2_reference(kt, nt, kc, nc)
    expected = 2 * stats.t.sf(abs(coefficient) / np.sqrt(variance), df)

    assert bell_mccaffrey_df(nt[None], nc[None])[0] == pytest.approx(df, rel=1e-9)
    assert cr2_pvalues(kt[None], nt[None], kc[None], nc[None])[0] == pytest.approx(
        expected, rel=1e-9)


def test_bell_mccaffrey_df_depends_on_the_design_not_the_outcomes():
    """Equal run sizes reduce it to Welch–Satterthwaite on 1/N per group."""
    assert bell_mccaffrey_df(np.full((1, 4), 80), np.full((1, 4), 80))[0] == pytest.approx(6.0)
    assert bell_mccaffrey_df(np.full((1, 16), 80), np.full((1, 8), 80))[0] == pytest.approx(
        14.10, abs=0.01)


def test_the_corrected_test_holds_nominal_size_where_the_study_test_did_not():
    """REVIEW F-C7: with eight clusters the cluster-robust logistic test rejected a
    true null ~12% of the time. The correction must bring that to ≤ 5% plus
    simulation noise, on the same simulated studies."""
    design = dict(p0=0.105, icc=0.0, m=80, runs_treat=4, runs_control=4,
                  deltas=(0.0,), sims=2000, seed=11)
    corrected = simulate_power(**design)[0.0]
    uncorrected = simulate_power(**design, test=cluster_pvalues)[0.0]
    assert corrected <= 0.065
    assert uncorrected >= 0.09


def test_no_within_group_variation_is_not_evidence():
    """Identical runs give a zero variance; that must read p = 1, not p = 0."""
    runs = np.full((1, 4), 80)
    assert cr2_pvalues(np.full((1, 4), 8), runs, np.full((1, 4), 8), runs)[0] == 1.0
    assert cr2_pvalues(np.full((1, 4), 16), runs, np.full((1, 4), 8), runs)[0] == 1.0


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
