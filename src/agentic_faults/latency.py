"""LatencyInjector — delays record delivery to the agent.

Simulates backpressure, slow brokers, and network congestion. In
``sleep=True`` mode the delay is real wall-clock time (used in live runs
and the demo); in ``sleep=False`` mode the delay is recorded analytically
in ``record.meta`` without blocking (used in unit tests and dry runs) —
either way the injected amount lands in ``meta['injected_latency_ms']``
so the AIRS calculator sees identical bookkeeping.

Severity presets (research plan §4.2): mild = 500 ms, severe = 3000 ms.
"""

from __future__ import annotations

import time

from .base import FaultInjector, Record


class LatencyInjector(FaultInjector):
    name = "latency"

    def configure(
        self,
        *,
        spike_ms: int,
        spike_probability: float = 1.0,
        sleep: bool = True,
    ) -> None:
        if spike_ms < 0:
            raise ValueError("spike_ms must be >= 0")
        if not 0.0 <= spike_probability <= 1.0:
            raise ValueError("spike_probability must be in [0, 1]")
        self.params = {
            "spike_ms": int(spike_ms),
            "spike_probability": float(spike_probability),
            "sleep": bool(sleep),
        }

    def apply(self, record: Record) -> Record:
        out = record.clone()
        if self.rng.random() < self.params["spike_probability"]:
            spike_ms = self.params["spike_ms"]
            if self.params["sleep"] and spike_ms > 0:
                time.sleep(spike_ms / 1000.0)
            out.meta["injected_latency_ms"] = out.meta.get("injected_latency_ms", 0) + spike_ms
            self._mark(out, spike_ms=spike_ms)
        return out
