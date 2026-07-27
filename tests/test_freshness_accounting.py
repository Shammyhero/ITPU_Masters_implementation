"""A record's stamped age must equal the true staleness of its values.

This is the freshness half of invariant 4. The loader serves values as of
``t_query - value_staleness_s`` (they must genuinely be old), and the AIRS
freshness dimension is computed from ``Record.age_seconds``. If those two
quantities disagree, AIRS reports a staleness the agent was never served, and
every threshold calibrated against it is wrong by that factor.

They did disagree. ``execute`` stamped ``event_ts = now - staleness`` — the
full staleness, injected delay included — and then ran FreshnessInjector, which
shifts ``event_timestamp`` back by the injected delay a second time. A severe
(5 s) streaming run therefore recorded a mean age of 10.05 s against values that
were 5.05 s stale, and scored AIRS freshness 9.95 instead of 19.8.

Nothing the agent saw was affected: records carry no timestamp unless the
detectability arm attaches one. Behavioural results from before the fix stand;
AIRS freshness values from before it do not.
"""

from __future__ import annotations

import pytest

from agentic_faults import Record
from airsbench.airs import freshness_score
from airsbench.runner.config import SEVERITY_PARAMS, RunConfig
from airsbench.runner.execute import (
    build_event_ts,
    build_fault_chain,
    inherent_staleness_s,
    value_staleness_s,
)

NOW = 1_000_000.0


def _config(pipeline: str, fault: str, severity: str) -> RunConfig:
    params = {} if fault == "none" else SEVERITY_PARAMS[fault][severity]
    return RunConfig(
        pipeline=pipeline,
        task="retrieval",
        fault_type=fault,
        severity=severity,
        replication=1,
        injector_params=dict(params),
        seed=1,
    )


def _delivered_age(config: RunConfig) -> float:
    record = Record(payload={"price": 1.0}, event_timestamp=build_event_ts(config, NOW))
    record.read_timestamp = NOW
    return build_fault_chain(config).apply(record).age_seconds(at=NOW)


def test_stamped_age_equals_value_staleness_in_every_condition():
    for pipeline in ("streaming", "batch"):
        for fault, severity in (
            ("none", "none"),
            ("freshness", "mild"),
            ("freshness", "severe"),
            ("latency", "severe"),
            ("schema_drift", "severe"),
            ("semantic_stripping", "severe"),
        ):
            config = _config(pipeline, fault, severity)
            expected = value_staleness_s(config)
            assert _delivered_age(config) == pytest.approx(expected, abs=1e-6), (
                f"{pipeline}/{fault}/{severity}: delivered age "
                f"{_delivered_age(config)} != value staleness {expected}"
            )


def test_the_injected_delay_is_counted_exactly_once():
    """The regression itself: severe freshness must age 5.05 s, not 10.05 s."""
    config = _config("streaming", "freshness", "severe")
    age = _delivered_age(config)
    assert age == pytest.approx(5.05, abs=1e-6)
    assert age != pytest.approx(10.05, abs=1e-6), "injected delay counted twice"
    assert round(freshness_score(age), 2) == 19.80


def test_inherent_staleness_is_the_only_component_stamped_before_the_chain():
    for pipeline in ("streaming", "batch"):
        config = _config(pipeline, "freshness", "severe")
        stamped = NOW - build_event_ts(config, NOW)
        assert stamped == pytest.approx(inherent_staleness_s(config), abs=1e-6)
        assert stamped < value_staleness_s(config)


def test_baseline_staleness_is_purely_inherent():
    for pipeline in ("streaming", "batch"):
        config = _config(pipeline, "none", "none")
        assert value_staleness_s(config) == inherent_staleness_s(config)
        assert _delivered_age(config) == pytest.approx(
            inherent_staleness_s(config), abs=1e-6
        )
