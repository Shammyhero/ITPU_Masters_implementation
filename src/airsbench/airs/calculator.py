"""AIRS — Agentic Infrastructure Readiness Score.

Operational definitions of the four dimensions as code, not prose
(research plan, Month 1 / Week 1–2). Each dimension maps runtime
measurements onto a 0–100 score; the composite is a weighted sum.

IMPORTANT: the default weights are equal-weight PLACEHOLDERS. The
published weights are derived in Week 6 by logistic regression on the
benchmark data (agent_failure ~ freshness + latency + consistency +
semantic) and loaded from a calibration JSON. They are estimated, never
assumed — this is a core methodological commitment of the thesis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from agentic_faults import Record

DIMENSIONS = ("freshness", "latency", "consistency", "semantic")
DEFAULT_WEIGHTS = {d: 0.25 for d in DIMENSIONS}

# Targets define "fully ready" (score 100). Scores decay proportionally
# beyond them: score = 100 * target / observed.
DEFAULT_FRESHNESS_TARGET_S = 1.0
DEFAULT_LATENCY_TARGET_MS = 500.0

REQUIRED_CONTEXT = ("entity_type", "units", "descriptions", "relationships")


def freshness_score(mean_age_s: float, target_s: float = DEFAULT_FRESHNESS_TARGET_S) -> float:
    """100 while mean record age <= target; proportional decay beyond."""
    if mean_age_s <= target_s:
        return 100.0
    return 100.0 * target_s / mean_age_s


def latency_score(observed_ms: float, target_ms: float = DEFAULT_LATENCY_TARGET_MS) -> float:
    """100 while end-to-end delivery <= target; proportional decay beyond."""
    if observed_ms <= target_ms:
        return 100.0
    return 100.0 * target_ms / observed_ms


def consistency_score(matched: int, total: int) -> float:
    """Percentage of records/fields that match across pipeline stages."""
    if total <= 0:
        raise ValueError("total must be > 0")
    return 100.0 * matched / total


def semantic_score(fraction_complete: float) -> float:
    """Percentage of required context present at read time."""
    if not 0.0 <= fraction_complete <= 1.0:
        raise ValueError("fraction_complete must be in [0, 1]")
    return 100.0 * fraction_complete


def semantic_completeness(
    record: Record, required: tuple[str, ...] = REQUIRED_CONTEXT
) -> float:
    """Fraction of required semantic-context categories present and non-empty."""
    present = sum(1 for key in required if record.context.get(key) not in (None, {}, [], ""))
    return present / len(required)


def payload_consistency(source: Record, sink: Record) -> float:
    """Fraction of fields identical between a source and sink record.

    Operationalizes the consistency dimension: schema drift shows up as
    renamed keys (missing on one side) or altered values (unequal).

    Dimension independence: field-name opacity from semantic stripping is
    reversed first, using the mapping the injector recorded. Opacity is
    attributed to the semantic dimension alone; without this reversal the
    two dimensions move together and the AIRS calibration regression
    cannot separate their effects (which RQ2 and RQ4 require).
    """
    sink_payload = sink.payload
    opaque_map = sink.meta.get("opaque_map")
    if opaque_map:
        sink_payload = {opaque_map.get(k, k): v for k, v in sink_payload.items()}

    keys = set(source.payload) | set(sink_payload)
    if not keys:
        return 1.0
    matched = sum(
        1
        for key in keys
        if key in source.payload
        and key in sink_payload
        and source.payload[key] == sink_payload[key]
    )
    return matched / len(keys)


def mean_semantic_completeness(records: Iterable[Record]) -> float:
    values = [semantic_completeness(r) for r in records]
    return sum(values) / len(values) if values else 1.0


class AIRSCalculator:
    """Combines the four dimension scores into the 0–100 composite."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        weights = dict(weights or DEFAULT_WEIGHTS)
        missing = set(DIMENSIONS) - set(weights)
        if missing:
            raise ValueError(f"weights missing dimensions: {sorted(missing)}")
        total = sum(weights[d] for d in DIMENSIONS)
        if total <= 0:
            raise ValueError("weights must sum to a positive value")
        self.weights = {d: weights[d] / total for d in DIMENSIONS}

    @classmethod
    def from_calibration(cls, path: str | Path) -> "AIRSCalculator":
        """Load logistic-regression-derived weights (produced in Week 6)."""
        data: dict[str, Any] = json.loads(Path(path).read_text())
        return cls(weights=data["weights"])

    def composite(self, scores: dict[str, float]) -> float:
        for dim in DIMENSIONS:
            if dim not in scores:
                raise ValueError(f"missing dimension score: {dim}")
            if not 0.0 <= scores[dim] <= 100.0:
                raise ValueError(f"score for {dim} must be in [0, 100]")
        return sum(self.weights[d] * scores[d] for d in DIMENSIONS)

    @staticmethod
    def zone(score: float) -> str:
        """Threshold zones used across the thesis and the AIST demo."""
        if score > 80:
            return "green"
        if score >= 60:
            return "amber"
        return "red"
