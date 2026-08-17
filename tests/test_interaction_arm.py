"""Tests for the fault-interaction arm (provisional — see docs/interaction_arm.md).

The arm asks whether two faults compose additively. That question is only
answerable if the *measurement* side composes exactly, so the load-bearing test
here is `test_composition_preserves_solo_marginals`: applying two injectors must
degrade each AIRS dimension by precisely the amount that injector degrades it
alone. If it does not, any non-additivity found in the outcome could be an
artifact of the injectors interfering rather than a fact about the agent.

`test_drift_before_stripping_corrupts_the_opaque_map` pins the reason the
composition order is fixed. It is the trap this arm nearly walked into.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agentic_faults import Record
from airsbench.airs import (
    mean_semantic_completeness,
    payload_consistency,
    semantic_score,
)
from airsbench.runner.config import (
    FAULT_TYPES,
    INTERACTION_PAIRS,
    INTERACTION_SEED_RANGE,
    SEVERITY_PARAMS,
    RunConfig,
    arm_of,
    build_grid,
    build_interaction_arm,
    compose_faults,
    fault_components,
)
from airsbench.runner.execute import (
    _component_seed,
    build_fault_chain,
    value_staleness_s,
)

SEVERE = "severe"


def record(i: int) -> Record:
    return Record(
        payload={"price": 10.0 + i, "stock": 3, "rating": 4.1},
        context={"entity_type": "product", "units": {"price": "USD"},
                 "descriptions": {"price": "unit price"}, "relationships": {}},
        event_timestamp=1000.0,
    )


def config_for(fault: str) -> RunConfig:
    components = fault_components(fault)
    params = (
        {f: SEVERITY_PARAMS[f][SEVERE] for f in components}
        if len(components) > 1
        else (SEVERITY_PARAMS[components[0]][SEVERE] if components else {})
    )
    return RunConfig(
        pipeline="streaming", task="retrieval", fault_type=fault,
        severity="none" if not components else SEVERE, replication=1,
        injector_params=params, seed=80_001,
    )


def dimensions(fault: str, n: int = 300) -> tuple[float, float]:
    """(consistency, semantic) after running this condition's real fault chain."""
    baseline = [record(i) for i in range(n)]
    chain = build_fault_chain(config_for(fault))
    delivered = [chain.apply(record(i)) for i in range(n)]
    consistency = 100.0 * sum(
        payload_consistency(b, d) for b, d in zip(baseline, delivered)
    ) / n
    return consistency, semantic_score(mean_semantic_completeness(delivered))


# ---- the load-bearing test ------------------------------------------------

@pytest.mark.parametrize("pair", INTERACTION_PAIRS)
def test_composition_preserves_solo_marginals(pair):
    """Two injectors must degrade each dimension exactly as much as one does.

    This is invariant 5 under composition. The arm's whole claim is that the
    independent variable is clean by construction, so that any non-additivity in
    the OUTCOME is behavioural. If a compound condition depressed consistency
    further than schema drift alone, the AIRS vector and the agent's impairment
    would move together for a mechanical reason and the test would be circular.
    """
    solo = {f: dimensions(f) for f in pair}
    both_consistency, both_semantic = dimensions(compose_faults(*pair))

    # Each dimension keeps whichever solo value actually degraded it.
    expected_consistency = min(c for c, _ in solo.values())
    expected_semantic = min(s for _, s in solo.values())

    assert both_consistency == pytest.approx(expected_consistency, abs=0.5)
    assert both_semantic == pytest.approx(expected_semantic, abs=0.5)


def test_drift_before_stripping_corrupts_the_opaque_map():
    """Why COMPOSITION_ORDER is fixed, and not an arbitrary convention.

    SemanticStrippingInjector's opaque map is keyed on the field name it is
    handed. Run schema drift first and it is handed `price_v2` on the records
    drift touched and `price` on the rest, so ONE semantic field acquires TWO
    opaque tokens. The agent then sees `f3` and `f4` both meaning price across a
    single batch — a token instability neither fault produces alone, and one no
    AIRS dimension can see. Composing in the declared order must not do this.
    """
    from agentic_faults import SchemaDriftInjector, SemanticStrippingInjector

    def opaque_map(order):
        drift = SchemaDriftInjector(seed=1, drift_probability=0.25)
        strip = SemanticStrippingInjector(seed=2, strip_rate=0.80)
        for i in range(40):
            out = record(i)
            for step in order:
                out = drift.apply(out) if step == "drift" else strip.apply(out)
        return strip._opaque

    fields = len(record(0).payload)
    assert len(opaque_map(("drift", "strip"))) > fields  # the artifact, reproduced
    assert len(opaque_map(("strip", "drift"))) == fields  # the declared order


# ---- composition mechanics ------------------------------------------------

def test_compose_is_commutative_and_canonical():
    assert (compose_faults("schema_drift", "semantic_stripping")
            == compose_faults("semantic_stripping", "schema_drift")
            == "semantic_stripping+schema_drift")


