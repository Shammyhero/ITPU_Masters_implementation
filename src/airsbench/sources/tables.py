"""Live sources: a SQLite or DuckDB table, or a JSON document over HTTP (plan A10).

A file is a snapshot, so `files.py` reads it once. These are not: a poller keeps
writing to the table, and a URL answers with whatever is true now. So every
`sample` and `fetch` reads again — the records a question is answered from are
the ones there at that moment, which is the only honest thing a live pipeline's
measurement can be.

    sqlite   a table in a SQLite file, opened read-only (`mode=ro`); stdlib
    duckdb   a table in a DuckDB file, opened read-only (`airs-bench[duckdb]`)
    http     a JSON document fetched with GET from a DECLARED url; stdlib

All three follow the files contract row for row (`rows_to_entries`): the
`id_field` column is lifted out of the payload and becomes the id; the columns
event_timestamp, read_timestamp and delivery_latency_ms are telemetry; every other
column is payload. `timestamp_field` names a source's own time column — a feed's
`last_reported` — which then becomes the event timestamp; without one, freshness
is UNMEASURED rather than invented.

**History.** A table declared `history: true` keeps many rows per id — every
snapshot a poller appended — stamped by its time column. Its current state is
each id's latest row, and it can be read *as of* a past time: each id's latest
row at or before it. That is what A1's consistency needs (`base.py`): delivered
records compared with upstream as of when their values were true, so consistency
measures what the pipeline did and freshness how old it is (invariant 5).

**Declared, never requested.** The table, the file and the URL come from
`sources.yaml` or the command line — never from an HTTP request to `airs serve`
(the W3 property). Only a table NAME is accepted, never SQL; anything fancier is a
view inside the database. Headers come only from environment variables
(`headers_env`), a url may carry no credentials, and a Tick names the source by
its id — never the path or the url.
"""

from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from agentic_faults import Record

from ..probe import ProbeError, normalise
from .base import Sample, SourceError, SourceSchema, schema_from_payloads

TELEMETRY = ("event_timestamp", "read_timestamp", "delivery_latency_ms")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
HTTP_TIMEOUT_S = 10.0
HTTP_MAX_BYTES = 16 * 1024 * 1024
# A url that carries a credential in its query string is refused: it would sit in
# sources.yaml, which is easy to commit. Headers from the environment instead.
SECRET_QUERY = re.compile(r"(key|token|secret|password|passwd|signature|auth)",
                          re.IGNORECASE)


def rows_to_entries(rows: Iterable[dict[str, Any]], *, name: str, where: str,
                    id_field: str, timestamp_field: str | None = None,
                    first: int = 1, label: str | None = None) -> list[dict[str, Any]]:
    """Flat rows as validated probe entries — the one row contract every table-like
    source shares (files' CSV and Parquet, SQLite, DuckDB, HTTP).

    `where` locates a row in messages (`where:number`); `label` is the shorter name
    used when a whole column is missing (a file's name rather than its path).
    """
    entries = []
    label = label or where
    for number, row in enumerate(rows, start=first):
        if id_field not in row:
            raise SourceError(f"{name}: {label} has no {id_field!r} column; declare "
                              f"id_field: with the column that identifies a record")
        payload = {k: v for k, v in row.items() if k is not None}
        entry: dict[str, Any] = {"id": payload.pop(id_field)}
        for field_name in TELEMETRY:
            value = payload.pop(field_name, None)
            if value is not None:
                entry[field_name] = value
        if timestamp_field is not None:
            if timestamp_field not in payload:
                raise SourceError(f"{name}: {label} has no {timestamp_field!r} column, "
                                  f"which timestamp_field: names")
            value = payload.pop(timestamp_field)
            if value is not None:
                entry["event_timestamp"] = value
        entry["payload"] = payload
        try:
            entries.append(normalise(entry, f"{where}:{number}"))
        except ProbeError as exc:
            raise SourceError(f"{name}: {exc}") from None
    return entries


