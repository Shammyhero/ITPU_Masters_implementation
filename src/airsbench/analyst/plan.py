"""Checkable question plans — what a question asks, as something Python can execute.

A question the Analyst can verify has a plan of one of six types:

    min_by       the id of the record with the lowest `measure`, among records matching `where`
    max_by       the id of the record with the highest `measure`
    top_k        the ids of the `k` records ordered by `measure` (`order`: asc | desc)
    count_where  how many records match `where`
    sum_where    the sum of `measure` over records matching `where`
    lookup       the value of `measure` on the record with id `id`

`where` is a list of conditions `{field, op, value}` with op one of
> >= < <= == !=, all of which must hold.

Execution is deterministic and makes no model call. Ties go to the record that
comes first in candidate order, which is what `min()` does — so `min_by(price,
stock > 0)` returns exactly `RetrievalAgent.ground_truth`, the corpus's answer
key (pinned by a test). Records are identified by the id their source stamped,
never by a payload field a fault may have renamed.

A plan executed over records that lack a field it reads, or hold a non-number
where it compares or ranks numbers, is NOT COMPUTABLE — the result says which
record and why, rather than guessing. That is how the verifier tells "the
delivered records do not support this answer" from "they support another one".

Answers are compared by type: ids as strings, counts exactly, sums and numeric
lookups within 1e-9, top_k as an ordered list.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

TYPES = ("min_by", "max_by", "top_k", "count_where", "sum_where", "lookup")
OPS = (">", ">=", "<", "<=", "==", "!=")
NUMERIC_OPS = (">", ">=", "<", "<=")
ORDERS = ("asc", "desc")
MAX_K = 1000
TOLERANCE = 1e-9
# Plans whose answer is a record, so "no record matched" means no well-defined answer.
RECORD_ANSWERS = ("min_by", "max_by", "lookup")
_KEYS = {
    "min_by": {"type", "measure", "where"},
    "max_by": {"type", "measure", "where"},
    "top_k": {"type", "measure", "where", "k", "order"},
    "count_where": {"type", "where"},
    "sum_where": {"type", "measure", "where"},
    "lookup": {"type", "id", "measure"},
}


class PlanError(ValueError):
    """A plan that is not one of the checkable shapes — the message names the fix."""


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def same_value(a: Any, b: Any) -> bool:
    """Equal values: numbers within tolerance (1 == 1.0), anything else by ==."""
    if is_number(a) and is_number(b):
        return math.isclose(a, b, rel_tol=TOLERANCE, abs_tol=TOLERANCE)
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: Any

    def holds_for(self, actual: Any) -> bool:
        if self.op == "==":
            return same_value(actual, self.value)
        if self.op == "!=":
            return not same_value(actual, self.value)
        if self.op == ">":
            return actual > self.value
        if self.op == ">=":
            return actual >= self.value
        if self.op == "<":
            return actual < self.value
        return actual <= self.value

    def signature(self) -> tuple[Any, ...]:
        value = float(self.value) if is_number(self.value) else self.value
        return (self.field, self.op, type(value).__name__, value)

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "op": self.op, "value": self.value}

    def describe(self) -> str:
        return f"{self.field} {self.op} {self.value!r}"


@dataclass(frozen=True)
class Plan:
    type: str
    measure: str | None = None
    where: tuple[Condition, ...] = ()
    id: str | None = None
    k: int | None = None
    order: str = "asc"

    @classmethod
    def from_dict(cls, data: Any) -> "Plan":
        if not isinstance(data, dict):
            raise PlanError("a plan must be a JSON object with a type")
        kind = data.get("type")
        if kind not in TYPES:
            raise PlanError(f"plan type must be one of {list(TYPES)}, got {kind!r}")
        unknown = sorted(set(data) - _KEYS[kind])
        if unknown:
            raise PlanError(f"{kind} plans take {sorted(_KEYS[kind])}; unknown: {unknown}")

        measure = data.get("measure")
        if "measure" in _KEYS[kind]:
            if not isinstance(measure, str) or not measure:
                raise PlanError(f"{kind} needs measure: the field it reads")
        where = data.get("where") or []
        if not isinstance(where, list):
            raise PlanError("where must be a list of {field, op, value} conditions")
        conditions = tuple(_condition(entry, index) for index, entry in enumerate(where))

        record_id = data.get("id")
        if kind == "lookup":
            if isinstance(record_id, bool) or not isinstance(record_id, (str, int)):
                raise PlanError("lookup needs id: the id of the record to read")
            record_id = str(record_id)

        k, order = None, "asc"
        if kind == "top_k":
            k = data.get("k")
            if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= MAX_K:
                raise PlanError(f"top_k needs k: a whole number from 1 to {MAX_K}")
            order = data.get("order", "asc")
            if order not in ORDERS:
                raise PlanError(f"top_k order must be one of {list(ORDERS)}, got {order!r}")
        return cls(kind, measure, conditions, record_id, k, order)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.measure is not None:
            out["measure"] = self.measure
        if self.type != "lookup":
            out["where"] = [condition.to_dict() for condition in self.where]
        if self.type == "lookup":
            out["id"] = self.id
        if self.type == "top_k":
            out["k"], out["order"] = self.k, self.order
        return out

    def fields_read(self) -> tuple[str, ...]:
        """Every payload field execution reads, in order, once each."""
        names = ([self.measure] if self.measure else []) + [c.field for c in self.where]
        return tuple(dict.fromkeys(names))

    def same_as(self, other: "Plan") -> bool:
        """The same question: conditions compared as a set, numbers by value."""
        return (
            (self.type, self.measure, self.id, self.k, self.order)
            == (other.type, other.measure, other.id, other.k, other.order)
            and sorted(map(Condition.signature, self.where), key=repr)
            == sorted(map(Condition.signature, other.where), key=repr)
        )

    def describe(self) -> str:
        where = (" where " + " and ".join(c.describe() for c in self.where)) if self.where else ""
        if self.type == "min_by":
            return f"the record with the lowest {self.measure}{where}"
        if self.type == "max_by":
            return f"the record with the highest {self.measure}{where}"
        if self.type == "top_k":
            direction = "lowest" if self.order == "asc" else "highest"
            return f"the {self.k} records with the {direction} {self.measure}{where}"
        if self.type == "count_where":
            return f"how many records{where or ' there are'}"
        if self.type == "sum_where":
            return f"the total {self.measure}{where}"
        return f"the {self.measure} of record {self.id}"


def _condition(entry: Any, index: int) -> Condition:
    label = f"where[{index}]"
    if not isinstance(entry, dict) or set(entry) != {"field", "op", "value"}:
        raise PlanError(f"{label} must be exactly {{field, op, value}}")
    field, op, value = entry["field"], entry["op"], entry["value"]
    if not isinstance(field, str) or not field:
        raise PlanError(f"{label}.field must be a field name")
    if op not in OPS:
        raise PlanError(f"{label}.op must be one of {list(OPS)}, got {op!r}")
    if op in NUMERIC_OPS and not is_number(value):
        raise PlanError(f"{label}: {op} compares numbers, so value must be a number")
    if not (value is None or isinstance(value, (str, bool)) or is_number(value)):
        raise PlanError(f"{label}.value must be a string, number, true/false or null")
    return Condition(field, op, value)


@dataclass(frozen=True)
class Row:
    """One record as execution sees it: the id its source stamped, and its payload."""

    id: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class Result:
    value: Any
    computable: bool = True
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "computable": self.computable, "reason": self.reason}


class _NotComputable(Exception):
    pass


def _read(row: Row, field: str, numeric: bool) -> Any:
    if field not in row.payload:
        raise _NotComputable(f"record {row.id} has no field {field!r}")
    value = row.payload[field]
    if numeric and not is_number(value):
        raise _NotComputable(f"record {row.id}: {field} is {value!r}, not a number")
    return value


def execute(plan: Plan, rows: Sequence[Row]) -> Result:
    """Run the plan over these rows, in order. Never raises for data it cannot use."""
    try:
        return Result(_execute(plan, rows))
    except _NotComputable as exc:
        return Result(None, computable=False, reason=str(exc))


def _execute(plan: Plan, rows: Sequence[Row]) -> Any:
    if plan.type == "lookup":
        for row in rows:
            if row.id == plan.id:
                return _read(row, plan.measure, numeric=False)
        return None

    matched = [row for row in rows
               if all(c.holds_for(_read(row, c.field, c.op in NUMERIC_OPS)) for c in plan.where)]
    if plan.type == "count_where":
        return len(matched)
    if plan.type == "sum_where":
        return math.fsum(_read(row, plan.measure, numeric=True) for row in matched)

    keyed = [(_read(row, plan.measure, numeric=True), index, row)
             for index, row in enumerate(matched)]
    if plan.type == "top_k":
        sign = 1 if plan.order == "asc" else -1
        keyed.sort(key=lambda item: (sign * item[0], item[1]))
        return [row.id for _, _, row in keyed[: plan.k]]

    best = None
    for value, _, row in keyed:  # strict comparison: the first of equal values wins
        if best is None or (value < best[0] if plan.type == "min_by" else value > best[0]):
            best = (value, row)
    return None if best is None else best[1].id


def _as_id(value: Any) -> Any:
    if isinstance(value, dict) and "id" in value:
        value = value["id"]
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ("not an id", repr(value))
    return str(value)


def answers_equal(plan: Plan, a: Any, b: Any) -> bool:
    """Whether two answers to this plan are the same answer."""
    if a is None or b is None:
        return a is None and b is None
    if plan.type in ("min_by", "max_by"):
        return _as_id(a) == _as_id(b)
    if plan.type == "top_k":
        return (isinstance(a, list) and isinstance(b, list)
                and [_as_id(x) for x in a] == [_as_id(y) for y in b])
    if plan.type == "count_where":
        return (is_number(a) and is_number(b) and float(a).is_integer()
                and float(b).is_integer() and int(a) == int(b))
    if plan.type == "sum_where":
        return is_number(a) and is_number(b) and same_value(a, b)
    return same_value(a, b)
