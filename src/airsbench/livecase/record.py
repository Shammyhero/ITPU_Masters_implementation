"""Record a live GBFS feed, and run real caching pipelines beside it (plan A11).

    python -u -m airsbench.livecase.record --db data/livecase/velib.db --minutes 180

Two kinds of writer, deliberately separate, into one SQLite file (WAL, so the
Analyst can read while it records):

- **The recorder** polls `station_status` every `--status-every` seconds (the feed
  republishes about every 60 s) and appends a row to `upstream` only when a
  station's report changed. That table is the system of record *as observed*: a
  `history: true` source whose version clock is `recorded_at` — the moment the
  recorder first saw that state — so "upstream as of t" is what the feed said at t,
  to within one poll.
- **The pipelines** are what an agent would be served: each fetches the feed on its
  own schedule (every `--caches` minutes) with its own request, and appends the
  whole snapshot to `cache_<K>`. Nothing is derived from the recorder — a cache is a
  real copy, taken when a real cron job would take it (brief correction 12: the data
  and its velocity are real, the pipeline's design is ours).

Two clocks per row, kept apart on purpose:

    last_reported  the station's own report time — the EVENT time, what freshness
                   measures (it is the feed's claim about when the values were true)
    recorded_at    when this copy was taken — the VERSION time, what "as of" orders by

Reads with a User-Agent: the feed answers 403 to Python's default one. One status
request every 20 s plus one per cache refresh is well within polite use of a feed
that republishes once a minute.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

VELIB = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole"
USER_AGENT = "airs-bench/0.1 (academic study; polite polling)"
TIMEOUT_S = 20.0
COLUMNS = ("station_id", "recorded_at", "published_at", "last_reported", "name",
           "num_bikes_available", "num_mechanical", "num_ebikes", "num_docks_available",
           "is_installed", "is_renting", "is_returning")
# What makes a station's state different from its last recorded one.
STATE = ("last_reported", "num_bikes_available", "num_mechanical", "num_ebikes",
         "num_docks_available", "is_installed", "is_renting", "is_returning")

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS stations (station_id TEXT PRIMARY KEY, name TEXT, lat REAL,
    lon REAL, capacity INTEGER, updated_at REAL);
CREATE TABLE IF NOT EXISTS polls (kind TEXT, at REAL, published_at REAL, status TEXT,
    n INTEGER, changed INTEGER);
CREATE TABLE IF NOT EXISTS upstream ({", ".join(COLUMNS)});
CREATE INDEX IF NOT EXISTS upstream_station ON upstream (station_id, recorded_at);
"""


def fetch(url: str, timeout: float = TIMEOUT_S) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                  "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def rows_from_status(document: dict[str, Any], names: dict[str, str],
                     recorded_at: float) -> list[dict[str, Any]]:
    """The feed's stations as table rows. Ids become text; types are split out."""
    published = document.get("lastUpdatedOther", document.get("last_updated"))
    rows = []
    for station in document["data"]["stations"]:
        types: dict[str, int] = {}
        for entry in station.get("num_bikes_available_types") or []:
            types.update(entry)
        station_id = str(station["station_id"])
        rows.append({
            "station_id": station_id,
            "recorded_at": recorded_at,
            "published_at": float(published) if published is not None else None,
            "last_reported": float(station["last_reported"]),
            "name": names.get(station_id),
            "num_bikes_available": int(station["num_bikes_available"]),
            "num_mechanical": int(types.get("mechanical", 0)),
            "num_ebikes": int(types.get("ebike", 0)),
            "num_docks_available": int(station["num_docks_available"]),
            "is_installed": int(station["is_installed"]),
            "is_renting": int(station["is_renting"]),
            "is_returning": int(station["is_returning"]),
        })
    return rows


