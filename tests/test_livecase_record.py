"""The A11 recorder: a live feed into a history, and real caches beside it.

What has to hold before hours of recording are spent on it:

- **Only changes are recorded**, so the history is the feed's versions, not its polls.
- **Two clocks, kept apart:** `last_reported` (the station's claim, what freshness
  measures) and `recorded_at` (when the copy was taken, what "as of" orders by).
- **A cache is its own copy**, taken on its own schedule — never derived from the
  recorder — or the pipeline under study would not be a real pipeline.
- **A bad response is logged, not fatal**, and a restart resumes without
  re-appending every station.

A scripted feed and a fake clock; nothing touches the network.
"""

from __future__ import annotations

import sqlite3
import urllib.error

from airsbench.livecase.record import Recorder, rows_from_status
from airsbench.sources.tables import SqliteSource

INFO = {"data": {"stations": [
    {"station_id": 1, "name": "Harbour", "lat": 48.86, "lon": 2.27, "capacity": 20},
    {"station_id": 2, "name": "Market", "lat": 48.87, "lon": 2.28, "capacity": 30},
]}}


def status(published, one, two):
    def station(i, bikes, reported):
        return {"station_id": i, "num_bikes_available": bikes,
                "num_bikes_available_types": [{"mechanical": bikes - 1}, {"ebike": 1}],
                "num_docks_available": 20 - bikes, "is_installed": 1, "is_renting": 1,
                "is_returning": 1, "last_reported": reported}
    return {"lastUpdatedOther": published,
            "data": {"stations": [station(1, *one), station(2, *two)]}}


class Feed:
    """station_status answers from a script; station_information is fixed."""

    def __init__(self, *documents):
        self.documents, self.urls = list(documents), []

    def __call__(self, url):
        self.urls.append(url)
        if url.endswith("station_information.json"):
            return INFO
        document = self.documents.pop(0) if len(self.documents) > 1 else self.documents[0]
        if isinstance(document, Exception):
            raise document
        return document


class Clock:
    def __init__(self, t=1_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(seconds, 0.001)


def rows(db, table):
    with sqlite3.connect(db) as connection:
        return connection.execute(f"SELECT * FROM {table} ORDER BY recorded_at, station_id"
                                  ).fetchall()


def test_the_feed_becomes_rows_with_ids_as_text_and_types_split():
    [first, _] = rows_from_status(status(990, (5, 900), (2, 950)), {"1": "Harbour"}, 1_000)
    assert first["station_id"] == "1" and first["name"] == "Harbour"
    assert (first["num_mechanical"], first["num_ebikes"]) == (4, 1)
    assert first["last_reported"] == 900 and first["recorded_at"] == 1_000
    assert first["published_at"] == 990


def test_only_changes_are_recorded(tmp_path):
    db = tmp_path / "rec.db"
    feed = Feed(status(990, (5, 900), (2, 950)), status(1010, (5, 900), (3, 1005)))
    recorder = Recorder(db, caches=(), clock=Clock(), fetcher=feed)
    recorder.refresh_stations()
    assert recorder.record_upstream() == 2   # first sight of both
    assert recorder.record_upstream() == 1   # only station 2 moved
    assert [r[0] for r in rows(db, "upstream")] == ["1", "2", "2"]


def test_a_cache_is_its_own_copy_on_its_own_schedule(tmp_path):
    db, clock = tmp_path / "rec.db", Clock()
    feed = Feed(status(990, (5, 900), (2, 950)))
    recorder = Recorder(db, caches=(5,), status_every=20, clock=clock, fetcher=feed)
    recorder.run(minutes=11, sleep=clock.sleep, say=lambda _: None)
    snapshots = {r[1] for r in rows(db, "cache_5")}
    assert len(snapshots) == 3                       # at 0, 5 and 10 minutes
    assert len(rows(db, "cache_5")) == 3 * 2         # every station, every refresh
    status_requests = [u for u in feed.urls if u.endswith("station_status.json")]
    assert len(status_requests) == 33 + 3            # polls at 0, 20 … 640 s; 3 cache runs


def test_the_recording_reads_back_as_a_history_source(tmp_path):
    db, clock = tmp_path / "rec.db", Clock(1_000)
    feed = Feed(status(990, (5, 900), (2, 950)), status(1010, (6, 1005), (2, 950)))
    recorder = Recorder(db, caches=(), clock=clock, fetcher=feed)
    recorder.refresh_stations()
    recorder.record_upstream()
    clock.t = 1_020
    recorder.record_upstream()
    source = SqliteSource("velib/upstream", db, "upstream", id_field="station_id",
                          timestamp_field="last_reported", history=True,
                          version_field="recorded_at")
    then = source.fetch(["1"], as_of=1_010)[0]
    now = source.fetch(["1"])[0]
    assert then.payload["num_bikes_available"] == 5 and then.event_timestamp == 900
    assert now.payload["num_bikes_available"] == 6 and now.event_timestamp == 1005


def test_a_failed_or_malformed_poll_is_logged_and_recording_goes_on(tmp_path):
    db = tmp_path / "rec.db"
    feed = Feed(urllib.error.URLError("down"), {"data": {}}, status(990, (5, 900), (2, 950)))
    recorder = Recorder(db, caches=(), clock=Clock(), fetcher=feed)
    assert recorder.record_upstream() == 0
    assert recorder.record_upstream() == 0
    assert recorder.record_upstream() == 2
    with sqlite3.connect(db) as connection:
        statuses = [r[0] for r in connection.execute(
            "SELECT status FROM polls WHERE kind = 'upstream' ORDER BY rowid")]
    assert statuses[0].startswith("error: URLError") and statuses[1].startswith("error: KeyError")
    assert statuses[2] == "ok"


def test_a_restart_does_not_append_every_station_again(tmp_path):
    db = tmp_path / "rec.db"
    feed = Feed(status(990, (5, 900), (2, 950)))
    Recorder(db, caches=(), clock=Clock(), fetcher=feed).record_upstream()
    assert Recorder(db, caches=(), clock=Clock(2_000), fetcher=feed).record_upstream() == 0


def test_a_finished_recording_archives_reproducibly_and_restores(tmp_path):
    from airsbench.livecase.record import archive, restore
    from airsbench.livecase.replay import recording_path

    db = tmp_path / "rec.db"
    Recorder(db, caches=(5,), clock=Clock(), fetcher=Feed(status(990, (5, 900), (2, 950)))
             ).record_upstream()
    first = archive(db, tmp_path / "a.db.gz").read_bytes()
    assert archive(db, tmp_path / "b.db.gz").read_bytes() == first   # same bytes twice
    fresh = tmp_path / "clone" / "velib.db"
    assert recording_path(fresh, tmp_path / "a.db.gz") == fresh and fresh.exists()
    with sqlite3.connect(fresh) as connection:
        assert connection.execute("SELECT COUNT(*) FROM upstream").fetchone()[0] == 2
    assert restore(tmp_path / "a.db.gz", tmp_path / "r.db").stat().st_size > 0
