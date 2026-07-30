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
    FAULTS,
    baseline_health,
    build_frame,
    kendall,
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
