"""The detectability arm must vary detectability and nothing else.

Design: docs/detectability_arm.md. The arm's whole claim is that A and B differ
in exactly one respect — whether the delivered record carries its own age — so
any behavioural difference is attributable to legibility rather than to the
fault, the queries, or the prompt. Each of those "nothing else"es is pinned
here, because a violation would leave the arm looking like it worked while
measuring something else.
"""

from __future__ import annotations

import pytest

from agentic_faults import Record
from airsbench.agents.prompts import (
    CLASSIFICATION_SYSTEM,
    CLASSIFICATION_USER,
    RECORD_AGE_FIELD,
    RETRIEVAL_SYSTEM,
    RETRIEVAL_USER,
    classification_messages,
    render_record,
    retrieval_messages,
)
from airsbench.airs import mean_semantic_completeness, payload_consistency
from airsbench.runner.config import build_detectability_arm, build_grid
from airsbench.runner.execute import attach_record_age


def _record() -> Record:
    record = Record(
        payload={"product_id": "A1", "price": 12.99, "stock": 4},
        context={"entity_type": "product", "units": {"price": "USD"},
                 "descriptions": {"price": "unit price"}, "relationships": {}},
        event_timestamp=1_000.0,
    )
    record.read_timestamp = 1_005.0
    return record


def _pairs(arm):
    """Group the arm's freshness runs into (A, B) pairs by task and replication."""
    faulted = [c for c in arm if c.fault_type == "freshness"]
    keyed = {}
    for cfg in faulted:
        keyed.setdefault((cfg.task, cfg.replication), {})[cfg.emit_record_age] = cfg
    return list(keyed.values())


# ---- the grid --------------------------------------------------------------

def test_arm_is_fourteen_runs_as_costed():
    arm = build_detectability_arm()
    assert len(arm) == 14
    assert sum(c.fault_type == "freshness" for c in arm) == 12
    assert sum(c.fault_type == "none" for c in arm) == 2


def test_every_freshness_condition_is_paired_on_metadata():
    pairs = _pairs(build_detectability_arm())
    assert len(pairs) == 6  # 2 tasks x 3 replications
    for pair in pairs:
        assert set(pair) == {False, True}, "each condition needs both arms"


def test_pairs_differ_only_in_the_metadata_flag():
    """Same queries, same times, same fault realization — one field apart."""
    for pair in _pairs(build_detectability_arm()):
        a, b = pair[False], pair[True]
        assert a.sample_seed == b.sample_seed, "paired design: identical queries"
        assert a.seed == b.seed, "identical fault realization"
        differing = {
            field
            for field in a.to_dict()
            if field != "run_id" and a.to_dict()[field] != b.to_dict()[field]
        }
        assert differing == {"emit_record_age"}, f"unexpected differences: {differing}"


def test_baselines_carry_the_metadata_to_test_over_caution():
    """Baselines without metadata already exist; the open cell is with it."""
    baselines = [c for c in build_detectability_arm() if c.fault_type == "none"]
    assert {c.task for c in baselines} == {"retrieval", "classification"}
    assert all(c.emit_record_age for c in baselines)


def test_arm_is_streaming_only():
    """Batch's inherent 3 s staleness would blur the contrast."""
    assert {c.pipeline for c in build_detectability_arm()} == {"streaming"}


def test_arm_seeds_do_not_collide_with_the_main_factorial():
    main_seeds = {c.seed for c in build_grid(replications=4)}
    assert not main_seeds & {c.seed for c in build_detectability_arm()}


def test_main_factorial_never_emits_record_age():
    assert not any(c.emit_record_age for c in build_grid(replications=4))


# ---- what reaches the agent ------------------------------------------------

def test_age_is_absent_unless_attached():
    assert RECORD_AGE_FIELD not in render_record(_record())


def test_attached_age_is_rendered_and_truthful():
    record = _record()
    attach_record_age(record, 1_005.0)
    rendered = render_record(record)
    assert rendered[RECORD_AGE_FIELD] == pytest.approx(5.0)


def test_age_is_measured_at_delivery_not_at_record_creation():
    record = _record()
    attach_record_age(record, 1_007.5)
    assert render_record(record)[RECORD_AGE_FIELD] == pytest.approx(7.5)


def test_metadata_does_not_enter_the_payload_or_context():
    """Invariant 5: it must not move an AIRS dimension it is not measuring."""
    before = _record()
    after = _record()
    attach_record_age(after, 1_005.0)
    assert after.payload == before.payload
    assert after.context == before.context
    assert payload_consistency(before, after) == 1.0
    assert mean_semantic_completeness([after]) == mean_semantic_completeness([before])


def test_system_prompts_are_byte_identical_across_the_two_arms():
    """Invariant 1: the prompt is a control variable, in this arm too."""
    plain, aged = _record(), _record()
    attach_record_age(aged, 1_005.0)

    for messages in (retrieval_messages("q", [plain]), retrieval_messages("q", [aged])):
        assert dict(messages)["system"] == RETRIEVAL_SYSTEM
    for messages in (classification_messages(plain), classification_messages(aged)):
        assert dict(messages)["system"] == CLASSIFICATION_SYSTEM


def test_user_messages_differ_only_by_the_rendered_age_field():
    plain, aged = _record(), _record()
    attach_record_age(aged, 1_005.0)
    a = dict(retrieval_messages("q", [plain]))["user"]
    b = dict(retrieval_messages("q", [aged]))["user"]
    assert a != b
    added = [line for line in b.splitlines() if line not in a.splitlines()]
    assert all(RECORD_AGE_FIELD in line for line in added), added


def test_no_prompt_text_hints_that_age_matters():
    """If the prompt said 'distrust old data' the arm would measure obedience."""
    forbidden = ("stale", "fresh", "age", "old", "outdated", "recent", "timestamp")
    for prompt in (RETRIEVAL_SYSTEM, RETRIEVAL_USER,
                   CLASSIFICATION_SYSTEM, CLASSIFICATION_USER):
        lowered = prompt.lower()
        for word in forbidden:
            assert word not in lowered, f"prompt hints at freshness: {word!r}"


def test_only_the_age_field_differs_between_the_two_rendered_records():
    plain, aged = _record(), _record()
    attach_record_age(aged, 1_005.0)
    rendered_plain, rendered_aged = render_record(plain), render_record(aged)
    assert set(rendered_aged) - set(rendered_plain) == {RECORD_AGE_FIELD}
    for key in rendered_plain:
        assert rendered_plain[key] == rendered_aged[key]


def test_other_injector_bookkeeping_still_never_reaches_the_agent():
    record = _record()
    record.meta["faults"] = [{"injector": "freshness", "delay_seconds": 5.0}]
    record.meta["injected_latency_ms"] = 3000
    rendered = render_record(record)
    assert "faults" not in str(rendered)
    assert "injected_latency_ms" not in rendered
