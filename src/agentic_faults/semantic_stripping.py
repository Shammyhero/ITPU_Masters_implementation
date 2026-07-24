"""SemanticStrippingInjector — removes the semantic layer from records.

Simulates data delivered without a semantic layer: bytes without meaning.
Context categories (entity type, units, field descriptions, relationship
links) are removed per record with probability ``strip_rate``, leaving the
agent to guess what raw values mean — the failure mode the thesis's
principal hypothesis is about (research plan §3.2).

Severity presets (research plan §4.2): mild = 30 %, severe = 80 %.
"""

from __future__ import annotations

from .base import FaultInjector, Record

DEFAULT_TARGETS = ("entity_type", "units", "descriptions", "relationships")


class SemanticStrippingInjector(FaultInjector):
    name = "semantic_stripping"

    def configure(
        self,
        *,
        strip_rate: float,
        strip_targets: tuple[str, ...] = DEFAULT_TARGETS,
    ) -> None:
        if not 0.0 <= strip_rate <= 1.0:
            raise ValueError("strip_rate must be in [0, 1]")
        if not strip_targets:
            raise ValueError("strip_targets must be non-empty")
        self.params = {"strip_rate": float(strip_rate), "strip_targets": tuple(strip_targets)}

    def apply(self, record: Record) -> Record:
        out = record.clone()
        stripped: list[str] = []
        for target in self.params["strip_targets"]:
            if target in out.context and self.rng.random() < self.params["strip_rate"]:
                del out.context[target]
                stripped.append(target)
        if stripped:
            self._mark(out, stripped=stripped)
        return out
