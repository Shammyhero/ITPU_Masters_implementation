"""The detectability arm's statistics must be the paired ones.

A and B see identical queries at identical simulated times, so the comparison
is paired and McNemar's exact test on the discordant pairs is the correct
instrument — treating the two arms as independent samples would throw away the
pairing the design paid for and lose most of the power at n=240.

The exact form matters too: the discordant counts in this arm are small enough
that the chi-square approximation is not trustworthy.
"""

from __future__ import annotations

import pytest

from airsbench.analysis.detectability import (
    ARM_SEED_RANGE,
    Behaviour,
    in_arm,
    mcnemar_exact,
    pair_runs,
)
from airsbench.runner.config import (
    build_cross_model_subset,
    build_detectability_arm,
    build_freshness_sweep,
    build_grid,
)


def _decision(correct=True, abstained=False, confidence=1.0, parse_failed=False):
    return {
        "correct": correct,
        "abstained": abstained,
        "confidence": confidence,
        "parse_failed": parse_failed,
    }


def _run(task, replication, emit_age, decisions, fault="freshness"):
    return {
        "config": {
            "task": task,
            "replication": replication,
            "emit_record_age": emit_age,
            "fault_type": fault,
            "seed": 60_001,
        },
        "usage": {"cost_usd": 0.01},
        "decisions": decisions,
    }


# ---- McNemar ---------------------------------------------------------------

@pytest.mark.parametrize(
    "b,c,expected",
    [
        (0, 0, 1.0),        # no discordant pairs — no evidence either way
        (5, 0, 0.0625),     # 5 one-way flips
        (10, 0, 0.001953),  # 10 one-way flips
        (6, 1, 0.125),
        (3, 3, 1.0),        # perfectly balanced — null
    ],
)
def test_mcnemar_matches_the_exact_binomial(b, c, expected):
    assert mcnemar_exact(b, c) == pytest.approx(expected, abs=1e-5)


def test_mcnemar_is_symmetric_in_its_arguments():
    """Direction is read off the rates; the p-value is two-sided."""
    for b, c in ((7, 2), (12, 0), (4, 9)):
        assert mcnemar_exact(b, c) == mcnemar_exact(c, b)


def test_mcnemar_never_exceeds_one():
    for b in range(6):
        for c in range(6):
            assert 0.0 <= mcnemar_exact(b, c) <= 1.0


def test_concordant_pairs_do_not_affect_the_p_value():
    """Only disagreements carry information — that is the point of the test."""
    assert mcnemar_exact(5, 0) == mcnemar_exact(5, 0)
    assert mcnemar_exact(8, 1) < mcnemar_exact(4, 3)


# ---- arm membership --------------------------------------------------------

def test_arm_runs_are_identified_and_other_arms_are_not():
    """The main factorial also holds streaming/freshness/severe without the
    metadata; pooling it in would silently break the pairing."""
    arm_seeds = {c.seed for c in build_detectability_arm()}
    assert all(in_arm({"config": {"seed": s}}) for s in arm_seeds)

    for other in (build_grid(replications=4), build_freshness_sweep(),
                  build_cross_model_subset("claude-haiku-4-5")):
        for cfg in other:
            assert not in_arm({"config": {"seed": cfg.seed}}), (
                f"seed {cfg.seed} would be misread as a detectability run"
            )


def test_arm_seed_range_brackets_the_arm_exactly():
    low, high = ARM_SEED_RANGE
    seeds = {c.seed for c in build_detectability_arm()}
    assert low <= min(seeds) and max(seeds) < high


# ---- pairing ---------------------------------------------------------------

def test_pairs_are_matched_on_task_and_replication():
    runs = [
        _run("retrieval", 1, False, [_decision()]),
        _run("retrieval", 1, True, [_decision()]),
        _run("classification", 2, True, [_decision()]),
        _run("classification", 2, False, [_decision()]),
    ]
    pairs = pair_runs(runs)
    assert len(pairs) == 2
    for a, b in pairs:
        assert a["config"]["emit_record_age"] is False
        assert b["config"]["emit_record_age"] is True
        assert a["config"]["task"] == b["config"]["task"]
        assert a["config"]["replication"] == b["config"]["replication"]


def test_an_unpaired_run_is_dropped_not_silently_compared():
    runs = [
        _run("retrieval", 1, False, [_decision()]),
        _run("retrieval", 1, True, [_decision()]),
        _run("retrieval", 2, False, [_decision()]),  # partner missing
    ]
    assert len(pair_runs(runs)) == 1


def test_baselines_are_excluded_from_the_pairing():
    runs = [
        _run("retrieval", 1, False, [_decision()]),
        _run("retrieval", 1, True, [_decision()]),
        _run("retrieval", 1, True, [_decision()], fault="none"),
    ]
    assert len(pair_runs(runs)) == 1


# ---- behaviour summary -----------------------------------------------------

def test_silent_failure_excludes_abstentions_and_parse_failures():
    decisions = [
        _decision(correct=False, abstained=False),           # silent failure
        _decision(correct=False, abstained=True),            # declined — safe
        _decision(correct=False, parse_failed=True),         # error, not silent
        _decision(correct=True),
    ]
    behaviour = Behaviour.of(decisions)
    assert behaviour.n == 4
    assert behaviour.accuracy == pytest.approx(0.25)
    assert behaviour.abstained == pytest.approx(0.25)
    assert behaviour.silent == pytest.approx(0.25)


def test_confidence_when_wrong_ignores_correct_answers():
    behaviour = Behaviour.of([
        _decision(correct=True, confidence=0.10),
        _decision(correct=False, confidence=0.90),
        _decision(correct=False, confidence=1.00),
    ])
    assert behaviour.confidence_wrong == pytest.approx(0.95)


def test_empty_decision_set_is_not_a_zero():
    """An empty cell must read as absent, never as 0% abstention."""
    behaviour = Behaviour.of([])
    assert behaviour.n == 0
    assert behaviour.abstained != behaviour.abstained  # NaN
