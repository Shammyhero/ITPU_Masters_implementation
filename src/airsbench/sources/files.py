"""File-backed sources: JSONL, CSV and Parquet — a file or a directory, read-only.

Pipelines often land as files: exports, a lake prefix synced locally, a nightly
dump. A files source reads one file, or every supported file in a directory.
It is declared (`sources.yaml`, command line), never named in an HTTP request,
and every file is opened for reading only.

    .jsonl / .ndjson  the probe's record contract, one record per line, validated
                      by `probe.parse_records` — ISO timestamps, line-numbered
                      refusals and the millisecond guard all apply
    .csv              flat rows: the `id_field` column is the id; the columns
                      event_timestamp, read_timestamp and delivery_latency_ms are
                      telemetry; every other column is payload. CSV carries no
                      types, so plain integers and decimals are read as numbers
                      (not ones with leading zeros, which are usually codes) and
                      empty cells as null
    .parquet          the same flat layout, through pyarrow (`airs-bench[parquet]`)

A record without an event_timestamp gets no invented one, so the probe reports
freshness UNMEASURED. A missing read_timestamp is the moment the record is read.

A file holds one version of each record, so a files source cannot be read as of
a past time: its consistency compares delivered records with upstream's current
state, and absorbs staleness (see `base.py`).
"""

from __future__ import annotations

import csv
import math
import random
import re
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from agentic_faults import Record

from ..probe import ProbeError, normalise, parse_records, read_jsonl
from .base import Sample, SourceError, SourceSchema, schema_from_payloads

FORMATS = {".jsonl": "jsonl", ".ndjson": "jsonl", ".csv": "csv", ".parquet": "parquet"}
TELEMETRY = ("event_timestamp", "read_timestamp", "delivery_latency_ms")
_INTEGER = re.compile(r"^[+-]?(0|[1-9]\d*)$")
_DECIMAL = re.compile(r"^[+-]?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$")


