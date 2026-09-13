"""Tests for the AIRS admission controller.

Two of these pin properties whose violation would be silent and dangerous:

- `test_unmeasured_dimension_is_a_violation` — a policy naming a dimension the
  probe could not measure must REFUSE, not admit. Admitting on an absent
  measurement is the failure mode that makes a gate worse than no gate: it
  issues a clean bill of health precisely because nobody looked.
- `test_controller_and_replay_agree` — the offline replay in
  `docs/gate_findings.md` is only evidence about the live controller if the two
  apply the same rules. They are separate implementations (one measures raw
  records, one reads already-scored runs), so the agreement needs pinning.
"""

from __future__ import annotations

import json

import pytest

from airsbench.gate import BatchRefused, Controller, Policy
from airsbench.gate.replay import Batch, Outcome, evaluate_batch, replay
from airsbench.probe import composite, measure

WEIGHTS = {"freshness": 0.13, "latency": 0.0, "consistency": 0.70, "semantic": 0.17}


def records(age_s: float, n: int = 4, drift: bool = False, context: bool = True):
    """Records the probe can score on all four dimensions."""
    source, delivered = [], []
    for i in range(n):
        ctx = {"entity_type": "product", "units": {"price": "USD"},
               "descriptions": {"price": "unit price"}, "relationships": {}}
        source.append({
            "id": f"SKU-{i}", "payload": {"price": 10.0 + i, "stock": 3},
            "context": ctx, "event_timestamp": 1_000.0,
            "read_timestamp": 1_000.0, "delivery_latency_ms": 50.0,
        })
        delivered.append({
            "id": f"SKU-{i}",
            "payload": {"price": 99.0 if drift else 10.0 + i, "stock": 3},
            "context": ctx if context else {},
            "event_timestamp": 1_000.0,
            "read_timestamp": 1_000.0 + age_s,
            "delivery_latency_ms": 50.0,
        })
    return source, delivered


# ---- policy validation ----------------------------------------------------

