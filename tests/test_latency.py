import time

import pytest

from agentic_faults import LatencyInjector, Record, verify_latency


def test_no_sleep_mode_records_injected_latency():
    injector = LatencyInjector(seed=1, spike_ms=500, sleep=False)
    faulted = injector.apply(Record(payload={"x": 1}))
    assert faulted.meta["injected_latency_ms"] == 500
    assert faulted.meta["faults"][0]["injector"] == "latency"


def test_zero_probability_never_fires():
    injector = LatencyInjector(seed=1, spike_ms=500, spike_probability=0.0, sleep=False)
    for _ in range(50):
        faulted = injector.apply(Record(payload={}))
        assert "injected_latency_ms" not in faulted.meta


def test_probabilistic_mode_fires_at_configured_rate():
    injector = LatencyInjector(seed=3, spike_ms=100, spike_probability=0.3, sleep=False)
    fired = sum(
        "injected_latency_ms" in injector.apply(Record(payload={})).meta for _ in range(1000)
    )
    assert 240 <= fired <= 360  # 0.3 +/- generous binomial margin


def test_sleep_mode_actually_delays():
    injector = LatencyInjector(seed=1, spike_ms=30, sleep=True)
    start = time.perf_counter()
    injector.apply(Record(payload={}))
    assert (time.perf_counter() - start) >= 0.030


def test_latency_accumulates_across_applications():
    injector = LatencyInjector(seed=1, spike_ms=200, sleep=False)
    record = injector.apply(injector.apply(Record(payload={})))
    assert record.meta["injected_latency_ms"] == 400


def test_verification_mode_within_tolerance():
    injector = LatencyInjector(seed=1, spike_ms=50, sleep=True)
    result = verify_latency(injector, tolerance_ms=50.0, trials=5)
    assert result.passed, result.summary()


def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        LatencyInjector(spike_ms=-1)
    with pytest.raises(ValueError):
        LatencyInjector(spike_ms=100, spike_probability=1.5)
