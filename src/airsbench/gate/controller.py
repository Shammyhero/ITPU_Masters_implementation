"""The admission controller — enforcement that the model cannot argue with.

Sits between the pipeline and the agent. Given a batch of records as the
pipeline would deliver them, it measures the AIRS dimensions, evaluates the
policy, and either admits the batch or refuses it *before the agent is asked*.

Why this shape, and not a prompt instruction or a tool the agent may call:

- The detectability arm handed the agent the record's own age and abstention did
  not move. Anything the model may weigh, it may also ignore.
- A refusal here is cheap and legible: the caller gets a typed verdict naming
  the rule and the observed value, which is an operations problem with an owner.
  A silent failure is expensive and has no owner at all.
- It needs no model call, so it costs nothing and cannot itself hallucinate.

The controller reuses `airsbench.probe`'s measurement rather than reimplementing
it — including the record age an age budget is held against — so what the gate
enforces and what `airs probe` reports are the same numbers by construction.
Malformed records raise `ProbeError` from that measurement, before any rule is
evaluated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..probe import DIMENSIONS, composite, measure
from .policy import Policy, Violation


@dataclass
class Verdict:
    """What the gate decided, and everything needed to explain it."""

    admitted: bool
    policy: str
    violations: list[Violation] = field(default_factory=list)
    airs: float | None = None
    weight_covered: float = 0.0
    dimensions: dict[str, dict[str, Any]] = field(default_factory=dict)
    record_age_seconds: float | None = None
    n_records: int = 0
    shadowed: bool = False

    @property
    def reason(self) -> str:
        if self.admitted and not self.violations:
            return "admitted"
        summary = "; ".join(str(v) for v in self.violations)
        if self.admitted:
            return f"admitted in shadow mode despite: {summary}"
        return f"refused: {summary}"

    def raise_for_status(self) -> None:
        """Fail loudly for callers that would rather not check a boolean."""
        if not self.admitted:
            raise BatchRefused(self)

    def to_dict(self) -> dict[str, Any]:
        """The verdict as JSON-safe data.

        A rule that could not be measured has no observed value. It is NaN in
        memory and null here: NaN is not JSON, and the verdict that most needs
        reading by another tool is exactly the one refused for an unmeasured rule.
        """
        return {
            "admitted": self.admitted,
            "policy": self.policy,
            "reason": self.reason,
            "airs": self.airs,
            "weight_covered": self.weight_covered,
            "record_age_seconds": self.record_age_seconds,
            "n_records": self.n_records,
            "shadowed": self.shadowed,
            "dimensions": self.dimensions,
            "violations": [
                {"rule": v.rule,
                 "observed": None if math.isnan(v.observed) else v.observed,
                 "threshold": v.threshold, "detail": v.detail}
                for v in self.violations
            ],
        }


class BatchRefused(RuntimeError):
    """Raised by `Verdict.raise_for_status` when a batch fails policy."""

    def __init__(self, verdict: Verdict) -> None:
        super().__init__(verdict.reason)
        self.verdict = verdict


class Controller:
    """Evaluate batches against a policy. Stateless apart from counters."""

    def __init__(self, policy: Policy, weights: dict[str, float] | None = None) -> None:
        self.policy = policy
        self.weights = weights or {d: 0.25 for d in DIMENSIONS}
        self.admitted = 0
        self.refused = 0

    def evaluate(
        self,
        delivered: Sequence[dict[str, Any]],
        source: Sequence[dict[str, Any]] | None = None,
    ) -> Verdict:
        measured = measure(list(delivered), list(source) if source else None)
        airs, covered = composite(measured, self.weights)
        age = measured["freshness"].get("mean_age_seconds")
        violations = self._violations(measured, airs, age)

        shadowed = bool(violations) and self.policy.on_violation == "warn"
        admitted = not violations or shadowed
        self.admitted += admitted
        self.refused += not admitted

        return Verdict(
            admitted=admitted,
            policy=self.policy.name,
            violations=violations,
            airs=airs,
            weight_covered=covered,
            dimensions=measured,
            record_age_seconds=age,
            n_records=len(delivered),
            shadowed=shadowed,
        )

    # ---- rules ----------------------------------------------------------

    def _violations(
        self, measured: dict[str, dict[str, Any]], airs: float | None, age: float | None
    ) -> list[Violation]:
        out: list[Violation] = []
        policy = self.policy

        if policy.max_record_age_seconds is not None:
            if age is None:
                if policy.unmeasured_is_violation:
                    out.append(Violation(
                        "max_record_age_seconds", float("nan"),
                        policy.max_record_age_seconds,
                        "record age could not be measured — the batch carries no "
                        "timestamps, so the budget cannot be shown to hold",
                    ))
            elif age > policy.max_record_age_seconds:
                out.append(Violation(
                    "max_record_age_seconds", age, policy.max_record_age_seconds,
                    f"records are {age:.2f}s old, budget is "
                    f"{policy.max_record_age_seconds:.2f}s",
                ))

        for dim, floor in sorted(policy.min_dimension.items()):
            score = measured.get(dim, {}).get("score")
            if score is None:
                if policy.unmeasured_is_violation:
                    out.append(Violation(
                        f"min_dimension.{dim}", float("nan"), floor,
                        f"{dim} could not be measured, so the floor of {floor:.0f} "
                        f"cannot be shown to hold",
                    ))
            elif score < floor:
                out.append(Violation(
                    f"min_dimension.{dim}", score, floor,
                    f"{dim} is {score:.1f}, floor is {floor:.0f}",
                ))

        if policy.min_airs is not None:
            if airs is None:
                if policy.unmeasured_is_violation:
                    out.append(Violation(
                        "min_airs", float("nan"), policy.min_airs,
                        "no dimension could be measured, so AIRS is undefined",
                    ))
            elif airs < policy.min_airs:
                out.append(Violation(
                    "min_airs", airs, policy.min_airs,
                    f"AIRS is {airs:.1f}, floor is {policy.min_airs:.0f}",
                ))
        return out