@pytest.mark.parametrize("bad, message", [
    (("freshness", "nonsense"), "unknown fault type"),
    (("freshness", "freshness"), "cannot compose with itself"),
])
def test_compose_rejects_nonsense(bad, message):
    with pytest.raises(ValueError, match=message):
        compose_faults(*bad)


def test_fault_components_round_trips_every_pair():
    for pair in INTERACTION_PAIRS:
        assert set(fault_components(compose_faults(*pair))) == set(pair)
    assert fault_components("none") == ()
    assert fault_components("freshness") == ("freshness",)


def test_component_seeds_are_distinct():
    """Identical seeds would make the two injectors hit correlated records."""
    seeds = {f: _component_seed(80_001, f) for f in FAULT_TYPES}
    assert len(set(seeds.values())) == len(FAULT_TYPES)
    assert 80_001 not in seeds.values()


def test_compound_params_must_be_declared():
    """A missing entry must raise, not silently run at the injector default."""
    config = RunConfig(
        pipeline="streaming", task="retrieval",
        fault_type="freshness+schema_drift", severity=SEVERE, replication=1,
        injector_params={"freshness": {"delay_seconds": 5.0}},  # drift missing
        seed=80_001,
    )
    with pytest.raises(ValueError, match="no injector_params entry"):
        build_fault_chain(config)


def test_value_staleness_sees_freshness_inside_a_compound():
    """A compound must not read as 'no freshness fault'.

    The trap `fault_components` exists to close.
    """
    solo = value_staleness_s(config_for("freshness"))
    compound = value_staleness_s(config_for("freshness+schema_drift"))
    without = value_staleness_s(config_for("schema_drift"))

    assert compound == pytest.approx(solo)
    assert compound > without


# ---- quarantine -----------------------------------------------------------

def test_arm_is_seed_quarantined():
    low, high = INTERACTION_SEED_RANGE
    for config in build_interaction_arm():
        assert low <= config.seed < high
        assert arm_of(config.seed) == "interaction"


def test_main_grid_is_untouched_by_compound_support():
    """The factorial on disk must stay single-fault, whatever this arm adds."""
    for config in build_grid(replications=1):
        assert len(fault_components(config.fault_type)) <= 1
        assert arm_of(config.seed) == "main"


def test_arm_is_self_contained():
    """Baseline + every solo + every pair, so the additivity test needs no other arm."""
    arm = build_interaction_arm(replications=3)
    faults = {c.fault_type for c in arm}

    assert "none" in faults
    assert set(FAULT_TYPES) <= faults
    assert {compose_faults(*p) for p in INTERACTION_PAIRS} <= faults
    assert len(arm) == 9 * 2 * 3
    assert {c.pipeline for c in arm} == {"streaming"}


def test_pairs_and_solos_share_a_replication_seed():
    """Paired on fault realization, not merely matched.

    Within a replication every condition shares `seed` and `sample_seed`, so a
    compound run and its two solo runs see the same queries AND corrupt the same
    records. Without this the additivity contrast would carry realization noise.
    """
    arm = build_interaction_arm(replications=2)
    for task in ("retrieval", "classification"):
        for rep in (1, 2):
            cell = [c for c in arm if c.task == task and c.replication == rep]
            assert len({c.seed for c in cell}) == 1
            assert len({c.sample_seed for c in cell}) == 1


def test_postgres_schema_still_bars_compound_fault_types():
    """The quarantine is physical: invariant 7's canonical store rejects this arm.

    If someone widens the CHECK constraint, that is a deliberate decision to
    promote the arm out of provisional status — and this test is where they will
    be told they are making it.
    """
    schema = Path("src/airsbench/runner/schema.sql").read_text()
    check = re.search(r"fault_type\s+TEXT NOT NULL CHECK \(fault_type IN\s*\(([^)]*)\)",
                      schema)
    assert check, "could not locate the fault_type CHECK constraint"
    allowed = {v.strip().strip("'") for v in check.group(1).split(",")}
    assert allowed == {"none", *FAULT_TYPES}
    assert not any("+" in value for value in allowed)


@pytest.mark.parametrize("shape", ["flat", "nested"])
def test_solo_params_work_in_either_shape(shape):
    """The arm writes its solos nested; the rest of the codebase writes them flat.

    `_params_for` decided by component count and passed the nested dict straight
    to the injector (`unexpected keyword argument 'freshness'`). It failed loudly
    here only by luck — the quiet version of the same bug runs a component at its
    injector default instead of the declared severity.
    """
    params = SEVERITY_PARAMS["freshness"][SEVERE]
    config = RunConfig(
        pipeline="streaming", task="retrieval", fault_type="freshness",
        severity=SEVERE, replication=1, seed=80_001,
        injector_params=params if shape == "flat" else {"freshness": params},
    )
    build_fault_chain(config)
    assert value_staleness_s(config) == pytest.approx(
        value_staleness_s(config_for("freshness"))
    )
