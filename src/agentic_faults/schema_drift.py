"""SchemaDriftInjector — alters field names, types, or values.

Simulates upstream schema changes that propagate without coordination
(the consistency fault family). Three drift types, per thesis Table 6.2:

- ``rename``:      field key changes (``price`` -> ``price_v2``)
- ``retype``:      numeric value becomes its string form; numeric-looking
                   strings become numbers (the classic "12" <-> 12 drift)
- ``value_shift``: numeric values are rescaled by a unit-change factor
                   (minutes->seconds, dollars->cents); categorical values
                   are relabeled through a stable substitution table
                   (simulating an upstream code-table migration)

Severity presets (research plan §4.2): mild = 5 %, severe = 25 % of fields.
"""

from __future__ import annotations

from typing import Any

from .base import FaultInjector, Record

DRIFT_TYPES = ("rename", "retype", "value_shift")
RENAME_SUFFIX = "_v2"
UNIT_SHIFT_FACTORS = (0.01, 60, 100)


class SchemaDriftInjector(FaultInjector):
    name = "schema_drift"

    def __init__(self, seed: int | None = None, **params: Any) -> None:
        # Stable relabel table: the same original category always maps to
        # the same drifted label, as a real code-table migration would.
        self._relabel: dict[str, str] = {}
        super().__init__(seed=seed, **params)

    def configure(
        self,
        *,
        drift_probability: float,
        drift_types: tuple[str, ...] = DRIFT_TYPES,
    ) -> None:
        if not 0.0 <= drift_probability <= 1.0:
            raise ValueError("drift_probability must be in [0, 1]")
        unknown = set(drift_types) - set(DRIFT_TYPES)
        if unknown or not drift_types:
            raise ValueError(f"drift_types must be a non-empty subset of {DRIFT_TYPES}")
        self.params = {
            "drift_probability": float(drift_probability),
            "drift_types": tuple(drift_types),
        }

    def apply(self, record: Record) -> Record:
        out = record.clone()
        for key in list(out.payload.keys()):
            if self.rng.random() >= self.params["drift_probability"]:
                continue
            drift = self.rng.choice(self.params["drift_types"])
            if drift == "rename":
                self._drift_rename(out, key)
            elif drift == "retype":
                self._drift_retype(out, key)
            else:
                self._drift_value_shift(out, key)
        return out

    def _drift_rename(self, record: Record, key: str) -> None:
        new_key = key + RENAME_SUFFIX
        while new_key in record.payload:
            new_key += RENAME_SUFFIX
        record.payload[new_key] = record.payload.pop(key)
        self._mark(record, drift="rename", field=key, new_field=new_key)

    def _drift_retype(self, record: Record, key: str) -> None:
        value = record.payload[key]
        if isinstance(value, bool):
            record.payload[key] = int(value)
        elif isinstance(value, (int, float)):
            record.payload[key] = str(value)
        elif isinstance(value, str):
            try:
                record.payload[key] = float(value)
            except ValueError:
                return  # non-numeric string: retype not applicable, no drift
        else:
            return
        self._mark(record, drift="retype", field=key)

    def _drift_value_shift(self, record: Record, key: str) -> None:
        value = record.payload[key]
        if isinstance(value, bool):
            record.payload[key] = not value
        elif isinstance(value, (int, float)):
            factor = self.rng.choice(UNIT_SHIFT_FACTORS)
            record.payload[key] = value * factor
            self._mark(record, drift="value_shift", field=key, factor=factor)
            return
        elif isinstance(value, str):
            if value not in self._relabel:
                self._relabel[value] = f"category_{len(self._relabel) + 1}"
            record.payload[key] = self._relabel[value]
        else:
            return
        self._mark(record, drift="value_shift", field=key)
