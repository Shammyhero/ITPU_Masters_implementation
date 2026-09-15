"""The verifier: correctness against upstream first, then four-way attribution.

`test_attribution_aggregates_to_the_published_flip_partition` is the property A4
depends on: whatever the refinement, answer_key_moved + both must be exactly the
wrong answers on flipped queries, and corrupted_in_transit + agent_impairment
exactly the wrong answers on unflipped ones.
"""

from __future__ import annotations

import random

from agentic_faults import Record
from airsbench.analyst import AgentAnswer, Plan, changed_fields, verify
from airsbench.runner.scoring import is_silent_failure

PLAN = Plan.from_dict({"type": "min_by", "measure": "price",
                       "where": [{"field": "stock", "op": ">", "value": 0}]})


def rec(record_id, price, stock, **meta):
    return Record(payload={"product_id": record_id, "price": price, "stock": stock},
                  meta={"record_id": record_id, **meta})


SERVED = [rec("A", 5.0, 1), rec("B", 3.0, 1), rec("C", 4.0, 1)]      # served best: B
MOVED = [rec("A", 5.0, 1), rec("B", 3.0, 0), rec("C", 4.0, 1)]       # true best:   C


def check(answer, delivered=SERVED, served=SERVED, truth=SERVED):
    return verify(PLAN, answer, delivered=delivered, served=served, truth=truth)


def test_a_correct_answer_is_correct_and_never_attributed_a_fault():
    result = check(AgentAnswer(value="B", confidence=1.0))
    assert (result.correct, result.silent_failure, result.flipped, result.attribution) == \
        (True, False, False, "correct")


def test_following_values_that_have_since_changed_is_the_answer_key_moving():
    result = check(AgentAnswer(value="B", confidence=1.0), truth=MOVED)
    assert (result.correct, result.silent_failure, result.flipped) == (False, True, True)
    assert result.attribution == "answer_key_moved"


def test_a_flipped_query_answered_with_neither_value_is_both():
    assert check(AgentAnswer(value="A"), truth=MOVED).attribution == "both"


def test_an_agent_that_ignored_stale_values_and_was_right_is_correct_not_impaired():
    """The brief's original table would have called this 'agent impairment'."""
    assert check(AgentAnswer(value="C"), truth=MOVED).attribution == "correct"


def test_a_wrong_answer_over_corrupted_fields_is_corrupted_in_transit():
    delivered = [rec("A", 5.0, 1), rec("B", "3.0", 1), rec("C", 4.0, 1)]
    result = check(AgentAnswer(value="A"), delivered=delivered)
    assert result.attribution == "corrupted_in_transit"
    assert result.changed_fields == [{"id": "B", "field": "price", "change": "retyped",
                                      "source": 3.0, "delivered": "3.0"}]


def test_a_wrong_answer_over_intact_records_is_agent_impairment():
    result = check(AgentAnswer(value="A", confidence=1.0))
    assert (result.attribution, result.changed_fields, result.silent_failure) == \
        ("agent_impairment", [], True)


def test_abstaining_and_unparseable_output_are_never_attributed_or_silent():
    for answer in (AgentAnswer(abstained=True), AgentAnswer(parse_failed=True)):
        result = check(answer, truth=MOVED)
        assert (result.correct, result.silent_failure, result.attribution) == (False, False, None)


def test_a_question_with_no_answer_at_answer_time_is_not_verified():
    nothing_in_stock = [rec("A", 5.0, 0), rec("B", 3.0, 0)]
    result = check(AgentAnswer(value="B"), truth=nothing_in_stock)
    assert not result.verifiable and "no well-defined answer" in result.reason
    assert result.attribution is None and result.silent_failure is None


