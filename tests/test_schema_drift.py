import pytest

from agentic_faults import Record, SchemaDriftInjector


def make_record():
    return Record(
        payload={"price": 23.5, "stock": 7, "brand": "Acme", "delay_min": "12"},
        context={"entity_type": "retail_product"},
    )


def test_rename_drifts_every_key_at_probability_one():
    injector = SchemaDriftInjector(seed=1, drift_probability=1.0, drift_types=("rename",))
    faulted = injector.apply(make_record())
    assert set(faulted.payload) == {"price_v2", "stock_v2", "brand_v2", "delay_min_v2"}
    assert faulted.payload["price_v2"] == 23.5


def test_retype_converts_numbers_and_numeric_strings():
    injector = SchemaDriftInjector(seed=1, drift_probability=1.0, drift_types=("retype",))
    faulted = injector.apply(make_record())
    assert faulted.payload["price"] == "23.5"     # float -> str
    assert faulted.payload["stock"] == "7"        # int -> str
    assert faulted.payload["delay_min"] == 12.0   # numeric str -> float
    assert faulted.payload["brand"] == "Acme"     # non-numeric str untouched


def test_value_shift_rescales_numbers_and_relabels_categories():
    injector = SchemaDriftInjector(seed=5, drift_probability=1.0, drift_types=("value_shift",))
    faulted = injector.apply(make_record())
    assert faulted.payload["price"] in (23.5 * 0.01, 23.5 * 60, 23.5 * 100)
    assert faulted.payload["brand"].startswith("category_")


def test_categorical_relabeling_is_stable_across_records():
    injector = SchemaDriftInjector(seed=5, drift_probability=1.0, drift_types=("value_shift",))
    first = injector.apply(Record(payload={"brand": "Acme"}))
    second = injector.apply(Record(payload={"brand": "Acme"}))
    assert first.payload["brand"] == second.payload["brand"]


def test_zero_probability_changes_nothing():
    injector = SchemaDriftInjector(seed=1, drift_probability=0.0)
    original = make_record()
    faulted = injector.apply(original)
    assert faulted.payload == original.payload


def test_input_record_is_not_mutated():
    injector = SchemaDriftInjector(seed=1, drift_probability=1.0)
    original = make_record()
    snapshot = dict(original.payload)
    injector.apply(original)
    assert original.payload == snapshot


def test_mild_severity_drifts_roughly_five_percent_of_fields():
    injector = SchemaDriftInjector(seed=11, drift_probability=0.05, drift_types=("rename",))
    drifted = 0
    total = 0
    for _ in range(500):
        faulted = injector.apply(make_record())
        drifted += sum(1 for k in faulted.payload if k.endswith("_v2"))
        total += 4
    assert 0.02 <= drifted / total <= 0.09


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        SchemaDriftInjector(drift_probability=1.5)
    with pytest.raises(ValueError):
        SchemaDriftInjector(drift_probability=0.5, drift_types=("teleport",))
