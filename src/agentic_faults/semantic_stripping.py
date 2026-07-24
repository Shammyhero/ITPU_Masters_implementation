"""SemanticStrippingInjector — removes the semantic layer from records.

Simulates data delivered without a semantic layer: bytes without meaning.
Context categories (entity type, units, field descriptions, relationship
links) are removed per record with probability ``strip_rate``, leaving the
agent to guess what raw values mean — the failure mode the thesis's
principal hypothesis is about (research plan §3.2).

Severity presets (research plan §4.2): mild = 30 %, severe = 80 %.

Field-name opacity
------------------
Removing the context block alone is not sufficient to remove meaning:
self-documenting keys such as ``DepDelay`` or ``price`` carry their own
semantics, and an LLM reads them fluently. The research plan's own
motivating example of missing semantics is ``{"id": 47291, "val": 23,
"src": "A"}`` — opaque keys. So when the ``descriptions`` category is
stripped from a record, that record's payload keys are also replaced with
stable opaque tokens (``price`` -> ``f3``).

This is distinct from SchemaDriftInjector's ``rename``: drift renames a
field to another plausible name (``price`` -> ``price_v2``), leaving the
meaning recoverable; stripping replaces it with a meaningless token,
destroying the meaning. Set ``opaque_field_names=False`` to disable and
measure context-block removal in isolation.
"""

from __future__ import annotations

from typing import Any

from .base import FaultInjector, Record

DEFAULT_TARGETS = ("entity_type", "units", "descriptions", "relationships")


class SemanticStrippingInjector(FaultInjector):
    name = "semantic_stripping"

    def __init__(self, seed: int | None = None, **params: Any) -> None:
        # Stable name map: a given field always opaquifies to the same
        # token, as an unlabelled upstream export would.
        self._opaque: dict[str, str] = {}
        super().__init__(seed=seed, **params)

    def configure(
        self,
        *,
        strip_rate: float,
        strip_targets: tuple[str, ...] = DEFAULT_TARGETS,
        opaque_field_names: bool = True,
    ) -> None:
        if not 0.0 <= strip_rate <= 1.0:
            raise ValueError("strip_rate must be in [0, 1]")
        if not strip_targets:
            raise ValueError("strip_targets must be non-empty")
        self.params = {
            "strip_rate": float(strip_rate),
            "strip_targets": tuple(strip_targets),
            "opaque_field_names": bool(opaque_field_names),
        }

    def _opaque_key(self, key: str) -> str:
        if key not in self._opaque:
            self._opaque[key] = f"f{len(self._opaque) + 1}"
        return self._opaque[key]

    def apply(self, record: Record) -> Record:
        out = record.clone()
        stripped: list[str] = []
        for target in self.params["strip_targets"]:
            if target in out.context and self.rng.random() < self.params["strip_rate"]:
                del out.context[target]
                stripped.append(target)

        if "descriptions" in stripped and self.params["opaque_field_names"]:
            mapping = {self._opaque_key(k): k for k in out.payload}
            out.payload = {opaque: out.payload[original]
                           for opaque, original in mapping.items()}
            # Record the mapping so the consistency dimension can reverse
            # it: field-name opacity belongs to the semantic dimension, and
            # letting it also depress consistency would make the two
            # dimensions collinear in the AIRS calibration regression.
            out.meta["opaque_map"] = {**out.meta.get("opaque_map", {}), **mapping}
            stripped.append("field_names")

        if stripped:
            self._mark(out, stripped=stripped)
        return out
