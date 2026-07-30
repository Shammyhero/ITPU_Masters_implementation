"""The decision frame is upstream of every model, so its errors are silent.

A mislabelled outcome or a wrong `flipped` flag would not raise; it would
produce a plausible odds ratio that happens to be wrong. These tests pin the
construction rules rather than the fitted numbers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from airsbench.analysis.decision_models import build_frame, fit_logit

RESULTS_DIR = Path("results/runs")
DATA_DIR = Path("data/ecommerce")

needs_runs = pytest.mark.skipif(
    not list(RESULTS_DIR.glob("*.json")) or not (DATA_DIR / "updates.jsonl").exists(),
    reason="no completed runs",
)


@pytest.fixture(scope="module")
def frame():
    return build_frame(RESULTS_DIR, DATA_DIR)


@needs_runs
def test_only_main_factorial_runs_are_modelled(frame):
    """Other arms differ in treatment and must not enter the RQ2/RQ3 models."""
    assert frame["run_id"].nunique() == 144
    assert set(frame["severity"]) <= {"none", "mild", "severe"}
    assert not any(s.startswith("sweep_") for s in frame["severity"].unique())


@needs_runs
def test_silent_failure_is_wrong_and_committed_and_parseable(frame):
    """A refusal and a parse failure are NOT silent failures — that distinction
    is the thesis's central one and must not blur in the modelling frame."""
    assert not ((frame["silent"] == 1) & (frame["abstained"] == 1)).any()
    assert not ((frame["silent"] == 1) & (frame["correct"] == 1)).any()


@needs_runs
def test_abstention_is_never_scored_correct(frame):
    assert not ((frame["abstained"] == 1) & (frame["correct"] == 1)).any()


@needs_runs
def test_flipped_is_false_for_every_classification_decision(frame):
    """The aviation label is a property of the flight; staleness cannot move it,
    so `flipped` is not-applicable there rather than missing."""
    assert not frame[frame["task"] == "classification"]["flipped"].any()


@needs_runs
def test_only_freshness_and_batch_flip_answers(frame):
    """A flip requires stale VALUES: either an injected freshness fault or the
    batch archetype's inherent staleness. Anything else flipping means the
    replay and value_staleness_s have come apart."""
    flipped = frame[frame["flipped"]]
    assert len(flipped) > 0
    offenders = flipped[(flipped["fault"] != "freshness") & (flipped["pipeline"] != "batch")]
    assert offenders.empty, f"unexpected flips in {set(offenders['condition'])}"


@needs_runs
def test_baseline_is_one_condition_level_not_a_crossed_cell(frame):
    """fault='none' has no severity, so it cannot enter a crossed design."""
    baseline = frame[frame["fault"] == "none"]
    assert set(baseline["condition"]) == {"baseline"}
    assert set(baseline["severity"]) == {"none"}
    assert "none_none" not in set(frame["condition"])


@needs_runs
def test_every_faulted_condition_is_labelled_fault_and_severity(frame):
    faulted = frame[frame["fault"] != "none"]
    for condition in faulted["condition"].unique():
        assert condition.endswith(("_mild", "_severe")), condition


@needs_runs
def test_the_frame_covers_every_decision_on_disk(frame):
    import json

    from airsbench.runner.config import run_arm

    expected = sum(
        len(run["decisions"])
        for path in RESULTS_DIR.glob("*.json")
        if run_arm(run := json.loads(path.read_text())) == "main"
    )
    assert len(frame) == expected


@needs_runs
def test_inference_is_clustered_by_run_not_by_decision(frame):
    """Decisions within a run are correlated. Naive SEs would be too small, so
    the clustered fit must produce WIDER intervals than the naive one."""
    formula = "C(condition) + C(task) + C(pipeline)"
    clustered = fit_logit(frame, "silent", formula)
    naive = clustered.model.fit()

    term = "C(condition)[T.freshness_severe]"
    clustered_width = (
        clustered.conf_int().loc[term, 1] - clustered.conf_int().loc[term, 0]
    )
    naive_width = naive.conf_int().loc[term, 1] - naive.conf_int().loc[term, 0]
    assert clustered_width > naive_width
    assert clustered.params[term] == pytest.approx(naive.params[term], rel=1e-6), (
        "clustering must change the standard errors, never the coefficients"
    )


@needs_runs
def test_latency_is_an_estimated_null_not_an_omitted_term(frame):
    """Analytic latency cannot change what the agent reads, so its odds ratio
    should sit on 1.0. If it drifts, the harness is leaking a difference."""
    import numpy as np

    result = fit_logit(frame, "silent", "C(condition) + C(task) + C(pipeline)")
    for term in ("C(condition)[T.latency_mild]", "C(condition)[T.latency_severe]"):
        assert np.exp(result.params[term]) == pytest.approx(1.0, abs=0.05)
