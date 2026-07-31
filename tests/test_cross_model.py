"""RQ5 claims the fault RANKING transfers across models — not the thresholds.

The claim is only meaningful if the comparison is like-for-like, each model is
measured against its own ceiling, and a floored arm is refused rather than
ranked. A rank correlation computed from an arm sitting at chance is worse than
no answer, because it looks like one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from airsbench.analysis.cross_model import (
    DAMAGING_OR,
    FAULTS,
    baseline_health,
    build_frame,
    damaging_set,
    kendall,
    min_achievable_p,
    rank,
)
from airsbench.analysis.phase1_check import CHANCE

RESULTS_DIR = Path("results/runs")
DATA_DIR = Path("data/ecommerce")

needs_runs = pytest.mark.skipif(
    not list(RESULTS_DIR.glob("*.json")) or not (DATA_DIR / "updates.jsonl").exists(),
    reason="no completed runs",
)


# ---- ranking ---------------------------------------------------------------

def test_rank_puts_the_most_damaging_fault_first():
    ranking = rank({"freshness": 1.0, "latency": 1.0,
                    "schema_drift": 3.4, "semantic_stripping": 2.7})
    assert ranking["schema_drift"] == 1
    assert ranking["semantic_stripping"] == 2


def test_rank_covers_every_fault_it_is_given():
    effects = {f: i + 1.0 for i, f in enumerate(FAULTS)}
    ranking = rank(effects)
    assert sorted(ranking.values()) == [1, 2, 3, 4]


# ---- rank agreement --------------------------------------------------------

def test_identical_rankings_agree_perfectly():
    a = {"freshness": 4, "latency": 3, "schema_drift": 1, "semantic_stripping": 2}
    tau, _ = kendall(a, dict(a))
    assert tau == pytest.approx(1.0)


def test_a_reversed_ranking_is_detected_as_inversion():
    a = {"freshness": 1, "latency": 2, "schema_drift": 3, "semantic_stripping": 4}
    b = {"freshness": 4, "latency": 3, "schema_drift": 2, "semantic_stripping": 1}
    tau, _ = kendall(a, b)
    assert tau == pytest.approx(-1.0)


def test_a_partial_rearrangement_lands_between():
    a = {"freshness": 1, "latency": 2, "schema_drift": 3, "semantic_stripping": 4}
    b = {"freshness": 1, "latency": 3, "schema_drift": 2, "semantic_stripping": 4}
    tau, _ = kendall(a, b)
    assert -1.0 < tau < 1.0


def test_too_few_shared_faults_returns_nan_not_a_number():
    tau, p = kendall({"freshness": 1, "latency": 2}, {"freshness": 2, "latency": 1})
    assert tau != tau and p != p


# ---- floor detection -------------------------------------------------------

@needs_runs
def test_a_healthy_baseline_is_not_flagged_as_floored():
    frame = build_frame(RESULTS_DIR, DATA_DIR)
    for task, health in baseline_health(frame, "gpt-4o-mini").items():
        assert not health["floored"], f"{task} baseline unexpectedly at chance"
        assert health["accuracy"] > CHANCE[task]


def test_a_chance_level_arm_is_flagged_as_floored():
    """Constructed: a model answering at chance has no headroom to degrade."""
    import pandas as pd

    rows = [
        {"model": "weak", "task": "classification", "fault": "none",
         "correct": i % 2, "abstained": 0, "silent": 1 - (i % 2),
         "parse_failed": 0, "flipped": False, "run_id": "r", "condition": "baseline"}
        for i in range(100)
    ]
    health = baseline_health(pd.DataFrame(rows), "weak")["classification"]
    assert health["accuracy"] == pytest.approx(0.5)
    assert health["floored"]


# ---- comparability ---------------------------------------------------------

@needs_runs
def test_the_frame_is_restricted_to_the_comparable_slice():
    """The cross-model subset is streaming-only and severe-only; the primary
    model must be cut to the same slice or the comparison is not like-for-like."""
    frame = build_frame(RESULTS_DIR, DATA_DIR)
    assert set(frame["fault"]) <= {"none", *FAULTS}
    runs = frame.groupby("run_id").first()
    assert not runs.empty


@needs_runs
def test_batch_and_mild_conditions_are_excluded():
    import json

    from airsbench.runner.config import run_arm

    frame = build_frame(RESULTS_DIR, DATA_DIR)
    kept = set(frame["run_id"])
    for path in RESULTS_DIR.glob("*.json"):
        run = json.loads(path.read_text())
        cfg = run["config"]
        if run["run_id"] not in kept:
            continue
        assert run_arm(run) in ("main", "cross_model")
        assert cfg["pipeline"] == "streaming"
        assert cfg["severity"] in ("severe", "none")


@needs_runs
def test_retrieval_effects_exclude_mechanically_unanswerable_decisions():
    """Otherwise freshness is credited with answer-key movement, and the
    cross-model ranking inherits the same error the flip partition removed."""
    from airsbench.analysis.cross_model import fault_effects

    frame = build_frame(RESULTS_DIR, DATA_DIR)
    effects = fault_effects(frame, "gpt-4o-mini", "retrieval")
    if effects:
        assert effects["freshness"] == pytest.approx(1.0, abs=0.4)
        assert effects["latency"] == pytest.approx(1.0, abs=0.2)


# ---- the p-value floor -----------------------------------------------------
#
# With 4 faults even perfect agreement gives p = 0.083. Reporting the p-values
# without saying so invites "not significant, so it does not generalise" from a
# number that could not have been significant.

def test_four_faults_cannot_reach_significance():
    assert min_achievable_p(len(FAULTS)) == pytest.approx(0.0833, abs=1e-3)
    assert min_achievable_p(len(FAULTS)) > 0.05


def test_more_ranked_items_would_allow_significance():
    assert min_achievable_p(6) < 0.05


def test_too_few_items_returns_nan():
    assert min_achievable_p(2) != min_achievable_p(2)


# ---- partition stability ---------------------------------------------------

def test_the_damaging_partition_ignores_order_within_each_group():
    """The coarse claim must survive the top two swapping places."""
    a = damaging_set({"freshness": 0.9, "latency": 1.0,
                      "schema_drift": 3.8, "semantic_stripping": 2.9})
    b = damaging_set({"freshness": 1.3, "latency": 1.4,
                      "schema_drift": 2.5, "semantic_stripping": 3.7})
    assert a == b == {"schema_drift", "semantic_stripping"}


def test_the_partition_threshold_sits_in_the_observed_gap():
    """Observed ORs cluster at 0.9-1.4 and 2.1-3.8, so the cut is not delicate."""
    assert 1.4 < DAMAGING_OR < 2.1


def test_a_fault_below_threshold_is_excluded():
    assert damaging_set({"freshness": 1.49, "schema_drift": 1.51}) == {"schema_drift"}


# ---- incomparable pairs must not poison the verdict ------------------------
#
# A pair with fewer than 3 shared faults yields NaN. Averaging that NaN in
# turns "not enough data" into a confident "does not generalise" — which is
# exactly what happened when the Haiku arm stopped part-way through
# classification and left one shared fault.

def test_a_nan_pair_would_poison_a_naive_mean():
    """The failure this guard exists to prevent, reproduced."""
    import math

    taus = [1.0, 0.667, 0.667, float("nan")]
    assert math.isnan(sum(taus) / len(taus))

    comparable = [t for t in taus if t == t]
    assert sum(comparable) / len(comparable) == pytest.approx(0.778, abs=0.01)


def test_one_shared_fault_is_reported_as_incomparable_not_as_disagreement(capsys):
    """An arm that only ran one condition must not read as a failed transfer."""
    tau, p = kendall({"freshness": 1}, {"freshness": 1})
    assert tau != tau and p != p


def test_two_shared_faults_are_still_incomparable():
    """Kendall needs 3 points; 2 always looks perfectly concordant."""
    tau, _ = kendall({"freshness": 1, "latency": 2}, {"freshness": 1, "latency": 2})
    assert tau != tau
