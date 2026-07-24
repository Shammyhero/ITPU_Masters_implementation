"""Core interfaces for the agentic_faults package.

Every injector implements the two-method contract from the thesis
methodology (Table 6.2): ``configure(**params)`` and ``apply(record)``.
``apply`` never mutates its input — it returns a faulted copy — so a
baseline and a faulted version of the same record can coexist in one run.
"""

from __future__ import annotations

import copy
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Record:
    """A single data record flowing from a pipeline to the agent.

    payload:
        Raw field values the agent reasons over.
    context:
        The semantic layer — ``entity_type``, ``units``, ``descriptions``,
        ``relationships``. This is what SemanticStrippingInjector removes.
    event_timestamp:
        Epoch seconds when the underlying event actually occurred.
    read_timestamp:
        Epoch seconds when the agent reads the record; set by the pipeline
        consumer immediately before agent handoff.
    meta:
        Injector bookkeeping (applied faults, injected delays). Consumed by
        the AIRS calculator and by verification mode; never shown to the agent.
    """

    payload: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    event_timestamp: float = field(default_factory=time.time)
    read_timestamp: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def age_seconds(self, at: float | None = None) -> float:
        """Freshness, operationally defined: read_time − event_time."""
        now = at if at is not None else (self.read_timestamp or time.time())
        return now - self.event_timestamp

    def clone(self) -> Record:
        return copy.deepcopy(self)


class FaultInjector(ABC):
    """Base class for all fault injectors.

    Subclasses set ``name`` and implement ``configure`` (parameter
    validation) and ``apply`` (the fault itself). A ``seed`` makes every
    stochastic decision reproducible, which the benchmark requires.
    """

    name: str = "base"

    def __init__(self, seed: int | None = None, **params: Any) -> None:
        self.rng = random.Random(seed)
        self.params: dict[str, Any] = {}
        if params:
            self.configure(**params)

    @abstractmethod
    def configure(self, **params: Any) -> None:
        """Validate and store fault parameters."""

    @abstractmethod
    def apply(self, record: Record) -> Record:
        """Return a faulted copy of ``record``. Must not mutate the input."""

    def _mark(self, record: Record, **info: Any) -> None:
        record.meta.setdefault("faults", []).append({"injector": self.name, **info})


class FaultChain:
    """Chain-of-responsibility composition of injectors (thesis §6.4).

    Injectors are applied in order; any subset of the four fault types can
    be composed for mixed-fault scenarios (demo Act 5).
    """

    def __init__(self, injectors: list[FaultInjector]) -> None:
        self.injectors = list(injectors)

    def apply(self, record: Record) -> Record:
        out = record
        for injector in self.injectors:
            out = injector.apply(out)
        return out
