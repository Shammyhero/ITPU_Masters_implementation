"""Verification mode: prove injected faults measure as configured.

Research plan, Month 1 / Week 4: every injector ships with a verification
routine asserting that the injected condition equals the configured
condition within tolerance — e.g. a 3 s freshness delay must produce
records whose measured injected age is 3 s ± 200 ms. These routines run
in CI and their outputs go into the thesis methodology appendix.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from .base import Record
from .freshness import FreshnessInjector
from .latency import LatencyInjector


@dataclass
class VerificationResult:
    injector: str
    configured: float
    measured_mean: float
    max_abs_error: float
    tolerance: float
    trials: int
    passed: bool

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.injector}: configured={self.configured:.4f} "
            f"measured_mean={self.measured_mean:.4f} "
            f"max_abs_error={self.max_abs_error:.4f} (tolerance={self.tolerance}) "
            f"over {self.trials} trials"
        )


def verify_freshness(
    injector: FreshnessInjector, tolerance_s: float = 0.2, trials: int = 100
) -> VerificationResult:
    """Assert measured injected staleness == configured delay ± tolerance.

    For ``distribution="constant"`` every trial must fall within tolerance.
    For ``poisson`` only the mean is compared (per-draw variance is the
    point of that mode), so use >= 1000 trials for a stable check.
    """
    configured = injector.params["delay_seconds"]
    measured = []
    for _ in range(trials):
        original = Record(payload={"v": 1})
        faulted = injector.apply(original)
        measured.append(injector.injected_delay(original, faulted))

    mean = statistics.fmean(measured)
    if injector.params["distribution"] == "constant":
        max_err = max(abs(m - configured) for m in measured)
    else:
        max_err = abs(mean - configured)
    return VerificationResult(
        injector=injector.name,
        configured=configured,
        measured_mean=mean,
        max_abs_error=max_err,
        tolerance=tolerance_s,
        trials=trials,
        passed=max_err <= tolerance_s,
    )


def verify_latency(
    injector: LatencyInjector, tolerance_ms: float = 100.0, trials: int = 10
) -> VerificationResult:
    """Assert wall-clock delay == configured spike ± tolerance (sleep mode)."""
    configured = float(injector.params["spike_ms"])
    measured = []
    for _ in range(trials):
        record = Record(payload={"v": 1})
        start = time.perf_counter()
        injector.apply(record)
        measured.append((time.perf_counter() - start) * 1000.0)

    mean = statistics.fmean(measured)
    max_err = abs(mean - configured)
    return VerificationResult(
        injector=injector.name,
        configured=configured,
        measured_mean=mean,
        max_abs_error=max_err,
        tolerance=tolerance_ms,
        trials=trials,
        passed=max_err <= tolerance_ms,
    )
