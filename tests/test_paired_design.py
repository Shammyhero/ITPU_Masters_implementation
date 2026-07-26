"""The design must be paired: conditions differ only by the fault.

Phase-1 evidence for why this is pinned by a test: when the query sample was
drawn from the condition-specific seed, every condition saw a different set of
queries, and sample variance alone produced a severe-latency run scoring 22
accuracy points ABOVE its own baseline — impossible, since analytic latency
cannot change what the agent reads.
"""

from __future__ import annotations

import random

from airsbench.pipelines.loader import DEP_DELAY_KNOWLEDGE_HORIZON_S, stale_dep_delay
from airsbench.runner.config import build_grid
from airsbench.runner.execute import BATCH_INHERENT_STALENESS_S, value_staleness_s


def _sample_for(cfg, n=20):
    return random.Random(cfg.sample_seed).sample(range(1500), n)


def test_all_conditions_in_a_replication_share_a_query_sample():
    grid = build_grid(replications=1)
    for task in ("retrieval", "classification"):
        samples = {tuple(_sample_for(c)) for c in grid if c.task == task}
        assert len(samples) == 1, f"{task}: conditions do not share a sample"


def test_replications_see_different_samples():
    grid = build_grid(replications=3)
    retrieval = [c for c in grid if c.task == "retrieval"]
    by_rep = {c.replication: tuple(_sample_for(c)) for c in retrieval}
    assert len(set(by_rep.values())) == 3, "replications must vary the sample"


def test_tasks_do_not_collide_on_sample_seed():
    grid = build_grid(replications=2)
    seeds = {(c.task, c.replication): c.sample_seed for c in grid}
    assert len(set(seeds.values())) == len(seeds)


def test_injector_seed_still_varies_by_condition():
    """Sampling is paired; the fault realization is the treatment and must not be."""
    grid = build_grid(replications=1)
    faulted = [c for c in grid if c.fault_type != "none"]
    assert len({c.seed for c in faulted}) == len(faulted)


def test_batch_staleness_does_not_floor_the_delay_signal():
    """The batch arm must retain predictive signal, before and after a fault."""
    assert BATCH_INHERENT_STALENESS_S < DEP_DELAY_KNOWLEDGE_HORIZON_S

    baseline = stale_dep_delay(45.0, BATCH_INHERENT_STALENESS_S)
    assert baseline > 0.0, "batch baseline zeroes the dominant feature"
    assert baseline < 45.0, "batch baseline should still be degraded"

    # Worst case in the grid: batch pipeline plus a severe freshness fault.
    worst = max(
        value_staleness_s(c)
        for c in build_grid(replications=1)
        if c.pipeline == "batch"
    )
    assert stale_dep_delay(45.0, worst) > 0.0, "severe batch condition hits the floor"


def test_batch_degrades_monotonically_with_added_freshness_fault():
    grid = build_grid(replications=1)
    batch = {
        (c.fault_type, c.severity): value_staleness_s(c)
        for c in grid
        if c.pipeline == "batch"
    }
    assert batch[("none", "none")] < batch[("freshness", "mild")]
    assert batch[("freshness", "mild")] < batch[("freshness", "severe")]
