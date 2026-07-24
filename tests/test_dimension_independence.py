"""AIRS dimensions must move independently.

RQ2 ranks the four dimensions by effect, and RQ4 fits a logistic
regression over all four. Both require that a fault targeting one
dimension does not depress another; otherwise the predictors are
collinear and their effects cannot be attributed separately.
"""

from __future__ import annotations

import pytest

from agentic_faults import (
    FreshnessInjector,
    LatencyInjector,
    Record,
    SchemaDriftInjector,
    SemanticStrippingInjector,
)
from airsbench.airs import payload_consistency, semantic_completeness


def make_record():
    return Record(
        payload={"price": 23.5, "stock": 7, "brand": "Acme"},
        context={
            "entity_type": "retail_product",
            "units": {"price": "USD"},
            "descriptions": {"price": "current listed price"},
            "relationships": {"product_id": "joins to queries"},
        },
    )


def test_semantic_stripping_does_not_depress_consistency():
    source = make_record()
    stripped = SemanticStrippingInjector(seed=1, strip_rate=1.0).apply(source)

    # Meaning is destroyed ...
    assert semantic_completeness(stripped) == 0.0
    # ... but no value disagrees across stages, so consistency is intact.
    assert payload_consistency(source, stripped) == 1.0


def test_schema_drift_does_not_depress_semantic_completeness():
    source = make_record()
    drifted = SchemaDriftInjector(seed=1, drift_probability=1.0).apply(source)

    assert payload_consistency(source, drifted) < 1.0
    assert semantic_completeness(drifted) == 1.0


def test_freshness_and_latency_touch_neither():
    source = make_record()
    stale = FreshnessInjector(seed=1, delay_seconds=5.0).apply(source)
    slow = LatencyInjector(seed=1, spike_ms=3000, sleep=False).apply(source)

    for faulted in (stale, slow):
        assert payload_consistency(source, faulted) == 1.0
        assert semantic_completeness(faulted) == 1.0


def test_partial_stripping_scales_semantic_only():
    source = make_record()
    partial = SemanticStrippingInjector(
        seed=1, strip_rate=1.0, strip_targets=("units", "relationships")
    ).apply(source)

    assert semantic_completeness(partial) == pytest.approx(0.5)
    assert payload_consistency(source, partial) == 1.0


def test_combined_faults_each_show_in_their_own_dimension():
    source = make_record()
    stripped = SemanticStrippingInjector(seed=1, strip_rate=1.0).apply(source)
    both = SchemaDriftInjector(
        seed=2, drift_probability=1.0, drift_types=("value_shift",)
    ).apply(stripped)

    assert semantic_completeness(both) == 0.0     # semantic fault visible
    assert payload_consistency(source, both) < 1.0  # drift visible, via reversal
