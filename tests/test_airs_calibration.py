"""RQ4's calibration must not flatter AIRS.

Three ways this analysis could quietly overstate the framework, each pinned:

1. Splitting held-out data by decision instead of by run. Every decision in a
   run carries the same AIRS vector, so a decision-level split puts the same
   predictor row on both sides and the held-out score approaches the training
   fit.
2. A hand-rolled DeLong that disagrees with a reference AUC — the comparison
   against agent confidence is the test of whether AIRS earns its keep, so its
   arithmetic has to be right.
3. Emitting a negative weight. In a readiness score a negative weight means
   "degrade this dimension to improve the score", which is not a calibration
   result, it is a broken one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from airsbench.analysis.airs_calibration import (
    DIMENSIONS,
    TRAINING_ARMS,
    auc,
    build_frame,
    delong_test,
    normalised_weights,
    run_level_ranking,
    split_by_run,
)

RESULTS_DIR = Path("results/runs")
DATA_DIR = Path("data/ecommerce")

needs_runs = pytest.mark.skipif(
    not list(RESULTS_DIR.glob("*.json")) or not (DATA_DIR / "updates.jsonl").exists(),
    reason="no completed runs",
)


# ---- DeLong ----------------------------------------------------------------

@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_delong_auc_matches_sklearn(seed):
    """The structural components must reproduce the reference AUC exactly."""
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, 2, 300)
    a = rng.normal(labels * 0.8, 1.0)
    b = rng.normal(labels * 0.3, 1.0)

    auc_a, auc_b, _ = delong_test(labels, a, b)
    assert auc_a == pytest.approx(auc(labels, a), abs=1e-9)
    assert auc_b == pytest.approx(auc(labels, b), abs=1e-9)


def test_delong_detects_a_real_difference():
    rng = np.random.default_rng(7)
    labels = rng.integers(0, 2, 2000)
    strong = rng.normal(labels * 1.5, 1.0)
    noise = rng.normal(0, 1.0, 2000)
    auc_a, auc_b, p = delong_test(labels, strong, noise)
    assert auc_a > 0.8 and 0.45 < auc_b < 0.55
    assert p < 0.001


def test_delong_finds_no_difference_between_two_equivalent_predictors():
    rng = np.random.default_rng(11)
    labels = rng.integers(0, 2, 2000)
    a = rng.normal(labels * 0.7, 1.0)
    b = rng.normal(labels * 0.7, 1.0)
    _, _, p = delong_test(labels, a, b)
    assert p > 0.05


def test_delong_handles_a_degenerate_label_vector():
    """All-one labels have no negatives; return NaN rather than dividing by 0."""
    auc_a, auc_b, p = delong_test(np.ones(50), np.arange(50.0), np.arange(50.0))
    assert auc_a != auc_a and auc_b != auc_b and p != p


def test_delong_is_symmetric_in_its_two_predictors():
    rng = np.random.default_rng(3)
    labels = rng.integers(0, 2, 500)
    a, b = rng.normal(labels, 1.0), rng.normal(labels * 0.4, 1.0)
    _, _, p_ab = delong_test(labels, a, b)
    _, _, p_ba = delong_test(labels, b, a)
    assert p_ab == pytest.approx(p_ba, rel=1e-9)


# ---- the split -------------------------------------------------------------

@needs_runs
def test_held_out_runs_share_no_run_with_training():
    """The leak this guards against: one run's decisions on both sides."""
    frame = build_frame(RESULTS_DIR, DATA_DIR)
    train, held = split_by_run(frame)
    assert not set(train["run_id"]) & set(held["run_id"])
    assert held["run_id"].nunique() > 0


@needs_runs
def test_the_split_is_deterministic():
    frame = build_frame(RESULTS_DIR, DATA_DIR)
    first = set(split_by_run(frame)[1]["run_id"])
    assert first == set(split_by_run(frame)[1]["run_id"])


