"""Live sources: SQLite, DuckDB and HTTP (plan A10).

What has to hold, and why each one is here:

- **Read-only, and read afresh.** A poller keeps writing the table and a URL answers
  with what is true now, so every sample and fetch reads again — and nothing here
  can write: SQLite opens `mode=ro`, DuckDB `read_only=True`.
- **The files row contract, unchanged.** The id is lifted out of the payload,
  telemetry is split off, `timestamp_field` becomes the event time, and a record
  without one gets no invented timestamp.
- **History is what makes as-of honest.** A table that keeps its snapshots can be
  read as of a past time, which is what A1's consistency needs; one that does not
  says so instead of pretending.
- **Declared, never requested.** Only a table name, never SQL; a url may carry no
  credential; headers only from the environment; and neither the path nor the url
  ever reaches a message or a Tick.

Every test runs against real SQLite and DuckDB files in a temporary directory and a
local HTTP server. Nothing touches the network.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from airsbench.analyst.answerers import LiteralAnswerer
from airsbench.analyst.loop import Loop
from airsbench.analyst.plan import Plan
from airsbench.analyst.session import Question
from airsbench.gate.policy import Policy
from airsbench.sources import SourceError, reads_as_of
from airsbench.sources.config import load_sources
from airsbench.sources.tables import DuckdbSource, HttpSource, SqliteSource, check_url

T0 = 1_760_000_000.0  # epoch seconds, as a feed reports them
STATIONS = [
    {"station_id": "s1", "name": "Harbour", "bikes": 3, "docks": 12, "last_reported": T0},
    {"station_id": "s2", "name": "Market", "bikes": 9, "docks": 6, "last_reported": T0},
    {"station_id": "s3", "name": "Library", "bikes": 0, "docks": 15, "last_reported": T0},
]
MOST_BIKES = Plan.from_dict({"type": "max_by", "measure": "bikes", "where": []})


# ---- fixtures: real SQLite and DuckDB files, a real HTTP server ------------------

def sqlite_db(path, rows, table="station_status"):
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE {table} (station_id TEXT, name TEXT, bikes INTEGER, "
                           f"docks INTEGER, last_reported REAL)")
        connection.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?)",
                               [tuple(r.values()) for r in rows])
    connection.close()
    return path


def duckdb_db(path, rows, table="station_status"):
    duckdb = pytest.importorskip("duckdb")
    connection = duckdb.connect(str(path))
    connection.execute(f"CREATE TABLE {table} (station_id VARCHAR, name VARCHAR, "
                       f"bikes INTEGER, docks INTEGER, last_reported DOUBLE)")
    connection.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?)",
                           [tuple(r.values()) for r in rows])
    connection.close()
    return path


ENGINES = {"sqlite": (SqliteSource, sqlite_db, "db"), "duckdb": (DuckdbSource, duckdb_db, "duckdb")}


def table_source(engine, tmp_path, rows=STATIONS, **options):
    cls, make, ext = ENGINES[engine]
    path = make(tmp_path / f"cache.{ext}", rows)
    options.setdefault("id_field", "station_id")
    options.setdefault("timestamp_field", "last_reported")
    return cls(f"{engine}-src", path, "station_status", **options), path


class Feed:
    """A local JSON endpoint whose document the test controls."""

    def __init__(self):
        self.document = {"data": {"stations": [dict(r) for r in STATIONS]}}
        self.body: bytes | None = None
        self.status = 200
        self.delay = 0.0
        self.hits = 0
        self.headers = {}
        feed = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                feed.hits += 1
                feed.headers = dict(self.headers)
                time.sleep(feed.delay)
                body = feed.body if feed.body is not None else json.dumps(feed.document).encode()
                self.send_response(feed.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/secret-path/status.json"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def feed():
    served = Feed()
    yield served
    served.close()


def http_source(feed, **options):
    options.setdefault("records_path", "data.stations")
    options.setdefault("id_field", "station_id")
    options.setdefault("timestamp_field", "last_reported")
    return HttpSource("bikes/upstream", feed.url, **options)


# ---- SQLite and DuckDB -----------------------------------------------------------------

@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_a_table_reads_as_the_files_contract(engine, tmp_path):
    source, _ = table_source(engine, tmp_path)
    sample = source.sample(3, seed=1)
    assert sample.ids == ["s1", "s2", "s3"]
    record = sample.records[0]
    assert record.meta["record_id"] == "s1"
    assert "station_id" not in record.payload and "last_reported" not in record.payload
    assert record.payload == {"name": "Harbour", "bikes": 3, "docks": 12}
    assert record.event_timestamp == T0
    schema = source.describe()
    assert schema.row_count == 3 and not schema.supports_as_of
    assert {f.name for f in schema.fields} == {"name", "bikes", "docks"}


@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_every_read_sees_what_the_poller_wrote_since(engine, tmp_path):
    source, path = table_source(engine, tmp_path)
    assert source.describe().row_count == 3
    row = ("s4", "Station Square", 5, 10, T0 + 60)
    if engine == "sqlite":
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO station_status VALUES (?, ?, ?, ?, ?)", row)
        connection.close()
    else:
        import duckdb

        connection = duckdb.connect(str(path))
        connection.execute("INSERT INTO station_status VALUES (?, ?, ?, ?, ?)", row)
        connection.close()
    assert source.describe().row_count == 4
    assert [r.payload["bikes"] for r in source.fetch(["s4"])] == [5]


def test_sqlite_is_opened_read_only(tmp_path, monkeypatch):
    source, path = table_source("sqlite", tmp_path)
    opened = []
    real = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect",
                        lambda target, **kw: opened.append(target) or real(target, **kw))
    source.fetch(["s1"])
    assert opened and all(str(target).endswith("?mode=ro") for target in opened)
    path.chmod(0o444)  # and a file nobody may write is enough
    try:
        assert len(source.fetch(["s1", "s2"])) == 2
    finally:
        path.chmod(0o644)


def test_duckdb_is_opened_read_only(tmp_path, monkeypatch):
    duckdb = pytest.importorskip("duckdb")
    source, _ = table_source("duckdb", tmp_path)
    seen = []
    real = duckdb.connect
    monkeypatch.setattr(duckdb, "connect",
                        lambda target, **kw: seen.append(kw) or real(target, **kw))
    source.fetch(["s1"])
    assert seen == [{"read_only": True}]


SNAPSHOTS = [
    {"station_id": "s1", "name": "Harbour", "bikes": 3, "docks": 12, "last_reported": T0},
    {"station_id": "s1", "name": "Harbour", "bikes": 7, "docks": 8, "last_reported": T0 + 60},
    {"station_id": "s2", "name": "Market", "bikes": 9, "docks": 6, "last_reported": T0},
    {"station_id": "s2", "name": "Market", "bikes": 1, "docks": 14, "last_reported": T0 + 120},
]


@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_a_history_table_is_its_latest_rows_and_reads_as_of(engine, tmp_path):
    source, _ = table_source(engine, tmp_path, SNAPSHOTS, history=True)
    assert source.supports_as_of and source.describe().supports_as_of
    now = {r.meta["record_id"]: r.payload["bikes"] for r in source.fetch(["s1", "s2"])}
    assert now == {"s1": 7, "s2": 1}
    then = {r.meta["record_id"]: r.payload["bikes"]
            for r in source.fetch(["s1", "s2"], as_of=T0 + 90)}
    assert then == {"s1": 7, "s2": 9}
    assert source.fetch(["s1"], as_of=T0 - 1) == []  # nothing was true yet
    assert source.describe().row_count == 2


def test_history_needs_a_clock(tmp_path):
    source, _ = table_source("sqlite", tmp_path, SNAPSHOTS, history=True, timestamp_field=None)
    with pytest.raises(SourceError, match="orders each id's versions by time"):
        source.fetch(["s1"])


def test_a_table_without_history_cannot_pretend_to_one(tmp_path):
    source, _ = table_source("sqlite", tmp_path)
    with pytest.raises(SourceError, match="declare history: true"):
        source.fetch(["s1"], as_of=T0)


def test_an_upstream_with_two_versions_of_an_id_is_refused(tmp_path):
    source, _ = table_source("sqlite", tmp_path, SNAPSHOTS, unique_ids=True)
    with pytest.raises(SourceError, match="more than once"):
        source.fetch(["s1"])


def test_whether_a_source_reads_as_of_is_known_without_reading_it(tmp_path, monkeypatch):
    source, _ = table_source("sqlite", tmp_path, SNAPSHOTS, history=True)
    monkeypatch.setattr(source, "_rows", lambda: pytest.fail("the table was read"))
    assert reads_as_of(source) is True


@pytest.mark.parametrize("table", ["station status", "t; DROP TABLE x", "1st", ""])
def test_only_a_table_name_is_accepted_never_sql(table, tmp_path):
    path = sqlite_db(tmp_path / "cache.db", STATIONS)
    with pytest.raises(SourceError, match="plain table or view name"):
        SqliteSource("s", path, table)


def test_a_missing_file_or_table_is_named(tmp_path):
    with pytest.raises(SourceError, match="does not exist"):
        SqliteSource("s", tmp_path / "nope.db", "t")
    path = sqlite_db(tmp_path / "cache.db", STATIONS)
    with pytest.raises(SourceError, match="no such table"):
        SqliteSource("s", path, "absent", id_field="station_id").fetch(["s1"])


# ---- HTTP ----------------------------------------------------------------------------------

def test_http_reads_the_list_at_records_path_afresh_each_time(feed):
    source = http_source(feed)
    assert [r.payload["bikes"] for r in source.fetch(["s2", "s1"])] == [9, 3]
    feed.document["data"]["stations"][1]["bikes"] = 4
    assert [r.payload["bikes"] for r in source.fetch(["s2"])] == [4]
    assert feed.hits == 2 and not source.supports_as_of


def test_headers_come_only_from_the_environment(feed, monkeypatch):
    source = http_source(feed, headers_env={"X-Api-Key": "BIKES_KEY"})
    monkeypatch.delenv("BIKES_KEY", raising=False)
    with pytest.raises(SourceError, match="BIKES_KEY, which is not set"):
        source.fetch(["s1"])
    monkeypatch.setenv("BIKES_KEY", "k-123")
    source.fetch(["s1"])
    assert feed.headers.get("X-Api-Key") == "k-123"


@pytest.mark.parametrize("change,match", [
    ({"status": 503}, "HTTP 503"),
    ({"body": b"<html>no</html>"}, "not JSON"),
    ({"document": {"data": {}}}, "does not match"),
    ({"document": {"data": {"stations": [1, 2]}}}, "list of objects"),
])
def test_a_bad_response_is_refused_with_a_reason(feed, change, match):
    for key, value in change.items():
        setattr(feed, key, value)
    with pytest.raises(SourceError, match=match) as caught:
        http_source(feed).fetch(["s1"])
    assert "secret-path" not in str(caught.value)  # the url never reaches a message


def test_a_slow_or_oversized_response_is_refused(feed):
    feed.delay = 0.5
    with pytest.raises(SourceError, match="could not be reached"):
        http_source(feed, timeout=0.1).fetch(["s1"])
    feed.delay = 0.0
    with pytest.raises(SourceError, match="larger than"):
        http_source(feed, max_bytes=64).fetch(["s1"])


@pytest.mark.parametrize("url,match", [
    ("file:///etc/passwd", "http:// or https://"),
    ("ftp://example.org/x.json", "http:// or https://"),
    ("https://user:pw@example.org/x.json", "user or password"),
    ("https://example.org/x.json?api_key=abc", "looks like a credential"),
    ("https://example.org/x.json?access_token=abc", "looks like a credential"),
])
def test_a_url_is_http_with_no_credential_in_it(url, match):
    with pytest.raises(SourceError, match=match):
        check_url(url, "bikes")


def test_an_http_source_cannot_keep_a_history(feed):
    with pytest.raises(SourceError, match="cannot keep a history"):
        http_source(feed, history=True)


# ---- sources.yaml ----------------------------------------------------------------------

def declare(tmp_path, body: str):
    path = tmp_path / "sources.yaml"
    path.write_text(body)
    return load_sources(path)


def test_a_pair_mixes_a_sqlite_cache_with_an_http_upstream(tmp_path, feed):
    sqlite_db(tmp_path / "cache.db", SNAPSHOTS)
    pairs = declare(tmp_path, f"""
