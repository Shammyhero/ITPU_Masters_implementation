"""Declared, read-only sources: the protocol, the files and inline adapters,
`sources.yaml`, and the `airs sources` command.

Two guarantees carry most of the weight:

- **Declared, never requested.** Sources come from a file the user wrote; a bad
  declaration is refused with the fix, and credentials never live in it.
- **Nobody looked is not fine.** A source never invents a timestamp, so a record
  without one leaves freshness UNMEASURED — the probe's rule survives the adapter.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from airsbench.probe import measure
from airsbench.sources import Source, SourceError, to_probe_entry
from airsbench.sources.config import load_sources
from airsbench.sources.files import FilesSource
from airsbench.sources.inline import InlineSource

UPSTREAM = [
    {"id": "A", "payload": {"price": 10.0, "stock": 3}},
    {"id": "B", "payload": {"price": 7.5, "stock": 0}},
    {"id": "C", "payload": {"price": 3.0, "stock": 9}},
]


def CLOCK():
    return 1_800_000_000.0


def _jsonl(path: Path, entries) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


def _yaml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(text)
    return path


# ---- the protocol ---------------------------------------------------------------

def test_every_adapter_satisfies_the_protocol(tmp_path):
    path = _jsonl(tmp_path / "d.jsonl", UPSTREAM)
    demo = load_sources()["demo-stale"]
    for source in (FilesSource("f", path), InlineSource("i", path.read_text()),
                   demo.delivered, demo.upstream):
        assert isinstance(source, Source), source


def test_the_demo_pairs_are_always_available_and_readable_as_of_a_time():
    pairs = load_sources()
    assert {"demo-healthy", "demo-stale", "demo-drift", "demo-stripped"} <= set(pairs)
    for pair in pairs.values():
        assert pair.upstream is not None and pair.upstream.describe().supports_as_of


# ---- files ------------------------------------------------------------------------

def test_jsonl_records_are_validated_by_the_probe_with_the_line(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('{"id": "A", "payload": {}}\n'
                    '{"id": "B", "payload": {}, "event_timestamp": "2026-09-13T10:00:00"}\n')
    with pytest.raises(SourceError, match=r"d\.jsonl:2: .*no timezone"):
        FilesSource("f", path).sample(1)


def test_csv_rows_become_typed_payload_with_telemetry_split_out(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("product_id,price,stock,zip,event_timestamp\n"
                    "A,10.50,3,00123,2026-09-13T10:00:00Z\n"
                    "B,,0,90210,\n")
    records = FilesSource("c", path, id_field="product_id", clock=CLOCK).fetch(["A", "B"])
    a, b = records
    assert a.payload == {"price": 10.5, "stock": 3, "zip": "00123"}  # leading zero kept as text
    assert b.payload == {"price": None, "stock": 0, "zip": 90210}
    assert to_probe_entry(a)["event_timestamp"] == \
        datetime(2026, 9, 13, 10, tzinfo=timezone.utc).timestamp()
    assert "event_timestamp" not in to_probe_entry(b)


def test_a_record_without_an_event_timestamp_gets_no_invented_age(tmp_path):
    source = FilesSource("f", _jsonl(tmp_path / "d.jsonl", UPSTREAM), clock=CLOCK)
    entries = [to_probe_entry(r) for r in source.sample(3).records]
    assert all("event_timestamp" not in e for e in entries)
    assert measure(entries)["freshness"]["score"] is None


def test_a_csv_without_the_id_column_names_the_fix(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("sku,price\nA,1\n")
    with pytest.raises(SourceError, match="declare id_field"):
        FilesSource("c", path).sample(1)


def test_parquet_is_read_through_pyarrow(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    moment = datetime(2026, 9, 13, 10, tzinfo=timezone.utc)
    pq.write_table(pa.table({"id": ["A", "B"], "price": [1.5, 2.0],
                             "event_timestamp": [moment, moment]}), tmp_path / "d.parquet")
    (record,) = FilesSource("p", tmp_path / "d.parquet", clock=CLOCK).fetch(["B"])
    assert record.payload == {"price": 2.0}
    assert record.event_timestamp == moment.timestamp()


def test_parquet_without_pyarrow_names_the_extra(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
    path = tmp_path / "d.parquet"
    path.write_bytes(b"PAR1")
    with pytest.raises(SourceError, match=re.escape('pip install "airs-bench[parquet]"')):
        FilesSource("p", path).sample(1)


def test_a_directory_reads_every_supported_file_and_nothing_else(tmp_path):
    _jsonl(tmp_path / "dir" / "a.jsonl", UPSTREAM[:2])
    (tmp_path / "dir" / "b.csv").write_text("id,price\nC,3.0\n")
    (tmp_path / "dir" / "notes.txt").write_text("not data")
    assert FilesSource("d", tmp_path / "dir").describe().row_count == 3


def test_an_upstream_source_refuses_two_versions_of_one_id(tmp_path):
    path = _jsonl(tmp_path / "u.jsonl", UPSTREAM)
    (tmp_path / "more.csv").write_text("id,price\nA,11.0\n")
    both = FilesSource("u", tmp_path, unique_ids=True)
    with pytest.raises(SourceError, match="more than once"):
        both.fetch(["A"])
    assert FilesSource("d", path).fetch(["A"])  # a delivered source may repeat ids


def test_a_file_cannot_be_read_as_of_a_past_time_and_says_so(tmp_path):
    source = FilesSource("f", _jsonl(tmp_path / "d.jsonl", UPSTREAM))
    assert source.describe().supports_as_of is False
    with pytest.raises(SourceError, match="cannot be read as of a past time"):
        source.fetch(["A"], as_of=1.0)


def test_a_file_source_has_no_sampling_keys(tmp_path):
    with pytest.raises(SourceError, match="no sampling keys"):
        FilesSource("f", _jsonl(tmp_path / "d.jsonl", UPSTREAM)).sample(2, key="x")


def test_reading_a_source_never_changes_it(tmp_path):
    path = _jsonl(tmp_path / "d.jsonl", UPSTREAM)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    source = FilesSource("f", path)
    source.describe()
    source.sample(2, seed=1)
    source.fetch(["A", "C"])
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_fetch_keeps_the_order_asked_and_skips_unknown_ids(tmp_path):
    source = FilesSource("f", _jsonl(tmp_path / "d.jsonl", UPSTREAM))
    assert [r.meta["record_id"] for r in source.fetch(["C", "Z", "A"])] == ["C", "A"]


def test_sampling_a_file_is_reproducible_with_a_seed(tmp_path):
    path = _jsonl(tmp_path / "d.jsonl", UPSTREAM)
    first, second = FilesSource("f", path), FilesSource("g", path)
    assert first.sample(2, seed=4).ids == second.sample(2, seed=4).ids


def test_a_missing_path_is_refused_when_declared(tmp_path):
    with pytest.raises(SourceError, match="does not exist"):
        FilesSource("f", tmp_path / "nope.jsonl")


# ---- inline -----------------------------------------------------------------------

def test_the_paste_box_is_a_source_with_the_probes_validation():
    with pytest.raises(SourceError, match="'payload' must be an object"):
        InlineSource("paste", '{"payload": "x"}\n').sample(1)
    good = InlineSource("paste", "".join(json.dumps(e) + "\n" for e in UPSTREAM), clock=CLOCK)
    assert [r.payload["price"] for r in good.fetch(["B"])] == [7.5]


# ---- sources.yaml -----------------------------------------------------------------

def test_a_files_pair_resolves_paths_against_the_declaring_file(tmp_path, monkeypatch):
    _jsonl(tmp_path / "exports" / "d.jsonl", UPSTREAM)
    _jsonl(tmp_path / "exports" / "u.jsonl", UPSTREAM)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    pairs = load_sources(_yaml(tmp_path, (
        "sources:\n"
        "  exports:\n"
        "    type: files\n"
        "    delivered: exports/d.jsonl\n"
        "    upstream:\n"
        "      path: exports/u.jsonl\n"
        "    description: nightly export\n")))
    pair = pairs["exports"]
    assert pair.kind == "files" and pair.description == "nightly export"
    assert pair.delivered.path == tmp_path / "exports" / "d.jsonl"
    assert pair.upstream.unique_ids and not pair.delivered.unique_ids


def test_a_declared_demo_condition_is_a_study_condition(tmp_path):
    pairs = load_sources(_yaml(tmp_path, (
        "sources:\n"
        "  sweep8:\n"
        "    type: demo\n"
        "    condition: {fault: freshness, severity: sweep_8s}\n")))
    assert pairs["sweep8"].delivered.staleness_seconds == pytest.approx(8.05)


@pytest.mark.parametrize("text, fragment", [
    ("sources:\n  x:\n    type: files\n    delivered: d.jsonl\n    colour: red\n",
     "unknown key(s) ['colour']"),
    ("sources:\n  x:\n    type: warehouse\n", "needs type:"),
    ("sources:\n  x:\n    type: files\n    delivered: missing.jsonl\n", "does not exist"),
    ("sources:\n  x:\n    type: files\n    delivered: d.jsonl\n    password: hunter2\n",
     "environment variable"),
    ("sources:\n  x:\n    type: demo\n    condition: {fault: freshness, severity: extreme}\n",
     "severity for freshness"),
    ("sources:\n  demo-stale:\n    type: demo\n", "built-in demo source"),
    ("sources:\n  x:\n    type: demo\n  x:\n    type: demo\n", "declared twice"),
    ("sources:\n  Bad Id:\n    type: demo\n", "source id"),
    ("sources: [1, 2]\n", "must map at least one"),
    ("sources:\n  x: {type: files, delivered: d.jsonl\n", "not valid YAML"),
    ("sources:\n  x:\n    type: files\n    upstream: d.jsonl\n", "needs delivered:"),
])
def test_a_bad_declaration_is_refused_with_the_fix(tmp_path, text, fragment):
    _jsonl(tmp_path / "d.jsonl", UPSTREAM)
    with pytest.raises(SourceError, match=re.escape(fragment)):
        load_sources(_yaml(tmp_path, text))


def test_a_missing_sources_file_is_named(tmp_path):
    with pytest.raises(SourceError, match="no such file"):
        load_sources(tmp_path / "absent.yaml")


# ---- airs sources ------------------------------------------------------------------

def test_airs_sources_list_shows_the_demo_pairs(capsys):
    from airsbench.cli import main

    assert main(["sources", "list"]) == 0
    assert "demo-stale" in capsys.readouterr().out


def test_a_freshness_fault_does_not_depress_consistency_in_a_sample(capsys):
    """Scored against upstream as of the moment the values were true — the corpus's
    reference — a pure freshness fault leaves consistency at 100 (invariant 5)."""
    from airsbench.cli import main

    assert main(["sources", "sample", "demo-stale", "--seed", "7", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["consistency_reference"].startswith("upstream as of the moment")
    dims = report["airs"]["dimensions"]
    assert dims["consistency"]["score"] == pytest.approx(100.0)
    assert dims["freshness"]["score"] == pytest.approx(100.0 / 5.05)


def test_a_file_pair_says_its_consistency_absorbs_staleness(tmp_path, capsys):
    from airsbench.cli import main

    _jsonl(tmp_path / "d.jsonl", UPSTREAM)
    _jsonl(tmp_path / "u.jsonl", UPSTREAM)
    path = _yaml(tmp_path, "sources:\n  ex:\n    type: files\n    delivered: d.jsonl\n"
                           "    upstream: u.jsonl\n")
    assert main(["sources", "--sources", str(path), "sample", "ex", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert "absorbs staleness" in report["consistency_reference"]
    assert report["airs"]["dimensions"]["consistency"]["score"] == pytest.approx(100.0)


def test_airs_sources_describe_and_an_unknown_id(capsys):
    from airsbench.cli import main

    assert main(["sources", "describe", "demo-drift"]) == 0
    assert "product_id" in capsys.readouterr().out
    assert main(["sources", "sample", "nope"]) == 2
    assert "no source 'nope'" in capsys.readouterr().err


def test_serve_refuses_a_bad_sources_file_before_listening(tmp_path, monkeypatch, capsys):
    import uvicorn

    from airsbench.server.__main__ import main

    monkeypatch.setattr(uvicorn.Server, "run", lambda self: pytest.fail("the server started"))
    bad = _yaml(tmp_path, "sources:\n  x:\n    type: files\n    delivered: missing.jsonl\n")
    assert main(["--sources", str(bad), "--no-browser", "--port", "0"]) == 2
    assert "does not exist" in capsys.readouterr().err
