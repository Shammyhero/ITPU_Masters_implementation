"""Field-name opacity: the mechanism that makes semantic stripping bite.

Removing the context block alone leaves self-documenting keys ("DepDelay",
"price") from which an LLM recovers the meaning, so the fault was
measurably toothless in the first smoke test. These tests pin the fixed
behaviour and the distinction from schema drift.
"""

from __future__ import annotations

from agentic_faults import Record, SchemaDriftInjector, SemanticStrippingInjector


def make_record():
    return Record(
        payload={"price": 23.5, "stock": 7},
        context={
            "entity_type": "retail_product",
            "units": {"price": "USD"},
            "descriptions": {"price": "current listed price"},
            "relationships": {"product_id": "joins to queries"},
        },
    )


def test_stripping_descriptions_opaquifies_field_names():
    injector = SemanticStrippingInjector(seed=1, strip_rate=1.0)
    faulted = injector.apply(make_record())

    assert "price" not in faulted.payload
    assert set(faulted.payload) == {"f1", "f2"}
    assert sorted(faulted.payload.values()) == [7, 23.5]  # values survive intact
    assert "field_names" in faulted.meta["faults"][0]["stripped"]


def test_opacity_is_stable_across_records():
    injector = SemanticStrippingInjector(seed=1, strip_rate=1.0)
    first = injector.apply(make_record())
    second = injector.apply(make_record())
    assert list(first.payload) == list(second.payload)


def test_opacity_can_be_disabled_to_isolate_context_removal():
    injector = SemanticStrippingInjector(seed=1, strip_rate=1.0, opaque_field_names=False)
    faulted = injector.apply(make_record())
    assert set(faulted.payload) == {"price", "stock"}
    assert faulted.context == {}


def test_names_survive_when_descriptions_survive():
    # strip only units: descriptions remain, so names must remain readable
    injector = SemanticStrippingInjector(seed=1, strip_rate=1.0, strip_targets=("units",))
    faulted = injector.apply(make_record())
    assert set(faulted.payload) == {"price", "stock"}


def test_stripping_destroys_meaning_where_drift_only_relocates_it():
    """Drift renames to a recoverable name; stripping to a meaningless token."""
    drifted = SchemaDriftInjector(seed=1, drift_probability=1.0,
                                  drift_types=("rename",)).apply(make_record())
    stripped = SemanticStrippingInjector(seed=1, strip_rate=1.0).apply(make_record())

    assert all("price" in key or "stock" in key for key in drifted.payload)
    assert not any("price" in key or "stock" in key for key in stripped.payload)
