"""RQ1's machinery must be able to return "not monotone".

The sweep exists because two severities always look monotonic and Shisher & Sun
(MobiHoc 2022) prove prediction error need not be monotone in age. A test suite
that only checked the monotone case would let a non-monotone response be
reported as monotone, which is the one error this arm is built to prevent — so
each statistic here is checked against data that should fail it.
"""

from __future__ import annotations

import pytest

from airsbench.analysis.freshness_sweep import (
    CEILING,
    MIN_CONDITIONAL_N,
    THRESHOLD_BAND,
    Level,
    changepoint,
    first_crossing,
    isotonic_cost,
    spearman,
)
from airsbench.pipelines.loader import DEP_DELAY_KNOWLEDGE_HORIZON_S


def _level(staleness, value=0.0):
    return Level(
        staleness_s=staleness, n_runs=3, n_decisions=60, accuracy=value,
        abstained=0.0, silent=value, run_accuracy=[], run_flip_silent=[],
    )


# ---- monotonicity ----------------------------------------------------------

def test_isotonic_costs_nothing_on_monotone_data():
    xs = [0.5, 0.5, 1.5, 1.5, 3.0, 3.0, 5.0, 5.0]
    ys = [0.10, 0.12, 0.20, 0.22, 0.35, 0.33, 0.50, 0.52]
    iso, free = isotonic_cost(xs, ys, increasing=True)
    assert iso == pytest.approx(free, rel=0.05), "monotone data should fit freely"


def test_isotonic_costs_real_error_on_a_non_monotone_response():
    """The case the sweep exists to detect: a dip in the middle."""
    xs = [0.5, 0.5, 1.5, 1.5, 3.0, 3.0, 5.0, 5.0]
    ys = [0.10, 0.12, 0.60, 0.62, 0.20, 0.22, 0.50, 0.52]
    iso, free = isotonic_cost(xs, ys, increasing=True)
    assert iso > free * 2, "a non-monotone response must cost the constraint"


def test_isotonic_direction_matters():
    """A decreasing series must not be scored as a good increasing fit."""
    xs = [1.0, 1.0, 2.0, 2.0, 3.0, 3.0]
    ys = [0.9, 0.88, 0.5, 0.52, 0.1, 0.12]
    iso_up, free = isotonic_cost(xs, ys, increasing=True)
    iso_down, _ = isotonic_cost(xs, ys, increasing=False)
    assert iso_down == pytest.approx(free, rel=0.05)
    assert iso_up > iso_down


def test_spearman_detects_rank_order_and_its_absence():
    rho, _ = spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
    assert rho == pytest.approx(1.0)
    rho, _ = spearman([1, 2, 3, 4, 5], [50, 40, 30, 20, 10])
    assert rho == pytest.approx(-1.0)


def test_spearman_returns_nan_rather_than_a_number_on_too_few_points():
    rho, p = spearman([1.0, 2.0], [1.0, 2.0])
    assert rho != rho and p != p


# ---- changepoint -----------------------------------------------------------

def test_changepoint_finds_an_obvious_step():
    split, explained = changepoint([0.1, 0.1, 0.1, 0.9, 0.9, 0.9])
    assert split == 3
    assert explained > 0.95


