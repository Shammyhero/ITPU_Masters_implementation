"""Failure-mode split: abstention vs. silent failure.

Accuracy alone cannot distinguish an agent that declined to answer from one
that answered confidently and wrongly. That distinction is the thesis's
distinctive claim (docs/literature_review.md §8.3), because prior work has
already established that missing semantics lowers accuracy.

Silent failure has ONE definition — committed, parseable, wrong, with no
confidence threshold (`runner/scoring.py::is_silent_failure`). Until 2026-09-13
this module and nine analysis modules disagreed about that: the tests here
pinned a 0.7 threshold the analyses never applied. The threshold's behaviour is
still tested, but only as the optional robustness parameter it now is.
"""

from __future__ import annotations

import itertools

import pytest

from airsbench.runner.scoring import HIGH_CONFIDENCE, failure_modes, is_silent_failure


def decision(correct: bool, confidence: float, abstained: bool = False,
             parse_failed: bool = False) -> dict:
    return {"correct": correct, "confidence": confidence,
            "abstained": abstained, "parse_failed": parse_failed}


# ---- the definition ------------------------------------------------------------

def test_wrong_committed_answers_are_silent_failures_at_any_confidence():
    """The deliberate reversal: a low-confidence wrong answer is still silent.

    It was committed and it was wrong, and nothing downstream is told otherwise.
    Excluding it would define the outcome partly by the agent's confidence —
    the very signal RQ4 compares AIRS against.
    """
    decisions = [decision(False, 0.95), decision(False, 0.2), decision(True, 0.9)]
    abstention, silent = failure_modes(decisions)
    assert abstention == 0.0
    assert silent == pytest.approx(2 / 3)


def test_abstention_is_not_silent_failure():
    decisions = [decision(False, 0.0, abstained=True) for _ in range(4)]
    abstention, silent = failure_modes(decisions)
    assert abstention == 1.0
    assert silent == 0.0


def test_parse_failures_are_failures_but_not_silent_ones():
    """Invariant 6 counts unparseable output as a failure — but it is visible."""
    _, silent = failure_modes([decision(False, 0.9, parse_failed=True)])
    assert silent == 0.0


def test_correct_answers_never_count_as_failures():
    decisions = [decision(True, 1.0) for _ in range(5)]
    assert failure_modes(decisions) == (0.0, 0.0)


def test_empty_input_is_safe():
    assert failure_modes([]) == (0.0, 0.0)


def test_mixed_population_splits_correctly():
    decisions = [
        decision(True, 0.9),                    # correct
        decision(False, 0.95),                  # silent failure
        decision(False, 0.1),                   # silent failure, low confidence
        decision(False, 0.0, abstained=True),   # abstention
    ]
    abstention, silent = failure_modes(decisions)
    assert abstention == 0.25
    assert silent == 0.5


def test_the_analyses_inline_formula_is_this_definition():
    """One construct, one name.

    gate/replay, interaction, airs_calibration, freshness_sweep, cross_model,
    detectability, decision_models and export_demo_data each compute silent
    failure inline as `not correct and not abstained and not parse_failed`. That
    is only legitimate if it is exactly `is_silent_failure` — checked over every
    combination of flags and a spread of confidences, not a hand-picked case.
    """
    for correct, abstained, parse_failed in itertools.product([True, False], repeat=3):
        for confidence in (0.0, 0.3, HIGH_CONFIDENCE, 0.95, 1.0):
            d = decision(correct, confidence, abstained, parse_failed)
            inline = not d["correct"] and not d["abstained"] and not d["parse_failed"]
            assert is_silent_failure(d) == inline, d


# ---- the robustness parameter ------------------------------------------------------

def test_min_confidence_reproduces_the_retired_threshold():
    """The original definition is still computable, for the sensitivity check."""
    decisions = [decision(False, 0.2), decision(False, 0.3), decision(False, 0.95)]
    _, silent = failure_modes(decisions, min_confidence=HIGH_CONFIDENCE)
    assert silent == pytest.approx(1 / 3)


def test_min_confidence_is_inclusive():
    _, silent = failure_modes([decision(False, HIGH_CONFIDENCE)],
                              min_confidence=HIGH_CONFIDENCE)
    assert silent == 1.0


def test_min_confidence_never_admits_abstentions_or_parse_failures():
    for d in (decision(False, 1.0, abstained=True), decision(False, 1.0, parse_failed=True)):
        assert not is_silent_failure(d, min_confidence=0.0)