sources:
  bikes:
    type: sqlite
    delivered: {{path: ./cache.db, table: station_status, history: true}}
    upstream:
      type: http
      url: {feed.url}
      records_path: data.stations
    id_field: station_id
    timestamp_field: last_reported
""")
    pair = pairs["bikes"]
    assert pair.kind == "sqlite"
    assert isinstance(pair.delivered, SqliteSource) and pair.delivered.history
    assert isinstance(pair.upstream, HttpSource) and pair.upstream.unique_ids
    assert reads_as_of(pair.delivered) and not reads_as_of(pair.upstream)


@pytest.mark.parametrize("side,match", [
    ("{type: sqlite, path: ./cache.db, table: station_status, query: 'select 1'}", "unknown key"),
    ("{type: sqlite, path: ./cache.db}", "needs path: and table:"),
    ("{type: postgres, dsn_env: PG}", "one of"),
    ("{type: http, url: 'https://example.org/x.json', timeout: 600}", "timeout"),
    ("{type: http, url: 'https://example.org/x.json', api_key: abc}", "credentials never go"),
    ("{type: http, url: 'https://example.org/x.json', headers_env: [X]}", "headers_env"),
    ("{type: sqlite, path: ./cache.db, table: station_status, history: yes-please}", "history"),
])
def test_a_side_declares_only_what_its_type_allows(tmp_path, side, match):
    sqlite_db(tmp_path / "cache.db", STATIONS)
    with pytest.raises(SourceError, match=match):
        declare(tmp_path, f"""
