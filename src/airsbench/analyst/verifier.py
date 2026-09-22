"""The verifier: was this answer right, and if not, whose fault was it?

The question's plan is executed three times, deterministically, with no model:

    truth      upstream as of the answer                  — the answer key (invariant 4)
    served     upstream as of when the delivered values   — what the pipeline carried
               were true                                    before anything happened in transit
    delivered  the records exactly as the agent received  — no opaque names reversed:
               them                                         the agent never had that map

Correctness is tested against truth first. Abstained and unparseable answers are
never attributed. Silent failure is `runner.scoring.is_silent_failure`, imported
and applied to the decision — one definition, no threshold (invariant 8).

A committed, parseable, wrong answer gets one of four labels:

    answer_key_moved      served ≠ truth, and the agent gave the served answer
    both                  served ≠ truth, and the agent gave something else
    corrupted_in_transit  served = truth, but a field the plan reads was missing,
                          renamed, retyped, changed or made opaque in delivery
    agent_impairment      served = truth, and the fields it reads arrived intact

This refines the published flip partition and aggregates to it exactly: a query
is flipped when the served-best differs from the true-best
(`analysis.flip_partition.QueryOutcome.flipped`), so answer_key_moved + both =
wrong answers on flipped queries, and corrupted_in_transit + agent_impairment =
wrong answers on unflipped ones.

`corrupted_in_transit` states a fact about the delivery — those fields changed —
and lists them as evidence. It does not claim the change caused the error. Removed
context (units, descriptions) with field names intact does not trigger it; an
opaque field name does, because the agent can no longer see which value it reads.

A source that cannot be read as of a past time (a file) has served = upstream as
read before answering, so pipeline lag shows up as values changed in transit
rather than as the answer key moving. The Tick says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from agentic_faults import Record

from ..runner.scoring import is_silent_failure
from .plan import RECORD_ANSWERS, Plan, PlanError, Result, Row, answers_equal, execute, same_value

LABELS = ("correct", "answer_key_moved", "both", "corrupted_in_transit", "agent_impairment")


@dataclass
class AgentAnswer:
    """What an answerer returned, in the corpus's decision vocabulary."""

    value: Any = None
    plan: Any = None
    text: str = ""
    confidence: float = 0.0
    abstained: bool = False
    parse_failed: bool = False
    # Ids the agent asked to have read again (agent-initiated refetch, A6). It is
    # a request, never an answer: the verifier ignores it entirely.
    refetch_ids: tuple[str, ...] = ()


@dataclass
class Verification:
    verifiable: bool
    reason: str | None
    truth: Result
    served: Result
    delivered: Result
    correct: bool | None = None
    silent_failure: bool | None = None
    flipped: bool | None = None
    attribution: str | None = None
    changed_fields: list[dict[str, Any]] = field(default_factory=list)
    plan_matches_question: bool | None = None
    agent_plan_agrees: bool | None = None
    agent_plan_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifiable": self.verifiable,
            "reason": self.reason,
            "answer_upstream": self.truth.to_dict(),
            "answer_served": self.served.to_dict(),
            "answer_delivered": self.delivered.to_dict(),
            "correct": self.correct,
            "silent_failure": self.silent_failure,
            "flipped": self.flipped,
            "attribution": self.attribution,
            "changed_fields": self.changed_fields,
            "plan_matches_question": self.plan_matches_question,
            "agent_plan_agrees": self.agent_plan_agrees,
            "agent_plan_error": self.agent_plan_error,
        }


