"""Every arm must draw its seeds from its own block.

Arms overlap in condition: the main factorial and the detectability arm both
contain streaming/freshness/severe runs, and the freshness sweep overlaps both.
An analysis that selected runs by condition rather than by provenance would
pool them silently — the flip-partition table would absorb records carrying
their own age, and the phase-1 checkpoint would count runs from arms it was
never meant to judge.

Seed blocks are what make provenance recoverable from an artifact alone, so
they must stay disjoint and must stay in step with the builders.
"""

from __future__ import annotations

import pytest

from airsbench.runner.config import (
    SEED_BLOCKS,
    arm_of,
    build_cross_model_subset,
    build_detectability_arm,
    build_freshness_sweep,
    build_grid,
    run_arm,
)

BUILDERS = {
    "main": lambda: build_grid(replications=4),
    "freshness_sweep": lambda: build_freshness_sweep(replications=3),
    "detectability": lambda: build_detectability_arm(replications=3),
    "cross_model": lambda: build_cross_model_subset("claude-haiku-4-5"),
}


@pytest.mark.parametrize("arm", sorted(BUILDERS))
def test_every_config_lands_in_its_own_block(arm):
    for cfg in BUILDERS[arm]():
        assert arm_of(cfg.seed) == arm, (
            f"{cfg.label()} seed {cfg.seed} resolves to {arm_of(cfg.seed)!r}"
        )


def test_no_seed_is_claimed_by_two_different_arms():
    """Across arms, seeds must be disjoint.

    Within the detectability arm they are deliberately *not*: each A/B pair
    shares a seed so the two conditions get an identical fault realisation.
    """
    seen: dict[int, str] = {}
    for arm, builder in BUILDERS.items():
        for cfg in builder():
            other = seen.setdefault(cfg.seed, arm)
            assert other == arm, f"seed {cfg.seed} used by both {other} and {arm}"


def test_detectability_pairs_share_a_seed_by_design():
    by_seed: dict[int, set[bool]] = {}
    for cfg in build_detectability_arm():
        if cfg.fault_type == "freshness":
            by_seed.setdefault(cfg.seed, set()).add(cfg.emit_record_age)
    assert by_seed
    for seed, arms in by_seed.items():
        assert arms == {False, True}, f"seed {seed} does not span both arms"


def test_blocks_do_not_overlap():
    ranges = sorted(SEED_BLOCKS.values())
    for (_, high), (low, _) in zip(ranges, ranges[1:]):
        assert high <= low, f"blocks overlap at {high}/{low}"


def test_a_seed_outside_every_block_is_not_silently_attributed():
    assert arm_of(10_000_000) == "unknown"
    assert run_arm({"config": {"seed": 10_000_000}}) == "unknown"


def test_run_arm_reads_the_artifact_shape():
    for cfg in build_detectability_arm():
        assert run_arm({"config": cfg.to_dict()}) == "detectability"


def test_main_grid_stays_inside_its_block_at_high_replication():
    """The main block must not run out as replications grow."""
    for cfg in build_grid(replications=12):
        assert arm_of(cfg.seed) == "main"
