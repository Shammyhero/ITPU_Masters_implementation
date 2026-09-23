"""The source protocol, and how a source's records reach the probe.

Four members, so that adding an adapter is an afternoon:

    name        a label for messages and Ticks — never a path, DSN or URL
    describe()  fields, types, example values, row count, and whether the source
                can be read as of a past time
    sample(n)   up to n records drawn together, with the ids they were drawn by
    fetch(ids)  the records with those ids — optionally `as_of` a past time

**Why `as_of` matters.** The corpus scored consistency by comparing what the
agent was served with the same records *before the fault chain ran* — the
catalog as of the moment the delivered values were true — not with the catalog
at answer time (`runner.execute.run_retrieval`). That keeps consistency about
what the pipeline did to the records, and freshness about how old they are
(invariant 5). A source that can read as of a time lets the Analyst do exactly
that. One that cannot — a file, a table with no history — compares delivered
records with upstream's current state, so its consistency also absorbs
staleness; `SourceSchema.supports_as_of` makes that visible rather than silent.

Records are `agentic_faults.Record`s, so the probe, the gate and the injectors
consume them unchanged. `to_probe_entry` converts one to the shape
`airsbench.probe` validates, keeping the opaque-name map semantic stripping
records, and never inventing a timestamp a source did not have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable

from agentic_faults import Record

from ..probe import ProbeError

EXAMPLES_PER_FIELD = 3


class SourceError(ProbeError):
    """A source that cannot be declared or read — the message names it and the fix."""


@dataclass(frozen=True)
class FieldInfo:
    name: str
    type: str
    examples: tuple[Any, ...] = ()


@dataclass(frozen=True)
class SourceSchema:
    source: str
    id_field: str
    fields: tuple[FieldInfo, ...]
    row_count: int | None
    supports_as_of: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "id_field": self.id_field,
            "row_count": self.row_count,
            "supports_as_of": self.supports_as_of,
            "fields": [{"name": f.name, "type": f.type, "examples": list(f.examples)}
                       for f in self.fields],
        }


@dataclass
class Sample:
    """Records drawn together, in order, with the ids they were drawn by.

    The ids travel beside the records because a fault can rename or opaquify the
    id field inside the payload itself. `as_of` is the moment the sample stands
    for (simulated time on the demo source, None where a source has no clock).
    """

    records: list[Record]
    ids: list[str | None]
    as_of: float | None = None
    key: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Source(Protocol):
    name: str

    def describe(self) -> SourceSchema: ...

    def sample(self, n: int, *, key: str | None = None, seed: int | None = None) -> Sample: ...

    def fetch(self, ids: Sequence[str], *, as_of: float | None = None) -> list[Record]: ...


@dataclass(frozen=True)
class SourcePair:
    """What the Analyst operates on: a pipeline's output and its system of record.

    `upstream` may be None. That is legal and consequential: consistency and the
    verifier are lost. Freshness is not — the probe measures it from the
    delivered records' own timestamps, exactly as `airs probe` does.
    """

    id: str
    kind: str
    delivered: Source
    upstream: Source | None
    description: str = ""
    manifest: str | None = None
    # The age at which freshness stops scoring 100, in seconds, declared for this
    # source's own cadence (`probe.freshness_target`); None is the calibrated 1 s.
    freshness_target_s: float | None = None


def reads_as_of(source: Source) -> bool:
    """Whether a source can be read as of a past time — without reading it.

    A live source answers from its declaration (`supports_as_of`); asking it to
    `describe()` would read the whole table, or GET someone's API, just to learn a
    flag. Sources without the attribute (demo, files) describe themselves cheaply.
    """
    flag = getattr(source, "supports_as_of", None)
    return flag if isinstance(flag, bool) else source.describe().supports_as_of


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def schema_from_payloads(
    source: str, id_field: str, payloads: Iterable[dict[str, Any]],
    row_count: int | None, supports_as_of: bool,
) -> SourceSchema:
    """Field names, the types seen, and a few distinct example values."""
    types: dict[str, set[str]] = {}
    examples: dict[str, list[Any]] = {}
    for payload in payloads:
        for key, value in payload.items():
            types.setdefault(key, set())
            seen = examples.setdefault(key, [])
            if value is None:
                continue
            types[key].add(type_name(value))
            if len(seen) < EXAMPLES_PER_FIELD and value not in seen:
                seen.append(value)
    fields = tuple(
        FieldInfo(name, "|".join(sorted(types[name])) or "null", tuple(examples[name]))
        for name in types
    )
    return SourceSchema(source, id_field, fields, row_count, supports_as_of)


def to_probe_entry(record: Record, record_id: str | None = None) -> dict[str, Any]:
    """One record in the shape `airsbench.probe` validates and scores.

    - The id is the one given, or the one the source stamped in
      `meta["record_id"]` — never read back out of the payload, which a fault may
      have renamed or made opaque.
    - `opaque_map` is kept, so consistency sees through the field names semantic
      stripping replaced (invariant 5).
    - A timestamp the source never had is never emitted: the probe then reports
      freshness UNMEASURED rather than scoring an invented age.
    - Delivery latency comes from the source's telemetry, or from the latency
      injector's record of the delay it added.
    """
    entry: dict[str, Any] = {"payload": dict(record.payload)}
    if record_id is None:
        record_id = record.meta.get("record_id")
    if record_id is not None:
        entry["id"] = record_id
    if record.context:
        entry["context"] = dict(record.context)
    if not record.meta.get("event_timestamp_absent"):
        entry["event_timestamp"] = record.event_timestamp
        if record.read_timestamp is not None:
            entry["read_timestamp"] = record.read_timestamp
    latency = record.meta.get("delivery_latency_ms", record.meta.get("injected_latency_ms"))
    if latency is not None:
        entry["delivery_latency_ms"] = float(latency)
    if record.meta.get("opaque_map"):
        entry["opaque_map"] = dict(record.meta["opaque_map"])
    return entry