@pytest.mark.parametrize("kwargs, message", [
    ({"min_dimension": {"frehsness": 50}}, "unknown dimension"),
    ({"min_dimension": {"freshness": 140}}, "must be 0-100"),
    ({"min_airs": -1}, "must be 0-100"),
    ({"max_record_age_seconds": -5}, "must be >= 0"),
    ({"on_violation": "explode"}, "reject"),
])
def test_policy_rejects_nonsense(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Policy(**kwargs)


def test_policy_rejects_unknown_field():
    """A typo'd field must not silently become a policy that checks nothing."""
    with pytest.raises(ValueError, match="unknown policy field"):
        Policy.from_dict({"name": "p", "max_age_seconds": 5.0})


def test_policy_round_trips():
    policy = Policy(name="p", max_record_age_seconds=3.0,
                    min_dimension={"consistency": 90.0}, min_airs=80.0)
    assert Policy.from_dict(json.loads(json.dumps(policy.to_dict()))) == policy


def test_empty_policy_admits_and_says_so():
    policy = Policy(name="empty")
    assert not policy.checks_anything
    assert "checks nothing" in policy.describe()
    source, delivered = records(age_s=9_999.0)
    assert Controller(policy, WEIGHTS).evaluate(delivered, source).admitted


# ---- the rules ------------------------------------------------------------

def test_age_budget_admits_fresh_refuses_stale():
    policy = Policy(name="budget", max_record_age_seconds=3.0)
    gate = Controller(policy, WEIGHTS)

    assert gate.evaluate(*reversed(records(age_s=1.0))).admitted
    verdict = gate.evaluate(*reversed(records(age_s=5.0)))

    assert not verdict.admitted
    assert "5.00s old, budget is 3.00s" in verdict.reason
    assert verdict.violations[0].rule == "max_record_age_seconds"
    assert (gate.admitted, gate.refused) == (1, 1)


def test_dimension_floor_catches_drift_the_age_budget_misses():
    """The finding in one test: the gates are not interchangeable.

    A batch can be perfectly fresh and still be corrupted. An age budget — the
    rule the thesis originally recommended — admits it; a consistency floor,
    which the RQ4 weights say carries 70% of retrieval risk, catches it.
    """
    source, delivered = records(age_s=0.5, drift=True)

    age_only = Controller(Policy(max_record_age_seconds=3.0), WEIGHTS)
    consistency = Controller(
        Policy(min_dimension={"consistency": 90.0}), WEIGHTS)

    assert age_only.evaluate(delivered, source).admitted
    assert not consistency.evaluate(delivered, source).admitted


def test_unmeasured_dimension_is_a_violation():
    """"We did not look" must never be recorded as "it is fine"."""
    _, delivered = records(age_s=1.0)
    policy = Policy(min_dimension={"consistency": 90.0})

    # No source sample, so consistency is unmeasurable.
    verdict = Controller(policy, WEIGHTS).evaluate(delivered, source=None)
    assert not verdict.admitted
    assert "could not be measured" in verdict.reason
    assert verdict.dimensions["consistency"]["score"] is None

    relaxed = Controller(
        Policy(min_dimension={"consistency": 90.0},
               unmeasured_is_violation=False), WEIGHTS)
    assert relaxed.evaluate(delivered, source=None).admitted


def test_missing_timestamps_cannot_satisfy_an_age_budget():
    _, delivered = records(age_s=1.0)
    for record in delivered:
        record.pop("event_timestamp")
        record.pop("read_timestamp")

    verdict = Controller(
        Policy(max_record_age_seconds=3.0), WEIGHTS).evaluate(delivered)
    assert not verdict.admitted
    assert "cannot be shown to hold" in verdict.reason


def test_composite_excludes_unmeasured_weight():
    """A gate must not score a pipeline well because most of it went unchecked."""
    _, delivered = records(age_s=1.0)
    airs, covered = composite(measure(delivered, None), WEIGHTS)
    assert covered == pytest.approx(1.0 - WEIGHTS["consistency"])
    assert airs is not None


def test_shadow_mode_admits_but_records():
    policy = Policy(name="candidate", max_record_age_seconds=1.0).shadow()
    verdict = Controller(policy, WEIGHTS).evaluate(*reversed(records(age_s=9.0)))

    assert verdict.admitted and verdict.shadowed
    assert verdict.violations
    assert "shadow mode despite" in verdict.reason
    verdict.raise_for_status()  # shadow mode must not raise


def test_raise_for_status_carries_the_verdict():
    gate = Controller(Policy(name="strict", max_record_age_seconds=0.0), WEIGHTS)
    verdict = gate.evaluate(*reversed(records(age_s=4.0)))
    with pytest.raises(BatchRefused) as excinfo:
        verdict.raise_for_status()
    assert excinfo.value.verdict is verdict


# ---- what the gate accepts and emits ----------------------------------------

def _jsonl(path, entries):
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


def test_gate_json_stays_valid_json_when_a_rule_could_not_be_measured(tmp_path, capsys):
    """An unmeasured rule has no observed value. Python would print NaN, which
    is not JSON — and the verdict refused for an unmeasured rule is exactly the
    one another tool most needs to read."""
    from airsbench.gate.__main__ import main

    _, delivered = records(age_s=1.0)
    batch = _jsonl(tmp_path / "batch.jsonl", delivered)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"min_dimension": {"consistency": 90.0}}))

    assert main(["--records", str(batch), "--policy", str(policy), "--json"]) == 1

    def no_constants(token):
        raise AssertionError(f"{token} in gate JSON output")

    verdict = json.loads(capsys.readouterr().out, parse_constant=no_constants)
    assert verdict["violations"][0]["observed"] is None
    assert verdict["dimensions"]["consistency"]["score"] is None


