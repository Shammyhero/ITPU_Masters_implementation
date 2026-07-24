"""FreshnessInjector — makes records appear older than they are.

Simulates a pipeline that updates infrequently or has a slow CDC tail.
The record's event_timestamp is shifted backward by ``delay_seconds``, so
at read time its measured age is its natural age plus the injected delay.

Severity presets (research plan §4.2): mild = 1.5 s, severe = 5.0 s.
"""

from __future__ import annotations

from .base import FaultInjector, Record

DISTRIBUTIONS = ("constant", "poisson")


class FreshnessInjector(FaultInjector):
    name = "freshness"

    def configure(self, *, delay_seconds: float, distribution: str = "constant") -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        if distribution not in DISTRIBUTIONS:
            raise ValueError(f"distribution must be one of {DISTRIBUTIONS}")
        self.params = {"delay_seconds": float(delay_seconds), "distribution": distribution}

    def _sample_delay(self) -> float:
        mean = self.params["delay_seconds"]
        if self.params["distribution"] == "constant" or mean <= 0:
            return mean
        # "poisson" mode models staleness as Poisson-process inter-arrival
        # gaps: exponentially distributed delays with the configured mean.
        return self.rng.expovariate(1.0 / mean)

    def apply(self, record: Record) -> Record:
        out = record.clone()
        delay = self._sample_delay()
        out.event_timestamp -= delay
        self._mark(out, delay_seconds=delay)
        return out

    def injected_delay(self, original: Record, faulted: Record) -> float:
        """Measured injected staleness — used by verification mode."""
        return original.event_timestamp - faulted.event_timestamp
