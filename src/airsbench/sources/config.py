"""Declared sources: `sources.yaml`, plus the demo pairs that are always available.

Sources are declared by the person running `airs serve` or `airs sources`, on
their own machine — never named in an HTTP request. That is the W3 security
property, kept by the author's decision of 14 Sep: any web page can send
requests to a server on localhost, so the server must not open a file or a
connection because a request asked it to.

    sources:
      exports:
        type: files
        delivered: ./exports/delivered.jsonl      # relative to this file
        upstream:                                 # optional
          path: ./exports/upstream.csv
        id_field: product_id                      # default: id
        description: Nightly catalog export
      stale-catalog:
        type: demo
        condition: {fault: freshness, severity: sweep_8s}
      bikes:                                      # live sources (A10)
        type: sqlite                              # also: duckdb, http
        delivered: {path: ./cache.db, table: station_status, history: true}
        upstream:                                 # a side may name its own type
          type: http
          url: https://example.org/station_status.json
          records_path: data.stations
        id_field: station_id
        timestamp_field: last_reported            # the source's own clock
        freshness_target_s: 60                    # its cadence: fresh up to a minute

A `sqlite` or `duckdb` side reads one table (a name, never SQL) opened read-only;
`history: true` means the table keeps each id's snapshots, so it can be read as of
a past time. An `http` side GETs a JSON document; `headers_env` maps a header to
the environment variable holding its value. Every live side is read afresh on
each question (`tables.py`).

Credentials never belong in this file — it is easy to commit. A key that names
one (password, token, dsn, api_key …) is refused with the environment variable
to use instead. Unknown keys are refused rather than ignored, and a source id
declared twice is an error, not a silent last-one-wins.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable

from .base import SourceError, SourcePair
from .demo import BUILT_IN, LIVE_SEED, Condition, demo_pair
from .files import FilesSource
from .tables import DuckdbSource, HttpSource, SqliteSource, check_url

SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SECRET_WORDS = ("password", "passwd", "secret", "token", "api_key", "apikey", "dsn",
                "credential")
_DECLARED = {"type", "delivered", "upstream", "id_field", "description", "manifest",
             "freshness_target_s"}
PAIR_KEYS = {
    "files": _DECLARED,
    "sqlite": _DECLARED | {"timestamp_field"},
    "duckdb": _DECLARED | {"timestamp_field"},
    "http": _DECLARED | {"timestamp_field"},
    "demo": {"type", "condition", "description", "manifest", "freshness_target_s"},
}
# What one side may declare, by the side's own type (which defaults to the pair's).
SIDE_KEYS = {
    "files": {"type", "path", "format", "id_field"},
    "sqlite": {"type", "path", "table", "id_field", "timestamp_field", "history",
               "version_field", "columns"},
    "duckdb": {"type", "path", "table", "id_field", "timestamp_field", "history",
               "version_field", "columns"},
    "http": {"type", "url", "records_path", "id_field", "timestamp_field", "headers_env",
             "timeout"},
}
SIDE_TYPES = tuple(SIDE_KEYS)
LIVE = {"sqlite": SqliteSource, "duckdb": DuckdbSource}
CONDITION_KEYS = {"fault", "severity", "pipeline"}
FILE_FORMATS = ("jsonl", "csv", "parquet")


class _DuplicateKey(Exception):
    pass


def load_sources(path: Path | None = None, *, seed: int = LIVE_SEED,
                 clock: Callable[[], float] = time.time) -> dict[str, SourcePair]:
    """The built-in demo pairs, plus every pair declared in `path`."""
    pairs = {pair_id: demo_pair(pair_id, condition, seed=seed, clock=clock)
             for pair_id, condition in BUILT_IN.items()}
    if path is None:
        return pairs

    path = Path(path).expanduser()
    where = str(path)
    document = _read_yaml(path)
    if not isinstance(document, dict):
        raise SourceError(f"{where}: expected a mapping with a top-level sources: key")
    _refuse_secrets(document, where)
    _only(document, {"sources"}, where)
    declared = document.get("sources")
    if not isinstance(declared, dict) or not declared:
        raise SourceError(f"{where}: sources: must map at least one source id to its declaration")

    for source_id, spec in declared.items():
        label = f"{where}: sources.{source_id}"
        if not isinstance(source_id, str) or not SOURCE_ID.match(source_id):
            raise SourceError(f"{label}: a source id is lowercase letters, digits, - and _, "
                              f"starting with a letter or digit")
        if source_id in pairs:
            raise SourceError(f"{label}: {source_id!r} is a built-in demo source; choose "
                              f"another id")
        if not isinstance(spec, dict) or spec.get("type") not in PAIR_KEYS:
            raise SourceError(f"{label}: needs type: one of {sorted(PAIR_KEYS)}")
        _only(spec, PAIR_KEYS[spec["type"]], label)
        build = _demo_pair if spec["type"] == "demo" else _declared_pair
        pairs[source_id] = build(source_id, spec, path.parent, label, seed, clock)
    return pairs


def _declared_pair(source_id: str, spec: dict[str, Any], base: Path, label: str,
                   seed: int, clock: Callable[[], float]) -> SourcePair:
    """A files, sqlite, duckdb or http pair; each side may name its own type."""
    kind = spec["type"]
    id_field = spec.get("id_field", "id")
    if not isinstance(id_field, str) or not id_field:
        raise SourceError(f"{label}.id_field: must be a column or key name")
    timestamp_field = spec.get("timestamp_field")
    if timestamp_field is not None and (not isinstance(timestamp_field, str)
                                        or not timestamp_field):
        raise SourceError(f"{label}.timestamp_field: must be a column or key name")
    if spec.get("delivered") is None:
        raise SourceError(f"{label}: needs delivered: — where your pipeline's output is read")
    delivered = _side(spec["delivered"], kind, base, f"{label}.delivered",
                      f"{source_id}/delivered", id_field, timestamp_field, False, clock)
    upstream = None
    if spec.get("upstream") is not None:
        upstream = _side(spec["upstream"], kind, base, f"{label}.upstream",
                         f"{source_id}/upstream", id_field, timestamp_field, True, clock)
    return SourcePair(id=source_id, kind=kind, delivered=delivered, upstream=upstream,
                      description=_text(spec, label), manifest=_manifest(spec, base, label),
                      freshness_target_s=_target(spec, label))


def _side(value: Any, pair_type: str, base: Path, label: str, name: str, id_field: str,
          timestamp_field: str | None, unique_ids: bool, clock: Callable[[], float]):
    if isinstance(value, str):
        value = {"path": value}
    if not isinstance(value, dict):
        raise SourceError(f"{label}: give a path, or a mapping")
    kind = value.get("type", pair_type)
    if kind not in SIDE_TYPES:
        raise SourceError(f"{label}.type: one of {list(SIDE_TYPES)}, got {kind!r}")
    _only(value, SIDE_KEYS[kind], label)
    side_id = value.get("id_field", id_field)
    side_ts = value.get("timestamp_field", timestamp_field)
    if kind == "files":
        return _files_side(value, base, label, name, side_id, unique_ids, clock)
    try:
        if kind == "http":
            timeout = value.get("timeout", 10)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
                    or not 0 < timeout <= 60:
                raise SourceError(f"{label}.timeout: seconds, between 0 and 60")
            headers = value.get("headers_env") or {}
            if not isinstance(headers, dict) or not all(
                    isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
                raise SourceError(f"{label}.headers_env: a mapping of header name to the "
                                  f"environment variable that holds its value")
            records_path = value.get("records_path", "")
            if not isinstance(records_path, str):
                raise SourceError(f"{label}.records_path: a dotted path such as data.stations")
            return HttpSource(name, check_url(value.get("url"), label),
                              records_path=records_path, headers_env=headers,
                              timeout=float(timeout), id_field=side_id,
                              timestamp_field=side_ts, unique_ids=unique_ids, clock=clock)
        if not isinstance(value.get("path"), str) or not isinstance(value.get("table"), str):
            raise SourceError(f"{label}: a {kind} side needs path: and table:")
        history = value.get("history", False)
        if not isinstance(history, bool):
            raise SourceError(f"{label}.history: true or false")
        version = value.get("version_field")
        if version is not None and (not isinstance(version, str) or not version):
            raise SourceError(f"{label}.version_field: a column name")
        columns = value.get("columns")
        if columns is not None and (not isinstance(columns, list) or not columns):
            raise SourceError(f"{label}.columns: a list of column names")
        return LIVE[kind](name, _resolve(value["path"], base), value["table"],
                          columns=columns, id_field=side_id, timestamp_field=side_ts,
                          history=history, version_field=version,
                          unique_ids=unique_ids and not history, clock=clock)
    except SourceError as exc:
        message = str(exc)
        raise SourceError(message if message.startswith(label) else f"{label}: {message}") \
            from None


def _files_side(value: dict[str, Any], base: Path, label: str, name: str, id_field: str,
                unique_ids: bool, clock: Callable[[], float]) -> FilesSource:
    if not isinstance(value.get("path"), str):
        raise SourceError(f"{label}: give a path, or a mapping with path:")
    fmt = value.get("format")
    if fmt is not None and fmt not in FILE_FORMATS:
        raise SourceError(f"{label}.format: one of {list(FILE_FORMATS)}, got {fmt!r}")
    path = _resolve(value["path"], base)
    try:
        return FilesSource(name, path, id_field=value.get("id_field", id_field),
                           unique_ids=unique_ids, format=fmt, clock=clock)
    except SourceError as exc:
        raise SourceError(f"{label}: {exc}") from None


def _demo_pair(source_id: str, spec: dict[str, Any], base: Path, label: str,
               seed: int, clock: Callable[[], float]) -> SourcePair:
    raw = spec.get("condition") or {}
    if not isinstance(raw, dict):
        raise SourceError(f"{label}.condition: a mapping of fault, severity and pipeline")
    _only(raw, CONDITION_KEYS, f"{label}.condition")
    try:
        condition = Condition(**raw)
    except ValueError as exc:
        raise SourceError(f"{label}.condition: {exc}") from None
    return demo_pair(source_id, condition, seed=seed, clock=clock,
                     description=_text(spec, label), manifest=_manifest(spec, base, label),
                     freshness_target_s=_target(spec, label))


def _target(spec: dict[str, Any], label: str) -> float | None:
    """`freshness_target_s`: this source's own cadence, in seconds (or the default)."""
    from ..probe import freshness_target

    value = spec.get("freshness_target_s")
    if value is None:
        return None
    try:
        return freshness_target(value)
    except SourceError:
        raise
    except Exception as exc:  # ProbeError: say which declaration
        raise SourceError(f"{label}.freshness_target_s: {exc}") from None


