"""Tests for the silent-failure threshold sensitivity check.

This module backs a sentence in the threats-to-validity section — that a
confidence threshold would not change the thesis's silent-failure numbers for
the primary model. If `rates` miscounted, that sentence would be unsupported
while reading as evidenced, so the counting rules are pinned here.
"""

from __future__ import annotations

import pytest

from airsbench.analysis.silent_definition import (
    THRESHOLDS,
    rates,
    sensitivity,
    shift_pp,
    verdict,
)
from airsbench.runner.scoring import HIGH_CONFIDENCE


def d(correct=False, confidence=1.0, abstained=False, parse_failed=False):
    return {"correct": correct, "confidence": confidence,
            "abstained": abstained, "parse_failed": parse_failed}


def test_threshold_is_inert_when_every_silent_failure_is_confident():
    """The gpt-4o-mini situation: nothing wrong is ever committed below 0.9."""
    out = rates([d(confidence=0.95), d(confidence=0.9), d(correct=True)])
    assert out["default"] == pytest.approx(2 / 3)
    for t in THRESHOLDS:
        assert out["by_threshold"][t] == pytest.approx(2 / 3), t
    assert out["below_reference"] == 0.0
    assert shift_pp(out) == 0.0


def test_low_confidence_silent_failures_are_exactly_what_a_threshold_removes():
    out = rates([d(confidence=0.6), d(confidence=0.95)])
    assert out["default"] == 1.0
    assert out["by_threshold"][0.5] == 1.0
    assert out["by_threshold"][0.6] == 1.0      # inclusive
    assert out["by_threshold"][HIGH_CONFIDENCE] == 0.5
    assert out["below_reference"] == 0.5
    assert shift_pp(out) == pytest.approx(50.0)


def test_a_threshold_never_increases_the_rate():
    out = rates([d(confidence=c) for c in (0.1, 0.55, 0.65, 0.75, 0.85, 0.95)]
                + [d(correct=True)] * 3)
    series = [out["default"]] + [out["by_threshold"][t] for t in sorted(THRESHOLDS)]
    assert all(a >= b for a, b in zip(series, series[1:])), series


def test_abstentions_and_parse_failures_never_count_at_any_threshold():
    out = rates([d(abstained=True), d(parse_failed=True), d(correct=True)])
    assert out["default"] == 0.0
    assert all(v == 0.0 for v in out["by_threshold"].values())


def test_empty_group_is_safe():
    out = rates([])
    assert out["n"] == 0 and out["default"] == 0.0


def run(seed, model, task, decisions):
    return {"config": {"seed": seed, "model": model, "task": task},
            "decisions": decisions}


def test_groups_by_arm_model_and_task_and_names_the_worst_non_primary_group():
    rows = sensitivity([
        run(1, "gpt-4o-mini", "retrieval", [d(confidence=1.0)] * 4),          # main arm
        run(70_001, "claude-haiku-4-5", "retrieval",
            [d(confidence=0.5), d(confidence=0.9)]),                           # cross_model
        run(70_002, "claude-haiku-4-5", "classification", [d(confidence=0.9)]),
    ])
    keys = [key for key, _ in rows]
    assert ("main", "gpt-4o-mini", "retrieval") in keys
    assert ("cross_model", "claude-haiku-4-5", "retrieval") in keys

    v = verdict(rows)
    assert v["primary_max_pp"] == 0.0
    assert v["other_worst_group"] == ("cross_model", "claude-haiku-4-5", "retrieval")
    assert v["other_max_pp"] == pytest.approx(50.0)