def test_gate_bad_input_exits_2_with_a_message_not_a_traceback(tmp_path, capsys):
    """The duplicate is found while measuring, inside the controller — that
    path must be guarded as well as the file loading."""
    from airsbench.gate.__main__ import main

    source, delivered = records(age_s=1.0)
    upstream = _jsonl(tmp_path / "source.jsonl", source + source[:1])
    batch = _jsonl(tmp_path / "batch.jsonl", delivered)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"max_record_age_seconds": 3.0}))

    assert main(["--records", str(batch), "--source", str(upstream),
                 "--policy", str(policy)]) == 2
    assert "appears on lines 1 and 5" in capsys.readouterr().err


def test_the_age_budget_reads_iso_timestamps_as_the_probe_does():
    _, delivered = records(age_s=5.0)
    for record in delivered:
        record["event_timestamp"] = "2026-09-13T10:00:00Z"
        record["read_timestamp"] = "2026-09-13T10:00:05+00:00"
    verdict = Controller(Policy(max_record_age_seconds=3.0), WEIGHTS).evaluate(delivered)
    assert not verdict.admitted
    assert "5.00s old, budget is 3.00s" in verdict.reason
    assert verdict.record_age_seconds == pytest.approx(5.0)


@pytest.mark.parametrize("data, message", [
    ([], "must be a JSON object"),
    ({"min_airs": "80"}, "must be a number"),
    ({"min_dimension": {"consistency": True}}, "must be a number"),
    ({"unmeasured_is_violation": "yes"}, "true or false"),
])
def test_policy_files_with_the_wrong_types_are_refused(data, message):
    """"80" is not a floor of 80, and `true` is not a floor of 1."""
    with pytest.raises(ValueError, match=message):
        Policy.from_dict(data)


# ---- the replay agrees with the live gate ---------------------------------

@pytest.mark.parametrize("age, drift, policy", [
    (0.5, False, Policy(max_record_age_seconds=3.0)),
    (9.0, False, Policy(max_record_age_seconds=3.0)),
    (0.5, True, Policy(min_dimension={"consistency": 90.0})),
    (0.5, False, Policy(min_dimension={"consistency": 90.0})),
    (9.0, True, Policy(min_airs=85.0)),
    (0.5, False, Policy(min_airs=85.0)),
    (9.0, False, Policy(max_record_age_seconds=3.0, min_airs=99.0)),
])
def test_controller_and_replay_agree(age, drift, policy):
    """Same batch, same policy, same verdict — via two implementations.

    `docs/gate_findings.md` is produced entirely by the replay path. If the
    replay were more permissive than the controller the reported numbers would
    understate what a deployed gate does, and nothing else would catch it.
    """
    source, delivered = records(age_s=age, drift=drift)
    measured = measure(delivered, source)
    live = Controller(policy, WEIGHTS).evaluate(delivered, source)

    batch = Batch(
        run_id="synthetic", task="retrieval", model="none", fault="none",
        severity="none",
        dims={d: measured[d]["score"] for d in WEIGHTS},
        record_age_seconds=age, n=10, correct=6, silent=3, abstained=1,
    )
    offline = evaluate_batch(batch, policy, WEIGHTS)

    assert live.admitted == offline.admitted, (live.reason, offline.reason)
    assert [v.rule for v in live.violations] == [v.rule for v in offline.violations]
    assert live.airs == pytest.approx(offline.airs)


# ---- the accounting -------------------------------------------------------

def _batch(run_id, dims, age, n, correct, silent):
    return Batch(run_id=run_id, task="retrieval", model="m", fault="none",
                 severity="none", dims=dims, record_age_seconds=age, n=n,
                 correct=correct, silent=silent, abstained=n - correct - silent)


CLEAN = {"freshness": 100.0, "latency": 100.0, "consistency": 100.0, "semantic": 100.0}
DIRTY = {"freshness": 20.0, "latency": 100.0, "consistency": 10.0, "semantic": 30.0}


@pytest.fixture
def corpus():
    return [_batch("clean", CLEAN, 0.5, 100, 80, 10),
            _batch("dirty", DIRTY, 9.0, 100, 40, 50)]


