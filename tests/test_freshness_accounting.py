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

from pathlib import Path

import pytest

from agentic_faults import Record
from airsbench.agents.llm import LLMUsage
from airsbench.agents.prompts import RECORD_AGE_FIELD
from airsbench.airs import freshness_score
from airsbench.runner.config import SEVERITY_PARAMS, RunConfig
from airsbench.runner.execute import (
    build_event_ts,
    build_fault_chain,
    inherent_staleness_s,
    run_classification,
    run_retrieval,
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


# ---- end to end, through the real runner -----------------------------------
#
# The unit tests above exercise build_event_ts and the chain in isolation. The
# quantity that actually lands in the run artifact is computed further down, in
# _airs_components, from ages collected per query inside the run loops. Driving
# the real loops with a stub client checks the whole path for free.

DATA_ROOTS = {"retrieval": Path("data/ecommerce"), "classification": Path("data/airline")}

needs_data = pytest.mark.skipif(
    not all((root / f).exists()
            for task, root in DATA_ROOTS.items()
            for f in (["updates.jsonl"] if task == "retrieval" else ["flights.parquet"])),
    reason="prepared datasets not present",
)


class _StubClient:
    """Answers without an API call, and remembers what it was shown."""

    def __init__(self) -> None:
        self.usage = LLMUsage()
        self.seen: list[str] = []

    def call_json(self, messages):
        self.seen.append(dict(messages)["user"])
        self.usage.add(10, 5, 1.0)
        return {"product_id": "X", "price": 1.0, "confidence": 0.5,
                "abstain": False, "delayed": False}


def _run_offline(config: RunConfig):
    runner = run_retrieval if config.task == "retrieval" else run_classification
    client = _StubClient()
    _, airs, _ = runner(config, DATA_ROOTS[config.task], client)
    return airs, client


@needs_data
@pytest.mark.parametrize("task", ["retrieval", "classification"])
@pytest.mark.parametrize("pipeline", ["streaming", "batch"])
@pytest.mark.parametrize(
    "fault,severity",
    [("none", "none"), ("freshness", "mild"), ("freshness", "severe"),
     ("schema_drift", "severe"), ("semantic_stripping", "severe")],
)
def test_recorded_airs_freshness_equals_the_true_value_staleness(
    task, pipeline, fault, severity
):
    config = _config(pipeline, fault, severity)
    config.task, config.n_queries = task, 6
    airs, _ = _run_offline(config)
    expected = freshness_score(value_staleness_s(config))
    assert airs["freshness"] == pytest.approx(expected, abs=0.05)


@needs_data
def test_the_regression_would_be_caught_end_to_end():
    """The artifact value itself: 19.80, not the 9.95 that was recorded."""
    config = _config("streaming", "freshness", "severe")
    config.n_queries = 6
    airs, _ = _run_offline(config)
    assert airs["freshness"] == pytest.approx(19.80, abs=0.05)


@needs_data
@pytest.mark.parametrize("task", ["retrieval", "classification"])
def test_delivering_record_age_does_not_change_the_airs_freshness_score(task):
    """The detectability treatment must not perturb the measurement."""
    scores = {}
    for emit in (False, True):
        config = _config("streaming", "freshness", "severe")
        config.task, config.n_queries, config.emit_record_age = task, 6, emit
        airs, client = _run_offline(config)
        scores[emit] = airs["freshness"]
        shown = any(RECORD_AGE_FIELD in message for message in client.seen)
        assert shown is emit, f"age field {'missing' if emit else 'leaked'}"
    assert scores[False] == pytest.approx(scores[True], abs=0.05)


@needs_data
def test_the_age_shown_to_the_agent_is_the_true_staleness():
    """Condition B must not overstate the age — that would be a different arm."""
    config = _config("streaming", "freshness", "severe")
    config.n_queries, config.emit_record_age = 6, True
    _, client = _run_offline(config)
    shown = {
        round(float(line.split(":")[1].strip().rstrip(",")), 2)
        for message in client.seen
        for line in message.splitlines()
        if RECORD_AGE_FIELD in line
    }
    assert len(shown) == 1, f"age must be constant within a run, saw {shown}"
    assert shown.pop() == pytest.approx(value_staleness_s(config), abs=0.01)
