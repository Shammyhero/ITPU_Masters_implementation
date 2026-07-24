import statistics

import pytest

from agentic_faults import FreshnessInjector, Record, verify_freshness


def test_constant_delay_shifts_age_exactly():
    injector = FreshnessInjector(seed=1, delay_seconds=3.0)
    original = Record(payload={"price": 9.99})
    faulted = injector.apply(original)

    injected = original.event_timestamp - faulted.event_timestamp
    assert injected == pytest.approx(3.0, abs=1e-9)
    # measured age at the original event time equals exactly the injected delay
    assert faulted.age_seconds(at=original.event_timestamp) == pytest.approx(3.0, abs=1e-9)


def test_input_record_is_not_mutated():
    injector = FreshnessInjector(seed=1, delay_seconds=3.0)
    original = Record(payload={"price": 9.99})
    ts_before = original.event_timestamp
    injector.apply(original)
    assert original.event_timestamp == ts_before
    assert original.meta == {}


def test_poisson_mode_has_configured_mean():
    injector = FreshnessInjector(seed=7, delay_seconds=3.0, distribution="poisson")
    samples = []
    for _ in range(2000):
        original = Record(payload={})
        faulted = injector.apply(original)
        samples.append(injector.injected_delay(original, faulted))
    assert statistics.fmean(samples) == pytest.approx(3.0, abs=0.3)


def test_verification_mode_within_tolerance():
    # Research-plan acceptance criterion: 3s injected -> measured 3s +/- 200ms
    injector = FreshnessInjector(seed=1, delay_seconds=3.0)
    result = verify_freshness(injector, tolerance_s=0.2, trials=100)
    assert result.passed, result.summary()


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        FreshnessInjector(delay_seconds=-1.0)
    with pytest.raises(ValueError):
        FreshnessInjector(delay_seconds=1.0, distribution="uniform")