class Recorder:
    def __init__(self, db: Path, *, base: str = VELIB, caches: tuple[int, ...] = (5, 15),
                 status_every: float = 20.0, clock: Callable[[], float] = time.time,
                 fetcher: Callable[[str], dict[str, Any]] = fetch) -> None:
        self.db = Path(db)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.base = base.rstrip("/")
        self.caches = caches
        self.status_every = status_every
        self.clock = clock
        self.fetcher = fetcher
        self.names: dict[str, str] = {}
        self.last: dict[str, tuple] = {}
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)
            for minutes in caches:
                connection.execute(f"CREATE TABLE IF NOT EXISTS cache_{minutes} "
                                   f"({', '.join(COLUMNS)})")
                connection.execute(f"CREATE INDEX IF NOT EXISTS cache_{minutes}_station "
                                   f"ON cache_{minutes} (station_id, recorded_at)")
            # Resuming: the last recorded state of each station, so a restart does
            # not append a duplicate version of every station.
            for row in connection.execute(
                    f"SELECT station_id, {', '.join(STATE)} FROM upstream u WHERE recorded_at "
                    f"= (SELECT MAX(recorded_at) FROM upstream WHERE station_id = u.station_id)"):
                self.last[row[0]] = tuple(row[1:])
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _log(self, connection, kind: str, at: float, published, status: str, n: int = 0,
             changed: int = 0) -> None:
        connection.execute("INSERT INTO polls VALUES (?, ?, ?, ?, ?, ?)",
                           (kind, at, published, status, n, changed))

    def refresh_stations(self) -> int:
        at = self.clock()
        with closing(self._connect()) as connection:
            try:
                document = self.fetcher(f"{self.base}/station_information.json")
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self._log(connection, "stations", at, None, f"error: {exc}")
                connection.commit()
                return 0
            stations = document["data"]["stations"]
            for s in stations:
                self.names[str(s["station_id"])] = s.get("name")
            connection.executemany(
                "INSERT OR REPLACE INTO stations VALUES (?, ?, ?, ?, ?, ?)",
                [(str(s["station_id"]), s.get("name"), s.get("lat"), s.get("lon"),
                  s.get("capacity"), at) for s in stations])
            self._log(connection, "stations", at, None, "ok", len(stations))
            connection.commit()
        return len(stations)

    def _status(self) -> tuple[float, dict[str, Any] | None, str]:
        """One status fetch; a malformed document is logged like a failed request."""
        at = self.clock()
        try:
            document = self.fetcher(f"{self.base}/station_status.json")
            rows_from_status(document, {}, at)  # validate the shape before anyone uses it
            return at, document, "ok"
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as exc:
            return at, None, f"error: {type(exc).__name__}: {exc}"

    def record_upstream(self) -> int:
        """One poll: append the stations whose state changed. Returns how many."""
        at, document, status = self._status()
        with closing(self._connect()) as connection:
            if document is None:
                self._log(connection, "upstream", at, None, status)
                connection.commit()
                return 0
            rows = rows_from_status(document, self.names, at)
            changed = []
            for row in rows:
                state = tuple(row[k] for k in STATE)
                if self.last.get(row["station_id"]) != state:
                    self.last[row["station_id"]] = state
                    changed.append(tuple(row[c] for c in COLUMNS))
            connection.executemany(f"INSERT INTO upstream VALUES ({', '.join('?' * len(COLUMNS))})",
                                   changed)
            self._log(connection, "upstream", at, rows[0]["published_at"] if rows else None,
                      "ok", len(rows), len(changed))
            connection.commit()
        return len(changed)

    def refresh_cache(self, minutes: int) -> int:
        """A pipeline run: its own request, the whole snapshot appended."""
        at, document, status = self._status()
        with closing(self._connect()) as connection:
            if document is None:
                self._log(connection, f"cache_{minutes}", at, None, status)
                connection.commit()
                return 0
            rows = rows_from_status(document, self.names, at)
            connection.executemany(
                f"INSERT INTO cache_{minutes} VALUES ({', '.join('?' * len(COLUMNS))})",
                [tuple(row[c] for c in COLUMNS) for row in rows])
            self._log(connection, f"cache_{minutes}", at,
                      rows[0]["published_at"] if rows else None, "ok", len(rows), len(rows))
            connection.commit()
        return len(rows)

    def run(self, minutes: float, sleep: Callable[[float], None] = time.sleep,
            say: Callable[[str], None] = print) -> None:
        start = self.clock()
        deadline = start + minutes * 60
        say(f"recording {self.base} into {self.db} for {minutes:g} min "
            f"(status every {self.status_every:g} s, caches every {self.caches} min)")
        self.refresh_stations()
        due = {"upstream": start, "stations": start + 3600}
        due.update({f"cache_{m}": start for m in self.caches})
        polls = changed = 0
        while self.clock() < deadline:
            now = self.clock()
            if now >= due["stations"]:
                self.refresh_stations()
                due["stations"] += 3600
            if now >= due["upstream"]:
                changed += self.record_upstream()
                polls += 1
                due["upstream"] += self.status_every
                if polls % 15 == 0:
                    say(f"  {int((now - start) / 60):>4} min · {polls} polls · "
                        f"{changed} station changes recorded")
            for m in self.caches:
                if now >= due[f"cache_{m}"]:
                    n = self.refresh_cache(m)
                    due[f"cache_{m}"] += m * 60
                    say(f"  cache_{m}: refreshed {n} stations")
            sleep(max(0.0, min(due.values()) - self.clock()))
        say(f"done: {polls} polls, {changed} station changes, {self.db}")


def archive(db: Path, out: Path) -> Path:
    """A committed copy of a finished recording: consolidated, compressed, reproducible.

    SQLite's backup API folds the write-ahead log into one file, and gzip is written
    with mtime 0, so archiving the same recording twice gives the same bytes.
    """
    import gzip
    import tempfile

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "recording.db"
        with closing(sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)) as src, \
                closing(sqlite3.connect(copy)) as dst:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.execute("VACUUM")
        out.write_bytes(gzip.compress(copy.read_bytes(), mtime=0))
    return out


def restore(archived: Path, db: Path) -> Path:
    """The recording, uncompressed where the runner and the analysis read it."""
    import gzip

    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(gzip.decompress(Path(archived).read_bytes()))
    return db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path("data/livecase/velib.db"))
    parser.add_argument("--minutes", type=float, default=180)
    parser.add_argument("--status-every", type=float, default=20.0)
    parser.add_argument("--caches", default="5,15",
                        help="refresh intervals of the caching pipelines, in minutes")
    parser.add_argument("--base", default=VELIB, help="the GBFS feed's base url")
    parser.add_argument("--archive", type=Path, default=None, metavar="OUT.db.gz",
                        help="write a finished recording's committed copy and stop")
    args = parser.parse_args(argv)
    if args.archive is not None:
        print(f"archived {args.db} -> {archive(args.db, args.archive)}")
        return 0
    caches = tuple(int(m) for m in args.caches.split(",") if m)
    Recorder(args.db, base=args.base, caches=caches, status_every=args.status_every).run(
        args.minutes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
