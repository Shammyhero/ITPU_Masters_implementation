"""The retroactive flip analysis must reconstruct what the runs actually saw.

The flip partition is what makes the freshness result reportable: raw accuracy
under staleness is near-arithmetic, so the finding lives in the behaviour on
queries whose correct answer moved. That reconstruction is only admissible
because it is exact — it replays `sample_seed` rather than re-sampling. Two
things must therefore hold, and both are pinned here:

1. `CatalogIndex` answers exactly what `CatalogTimeMachine.state_at` answers.
   It exists only to make ~5.7k lookups affordable; a divergence would
   silently mislabel which queries flipped.
2. The replay reproduces every logged ground truth. `Replayer.outcomes` raises
   on the first disagreement, so running it over the completed runs is itself
   the assertion.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from airsbench.analysis.flip_partition import (
    CatalogIndex,
    QueryOutcome,
    Replayer,
    load_retrieval_runs,
)
from airsbench.pipelines.loader import CatalogTimeMachine

DATA_DIR = Path("data/ecommerce")
RESULTS_DIR = Path("results/runs")

needs_catalog = pytest.mark.skipif(
    not (DATA_DIR / "updates.jsonl").exists(), reason="prepared catalog not present"
)


@pytest.fixture(scope="module")
def machine() -> CatalogTimeMachine:
    return CatalogTimeMachine.load(DATA_DIR)


@needs_catalog
def test_index_matches_the_time_machine(machine):
    """Same price and stock as a full state_at replay, at every probe time."""
    index = CatalogIndex(machine)
    rng = random.Random(11)
    pids = rng.sample(sorted(machine.base), 40)

    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        ts = machine.max_ts * fraction
        state = machine.state_at(ts)
        for pid in pids:
            got = index.value_at(pid, ts)
            assert got["price"] == state[pid]["price"], f"price drift at {ts} for {pid}"
            assert got["stock"] == state[pid]["stock"], f"stock drift at {ts} for {pid}"


@needs_catalog
def test_index_best_matches_ground_truth_over_the_time_machine(machine):
    from airsbench.agents.retrieval import RetrievalAgent

    index = CatalogIndex(machine)
    rng = random.Random(3)
    ts = machine.max_ts * 0.8
    state = machine.state_at(ts)
    for _ in range(50):
        pids = rng.sample(sorted(machine.base), 6)
        expected = RetrievalAgent.ground_truth([state[pid] for pid in pids])
        expected_id = expected["product_id"] if expected else None
        assert index.best(pids, ts) == expected_id


@pytest.mark.skipif(
    not list(RESULTS_DIR.glob("*.json")) or not (DATA_DIR / "updates.jsonl").exists(),
    reason="no completed runs to replay",
)
def test_replay_reproduces_every_completed_run():
    """Raises on any divergence from a run artifact — see Replayer.outcomes."""
    runs = load_retrieval_runs(RESULTS_DIR)
    replayer = Replayer(DATA_DIR)
    for run in runs:
        outcomes = replayer.outcomes(run)
        assert len(outcomes) == len(run["decisions"])


@pytest.mark.skipif(
    not list(RESULTS_DIR.glob("*.json")) or not (DATA_DIR / "updates.jsonl").exists(),
    reason="no completed runs to replay",
)
def test_streaming_baseline_has_no_flips_and_batch_baseline_does():
    """Flip status must track staleness, not noise.

    Streaming's 0.05 s inherent staleness cannot move an answer; batch's 3 s
    can, and that inherent flip rate is why the batch baseline sits below the
    streaming one. If this inverts, `value_staleness_s` and the replay have
    come apart.
    """
    runs = load_retrieval_runs(RESULTS_DIR)
    replayer = Replayer(DATA_DIR)
    flips = {"streaming": [], "batch": []}
    for run in runs:
        cfg = run["config"]
        if cfg["fault_type"] != "none":
            continue
        flips[cfg["pipeline"]].extend(o.flipped for o in replayer.outcomes(run))

    if flips["streaming"]:
        assert not any(flips["streaming"]), "streaming baseline must not flip answers"
    if flips["batch"]:
        assert any(flips["batch"]), "batch inherent staleness must flip some answers"


def test_outcome_flags_are_independent():
    """`flipped` is about the world; `served_faithful` is about the agent."""
    faithful_under_flip = QueryOutcome(
        query="q", truth_id="A", served_id="B", chosen="B",
        correct=False, confidence=1.0, abstained=False, parse_failed=False,
    )
    assert faithful_under_flip.flipped
    assert faithful_under_flip.served_faithful

    confused_under_flip = QueryOutcome(
        query="q", truth_id="A", served_id="B", chosen="C",
        correct=False, confidence=1.0, abstained=False, parse_failed=False,
    )
    assert confused_under_flip.flipped
    assert not confused_under_flip.served_faithful

    abstained = QueryOutcome(
        query="q", truth_id="A", served_id="A", chosen=None,
        correct=False, confidence=0.0, abstained=True, parse_failed=False,
    )
    assert not abstained.flipped
    assert not abstained.served_faithful


@needs_catalog
def test_plan_is_cached_per_sample_seed_not_per_run():
    """The paired design means one plan serves every condition in a replication."""
    replayer = Replayer(DATA_DIR)
    first = replayer._plan(10001, 80)
    second = replayer._plan(10001, 80)
    assert first is second, "plan must be reused across conditions"
    assert replayer._plan(10002, 80) is not first


@pytest.mark.skipif(
    not list(RESULTS_DIR.glob("*.json")) or not (DATA_DIR / "updates.jsonl").exists(),
    reason="no completed runs to replay",
)
def test_a_corrupted_artifact_is_rejected_not_silently_realigned():
    runs = load_retrieval_runs(RESULTS_DIR)
    replayer = Replayer(DATA_DIR)
    tampered = json.loads(json.dumps(runs[0]))
    tampered["decisions"][5]["ground_truth"] = "NOT-A-REAL-PRODUCT"
    with pytest.raises(ValueError, match="diverged"):
        replayer.outcomes(tampered)