def test_no_gate_is_the_baseline(corpus):
    out = replay(corpus, Policy(name="no gate"), WEIGHTS)
    assert out.coverage == 1.0
    assert out.prevented == 0 and out.forfeited == 0
    assert out.residual_silent_rate == out.baseline_silent_rate == pytest.approx(0.30)
    assert out.exchange_rate == float("inf")


def test_gate_accounting_is_two_sided(corpus):
    out = replay(corpus, Policy(name="strict", min_airs=90.0), WEIGHTS)

    assert out.refused_batches == 1
    assert out.coverage == pytest.approx(0.5)
    assert out.prevented == 50 and out.forfeited == 40
    assert out.residual_silent_rate == pytest.approx(0.10)
    assert out.exchange_rate == pytest.approx(40 / 50)


def test_refusing_everything_prevents_everything_and_is_useless(corpus):
    """The reason `coverage` is reported beside `prevented`, in a test."""
    out = replay(corpus, Policy(name="paranoid", max_record_age_seconds=0.0), WEIGHTS)
    assert out.prevented_share == 1.0
    assert out.coverage == 0.0
    assert out.residual_silent_rate == 0.0  # vacuously — nothing got through


@pytest.mark.parametrize("policy", [
    Policy(name="a", min_airs=90.0),
    Policy(name="b", max_record_age_seconds=3.0),
    Policy(name="c", min_dimension={"consistency": 50.0}),
    Policy(name="d", max_record_age_seconds=0.0),
    Policy(name="none"),
])
def test_conservation_identities_hold(corpus, policy):
    out = replay(corpus, policy, WEIGHTS)
    total = Outcome("t", 0, 0, out.decisions, out.decisions, out.silent_total,
                    out.silent_total, out.correct_total, out.correct_total)

    assert out.prevented + out.silent_admitted == total.silent_total
    assert out.forfeited + out.correct_admitted == total.correct_total
    assert 0.0 <= out.coverage <= 1.0
    assert 0.0 <= out.prevented_share <= 1.0
    assert out.admitted_decisions <= out.decisions


def test_the_fault_free_floor_is_a_pooled_rate_with_its_range(corpus):
    from airsbench.gate.replay import fault_free_baseline

    corpus[1].fault = "schema_drift"  # the dirty batch is faulted, so not part of the floor
    corpus.append(_batch("clean-2", CLEAN, 0.5, 300, 240, 60))
    floor = fault_free_baseline(corpus)
    assert floor["rate"] == pytest.approx((10 + 60) / (100 + 300))
    assert (floor["min"], floor["max"], floor["pipelines"]) == (0.10, 0.20, 2)
    assert fault_free_baseline([corpus[1]]) is None, "no healthy pipeline, no floor"


def test_outcome_json_has_no_infinity(corpus):
    """No gate prevents nothing, so its exchange rate is infinite — null in JSON."""
    data = replay(corpus, Policy(name="no gate"), WEIGHTS).to_dict()
    assert data["exchange_rate"] is None
    json.dumps(data, allow_nan=False)


# ---- attribution ----------------------------------------------------------

def test_attribution_credits_only_excess_silent_failure(capsys):
    """A gate must not be credited with failures that would have happened anyway.

    The sweep tables count every silent failure inside a refused batch as
    prevented. Most of them would have occurred on a healthy pipeline too, so
    that overstates the gate. `attribution` charges only the excess — and here
    the faulted batch has exactly the same silent rate as the clean one, so the
    honest credit is zero and the gate is pure loss.
    """
    from airsbench.gate.replay import attribution

    corpus = [
        _batch("clean", CLEAN, 0.5, 100, 80, 10),
        _batch("no-worse", DIRTY, 9.0, 100, 80, 10),
    ]
    corpus[1].fault = "latency"
    assert attribution(corpus, "retrieval") == 0

    out = capsys.readouterr().out
    assert "fault-free silent rate 10.0%" in out
    assert "never" in out  # zero excess ⇒ refusing for it can never pay
