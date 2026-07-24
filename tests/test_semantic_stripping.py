import pytest

from agentic_faults import Record, SemanticStrippingInjector


def make_record():
    return Record(
        payload={"val": 23, "src": "A"},
        context={
            "entity_type": "flight",
            "units": {"val": "minutes"},
            "descriptions": {"val": "arrival delay", "src": "carrier code"},
            "relationships": {"src": "joins to carrier reference"},
        },
    )


def test_full_strip_removes_all_context():
    injector = SemanticStrippingInjector(seed=1, strip_rate=1.0)
    faulted = injector.apply(make_record())
    assert faulted.context == {}
    assert faulted.meta["faults"][0]["stripped"] == [
        "entity_type", "units", "descriptions", "relationships",
    ]
    # payload must be untouched — stripping removes meaning, not data
    assert faulted.payload == {"val": 23, "src": "A"}


def test_zero_strip_rate_keeps_context_intact():
    injector = SemanticStrippingInjector(seed=1, strip_rate=0.0)
    faulted = injector.apply(make_record())
    assert faulted.context == make_record().context
    assert "faults" not in faulted.meta


def test_custom_targets_limit_what_is_stripped():
    injector = SemanticStrippingInjector(seed=1, strip_rate=1.0, strip_targets=("units",))
    faulted = injector.apply(make_record())
    assert "units" not in faulted.context
    assert "entity_type" in faulted.context
    assert "descriptions" in faulted.context


def test_mild_severity_strips_roughly_thirty_percent():
    injector = SemanticStrippingInjector(seed=9, strip_rate=0.30)
    stripped = 0
    total = 0
    for _ in range(500):
        faulted = injector.apply(make_record())
        stripped += 4 - len(faulted.context)
        total += 4
    assert 0.25 <= stripped / total <= 0.35


def test_input_record_is_not_mutated():
    injector = SemanticStrippingInjector(seed=1, strip_rate=1.0)
    original = make_record()
    injector.apply(original)
    assert len(original.context) == 4


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        SemanticStrippingInjector(strip_rate=1.5)
    with pytest.raises(ValueError):
        SemanticStrippingInjector(strip_rate=0.5, strip_targets=())