def _resolve(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def _text(spec: dict[str, Any], label: str) -> str:
    value = spec.get("description", "")
    if not isinstance(value, str):
        raise SourceError(f"{label}.description: must be text")
    return value


def _manifest(spec: dict[str, Any], base: Path, label: str) -> str | None:
    value = spec.get("manifest")
    if value is None:
        return None
    if not isinstance(value, str):
        raise SourceError(f"{label}.manifest: a path to a manifest file")
    path = _resolve(value, base)
    if path.exists() and not path.is_file():
        raise SourceError(f"{label}.manifest: {path} is not a file")
    # A manifest that does not exist yet is not a broken declaration: it is the
    # file `airs manifest propose --out` is about to write. Semantic reports it as
    # absent, with that command (sources/manifest.py).
    return str(path)


def _only(mapping: dict[Any, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(str(key) for key in mapping if key not in allowed)
    if unknown:
        raise SourceError(f"{label}: unknown key(s) {unknown}; known: {sorted(allowed)}")


def _refuse_secrets(value: Any, where: str, trail: str = "") -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            name = str(key).lower()
            if not name.endswith("_env") and any(word in name for word in SECRET_WORDS):
                raise SourceError(
                    f"{where}: {trail}{key}: credentials never go in this file — it is easy "
                    f"to commit. Put the value in an environment variable and reference it "
                    f"as {key}_env"
                )
            _refuse_secrets(inner, where, f"{trail}{key}.")
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            _refuse_secrets(inner, where, f"{trail}{index}.")


def _read_yaml(path: Path) -> Any:
    import yaml

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SourceError(f"{path}: no such file") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise SourceError(f"{path}: cannot be read — {exc}") from None

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise _DuplicateKey(f"line {key_node.start_mark.line + 1}: {key!r} is "
                                    f"declared twice")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                    construct_mapping)
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)  # a SafeLoader subclass
    except _DuplicateKey as exc:
        raise SourceError(f"{path}: {exc}") from None
    except yaml.YAMLError as exc:
        raise SourceError(f"{path}: not valid YAML — {exc}") from None
