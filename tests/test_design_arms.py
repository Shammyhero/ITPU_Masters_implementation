"""Grid builders for the two arms the related-work review required.

See docs/related_work_positioning.md §4 (monotonicity cannot be tested with
two severity levels) and §5 (single-model coverage is the study's biggest
exposure against comparison papers using 2-8 models).
"""

from __future__ import annotations

from airsbench.runner.config import (
    FAULT_TYPES,
    FRESHNESS_SWEEP_SECONDS,
    TASKS,
    build_cross_model_subset,
    build_freshness_sweep,
)


def test_sweep_has_enough_levels_to_test_monotonicity():
    # Two points always look monotonic; a curve needs at least four.
    assert len(FRESHNESS_SWEEP_SECONDS) >= 4
    assert list(FRESHNESS_SWEEP_SECONDS) == sorted(FRESHNESS_SWEEP_SECONDS)


def test_sweep_spans_both_main_factorial_severities():
    # The sweep must contain the mild (1.5s) and severe (5s) levels so its
    # curve can be tied back to the main factorial's two conditions.
    assert 1.5 in FRESHNESS_SWEEP_SECONDS
    assert 5.0 in FRESHNESS_SWEEP_SECONDS


def test_sweep_grid_shape_and_uniqueness():
    sweep = build_freshness_sweep(replications=3)
    assert len(sweep) == len(TASKS) * len(FRESHNESS_SWEEP_SECONDS) * 3
    assert len({cfg.seed for cfg in sweep}) == len(sweep)
    assert all(cfg.fault_type == "freshness" for cfg in sweep)
    # Streaming only: the batch arm's inherent staleness would confound the
    # low end of the sweep.
    assert all(cfg.pipeline == "streaming" for cfg in sweep)


def test_sweep_delays_land_in_injector_params():
    sweep = build_freshness_sweep(replications=1)
    delays = sorted({cfg.injector_params["delay_seconds"] for cfg in sweep})
    assert delays == sorted(FRESHNESS_SWEEP_SECONDS)


def test_cross_model_subset_covers_every_fault_and_task():
    subset = build_cross_model_subset("llama3:8b", replications=2)
    faulted = [cfg for cfg in subset if cfg.fault_type != "none"]
    assert {cfg.fault_type for cfg in faulted} == set(FAULT_TYPES)
    assert {cfg.task for cfg in faulted} == set(TASKS)
    assert all(cfg.model == "llama3:8b" for cfg in subset)


def test_cross_model_subset_has_one_baseline_per_task():
    subset = build_cross_model_subset("llama3:8b", replications=2)
    baselines = [cfg for cfg in subset if cfg.fault_type == "none"]
    assert len(baselines) == len(TASKS)
    assert {cfg.task for cfg in baselines} == set(TASKS)


def test_arm_seeds_do_not_collide_with_main_grid():
    from airsbench.runner.config import build_grid

    main = {cfg.seed for cfg in build_grid(replications=4)}
    sweep = {cfg.seed for cfg in build_freshness_sweep(replications=3)}
    cross = {cfg.seed for cfg in build_cross_model_subset("m", replications=2)}
    assert not (main & sweep)
    assert not (main & cross)
    assert not (sweep & cross)
