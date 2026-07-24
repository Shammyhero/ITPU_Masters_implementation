"""Dataset -> Record loading, and the catalog time machine.

Design note (methodology-relevant):
    A freshness fault must change what the agent *knows*, not merely how
    old the record claims to be. Marking a record stale while serving
    current values would test metadata handling, not staleness. So the
    loader serves the catalog state as of ``t_query - delay`` by replaying
    the update stream; FreshnessInjector still stamps the timestamps that
    the AIRS freshness dimension is computed from.

    For the airline task there is no natural update stream, so staleness
    is modelled on the one feature that genuinely accrues information as
    departure approaches: DepDelay. A feature store lagging by N seconds
    is modelled as knowing a proportionally smaller share of the final
    delay (see ``stale_dep_delay``). This is a documented modelling
    assumption, reported in the thesis limitations.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_faults import Record

# Staleness horizon for the airline task: the delay signal is treated as
# fully known at pushback and proportionally less known before it.
DEP_DELAY_KNOWLEDGE_HORIZON_S = 10.0


@dataclass
class CatalogTimeMachine:
    """Serves e-commerce catalog state at any point in the update stream."""

    base: dict[str, dict[str, Any]]
    updates: list[dict[str, Any]]

    def __post_init__(self) -> None:
        self._ts = [u["ts"] for u in self.updates]

    @classmethod
    def load(cls, data_dir: str | Path) -> "CatalogTimeMachine":
        import pandas as pd

        data_dir = Path(data_dir)
        catalog = pd.read_parquet(data_dir / "catalog.parquet").to_dict("records")
        base = {row["product_id"]: dict(row) for row in catalog}
        updates = [
            json.loads(line)
            for line in (data_dir / "updates.jsonl").read_text().splitlines()
            if line
        ]
        return cls(base=base, updates=updates)

    @property
    def max_ts(self) -> float:
        return self._ts[-1] if self._ts else 0.0

    def state_at(self, ts: float) -> dict[str, dict[str, Any]]:
        """Catalog state after replaying every update with u.ts <= ts."""
        state = {pid: dict(row) for pid, row in self.base.items()}
        cutoff = bisect.bisect_right(self._ts, ts)
        for update in self.updates[:cutoff]:
            product = state.get(update["product_id"])
            if product is None:
                continue
            for field in ("price", "stock"):
                if field in update:
                    product[field] = update[field]
            product["last_updated"] = update["ts"]
        return state


def stale_dep_delay(true_delay: float, staleness_s: float) -> float:
    """Model a lagging feature store for the airline task.

    At zero staleness the agent sees the final departure delay; as
    staleness grows toward the horizon it sees a proportionally smaller
    share of it (the delay had not yet accrued when the record was cut).
    """
    if staleness_s <= 0:
        return true_delay
    known = max(0.0, 1.0 - staleness_s / DEP_DELAY_KNOWLEDGE_HORIZON_S)
    return round(true_delay * known, 1)


def load_semantic_context(data_dir: str | Path) -> dict[str, Any]:
    return json.loads((Path(data_dir) / "semantic_context.json").read_text())


def build_product_record(
    product: dict[str, Any], context: dict[str, Any], event_ts: float
) -> Record:
    """One catalog row as a Record, carrying the full semantic layer."""
    return Record(
        payload={
            "product_id": product["product_id"],
            "title": product["title"],
            "brand": product.get("brand"),
            "price": product["price"],
            "stock": product["stock"],
        },
        context={
            "entity_type": context["entity_type"],
            "units": {k: v for k, v in context["units"].items() if k in ("price", "stock")},
            "descriptions": {
                k: v
                for k, v in context["descriptions"].items()
                if k in ("product_id", "title", "brand", "price", "stock")
            },
            "relationships": context["relationships"],
        },
        event_timestamp=event_ts,
    )


def build_flight_record(
    flight: dict[str, Any], context: dict[str, Any], event_ts: float
) -> Record:
    """One flight as a Record; the label is never part of the payload."""
    payload = {k: v for k, v in flight.items() if k != "ArrDel15"}
    return Record(
        payload=payload,
        context={
            "entity_type": context["entity_type"],
            "units": context["units"],
            "descriptions": {
                k: v for k, v in context["descriptions"].items() if k != "ArrDel15"
            },
            "relationships": context["relationships"],
        },
        event_timestamp=event_ts,
    )