def test_changepoint_explains_little_on_a_flat_series():
    _, explained = changepoint([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
    assert explained == pytest.approx(0.0, abs=1e-9)


def test_changepoint_needs_enough_points():
    split, _ = changepoint([0.1, 0.9, 0.9])
    assert split is None


def test_changepoint_locates_a_late_step():
    split, _ = changepoint([0.1, 0.1, 0.1, 0.1, 0.1, 0.8])
    assert split == 5


# ---- threshold -------------------------------------------------------------

def test_first_crossing_of_a_rising_outcome():
    levels = [_level(s) for s in (0.5, 1.5, 3.0, 5.0)]
    values = [0.10, 0.14, 0.25, 0.60]
    assert first_crossing(levels, values, rising=True) == 3.0


def test_first_crossing_of_a_falling_outcome():
    levels = [_level(s) for s in (0.5, 1.5, 3.0, 5.0)]
    values = [0.90, 0.86, 0.78, 0.50]
    assert first_crossing(levels, values, rising=False) == 3.0


def test_no_crossing_returns_none_rather_than_the_last_level():
    levels = [_level(s) for s in (0.5, 1.5, 3.0, 5.0)]
    values = [0.10, 0.11, 0.13, 0.15]
    assert first_crossing(levels, values, rising=True) is None


def test_crossing_is_measured_against_the_least_stale_level():
    levels = [_level(s) for s in (0.5, 1.5, 3.0)]
    exactly_at_band = [0.10, 0.10 + THRESHOLD_BAND, 0.30]
    assert first_crossing(levels, exactly_at_band, rising=True) == 1.5


# ---- the classification horizon --------------------------------------------

def test_levels_past_the_horizon_are_flagged_as_saturated():
    """Past the horizon the delay feature is zero for every flight, so the arm
    measures an absent feature rather than a stale one."""
    assert not _level(DEP_DELAY_KNOWLEDGE_HORIZON_S - 2).saturated_classification
    assert _level(DEP_DELAY_KNOWLEDGE_HORIZON_S).saturated_classification
    assert _level(DEP_DELAY_KNOWLEDGE_HORIZON_S + 2).saturated_classification


def test_the_sweep_actually_reaches_the_horizon():
    """If this fails the sweep no longer probes saturation and the exclusion
    logic above is dead code."""
    from airsbench.runner.config import FRESHNESS_SWEEP_SECONDS, RunConfig
    from airsbench.runner.execute import value_staleness_s

    stalenesses = [
        value_staleness_s(RunConfig(
            pipeline="streaming", task="classification", fault_type="freshness",
            severity=f"sweep_{d:g}s", replication=1,
            injector_params={"delay_seconds": d}, seed=1,
        ))
        for d in FRESHNESS_SWEEP_SECONDS
    ]
    assert any(s >= DEP_DELAY_KNOWLEDGE_HORIZON_S for s in stalenesses)
    assert any(s < DEP_DELAY_KNOWLEDGE_HORIZON_S for s in stalenesses)


# ---- the small-n guard -----------------------------------------------------
#
# The conditional rate's denominator is the flip count, which is small at low
# staleness by construction. Reporting a monotonicity verdict off it would be
# the easiest wrong answer this arm could produce, so the guard is pinned.

def test_the_guard_threshold_is_above_the_smallest_real_denominator():
    """The observed sweep has n=4 at its mildest level; the guard must catch it."""
    assert MIN_CONDITIONAL_N > 4


def test_ceiling_is_below_every_observed_conditional_rate():
    """Observed conditional rates run 85-100%; the ceiling test must fire."""
    assert CEILING <= 0.85


def test_a_tiny_denominator_produces_an_interval_that_spans_most_of_the_range():
    """Why the guard exists: 100% of 4 is not evidence of a high rate."""
    from airsbench.analysis.phase1_check import wilson_halfwidth

    assert wilson_halfwidth(1.0, 4) > 0.4
    assert wilson_halfwidth(1.0, 100) < 0.1


def test_spearman_can_be_significant_on_noise_at_small_n():
    """The failure mode the guard prevents, reproduced.

    A flat-at-ceiling series read through unstable small-n estimates can yield
    a significant rank correlation in the WRONG direction. The statistic is not
    at fault; using it on this series would be.
    """
    staleness = [0.55, 0.55, 0.55, 1.55, 1.55, 1.55, 3.05, 3.05, 3.05]
    at_ceiling_with_noise = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 0.85, 0.88]
    rho, p = spearman(staleness, at_ceiling_with_noise)
    assert rho < 0, "declining, though the underlying rate is flat at ceiling"
    assert p < 0.05, "and significantly so — hence the guard, not the p-value"