sources:
  bikes:
    type: sqlite
    delivered: {side}
    id_field: station_id
""")


def test_a_files_pair_is_unchanged(tmp_path):
    (tmp_path / "d.jsonl").write_text(json.dumps({"id": "a", "payload": {"x": 1}}) + "\n")
    pairs = declare(tmp_path, "sources:\n  f:\n    type: files\n    delivered: ./d.jsonl\n")
    assert pairs["f"].kind == "files" and pairs["f"].upstream is None


# ---- end to end: the Analyst over a live pair -------------------------------------------

def test_the_loop_answers_from_the_cache_and_verifies_against_the_live_feed(tmp_path, feed):
    # The cache lags: it still holds the first snapshot, while the feed has moved on.
    sqlite_db(tmp_path / "cache.db", STATIONS)
    feed.document["data"]["stations"][2]["bikes"] = 20  # the Library filled up
    pairs = declare(tmp_path, f"""
sources:
  bikes:
    type: sqlite
    delivered: {{path: ./cache.db, table: station_status}}
    upstream: {{type: http, url: {feed.url}, records_path: data.stations}}
    id_field: station_id
    timestamp_field: last_reported
""")
    question = Question("Which of these stations has the most bikes available right now?",
                        MOST_BIKES, n=3)
    tick = Loop(pair=pairs["bikes"], policy=Policy(name="open"), answerer=LiteralAnswerer(),
                mode="off").ask(question, seed=1)
    decision = tick["decision"]
    assert decision["value"] == "s2"                     # what the cache implies
    assert decision["answer_upstream"]["value"] == "s3"  # what is true now
    assert decision["correct"] is False and decision["silent_failure"] is True
    assert tick["source"]["pair"] == "bikes" and tick["source"]["supports_as_of"] is False
    text = json.dumps(tick)
    assert "secret-path" not in text and str(tmp_path) not in text  # no url, no path


def test_the_api_lists_a_live_pair_without_its_url_or_path(tmp_path, feed, monkeypatch):
    from fastapi.testclient import TestClient

    from airsbench.server.app import create_app

    sqlite_db(tmp_path / "cache.db", STATIONS)
    (tmp_path / "sources.yaml").write_text(f"""