def rows(records: Sequence[Record]) -> list[Row]:
    return [Row(record.meta.get("record_id"), dict(record.payload)) for record in records]


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def changed_fields(fields: Sequence[str], delivered: Sequence[Record],
                   served: Sequence[Record]) -> list[dict[str, Any]]:
    """What happened in transit to the fields a plan reads, record by record."""
    by_id = {record.meta.get("record_id"): record for record in delivered}
    out: list[dict[str, Any]] = []
    for source in served:
        record_id = source.meta.get("record_id")
        received = by_id.get(record_id)
        if received is None:
            out.append({"id": record_id, "field": None, "change": "record not delivered"})
            continue
        for name in fields:
            if name not in source.payload:
                continue  # the source never had it: nothing the pipeline did
            before = source.payload[name]
            if name in received.payload:
                after = received.payload[name]
                if _kind(after) != _kind(before):
                    change = "retyped"
                elif not same_value(after, before):
                    change = "value changed"
                else:
                    continue
                out.append({"id": record_id, "field": name, "change": change,
                            "source": before, "delivered": after})
                continue
            opaque = [key for key, original in (received.meta.get("opaque_map") or {}).items()
                      if original == name and key in received.payload]
            if opaque:
                out.append({"id": record_id, "field": name, "change": "name made opaque",
                            "delivered_as": opaque[0], "source": before,
                            "delivered": received.payload[opaque[0]]})
                continue
            renamed = [key for key, value in received.payload.items()
                       if key not in source.payload and _kind(value) == _kind(before)
                       and same_value(value, before)]
            if renamed:
                out.append({"id": record_id, "field": name, "change": "renamed",
                            "delivered_as": renamed[0], "source": before})
            else:
                out.append({"id": record_id, "field": name, "change": "missing",
                            "source": before})
    return out


def verify(plan: Plan, answer: AgentAnswer, *, delivered: Sequence[Record],
           served: Sequence[Record], truth: Sequence[Record]) -> Verification:
    truth_result = execute(plan, rows(truth))
    served_result = execute(plan, rows(served))
    delivered_result = execute(plan, rows(delivered))

    # The agent's own plan is evidence about how it read the question, never the
    # standard it is graded against. Two readings of it: the same form as the
    # question's plan, and — because `stock >= 1` and `stock > 0` differ in form but
    # not on whole-number stock, while `stock >= 0` really does admit more — whether
    # it gives the same answer over the records as they were served.
    matches, agrees, plan_error = None, None, None
    if answer.plan is not None:
        try:
            agent_plan = Plan.from_dict(answer.plan)
        except PlanError as exc:
            matches, agrees, plan_error = False, False, str(exc)
        else:
            matches = agent_plan.same_as(plan)
            own = execute(agent_plan, rows(served))
            agrees = (own.computable and served_result.computable
                      and answers_equal(plan, own.value, served_result.value))

    base = dict(truth=truth_result, served=served_result, delivered=delivered_result,
                plan_matches_question=matches, agent_plan_agrees=agrees,
                agent_plan_error=plan_error)
    if not truth_result.computable:
        return Verification(False, f"upstream cannot answer the question: "
                                   f"{truth_result.reason}", **base)
    if plan.type in RECORD_ANSWERS and truth_result.value is None:
        return Verification(False, "no well-defined answer: no record matches the question "
                                   "at answer time", **base)

    # A request to read records again is not an answer, whatever else it carries;
    # the loop already marks a leftover one unparseable, and this holds if it did not.
    committed = not answer.abstained and not answer.parse_failed and not answer.refetch_ids
    correct = committed and answers_equal(plan, answer.value, truth_result.value)
    silent = is_silent_failure({"correct": correct, "abstained": answer.abstained,
                                "parse_failed": answer.parse_failed
                                or bool(answer.refetch_ids)})
    flipped = (not answers_equal(plan, served_result.value, truth_result.value)
               if served_result.computable else None)
    changes = changed_fields(plan.fields_read(), delivered, served)

    if not committed:
        attribution = None
    elif correct:
        attribution = "correct"
    elif flipped:
        attribution = ("answer_key_moved" if answers_equal(plan, answer.value, served_result.value)
                       else "both")
    elif changes:
        attribution = "corrupted_in_transit"
    else:
        attribution = "agent_impairment"

    return Verification(True, None, correct=correct, silent_failure=silent, flipped=flipped,
                        attribution=attribution, changed_fields=changes, **base)