def plain(value: Any) -> Any:
    """A database or JSON value as a JSON-safe Python value."""
    from .files import _plain

    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return _plain(value)


class LiveSource:
    """Rows read afresh on every call, with an optional history of versions."""

    def __init__(self, name: str, *, id_field: str = "id", timestamp_field: str | None = None,
                 history: bool = False, version_field: str | None = None,
                 unique_ids: bool = False, clock: Callable[[], float] = time.time) -> None:
        if version_field is not None and not history:
            raise SourceError(f"{name}: version_field: orders a history's versions — it "
                              f"needs history: true")
        self.name = name
        self.id_field = id_field
        self.timestamp_field = timestamp_field
        self.history = history
        # The VERSION clock — when each copy was taken — which "as of" orders by.
        # Defaults to the event time; a recorder that stamps what it saw, when it saw
        # it, keeps the two apart: last_reported (the event, for freshness) and
        # recorded_at (the version, for as-of).
        self.version_field = version_field
        self.unique_ids = unique_ids
        self._clock = clock

    @property
    def supports_as_of(self) -> bool:
        """Declared, so the loop need not read the source to learn it (`reads_as_of`)."""
        return self.history

    # ---- what each backend supplies ---------------------------------------------

    def _rows(self, ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        """Raw rows. `ids` is a hint a backend MAY use to read less (SQL pushes it
        down); everything after is filtered again in Python, so ignoring it is safe."""
        raise NotImplementedError

    def _where(self) -> str:
        return self.name

    # ---- the protocol -----------------------------------------------------------

    def versioned(self, ids: Sequence[str] | None = None
                  ) -> list[tuple[float | None, dict[str, Any]]]:
        """Every row as (version time, entry). The version is None without history."""
        rows = self._rows(ids)
        versions: list[Any] = [None] * len(rows)
        if self.version_field is not None:
            missing = [i for i, row in enumerate(rows) if self.version_field not in row]
            if missing:
                raise SourceError(f"{self.name}: {self._where()} has no {self.version_field!r} "
                                  f"column, which version_field: names")
            versions = [row.pop(self.version_field) for row in rows]
        entries = rows_to_entries(rows, name=self.name, where=self._where(),
                                  id_field=self.id_field, timestamp_field=self.timestamp_field)
        if not self.history:
            return [(None, entry) for entry in entries]
        if self.version_field is None:
            versions = [entry.get("event_timestamp") for entry in entries]
        undated = sum(v is None for v in versions)
        if undated:
            raise SourceError(
                f"{self.name}: a history table orders each id's versions by time, and "
                f"{undated} row(s) have none — declare timestamp_field: (or version_field:) "
                f"or fill it")
        return [(float(v), entry) for v, entry in zip(versions, entries)]

    def entries(self) -> list[dict[str, Any]]:
        return [entry for _, entry in self.versioned()]

    def current(self, as_of: float | None = None,
                ids: Sequence[str] | None = None) -> dict[str, dict[str, Any]]:
        """Each id's record: its only row, or with history its latest (at `as_of`)."""
        state: dict[str, dict[str, Any]] = {}
        stamps: dict[str, float] = {}
        wanted = None if ids is None else {str(i) for i in ids}
        for stamp, entry in self.versioned(ids):
            if wanted is not None and str(entry.get("id")) not in wanted:
                continue
            if entry.get("id") is None:
                continue
            key = str(entry["id"])
            if self.history:
                if as_of is not None and stamp > as_of:
                    continue
                if key not in stamps or stamp >= stamps[key]:
                    state[key], stamps[key] = entry, stamp
                continue
            if key in state and self.unique_ids:
                raise SourceError(
                    f"{self.name}: id {key!r} appears more than once; an upstream source "
                    f"needs exactly one version per id — keep the latest, or declare "
                    f"history: true with a timestamp_field")
            state.setdefault(key, entry)
        return state

    def describe(self) -> SourceSchema:
        state = self.current()
        return schema_from_payloads(self.name, self.id_field,
                                    (e["payload"] for e in state.values()), len(state),
                                    self.history)

    def sample(self, n: int, *, key: str | None = None, seed: int | None = None) -> Sample:
        if key is not None:
            raise SourceError(f"{self.name}: this source has no sampling keys; sample it "
                              f"without a key")
        if n < 1:
            raise SourceError(f"{self.name}: n must be at least 1, got {n}")
        state = self.current()
        if not state:
            raise SourceError(f"{self.name}: holds no records with an id")
        ids = sorted(state)
        chosen = sorted(random.Random(seed).sample(ids, min(n, len(ids))))
        now = self._clock()
        return Sample(records=[_record(state[i], now) for i in chosen], ids=list(chosen),
                      as_of=now)

    def fetch(self, ids: Sequence[str], *, as_of: float | None = None) -> list[Record]:
        """The records with these ids, in the order asked; unknown ids are skipped."""
        if as_of is not None and not self.history:
            raise SourceError(f"{self.name}: holds one version of each record and cannot be "
                              f"read as of a past time — declare history: true on a table "
                              f"that keeps its snapshots")
        state = self.current(as_of, ids=list(ids))
        now = self._clock()
        return [_record(state[str(i)], now) for i in ids if str(i) in state]


def _record(entry: dict[str, Any], now: float) -> Record:
    from .files import EntrySource

    return EntrySource._record(entry, now)


# ---- SQLite and DuckDB ------------------------------------------------------------

class _TableSource(LiveSource):
    engine = ""

    def __init__(self, name: str, path: Path, table: str, *,
                 columns: Sequence[str] | None = None, **options: Any) -> None:
        super().__init__(name, **options)
        self.path = Path(path)
        if not IDENTIFIER.match(table or ""):
            raise SourceError(f"{name}: table: must be a plain table or view name (letters, "
                              f"digits, _), got {table!r}; put anything fancier in a view")
        self.table = table
        # Read only these columns (names, never SQL). The id and clock columns are
        # always read — without them there is no record.
        if columns is not None:
            wanted = list(dict.fromkeys(
                [self.id_field, *(c for c in (self.timestamp_field, self.version_field) if c),
                 *columns]))
            bad = [c for c in wanted if not isinstance(c, str) or not IDENTIFIER.match(c)]
            if bad:
                raise SourceError(f"{name}: columns: plain column names only, got {bad}")
            columns = wanted
        self.columns = columns
        if not self.path.is_file():
            raise SourceError(f"{name}: {self.path} does not exist")

    def _where(self) -> str:
        return f"{self.path.name}:{self.table}"

    def _select(self, ids: Sequence[str] | None) -> tuple[str, list[Any]]:
        """The query: named columns (or all), and the ids asked for, compared as text
        so an INTEGER id column matches the string ids a Sample carries."""
        cols = "*" if self.columns is None else ", ".join(f'"{c}"' for c in self.columns)
        sql, params = f'SELECT {cols} FROM "{self.table}"', []
        if ids is not None:
            if not ids:
                return sql + " WHERE 0 = 1", []
            params = [str(i) for i in ids]
            sql += (f' WHERE CAST("{self.id_field}" AS VARCHAR) IN '
                    f'({", ".join("?" * len(params))})')
        return sql, params


class SqliteSource(_TableSource):
    """A table in a SQLite file, opened read-only for every read."""

    engine = "sqlite"

    def _rows(self, ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        sql, params = self._select(ids)
        try:
            # `with connect()` scopes a transaction, not the connection: close it.
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                cursor = connection.execute(sql, params)
                columns = [column[0] for column in cursor.description]
                return [{c: plain(v) for c, v in zip(columns, row)} for row in cursor]
        except sqlite3.Error as exc:
            raise SourceError(f"{self.name}: cannot read {self._where()} — {exc}") from None


class DuckdbSource(_TableSource):
    """A table in a DuckDB file, opened read-only (`airs-bench[duckdb]`)."""

    engine = "duckdb"

    def _rows(self, ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        try:
            import duckdb
        except ImportError:
            raise SourceError(f'{self.name}: reading a DuckDB file needs duckdb; install it '
                              f'with pip install "airs-bench[duckdb]"') from None
        try:
            connection = duckdb.connect(str(self.path), read_only=True)
        except duckdb.Error as exc:
            raise SourceError(f"{self.name}: cannot open {self.path.name} — {exc}") from None
        sql, params = self._select(ids)
        try:
            cursor = connection.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            return [{c: plain(v) for c, v in zip(columns, row)} for row in cursor.fetchall()]
        except duckdb.Error as exc:
            raise SourceError(f"{self.name}: cannot read {self._where()} — {exc}") from None
        finally:
            connection.close()


# ---- HTTP -------------------------------------------------------------------------

def check_url(url: Any, name: str) -> str:
    """A declared url: http(s), a host, and no credential anywhere in it."""
    if not isinstance(url, str) or not url:
        raise SourceError(f"{name}: url: must be an http:// or https:// address")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SourceError(f"{name}: url: must be an http:// or https:// address, got "
                          f"scheme {parts.scheme or 'none'!r}")
    if parts.username or parts.password:
        raise SourceError(f"{name}: url: carries a user or password; credentials never go "
                          f"in sources.yaml — send them as a header from headers_env:")
    for key, _ in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        if SECRET_QUERY.search(key):
            raise SourceError(f"{name}: url: query parameter {key!r} looks like a credential; "
                              f"send it as a header from headers_env: instead")
    return url


class HttpSource(LiveSource):
    """A JSON document from a declared url; the records are the list at `records_path`."""

    def __init__(self, name: str, url: str, *, records_path: str = "",
                 headers_env: dict[str, str] | None = None, timeout: float = HTTP_TIMEOUT_S,
                 max_bytes: int = HTTP_MAX_BYTES, **options: Any) -> None:
        if options.get("history"):
            raise SourceError(f"{name}: an http source answers with what is true now and "
                              f"cannot keep a history")
        super().__init__(name, **options)
        self.url = check_url(url, name)
        self.records_path = records_path
        self.headers_env = dict(headers_env or {})
        self.timeout = float(timeout)
        self.max_bytes = int(max_bytes)

    def _where(self) -> str:
        # Never the url: this reaches error messages, which can reach a Tick.
        return f"{self.name} (http)"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "airs-bench"}
        for header, variable in self.headers_env.items():
            value = os.environ.get(variable)
            if not value:
                raise SourceError(f"{self.name}: header {header!r} comes from the environment "
                                  f"variable {variable}, which is not set")
            headers[header] = value
        return headers

    def _rows(self, ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        request = urllib.request.Request(self.url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read(self.max_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise SourceError(f"{self.name}: the server answered HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise SourceError(f"{self.name}: could not be reached ({reason})") from None
        if len(body) > self.max_bytes:
            raise SourceError(f"{self.name}: the response is larger than "
                              f"{self.max_bytes // (1024 * 1024)} MB; point url: at a "
                              f"smaller document")
        try:
            document = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise SourceError(f"{self.name}: the response is not JSON") from None
        rows = _at_path(document, self.records_path, self.name)
        return [{k: plain(v) for k, v in row.items()} for row in rows]


def _at_path(document: Any, path: str, name: str) -> list[dict[str, Any]]:
    node = document
    for step in [p for p in path.split(".") if p]:
        if not isinstance(node, dict) or step not in node:
            raise SourceError(f"{name}: records_path {path!r} does not match the response "
                              f"(no {step!r})")
        node = node[step]
    if not isinstance(node, list) or not all(isinstance(row, dict) for row in node):
        raise SourceError(f"{name}: records_path {path or '(the document)'!r} must point at a "
                          f"list of objects")
    return node