sources:
  bikes:
    type: sqlite
    delivered: {{path: ./cache.db, table: station_status}}
    upstream: {{type: http, url: {feed.url}, records_path: data.stations}}
    id_field: station_id
    timestamp_field: last_reported
""")
    monkeypatch.setattr("airsbench.analyst.sessions.SESSIONS_DIR", tmp_path / "sessions")
    client = TestClient(create_app(web_dir=tmp_path / "no-web",
                                   sources=load_sources(tmp_path / "sources.yaml")),
                        base_url="http://127.0.0.1")
    body = client.get("/api/sources").text
    assert '"bikes"' in body and "secret-path" not in body and str(tmp_path) not in body


def test_a_live_sample_is_labelled_with_its_real_moment(tmp_path, capsys):
    from airsbench.sources.__main__ import _print_sample, sample_report

    sqlite_db(tmp_path / "cache.db", STATIONS)
    pair = declare(tmp_path, """
sources:
  bikes:
    type: sqlite
    delivered: {path: ./cache.db, table: station_status}
    id_field: station_id
    timestamp_field: last_reported
""")["bikes"]
    _print_sample(sample_report(pair, 3, None, 1, "retrieval"))
    header = capsys.readouterr().out.splitlines()[0]
    assert "read at" in header and "simulated" not in header


def test_a_history_orders_by_its_version_clock_and_ages_by_its_event_clock(tmp_path):
    """A recorder stamps each copy when it took it (recorded_at); the station's own
    report time (last_reported) is still what the values' age is measured from."""
    path = tmp_path / "rec.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE upstream (station_id TEXT, recorded_at REAL, "
                           "last_reported REAL, bikes INTEGER)")
        connection.executemany("INSERT INTO upstream VALUES (?, ?, ?, ?)", [
            ("s1", T0 + 20, T0 - 100, 3),   # seen at +20, reported long before
            ("s1", T0 + 80, T0 + 70, 5),
        ])
    connection.close()
    source = SqliteSource("rec", path, "upstream", id_field="station_id",
                          timestamp_field="last_reported", history=True,
                          version_field="recorded_at")
    at_50 = source.fetch(["s1"], as_of=T0 + 50)[0]
    assert at_50.payload == {"bikes": 3} and at_50.event_timestamp == T0 - 100
    assert source.fetch(["s1"], as_of=T0 + 10) == []  # the recorder had not seen it yet
    assert source.fetch(["s1"])[0].payload == {"bikes": 5}
    with pytest.raises(SourceError, match="needs history: true"):
        SqliteSource("rec", path, "upstream", id_field="station_id",
                     version_field="recorded_at")