def test_changed_fields_names_what_happened_to_each_field_the_plan_reads():
    source = [rec("A", 5.0, 1), rec("B", 3.0, 1), rec("C", 4.0, 1), rec("D", 2.0, 1),
              rec("E", 6.0, 1)]
    delivered = [
        Record({"product_id": "A", "price_v2": 5.0, "stock": 1}, meta={"record_id": "A"}),
        Record({"f1": "B", "f2": 3.0, "f3": 1}, meta={
            "record_id": "B", "opaque_map": {"f1": "product_id", "f2": "price", "f3": "stock"}}),
        rec("C", 400.0, 1),
        Record({"product_id": "D", "stock": 1}, meta={"record_id": "D"}),
    ]
    changes = changed_fields(("price", "stock"), delivered, source)
    summary = [(c["id"], c["field"], c["change"]) for c in changes]
    assert summary == [
        ("A", "price", "renamed"),
        ("B", "price", "name made opaque"), ("B", "stock", "name made opaque"),
        ("C", "price", "value changed"),
        ("D", "price", "missing"),
        ("E", None, "record not delivered"),
    ]
    assert changes[0]["delivered_as"] == "price_v2"
    assert changes[1]["delivered_as"] == "f2"


def test_removed_context_with_names_intact_is_not_a_field_change():
    delivered = [Record(dict(r.payload), context={}, meta=dict(r.meta)) for r in SERVED]
    source = [Record(dict(r.payload), context={"units": {"price": "USD"}}, meta=dict(r.meta))
              for r in SERVED]
    assert changed_fields(PLAN.fields_read(), delivered, source) == []


def test_the_agents_own_plan_is_recorded_but_never_graded():
    misread = {"type": "max_by", "measure": "price",
               "where": [{"field": "stock", "op": ">", "value": 0}]}
    result = check(AgentAnswer(value="A", plan=misread))
    assert result.plan_matches_question is False
    assert result.attribution == "agent_impairment"
    garbled = check(AgentAnswer(value="B", plan={"type": "cheapest"}))
    assert garbled.plan_matches_question is False and "plan type" in garbled.agent_plan_error
    assert garbled.attribution == "correct"


def test_a_reworded_plan_agrees_on_the_data_and_a_widened_one_does_not():
    """Seen live with llama3.1:8b: `stock >= 1` for `stock > 0` is harmless on
    whole-number stock; `stock >= 0` admits out-of-stock records and changes the
    answer when one of them is the cheapest."""
    def stock(op, value):
        return {"type": "min_by", "measure": "price",
                "where": [{"field": "stock", "op": op, "value": value}]}

    served = [rec("A", 5.0, 1), rec("B", 3.0, 1), rec("C", 1.0, 0)]
    reworded = check(AgentAnswer(value="B", plan=stock(">=", 1)), delivered=served,
                     served=served, truth=served)
    assert (reworded.plan_matches_question, reworded.agent_plan_agrees) == (False, True)
    widened = check(AgentAnswer(value="B", plan=stock(">=", 0)), delivered=served,
                    served=served, truth=served)
    assert (widened.plan_matches_question, widened.agent_plan_agrees) == (False, False)
    assert widened.attribution == "correct"


def test_attribution_aggregates_to_the_published_flip_partition():
    rng = random.Random(15)
    ids = ["A", "B", "C", "D"]
    for _ in range(3000):
        served = [rec(i, rng.choice([1.0, 2.0, 3.0]), rng.choice([0, 1, 2])) for i in ids]
        truth = [rec(r.meta["record_id"], r.payload["price"] if rng.random() < 0.7
                     else rng.choice([1.0, 2.0, 3.0]),
                     r.payload["stock"] if rng.random() < 0.7 else rng.choice([0, 1]))
                 for r in served]
        delivered = [rec(r.meta["record_id"], r.payload["price"] if rng.random() < 0.85
                         else str(r.payload["price"]), r.payload["stock"]) for r in served]
        answer = AgentAnswer(value=rng.choice(ids + [None]), abstained=rng.random() < 0.1,
                             parse_failed=rng.random() < 0.05)
        result = verify(PLAN, answer, delivered=delivered, served=served, truth=truth)
        if not result.verifiable:
            continue
        committed = not answer.abstained and not answer.parse_failed
        wrong = committed and not result.correct
        assert (result.attribution in ("answer_key_moved", "both")) == (wrong and result.flipped)
        assert (result.attribution in ("corrupted_in_transit", "agent_impairment")) == \
            (wrong and not result.flipped)
        assert result.silent_failure == is_silent_failure(
            {"correct": result.correct, "abstained": answer.abstained,
             "parse_failed": answer.parse_failed})
        assert result.silent_failure == wrong
