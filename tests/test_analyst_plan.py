"""Checkable plans: deterministic execution, honest non-computability, typed equality.

`test_min_by_is_exactly_the_corpus_answer_key` carries the weight. The verifier
must reproduce the published flip partition exactly (A4), which is only possible
if its answer rule — ties included — is the rule the corpus scored against.
"""

from __future__ import annotations

import random

import pytest

from airsbench.agents.retrieval import RetrievalAgent
from airsbench.analyst.plan import Plan, PlanError, Row, answers_equal, execute

CHEAPEST_IN_STOCK = Plan.from_dict({"type": "min_by", "measure": "price",
                                    "where": [{"field": "stock", "op": ">", "value": 0}]})


def catalog(*rows):
    return [Row(record_id, {"price": price, "stock": stock}) for record_id, price, stock in rows]


def test_min_by_is_exactly_the_corpus_answer_key():
    rng = random.Random(3)
    for _ in range(2000):
        products = [{"product_id": f"P{i}", "price": rng.choice([1.0, 2.0, 2.5, 3.0]),
                     "stock": rng.choice([0, 0, 1, 5])} for i in range(rng.randint(1, 6))]
        truth = RetrievalAgent.ground_truth(products)
        result = execute(CHEAPEST_IN_STOCK,
                         [Row(p["product_id"], {"price": p["price"], "stock": p["stock"]})
                          for p in products])
        assert result.computable
        assert result.value == (truth["product_id"] if truth else None)


@pytest.mark.parametrize("plan, expected", [
    ({"type": "max_by", "measure": "price", "where": []}, "B"),
    ({"type": "top_k", "measure": "price", "k": 2, "order": "asc", "where": []}, ["C", "D"]),
    ({"type": "top_k", "measure": "price", "k": 3, "order": "desc", "where": []}, ["B", "A", "C"]),
    ({"type": "count_where", "where": [{"field": "stock", "op": "==", "value": 0}]}, 2),
    ({"type": "sum_where", "measure": "price",
      "where": [{"field": "stock", "op": ">=", "value": 1}]}, 9.0),
    ({"type": "sum_where", "measure": "price",
      "where": [{"field": "stock", "op": ">", "value": 99}]}, 0.0),
    ({"type": "lookup", "id": "C", "measure": "stock"}, 0),
    ({"type": "lookup", "id": "Z", "measure": "stock"}, None),
    ({"type": "min_by", "measure": "price",
      "where": [{"field": "stock", "op": ">", "value": 99}]}, None),
])
def test_each_plan_type_executes(plan, expected):
    rows = catalog(("A", 7.0, 1), ("B", 9.0, 0), ("C", 2.0, 0), ("D", 2.0, 4))
    result = execute(Plan.from_dict(plan), rows)
    assert result.computable and result.value == expected


def test_ties_go_to_the_first_record_in_candidate_order():
    rows = catalog(("A", 5.0, 1), ("B", 2.0, 1), ("C", 2.0, 1), ("D", 9.0, 1), ("E", 9.0, 1))
    assert execute(CHEAPEST_IN_STOCK, rows).value == "B"
    top = Plan.from_dict({"type": "top_k", "measure": "price", "k": 2, "order": "desc",
                          "where": []})
    assert execute(top, rows).value == ["D", "E"]


@pytest.mark.parametrize("rows, reason", [
    ([Row("A", {"price": 1.0})], "record A has no field 'stock'"),
    ([Row("A", {"price": "1.0", "stock": 2})], "record A: price is '1.0', not a number"),
    ([Row("A", {"price_v2": 1.0, "stock": 2})], "record A has no field 'price'"),
])
def test_records_that_do_not_support_the_plan_are_not_computable(rows, reason):
    result = execute(CHEAPEST_IN_STOCK, rows)
    assert not result.computable and result.value is None
    assert result.reason == reason


def test_a_measure_on_a_record_the_filter_excludes_is_never_read():
    """The corpus rule filters to in-stock first; an out-of-stock record's price is
    irrelevant to the answer, so a corrupted one must not make it uncomputable."""
    rows = [Row("A", {"price": "garbled", "stock": 0}), Row("B", {"price": 4.0, "stock": 2})]
    assert execute(CHEAPEST_IN_STOCK, rows).value == "B"


