"""Tests for the additivity estimator (interaction arm, provisional).

`test_estimator_recovers_a_planted_interaction` is the positive control the
*design* cannot supply. The latency control in the arm itself only proves the
arithmetic returns ~0 where nothing can interact; it cannot show the estimator
would detect a real interaction, because latency runs analytically and could
never produce one. Planting a known psi and recovering it closes that gap for
the statistic, though not for the experiment.
"""

from __future__ import annotations

import math

import pytest

from airsbench.analysis.interaction import (
    AlignmentError,
    interaction_estimates,
    outcome_vector,
    paired_cells,
)

PAIR = ("freshness", "schema_drift")
COMPOUND = "freshness+schema_drift"


def bernoulli(p: float, n: int, seed: int) -> list[int]:
    import numpy as np
    return list(np.random.default_rng(seed).binomial(1, p, n).astype(int))


def cells_from(rates: dict[str, float], n: int = 8000) -> dict[str, list[list[int]]]:
    """Synthetic cells with FIXED seeds.

    Seeded by position, not by `hash(condition)`: Python randomises string
    hashing per process, so that version drew different data in every pytest
    invocation and the planted-effect assertions passed or failed depending on
    PYTHONHASHSEED. An intermittently green test is worse than a red one.
    """
    return {
        condition: [bernoulli(p, n, seed=1000 + index)]
        for index, (condition, p) in enumerate(rates.items())
    }


def run_stub(fault: str, replication: int, task: str, outcomes: list[tuple]):
    """A run artifact carrying only what the analysis reads."""
    return {
        "config": {"task": task, "fault_type": fault, "replication": replication},
        "decisions": [
            {"correct": c, "abstained": a, "parse_failed": p} for c, a, p in outcomes
        ],
    }


# ---- the positive control -------------------------------------------------

@pytest.mark.parametrize("psi", [0.0, 0.8, -0.8])
def test_estimator_recovers_a_planted_interaction(psi):
    """Plant a known log-odds interaction; the estimator must find it.

    Cells are built so that logit p(AB) = logit p(A) + logit p(B) - logit p(0) +
    psi exactly. Recovering psi shows the statistic can detect a real departure
    from additivity — which the arm's own latency control cannot demonstrate.
    """
    def inv_logit(x):
        return 1 / (1 + math.exp(-x))

    l0, la, lb = math.log(0.15 / 0.85), math.log(0.25 / 0.75), math.log(0.30 / 0.70)
    rates = {
        "none": inv_logit(l0),
        PAIR[0]: inv_logit(la),
        PAIR[1]: inv_logit(lb),
        COMPOUND: inv_logit(la + lb - l0 + psi),
    }
    est = interaction_estimates(cells_from(rates), PAIR)

    assert est["logit"]["point"] == pytest.approx(psi, abs=0.2)
    assert est["logit"]["lo"] <= psi <= est["logit"]["hi"]
    if psi == 0.0:
        assert est["logit"]["lo"] <= 0 <= est["logit"]["hi"], "false positive"
    else:
        assert not (est["logit"]["lo"] <= 0 <= est["logit"]["hi"]), "missed a real effect"


def test_additive_on_logit_can_depart_on_risk_scale():
    """Scale-dependence is arithmetic, not a contradiction — and is reported as such.

    A constant odds ratio produces unequal risk differences wherever the
    baselines differ. If the report conflated the two scales it would announce
    an interaction that is purely a property of the link function.
    """
    def inv_logit(x):
        return 1 / (1 + math.exp(-x))

    l0, la, lb = math.log(0.05 / 0.95), math.log(0.40 / 0.60), math.log(0.45 / 0.55)
    est = interaction_estimates(cells_from({
        "none": inv_logit(l0), PAIR[0]: inv_logit(la), PAIR[1]: inv_logit(lb),
        COMPOUND: inv_logit(la + lb - l0),  # exactly additive in log odds
    }, n=8000), PAIR)

    assert est["logit"]["lo"] <= 0 <= est["logit"]["hi"]
    assert abs(est["rd"]["point"]) > 0.02  # yet visibly non-additive on risk


# ---- pairing guards -------------------------------------------------------

def test_alignment_error_when_a_replication_is_ragged():
    """Unequal decision counts within a replication means different questions."""
    runs = [
        run_stub("none", 1, "retrieval", [(True, False, False)] * 10),
        run_stub(PAIR[0], 1, "retrieval", [(True, False, False)] * 10),
        run_stub(PAIR[1], 1, "retrieval", [(True, False, False)] * 9),  # ragged
        run_stub(COMPOUND, 1, "retrieval", [(True, False, False)] * 10),
    ]
    with pytest.raises(AlignmentError, match="different numbers of decisions"):
        paired_cells(runs, "retrieval", PAIR, "silent")


def test_only_replications_complete_in_every_condition_are_used():
    """A partial arm must narrow the contrast, never unbalance it."""
    runs = [run_stub(c, rep, "retrieval", [(True, False, False)] * 10)
            for c in ("none", PAIR[0], PAIR[1], COMPOUND) for rep in (1, 2)]
    # Replication 2 of the compound condition has not run yet.
    runs = [r for r in runs
            if not (r["config"]["fault_type"] == COMPOUND
                    and r["config"]["replication"] == 2)]

    cells = paired_cells(runs, "retrieval", PAIR, "silent")
    assert all(len(v) == 1 for v in cells.values())


def test_replication_counts_differing_between_reps_is_fine():
    """Different replications ask different questions — only within-rep matters."""
    runs = []
    for condition in ("none", PAIR[0], PAIR[1], COMPOUND):
        runs.append(run_stub(condition, 1, "retrieval", [(True, False, False)] * 10))
        runs.append(run_stub(condition, 2, "retrieval", [(True, False, False)] * 7))
    cells = paired_cells(runs, "retrieval", PAIR, "silent")
    assert [len(v) for v in cells["none"]] == [10, 7]


def test_missing_condition_yields_empty_not_a_crash():
    runs = [run_stub("none", 1, "retrieval", [(True, False, False)] * 5)]
    assert paired_cells(runs, "retrieval", PAIR, "silent")["none"] == []


# ---- outcome definitions --------------------------------------------------

def test_silent_failure_excludes_abstention_and_parse_failure():
    """Invariant 6: a refusal is not a silent failure, and neither is garbage."""
    run = run_stub("none", 1, "retrieval", [
        (False, False, False),  # wrong, committed  -> silent
        (False, True, False),   # wrong, abstained  -> not silent
        (False, False, True),   # unparseable       -> not silent
        (True, False, False),   # correct           -> not silent
    ])
    assert outcome_vector(run, "silent") == [1, 0, 0, 0]
    assert outcome_vector(run, "error") == [1, 1, 1, 0]