@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_columns_reads_only_what_is_named(engine, tmp_path):
    source, _ = table_source(engine, tmp_path, columns=["name", "bikes"])
    record = source.fetch(["s2"])[0]
    assert record.payload == {"name": "Market", "bikes": 9}   # docks never read
    assert record.event_timestamp == T0                      # clock column still read


def test_columns_are_names_never_sql(tmp_path):
    path = sqlite_db(tmp_path / "cache.db", STATIONS)
    with pytest.raises(SourceError, match="plain column names"):
        SqliteSource("s", path, "station_status", id_field="station_id",
                     columns=["bikes; drop"])


@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_an_integer_id_column_matches_the_string_ids_a_sample_carries(engine, tmp_path):
    rows = [dict(r, station_id=i) for i, r in enumerate(STATIONS, start=101)]
    if engine == "sqlite":
        path = tmp_path / "ints.db"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE station_status (station_id INTEGER, name TEXT, "
                               "bikes INTEGER, docks INTEGER, last_reported REAL)")
            connection.executemany("INSERT INTO station_status VALUES (?, ?, ?, ?, ?)",
                                   [tuple(r.values()) for r in rows])
        connection.close()
    else:
        duckdb = pytest.importorskip("duckdb")
        path = tmp_path / "ints.duckdb"
        connection = duckdb.connect(str(path))
        connection.execute("CREATE TABLE station_status (station_id INTEGER, name VARCHAR, "
                           "bikes INTEGER, docks INTEGER, last_reported DOUBLE)")
        connection.executemany("INSERT INTO station_status VALUES (?, ?, ?, ?, ?)",
                               [tuple(r.values()) for r in rows])
        connection.close()
    cls = SqliteSource if engine == "sqlite" else DuckdbSource
    source = cls("s", path, "station_status", id_field="station_id",
                 timestamp_field="last_reported")
    fetched = source.fetch(["103", "101"])
    assert [r.meta["record_id"] for r in fetched] == ["103", "101"]
    assert [r.payload["bikes"] for r in fetched] == [0, 3]


def test_asking_for_ids_reads_only_their_rows(tmp_path, monkeypatch):
    source, _ = table_source("sqlite", tmp_path, SNAPSHOTS, history=True)
    seen = []
    real = source._rows
    monkeypatch.setattr(source, "_rows", lambda ids=None: seen.append(len(real(ids))) or
                        real(ids))
    source.fetch(["s2"])
    assert seen == [2]  # s2's two versions, not all four rows