@needs_runs
def test_the_split_holds_out_roughly_a_fifth_of_runs():
    frame = build_frame(RESULTS_DIR, DATA_DIR)
    train, held = split_by_run(frame)
    total = train["run_id"].nunique() + held["run_id"].nunique()
    assert 0.12 < held["run_id"].nunique() / total < 0.28


# ---- weights ---------------------------------------------------------------

class _FakeResult:
    def __init__(self, params):
        self.params = params


def test_a_non_protective_dimension_gets_zero_not_a_negative_weight():
    """A negative weight would mean 'degrade this to score better'."""
    weights = normalised_weights(_FakeResult(
        {"freshness": -0.01, "latency": +0.02, "consistency": -0.03, "semantic": -0.01}
    ))
    assert weights["latency"] == 0.0
    assert all(w >= 0 for w in weights.values())
    assert sum(weights.values()) == pytest.approx(1.0)


def test_weights_are_proportional_to_protective_magnitude():
    weights = normalised_weights(_FakeResult(
        {"freshness": -0.01, "latency": 0.0, "consistency": -0.03, "semantic": 0.0}
    ))
    assert weights["consistency"] == pytest.approx(0.75)
    assert weights["freshness"] == pytest.approx(0.25)


def test_an_all_harmful_fit_returns_zeros_rather_than_dividing_by_zero():
    weights = normalised_weights(_FakeResult({d: 0.01 for d in DIMENSIONS}))
    assert set(weights.values()) == {0.0}


# ---- the run-level test ----------------------------------------------------

def test_run_level_ranking_is_negative_when_a_higher_score_means_fewer_failures():
    """AIRS is oriented so high = healthy, so the correlation with a failure
    rate must come out NEGATIVE. A positive rho means the score is inverted."""
    import pandas as pd

    rows = []
    for i, (score, rate) in enumerate([(100, 0.05), (75, 0.15), (50, 0.30), (20, 0.60)]):
        for j in range(50):
            rows.append({
                "run_id": f"r{i}", "silent": int(j < rate * 50),
                "freshness": score, "latency": 100.0,
                "consistency": 100.0, "semantic": 100.0,
            })
    weights = {"freshness": 1.0, "latency": 0.0, "consistency": 0.0, "semantic": 0.0}
    rho, p, n = run_level_ranking(pd.DataFrame(rows), weights, "silent")
    assert n == 4
    assert rho < -0.9


def test_run_level_ranking_needs_variation_to_report_anything():
    import pandas as pd

    rows = [{"run_id": f"r{i}", "silent": 0, **{d: 100.0 for d in DIMENSIONS}}
            for i in range(5)]
    rho, _, _ = run_level_ranking(pd.DataFrame(rows), {d: 0.25 for d in DIMENSIONS},
                                  "silent")
    assert rho != rho


# ---- what enters the calibration -------------------------------------------

@needs_runs
def test_the_detectability_arm_is_excluded_from_training():
    """Its runs share an AIRS vector while differing in outcome — the treatment
    is delivered record age, which AIRS does not score."""
    frame = build_frame(RESULTS_DIR, DATA_DIR)
    assert "detectability" not in set(frame["arm"])
    assert set(frame["arm"]) <= {*TRAINING_ARMS, "cross_model"}


@needs_runs
def test_calibration_uses_corrected_airs_not_the_recorded_value():
    """16 early runs carry a double-counted freshness dimension on disk."""
    import json

    from airsbench.analysis.airs_correction import needs_correction

    frame = build_frame(RESULTS_DIR, DATA_DIR)
    for path in RESULTS_DIR.glob("*.json"):
        run = json.loads(path.read_text())
        if not needs_correction(run):
            continue
        rows = frame[frame["run_id"] == run["run_id"]]
        if rows.empty:
            continue
        assert rows["freshness"].iloc[0] != pytest.approx(
            run["airs"]["freshness"], abs=0.01
        ), "an uncorrected freshness value reached the calibration"
        break
