"""Runs recorded before the freshness fix must be corrected, not re-run.

The correction lives in the analysis layer so run artifacts stay immutable
records of what the instrument actually emitted. That only works if the
recomputation is exact, is confined to the dimension that was wrong, and is
idempotent — a run recorded after the fix must pass through untouched, so the
correction quietly becomes a no-op as the campaign completes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from airsbench.analysis.airs_correction import (
    corrected_airs,
    load_corrected,
    needs_correction,
    true_freshness_score,
)
from airsbench.runner.config import SEVERITY_PARAMS, RunConfig

RESULTS_DIR = Path("results/runs")

# The recorded/corrected pairs, verified against the artifacts on disk.
KNOWN = {
    ("streaming", "mild"): (32.79, 64.52),
    ("streaming", "severe"): (9.95, 19.80),
    ("batch", "mild"): (16.67, 22.22),
    ("batch", "severe"): (7.69, 12.50),
}


def _run(pipeline, fault, severity, recorded_freshness):
    params = {} if fault == "none" else SEVERITY_PARAMS[fault][severity]
    config = RunConfig(
        pipeline=pipeline, task="retrieval", fault_type=fault, severity=severity,
        replication=1, injector_params=dict(params), seed=1,
    )
    return {
        "config": config.to_dict(),
        "airs": {
            "freshness": recorded_freshness, "latency": 100.0,
            "consistency": 100.0, "semantic": 100.0, "total": 0.0,
        },
    }


@pytest.mark.parametrize("pipeline,severity", sorted(KNOWN))
def test_recomputed_value_matches_the_documented_correction(pipeline, severity):
    recorded, expected = KNOWN[(pipeline, severity)]
    run = _run(pipeline, "freshness", severity, recorded)
    assert true_freshness_score(run) == pytest.approx(expected, abs=0.01)
    assert needs_correction(run)
    assert corrected_airs(run)["freshness"] == pytest.approx(expected, abs=0.01)


def test_correction_touches_only_the_freshness_dimension():
    run = _run("streaming", "freshness", "severe", 9.95)
    before = dict(run["airs"])
    after = corrected_airs(run)
    for dimension in ("latency", "consistency", "semantic"):
        assert after[dimension] == before[dimension]
    assert after["freshness"] != before["freshness"]
    assert after["total"] != before["total"]  # composite must be refreshed


def test_the_input_run_is_not_mutated():
    run = _run("streaming", "freshness", "severe", 9.95)
    corrected_airs(run)
    assert run["airs"]["freshness"] == 9.95


@pytest.mark.parametrize("fault", ["none", "latency", "schema_drift", "semantic_stripping"])
def test_runs_without_a_freshness_injector_need_no_correction(fault):
    """They had nothing to double-count; their recorded value was already right."""
    for pipeline, recorded in (("streaming", 100.0), ("batch", 33.33)):
        run = _run(pipeline, fault, "severe" if fault != "none" else "none", recorded)
        assert not needs_correction(run)
        assert corrected_airs(run)["freshness"] == pytest.approx(recorded, abs=0.01)


def test_correction_is_idempotent():
    """A run recorded after the fix passes through unchanged."""
    run = _run("streaming", "freshness", "severe", 19.80)
    assert not needs_correction(run)
    once = corrected_airs(run)
    run["airs"] = once
    assert corrected_airs(run) == once


@pytest.mark.skipif(not list(RESULTS_DIR.glob("*.json")), reason="no completed runs")
def test_every_run_on_disk_gets_a_consistent_correction():
    runs = load_corrected(RESULTS_DIR)
    assert runs
    for run in runs:
        assert "airs_recorded" in run, "the recorded value must be kept for audit"
        assert run["airs"]["freshness"] == pytest.approx(
            true_freshness_score(run), abs=0.01
        )


@pytest.mark.skipif(not list(RESULTS_DIR.glob("*.json")), reason="no completed runs")
def test_only_freshness_runs_on_disk_need_correcting():
    for path in sorted(RESULTS_DIR.glob("*.json")):
        run = json.loads(path.read_text())
        if needs_correction(run):
            assert run["config"]["fault_type"] == "freshness", (
                f"{path.name}: a non-freshness run should never need correcting"
            )
