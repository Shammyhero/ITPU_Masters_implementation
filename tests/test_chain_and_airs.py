import pytest

from agentic_faults import (
    FaultChain,
    FreshnessInjector,
    Record,
    SchemaDriftInjector,
    SemanticStrippingInjector,
)
from airsbench.airs import (
    AIRSCalculator,
    consistency_score,
    freshness_score,
    latency_score,
    payload_consistency,
    semantic_completeness,
    semantic_score,
)
from airsbench.runner import build_grid


def test_chain_composes_faults_without_mutating_input():
    chain = FaultChain([
        FreshnessInjector(seed=1, delay_seconds=2.0),
        SemanticStrippingInjector(seed=2, strip_rate=1.0),
    ])
    original = Record(payload={"v": 1}, context={"entity_type": "x", "units": {"v": "ms"}})
    faulted = chain.apply(original)

    assert original.context != {} and original.meta == {}
    assert faulted.context == {}
    assert original.event_timestamp - faulted.event_timestamp == pytest.approx(2.0)
    assert len(faulted.meta["faults"]) == 2


def test_dimension_scores_operational_definitions():
    assert freshness_score(0.5, target_s=1.0) == 100.0
    assert freshness_score(2.0, target_s=1.0) == 50.0
    assert latency_score(250, target_ms=500) == 100.0
    assert latency_score(1000, target_ms=500) == 50.0
    assert consistency_score(95, 100) == 95.0
    assert semantic_score(0.75) == 75.0


def test_payload_consistency_detects_schema_drift():
    source = Record(payload={"price": 10.0, "stock": 3})
    assert payload_consistency(source, source.clone()) == 1.0

    drifted = SchemaDriftInjector(seed=1, drift_probability=1.0,
                                  drift_types=("rename",)).apply(source)
    assert payload_consistency(source, drifted) == 0.0


def test_semantic_completeness_fraction():
    full = Record(payload={}, context={
        "entity_type": "x", "units": {"a": "s"},
        "descriptions": {"a": "d"}, "relationships": {"a": "r"},
    })
    assert semantic_completeness(full) == 1.0
    stripped = SemanticStrippingInjector(seed=1, strip_rate=1.0,
                                         strip_targets=("units", "descriptions")).apply(full)
    assert semantic_completeness(stripped) == 0.5


def test_composite_score_and_zones():
    calc = AIRSCalculator()  # placeholder equal weights until Week-6 calibration
    scores = {"freshness": 100.0, "latency": 100.0, "consistency": 50.0, "semantic": 50.0}
    assert calc.composite(scores) == pytest.approx(75.0)
    assert calc.zone(85) == "green"
    assert calc.zone(70) == "amber"
    assert calc.zone(59) == "red"
    with pytest.raises(ValueError):
        calc.composite({"freshness": 100.0})


def test_experiment_grid_matches_thesis_design():
    grid = build_grid(replications=4)
    # (2 pipelines x 2 tasks) x (1 baseline + 4 faults x 2 severities) x 4 reps
    assert len(grid) == 2 * 2 * 9 * 4
    labels = {cfg.label() for cfg in grid}
    assert len(labels) == len(grid)  # every run uniquely identified
    seeds = {cfg.seed for cfg in grid}
    assert len(seeds) == len(grid)  # every run independently reproducible