def test_equality_compares_values_not_types_where_they_mean_the_same():
    plan = Plan.from_dict({"type": "count_where", "where": [
        {"field": "stock", "op": "==", "value": 3}]})
    assert execute(plan, catalog(("A", 1.0, 3.0))).value == 1


@pytest.mark.parametrize("data, message", [
    ([], "must be a JSON object"),
    ({"type": "average"}, "plan type must be one of"),
    ({"type": "min_by"}, "needs measure"),
    ({"type": "min_by", "measure": "price", "k": 3}, "unknown: ['k']"),
    ({"type": "top_k", "measure": "price", "k": 0}, "whole number from 1"),
    ({"type": "top_k", "measure": "price", "k": 2, "order": "up"}, "order must be one of"),
    ({"type": "lookup", "measure": "price"}, "lookup needs id"),
    ({"type": "count_where", "where": [{"field": "stock", "op": "~", "value": 1}]},
     "op must be one of"),
    ({"type": "count_where", "where": [{"field": "stock", "op": ">", "value": "1"}]},
     "compares numbers"),
    ({"type": "count_where", "where": [{"field": "stock", "op": "=="}]}, "exactly"),
    ({"type": "count_where", "where": "stock > 0"}, "must be a list"),
])
def test_malformed_plans_are_refused_with_the_fix(data, message):
    with pytest.raises(PlanError, match=message.replace("[", r"\[").replace("]", r"\]")):
        Plan.from_dict(data)


def test_a_plan_round_trips_and_equivalent_plans_are_the_same_question():
    plan = Plan.from_dict({"type": "top_k", "measure": "price", "k": 3, "order": "desc",
                           "where": [{"field": "stock", "op": ">", "value": 0},
                                     {"field": "brand", "op": "==", "value": "Acme"}]})
    assert Plan.from_dict(plan.to_dict()) == plan
    reordered = Plan.from_dict({"type": "top_k", "measure": "price", "k": 3, "order": "desc",
                                "where": [{"field": "brand", "op": "==", "value": "Acme"},
                                          {"field": "stock", "op": ">", "value": 0.0}]})
    assert plan.same_as(reordered)
    assert not CHEAPEST_IN_STOCK.same_as(Plan.from_dict(
        {"type": "max_by", "measure": "price",
         "where": [{"field": "stock", "op": ">", "value": 0}]}))


def test_fields_read_lists_each_field_once():
    plan = Plan.from_dict({"type": "sum_where", "measure": "price", "where": [
        {"field": "price", "op": ">", "value": 1}, {"field": "stock", "op": ">", "value": 0}]})
    assert plan.fields_read() == ("price", "stock")


@pytest.mark.parametrize("plan, a, b, equal", [
    (CHEAPEST_IN_STOCK, "B07", "B07", True),
    (CHEAPEST_IN_STOCK, {"id": "B07", "price": 3.0}, "B07", True),
    (CHEAPEST_IN_STOCK, 7, "7", True),
    (CHEAPEST_IN_STOCK, None, "B07", False),
    (CHEAPEST_IN_STOCK, None, None, True),
    (CHEAPEST_IN_STOCK, True, "True", False),
    (Plan("count_where"), 3, 3.0, True),
    (Plan("count_where"), "3", 3, False),
    (Plan("count_where"), 3.5, 3, False),
    (Plan("sum_where", "price"), 0.1 + 0.2, 0.3, True),
    (Plan("sum_where", "price"), 0.3, 0.31, False),
    (Plan("top_k", "price", k=2), ["A", "B"], ["A", "B"], True),
    (Plan("top_k", "price", k=2), ["B", "A"], ["A", "B"], False),
    (Plan("lookup", "brand", id="A"), "Acme", "Acme", True),
])
def test_answers_are_compared_by_the_type_the_plan_returns(plan, a, b, equal):
    assert answers_equal(plan, a, b) is equal
