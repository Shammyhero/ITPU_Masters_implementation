"""Declarative admission policy — the thing the thesis concludes you need.

The campaign's practitioner finding is that disclosure does not work: the
detectability arm delivered each record's own age to the agent and abstention
did not move (`docs/detectability_findings.md`). An age is not actionable
without a standard to judge it against, and the agent has no such standard.

So the standard has to live outside the model. That is what a policy is: a
declared, machine-checkable statement of what data this agent may be asked to
reason over. It is deliberately boring — thresholds, not inference — because
its job is to be enforceable by something that cannot be talked out of it.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

DIMENSIONS = ("freshness", "latency", "consistency", "semantic")

# Rules a re-read repairs *legitimately*. Only staleness: record age and
# freshness are about WHEN the values were true, and reading the system of record
# again answers exactly that.
#
# Consistency and semantic completeness are deliberately absent, and the reason is
# not mechanical — a re-read of upstream would raise both, because upstream is by
# definition intact. It is that a re-read BYPASSES the pipeline. Quietly going
# around a pipeline that is renaming fields or dropping the semantic layer turns a
# contract violation into an invisible workaround, and the agent keeps answering
# from a source the pipeline is no longer able to deliver. Those refuse, loudly,
# with the rule and the observed value (author decision, 18 Sep).
#
# `min_airs` is absent for a related reason: a composite floor can be breached by
# any dimension, so it does not say what a re-read would be fixing.
REPAIRABLE = ("max_record_age_seconds", "min_dimension.freshness")


def _require_number(name: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a number, got {value!r}")


@dataclass(frozen=True)
class Violation:
    """One reason a batch was refused, in terms an operator can act on."""

    rule: str
    observed: float
    threshold: float
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


@dataclass(frozen=True)
class Policy:
    """What this agent is permitted to reason over.

    Every field is optional. An unset rule is not checked — and, importantly, an
    unset rule is never treated as satisfied by a measurement that was not taken
    (see `Controller`). A policy that checks nothing admits everything, and says
    so rather than reporting a clean bill of health.
    """

    name: str = "default"
    # The staleness budget. This is the rule the detectability arm implies:
    # the agent cannot judge 5.05s on its own, so the pipeline declares the
    # limit and something outside the model holds it.
    max_record_age_seconds: float | None = None
    # Composite floor, using the RQ4-calibrated weights for the task.
    min_airs: float | None = None
    # Per-dimension floors, for when one property is load-bearing for the task.
    min_dimension: dict[str, float] = field(default_factory=dict)
    # A dimension the policy names but the probe could not measure is a
    # violation by default: "we did not look" must not read as "it is fine".
    # Set False only when a dimension is genuinely inapplicable.
    unmeasured_is_violation: bool = True
    # reject = refuse the batch. warn = admit but record the violations, for
    # running a policy in shadow mode before it gates production traffic.
    on_violation: str = "reject"

    def __post_init__(self) -> None:
        # Policies arrive as JSON from files and from the web console, so the
        # types are checked before the ranges: "80" is not a floor of 80.
        if not isinstance(self.name, str):
            raise ValueError(f"name must be a string, got {self.name!r}")
        if self.on_violation not in ("reject", "warn"):
            raise ValueError("on_violation must be 'reject' or 'warn'")
        if not isinstance(self.unmeasured_is_violation, bool):
            raise ValueError("unmeasured_is_violation must be true or false, got "
                             f"{self.unmeasured_is_violation!r}")
        if not isinstance(self.min_dimension, dict):
            raise ValueError("min_dimension must be an object of dimension to floor")
        unknown = set(self.min_dimension) - set(DIMENSIONS)
        if unknown:
            raise ValueError(f"unknown dimension(s) in min_dimension: {sorted(unknown)}")
        for name, value in self.min_dimension.items():
            _require_number(f"min_dimension[{name}]", value)
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"min_dimension[{name}] must be 0-100, got {value}")
        if self.min_airs is not None:
            _require_number("min_airs", self.min_airs)
            if not 0.0 <= self.min_airs <= 100.0:
                raise ValueError("min_airs must be 0-100")
        if self.max_record_age_seconds is not None:
            _require_number("max_record_age_seconds", self.max_record_age_seconds)
            if self.max_record_age_seconds < 0:
                raise ValueError("max_record_age_seconds must be >= 0")

    @property
    def checks_anything(self) -> bool:
        return bool(
            self.max_record_age_seconds is not None
            or self.min_airs is not None
            or self.min_dimension
        )

    def shadow(self) -> "Policy":
        """The same policy in warn-only mode, for measuring before enforcing."""
        return replace(self, on_violation="warn")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Policy":
        if not isinstance(data, dict):
            raise ValueError(f"a policy must be a JSON object, got {type(data).__name__}")
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                f"unknown policy field(s): {sorted(unknown)}. "
                f"Known fields: {sorted(known)}"
            )
        return cls(**data)

    @classmethod
    def load(cls, path: str | Path) -> "Policy":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "max_record_age_seconds": self.max_record_age_seconds,
            "min_airs": self.min_airs,
            "min_dimension": dict(self.min_dimension),
            "unmeasured_is_violation": self.unmeasured_is_violation,
            "on_violation": self.on_violation,
        }

    def describe(self) -> str:
        if not self.checks_anything:
            return f"{self.name}: checks nothing — admits everything"
        parts = []
        if self.max_record_age_seconds is not None:
            parts.append(f"age <= {self.max_record_age_seconds}s")
        if self.min_airs is not None:
            parts.append(f"AIRS >= {self.min_airs}")
        for dim, floor in sorted(self.min_dimension.items()):
            parts.append(f"{dim} >= {floor}")
        return f"{self.name}: " + ", ".join(parts) + f" [{self.on_violation}]"