class EntrySource:
    """A source over validated probe entries, loaded once and held in memory."""

    def __init__(self, name: str, *, id_field: str = "id", unique_ids: bool = False,
                 clock: Callable[[], float] = time.time) -> None:
        self.name = name
        self.id_field = id_field
        self.unique_ids = unique_ids
        self._clock = clock
        self._entries: list[dict[str, Any]] | None = None
        self._by_id: dict[str, dict[str, Any]] = {}

    def _read(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def entries(self) -> list[dict[str, Any]]:
        if self._entries is None:
            entries = self._read()
            by_id: dict[str, dict[str, Any]] = {}
            for entry in entries:
                if entry.get("id") is None:
                    continue
                key = str(entry["id"])
                if key in by_id and self.unique_ids:
                    raise SourceError(
                        f"{self.name}: id {key!r} appears more than once; an upstream "
                        f"source needs exactly one version per id — keep the latest"
                    )
                by_id.setdefault(key, entry)
            self._entries, self._by_id = entries, by_id
        return self._entries

    def describe(self) -> SourceSchema:
        entries = self.entries()
        return schema_from_payloads(self.name, self.id_field,
                                    (e["payload"] for e in entries), len(entries), False)

    def sample(self, n: int, *, key: str | None = None, seed: int | None = None) -> Sample:
        if key is not None:
            raise SourceError(f"{self.name}: a file source has no sampling keys; "
                              f"sample it without a key")
        if n < 1:
            raise SourceError(f"{self.name}: n must be at least 1, got {n}")
        entries = self.entries()
        chosen = sorted(random.Random(seed).sample(range(len(entries)), min(n, len(entries))))
        now = self._clock()
        picked = [entries[i] for i in chosen]
        return Sample(
            records=[self._record(entry, now) for entry in picked],
            ids=[None if entry.get("id") is None else str(entry["id"]) for entry in picked],
        )

    def fetch(self, ids: Sequence[str], *, as_of: float | None = None) -> list[Record]:
        """The records with these ids, in the order asked; unknown ids are skipped."""
        if as_of is not None:
            raise SourceError(f"{self.name}: a file holds one version of each record and "
                              f"cannot be read as of a past time")
        self.entries()
        now = self._clock()
        return [self._record(self._by_id[str(i)], now) for i in ids if str(i) in self._by_id]

    @staticmethod
    def _record(entry: dict[str, Any], now: float) -> Record:
        event = entry.get("event_timestamp")
        record = Record(
            payload=dict(entry["payload"]),
            context=dict(entry.get("context") or {}),
            event_timestamp=float(event) if event is not None else 0.0,
        )
        if event is None:
            record.meta["event_timestamp_absent"] = True
        if entry.get("id") is not None:
            record.meta["record_id"] = str(entry["id"])
        read = entry.get("read_timestamp")
        record.read_timestamp = float(read) if read is not None else now
        if entry.get("delivery_latency_ms") is not None:
            record.meta["delivery_latency_ms"] = float(entry["delivery_latency_ms"])
        if entry.get("opaque_map"):
            record.meta["opaque_map"] = dict(entry["opaque_map"])
        return record


class FilesSource(EntrySource):
    """One file, or every .jsonl / .ndjson / .csv / .parquet file in a directory."""

    def __init__(self, name: str, path: Path, *, id_field: str = "id",
                 unique_ids: bool = False, format: str | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        super().__init__(name, id_field=id_field, unique_ids=unique_ids, clock=clock)
        self.path = Path(path)
        self.format = format
        if not self.path.exists():
            raise SourceError(f"{name}: {self.path} does not exist")

    def files(self) -> list[Path]:
        if not self.path.is_dir():
            return [self.path]
        found = sorted(p for p in self.path.iterdir()
                       if p.is_file() and p.suffix.lower() in FORMATS)
        if not found:
            raise SourceError(f"{self.name}: {self.path} holds no .jsonl, .ndjson, .csv "
                              f"or .parquet files")
        return found

    def _format_of(self, path: Path) -> str:
        fmt = self.format or FORMATS.get(path.suffix.lower())
        if fmt is None:
            raise SourceError(f"{self.name}: cannot tell the format of {path.name}; give it "
                              f"a .jsonl, .ndjson, .csv or .parquet extension, or declare format:")
        return fmt

    def _read(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for path in self.files():
            fmt = self._format_of(path)
            if fmt == "jsonl":
                entries.extend(self._jsonl(path))
            elif fmt == "csv":
                entries.extend(self._rows(path, _csv_rows(path, self.name), first=2))
            else:
                entries.extend(self._rows(path, _parquet_rows(path, self.name), first=1))
        if not entries:
            raise SourceError(f"{self.name}: {self.path} holds no records")
        return entries

    def _jsonl(self, path: Path) -> list[dict[str, Any]]:
        try:
            return parse_records(read_jsonl(path), str(path))
        except SourceError:
            raise
        except ProbeError as exc:
            raise SourceError(f"{self.name}: {exc}") from None

    def _rows(self, path: Path, rows: Iterable[dict[str, Any]],
              first: int) -> list[dict[str, Any]]:
        entries = []
        for number, row in enumerate(rows, start=first):
            if self.id_field not in row:
                raise SourceError(f"{self.name}: {path.name} has no {self.id_field!r} column; "
                                  f"declare id_field: with the column that identifies a record")
            payload = {k: v for k, v in row.items() if k is not None}
            entry: dict[str, Any] = {"id": payload.pop(self.id_field)}
            for name in TELEMETRY:
                value = payload.pop(name, None)
                if value is not None:
                    entry[name] = value
            entry["payload"] = payload
            try:
                entries.append(normalise(entry, f"{path}:{number}"))
            except ProbeError as exc:
                raise SourceError(f"{self.name}: {exc}") from None
        return entries


def _coerce(value: str | None) -> Any:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if _INTEGER.match(text):
        return int(text)
    if _DECIMAL.match(text):
        return float(text)
    return value


def _csv_rows(path: Path, name: str) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [{k: _coerce(v) for k, v in row.items()} for row in csv.DictReader(handle)]
    except UnicodeDecodeError:
        raise SourceError(f"{name}: {path} is not a UTF-8 text file") from None
    except csv.Error as exc:
        raise SourceError(f"{name}: {path} is not valid CSV — {exc}") from None


def _plain(value: Any) -> Any:
    """Parquet values as JSON-safe Python values.

    A timestamp becomes ISO-8601; a zoneless one stays zoneless, so the probe
    refuses it as a timestamp exactly as it would in JSONL.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _parquet_rows(path: Path, name: str) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise SourceError(f'{name}: reading {path.name} needs pyarrow; install it with '
                          f'pip install "airs-bench[parquet]"') from None
    try:
        rows = pq.read_table(path).to_pylist()
    except Exception as exc:  # pyarrow raises several unrelated types for a bad file
        raise SourceError(f"{name}: {path} is not a readable Parquet file — {exc}") from None
    return [{k: _plain(v) for k, v in row.items()} for row in rows]
