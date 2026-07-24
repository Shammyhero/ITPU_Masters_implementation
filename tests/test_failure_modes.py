"""Failure-mode split: abstention vs. silent failure.

Accuracy alone cannot distinguish an agent that declined to answer from one
that answered confidently and wrongly. That distinction is the thesis's
distinctive claim (docs/literature_review.md §8.3), because prior work has
already established that missing semantics lowers accuracy.
"""

from __future__ import annotations

import pytest

from airsbench.runner.scoring import HIGH_CONFIDENCE, failure_modes


def decision(correct: bool, confidence: float, abstained: bool = False) -> dict:
    return {"correct": correct, "confidence": confidence, "abstained": abstained}


def test_confident_wrong_answers_are_silent_failures():
    decisions = [decision(False, 0.95), decision(False, 0.9), decision(True, 0.9)]
    abstention, silent = failure_modes(decisions)
    assert abstention == 0.0
    assert silent == pytest.approx(2 / 3)


def test_abstention_is_not_silent_failure():
    decisions = [decision(False, 0.0, abstained=True) for _ in range(4)]
    abstention, silent = failure_modes(decisions)
    assert abstention == 1.0
    assert silent == 0.0


def test_low_confidence_errors_are_not_silent_failures():
    decisions = [decision(False, 0.2), decision(False, 0.3)]
    _, silent = failure_modes(decisions)
    assert silent == 0.0


def test_threshold_is_inclusive():
    _, silent = failure_modes([decision(False, HIGH_CONFIDENCE)])
    assert silent == 1.0


def test_correct_answers_never_count_as_failures():
    decisions = [decision(True, 1.0) for _ in range(5)]
    assert failure_modes(decisions) == (0.0, 0.0)


def test_empty_input_is_safe():
    assert failure_modes([]) == (0.0, 0.0)


def test_mixed_population_splits_correctly():
    decisions = [
        decision(True, 0.9),                    # correct
        decision(False, 0.95),                  # silent failure
        decision(False, 0.1),                   # honest low-confidence error
        decision(False, 0.0, abstained=True),   # abstention
    ]
    abstention, silent = failure_modes(decisions)
    assert abstention == 0.25
    assert silent == 0.25
