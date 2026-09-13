"""Tests for the query-fragility analysis.

The load-bearing properties:

- `test_null_preserves_each_runs_failure_count` — the whole inference rests on a
  null in which condition severity cannot pass for fragility. That holds only if
  the permutation keeps every run's failure count and every unobserved cell
  fixed.
- `test_align_assigns_duplicate_questions_in_order` — classification flight
  identities are ~99% unique, not 100%. Keying on content alone would pour a
  duplicated flight's observations onto one row and inflate its count.
- `test_independent_failures_are_not_called_fragile` — the analysis must be able
  to return a null, or its positive result means nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

from airsbench.analysis.fragility import align, analyse, build_panels, lorenz, null_sums

MAIN, SWEEP, DETECT, INTERACT = 1, 50_001, 60_001, 80_001


def decision(question, silent):
    return {"query": question, "correct": not silent, "abstained": False,
            "parse_failed": False, "confidence": 1.0}


def run(run_id, seed, fault, questions, silent=(), pipeline="streaming",
        severity=None, age=False, replication=1):
    return {"run_id": run_id, "config": {
        "seed": seed, "model": "gpt-4o-mini", "task": "retrieval",
        "replication": replication, "pipeline": pipeline, "fault_type": fault,
        "severity": severity or ("none" if fault == "none" else "severe"),
        "emit_record_age": age},
        "decisions": [decision(q, q in silent) for q in questions]}


# ---- alignment ------------------------------------------------------------------

def test_align_identical_and_prefix_map_by_position():
    reference = ["a", "b", "c", "d"]
    assert align(reference, reference) == [0, 1, 2, 3]
    assert align(["a", "b"], reference) == [0, 1]


def test_align_assigns_duplicate_questions_in_order():
    """A question appearing twice takes its occurrences left to right."""
    assert align(["a", "a", "c", "z"], ["a", "b", "a", "c"]) == [0, 2, 3, None]


# ---- panels ---------------------------------------------------------------------

def test_baseline_is_the_main_streaming_clean_run_and_non_faults_are_excluded():
    qs = ["q0", "q1", "q2"]
    panels = build_panels([
        run("m-base", MAIN, "none", qs),
        run("m-batch", MAIN + 1, "none", qs, pipeline="batch"),
        run("i-base", INTERACT, "none", qs),
        run("d-base", DETECT, "none", qs, age=True),
        run("m-fresh", MAIN + 2, "freshness", qs, silent={"q1"}),
    ])
    (panel,) = panels
    base = panel.columns[panel.baseline]
    assert (base["arm"], base["pipeline"], base["run_id"]) == ("main", "streaming", "m-base")
    assert [panel.columns[i]["run_id"] for i in panel.faulted] == ["m-fresh"]


def test_shorter_sweep_runs_leave_their_unasked_questions_unobserved():
    qs = ["q0", "q1", "q2", "q3"]
    panels = build_panels([run("m-base", MAIN, "none", qs),
                           run("s-fresh", SWEEP, "freshness", qs[:2], silent={"q0"})])
    column = panels[0].columns.index(next(c for c in panels[0].columns if c["run_id"] == "s-fresh"))
    values = panels[0].silent[:, column]
    assert values[0] == 1.0 and values[1] == 0.0 and np.isnan(values[2:]).all()


# ---- the null -------------------------------------------------------------------

def test_null_preserves_each_runs_failure_count():
    rng = np.random.default_rng(0)
    values = np.array([[1, 0, np.nan],
                       [0, 1, 1],
                       [1, 1, np.nan],
                       [np.nan, np.nan, np.nan],
                       [0, 0, 0]], dtype=float)
    sums = null_sums(values, rng, permutations=200)
    assert np.allclose(sums.sum(axis=1), np.nansum(values))     # total preserved
    assert np.all(sums[:, 3] == 0)                              # unobserved row stays empty
    # Alone, the third column has one failure among its two observed rows (1 and 4),
    # so rows 0, 2 and 3 can never receive it.
    third_only = values.copy()
    third_only[:, :2] = np.nan
    s3 = null_sums(third_only, rng, permutations=200)
    assert np.all(s3[:, [0, 2, 3]] == 0) and np.allclose(s3.sum(axis=1), 1.0)


def test_lorenz_orders_most_fragile_first_and_ends_at_one():
    curve = lorenz(np.array([0.0, 4.0, 1.0]), np.array([4, 4, 4]))
    assert curve[0] == pytest.approx(0.8) and curve[-1] == pytest.approx(1.0)


# ---- inference ------------------------------------------------------------------

def _study(silent_for_run, n_questions=40, n_faulted=12):
    qs = [f"q{i}" for i in range(n_questions)]
    faults = ["freshness", "schema_drift", "semantic_stripping", "latency"]
    runs = [run("base", MAIN, "none", qs, silent=silent_for_run(-1, qs))]
    for i in range(n_faulted):
        runs.append(run(f"r{i}", MAIN + 10 + i, faults[i % 4], qs,
                        silent=silent_for_run(i, qs)))
    return analyse(build_panels(runs), permutations=300, seed=7)["retrieval"]


def test_a_planted_fragile_pool_is_detected():
    fragile = {f"q{i}" for i in range(6)}
    r = _study(lambda i, qs: fragile)
    assert r["p_concentration"] < 0.01
    assert r["top_share"] > r["top_share_null"]["hi"]
    assert r["carryover"] == pytest.approx(1.0)
    assert r["carryover"] > r["carryover_null"]["hi"]


def test_independent_failures_are_not_called_fragile():
    rng = np.random.default_rng(11)
    draws = {i: {f"q{j}" for j in range(60) if rng.random() < 0.2} for i in range(-1, 16)}
    r = _study(lambda i, qs: draws[i], n_questions=60, n_faulted=16)
    assert r["p_concentration"] > 0.01
    # The p-value is the claim; the band check only guards against a gross miss,
    # since an iid draw lands outside a 95% band 5% of the time by construction.
    assert r["top_share"] < r["top_share_null"]["hi"] + 0.05
