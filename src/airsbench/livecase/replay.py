"""The recording, replayed: questions asked at seeded moments of a real evening.

A question is a moment *t* in the recording and the six stations a rider's app
would show there: an anchor station installed at *t* and its five nearest
installed neighbours. What the agent is served is a cache — the table a real
pipeline refreshed every K minutes — as it stood at *t*; the answer key is the
recorder's view of the feed at *t*. Both are read through A10's `SqliteSource`,
so the Analyst's loop answers, measures and verifies exactly as it does on any
declared source.

**Paired (invariant 2).** The moment, the anchor and the six stations come from
the seed and the RECORDER only — never from the cache being asked about or the
model answering — so every cell of the case study sees the same questions.

**The moment a record is read is t, not today.** A replayed record's age is
`t − last_reported`. Left to the source's clock it would be read "now", hours
after the recording ended, and every record would look hours old.

**The consistency reference is the feed version the cache copied**
(`served_as_of`): upstream as the recorder held it once it had seen the same feed
publication the pipeline fetched. Consistency then measures what the pipeline did
to the values, and freshness how old they were (invariant 5; A1's rule).

*Corrected 23 Sep, after the paid run:* the reference was first the cache's
snapshot **moment** (`reference="clock"`). The recorder polls about every 41 s, so
at most snapshot moments it still held the PREVIOUS feed version (23 of 36 5-min
copies, 10 of 12 15-min ones): consistency fell below 100 on half the questions
and four answers read `corrupted_in_transit`, although the caches copy the feed
exactly. Aligning by feed version (`reference="version"`, the default) removes
that where it can: the feed stamps one publication up to a second apart on
different requests, so versions match within `PUBLICATION_JITTER_S`; where the
recorder saw the same publication, the copies agree on 100% of stations. It never
saw 20 of the 48 publications the caches copied (it polled every ~41 s against a
~60 s feed), and those fall back to the clock — so on this source, consistency below
100 is a gap in the reference, not something the pipeline did. The runs as
executed used the clock reference; the analysis reports both.
"""

from __future__ import annotations

import bisect
import math
import random
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Sequence

from agentic_faults import Record

from ..runner.config import LIVECASE_CACHES
from ..sources.base import Sample, SourceError, SourcePair, SourceSchema
from ..sources.tables import SqliteSource

# Where the recording is read, and the committed copy it is restored from on a
# fresh clone (the recording is data under the Etalab Licence Ouverte: see
# results/livecase/README.md for the attribution).
DEFAULT_DB = Path("data/livecase/velib.db")
ARCHIVE = Path("results/livecase/velib-2026-09-23.db.gz")


def recording_path(db: Path = DEFAULT_DB, archived: Path = ARCHIVE) -> Path:
    """The recording, restored from the committed archive if it is not on disk yet."""
    db = Path(db)
    if not db.exists() and Path(archived).exists():
        from .record import restore

        restore(archived, db)
    return db


# What a rider's app shows — and all the agent is given. The recorder's own
# timestamps (`published_at`, `recorded_at`) never reach a payload: a timestamp
# beside the values would be the detectability treatment, by accident.
PAYLOAD = ("name", "num_bikes_available", "num_mechanical", "num_ebikes",
           "num_docks_available", "is_installed", "is_renting", "is_returning")
N_STATIONS = 6
# One publication, stamped up to a second apart on different requests (measured 23 Sep).
PUBLICATION_JITTER_S = 2.0


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres (haversine); plenty for neighbours in a city."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6_371_000 * 2 * math.asin(math.sqrt(h))


class Recording:
    """One recorded evening: the recorder's history, the caches, the stations."""

    def __init__(self, db: Path, caches: Sequence[int] = LIVECASE_CACHES,
                 reference: str = "version") -> None:
        if reference not in ("version", "clock"):
            raise ValueError("reference is 'version' or 'clock'")
        self.reference = reference
        self.db = Path(db)
        if not self.db.is_file():
            raise SourceError(f"no recording at {self.db}; record one with "
                              f"python -m airsbench.livecase.record")
        self.caches = tuple(caches)
        with closing(sqlite3.connect(f"{self.db.resolve().as_uri()}?mode=ro", uri=True)) as c:
            self.coords = {str(sid): (lat, lon) for sid, lat, lon in
                           c.execute("SELECT station_id, lat, lon FROM stations "
                                     "WHERE lat IS NOT NULL AND lon IS NOT NULL")}
            self.names = {str(sid): name for sid, name in
                          c.execute("SELECT station_id, name FROM stations")}
            self.snapshots = {
                minutes: [row[0] for row in c.execute(
                    f"SELECT DISTINCT recorded_at FROM cache_{minutes} ORDER BY recorded_at")]
                for minutes in self.caches}
            (last,) = c.execute("SELECT MAX(at) FROM polls WHERE kind = 'upstream' "
                                "AND status = 'ok'").fetchone()
            # The feed version each copy holds, and when the recorder first saw it.
            saw: dict[float, float] = {}
            for at, published in c.execute(
                    "SELECT at, published_at FROM polls WHERE kind = 'upstream' AND "
                    "status = 'ok' AND published_at IS NOT NULL ORDER BY at"):
                saw.setdefault(float(published), float(at))
            self._published = sorted(saw)           # publications the recorder saw
            self._recorder_saw = saw                # ... and when it first saw each
            self._copied: dict[int, dict[float, float]] = {
                minutes: {float(at): float(published) for at, published in c.execute(
                    f"SELECT at, published_at FROM polls WHERE kind = 'cache_{minutes}' "
                    f"AND status = 'ok' AND published_at IS NOT NULL")}
                for minutes in self.caches}
            # Which stations were installed when: read once, not once per question
            # (the history is ~60 000 rows; draw() needs only this column of it).
            self._installed: dict[str, tuple[list[float], list[int]]] = {}
            for sid, at, installed in c.execute(
                    "SELECT station_id, recorded_at, is_installed FROM upstream "
                    "ORDER BY station_id, recorded_at"):
                times, flags = self._installed.setdefault(str(sid), ([], []))
                times.append(float(at))
                flags.append(int(installed))
        if not all(self.snapshots.values()) or last is None:
            raise SourceError(f"{self.db}: the recording has no cache snapshot or no "
                              f"successful poll yet")
        # A question is only fair once every cache has taken its first copy.
        self.start = max(snaps[0] for snaps in self.snapshots.values())
        self.end = float(last)
        if self.end <= self.start:
            raise SourceError(f"{self.db}: the recording is shorter than its slowest cache")
        self.upstream = SqliteSource(
            "velib/upstream", self.db, "upstream", columns=PAYLOAD, id_field="station_id",
            timestamp_field="last_reported", history=True, version_field="recorded_at")

    def cache(self, minutes: int) -> SqliteSource:
        return SqliteSource(f"velib/cache-{minutes}min", self.db, f"cache_{minutes}",
                            columns=PAYLOAD, id_field="station_id",
                            timestamp_field="last_reported", history=True,
                            version_field="recorded_at")

    def snapshot_at(self, minutes: int, t: float) -> float:
        """When the cache's copy that was current at `t` was taken."""
        snaps = self.snapshots[minutes]
        return snaps[bisect.bisect_right(snaps, t) - 1]

    def reference_for(self, minutes: int, snapshot: float) -> float:
        """The moment upstream held exactly what this copy holds.

        By feed version: when the recorder first saw the publication the cache
        copied. Falls back to the snapshot's own moment if the recorder never saw
        that version (it saw 213 of the evening's publications), and always under
        `reference="clock"`, which is how the paid runs were executed.
        """
        if self.reference == "clock":
            return snapshot
        published = self._copied.get(minutes, {}).get(snapshot)
        if published is None:
            return snapshot
        # The feed stamps one publication a second apart on different requests
        # (…840, …841), so a publication is matched to within PUBLICATION_JITTER_S.
        i = bisect.bisect_left(self._published, published)
        near = [p for p in self._published[max(0, i - 1):i + 1]
                if abs(p - published) <= PUBLICATION_JITTER_S]
        if not near:
            return snapshot  # the recorder never saw this publication
        return self._recorder_saw[min(near, key=lambda p: abs(p - published))]

    def reference_coverage(self) -> dict[int, tuple[int, int]]:
        """Per cache: copies whose publication the recorder saw, of all copies."""
        return {m: (sum(self.reference_for(m, snap) != snap or self._saw_exactly(m, snap)
                        for snap in snaps), len(snaps))
                for m, snaps in self.snapshots.items()}

    def _saw_exactly(self, minutes: int, snapshot: float) -> bool:
        published = self._copied.get(minutes, {}).get(snapshot)
        return published is not None and any(
            abs(p - published) <= PUBLICATION_JITTER_S for p in self._published)

    def installed_at(self, station: str, t: float) -> bool:
        """Was the station installed in its latest recorded state at or before `t`?"""
        times, flags = self._installed[station]
        i = bisect.bisect_right(times, t) - 1
        return i >= 0 and flags[i] == 1

    def draw(self, seed: int, n: int = N_STATIONS) -> tuple[float, str, list[str]]:
        """The moment, the anchor station and the stations shown — from the seed and
        the recorder alone, so every cache and every model gets the same question."""
        rng = random.Random(seed)
        t = rng.uniform(self.start, self.end)
        installed = sorted(sid for sid in self._installed
                           if sid in self.coords and self.installed_at(sid, t))
        if len(installed) < n:
            raise SourceError(f"only {len(installed)} installed stations at {t:.0f}")
        anchor = rng.choice(installed)
        here = self.coords[anchor]
        nearest = sorted(installed, key=lambda sid: (_distance_m(here, self.coords[sid]), sid))
        return t, anchor, nearest[:n]

    def pair(self, minutes: int, freshness_target_s: float | None = None) -> SourcePair:
        return SourcePair(
            id=f"velib-cache-{minutes}min", kind="sqlite",
            delivered=CacheReplay(self, minutes), upstream=self.upstream,
            description=(f"Vélib' Métropole, recorded live: a cache refreshed every "
                         f"{minutes} min, against the feed as recorded every 20 s"),
            freshness_target_s=freshness_target_s)


class CacheReplay:
    """The delivered side: a cache as it stood at a question's moment."""

    def __init__(self, recording: Recording, minutes: int) -> None:
        self.recording = recording
        self.minutes = minutes
        self.source = recording.cache(minutes)
        self.name = self.source.name

    def describe(self) -> SourceSchema:
        return self.source.describe()

    def sample(self, n: int = N_STATIONS, *, key: str | None = None,
               seed: int | None = None) -> Sample:
        if key is not None:
            raise SourceError(f"{self.name}: questions are drawn by seed, not by key")
        if seed is None:
            raise SourceError(f"{self.name}: a replayed question needs a seed")
        t, anchor, ids = self.recording.draw(seed, n)
        snapshot = self.recording.snapshot_at(self.minutes, t)
        reference = self.recording.reference_for(self.minutes, snapshot)
        records = self.source.fetch(ids, as_of=t)
        for record in records:
            record.read_timestamp = t  # read at the question's moment, not today
        return Sample(
            records=records, ids=[r.meta["record_id"] for r in records], as_of=t, key=anchor,
            meta={"query": self.recording.names.get(anchor) or anchor,
                  "served_as_of": reference, "snapshot_at": snapshot,
                  "cache_minutes": self.minutes,
                  "cache_age_seconds": t - snapshot,
                  "condition": f"a cache refreshed every {self.minutes} min"})

    def fetch(self, ids: Sequence[str], *, as_of: float | None = None) -> list[Record]:
        raise SourceError(f"{self.name}: the delivered side is read by drawing a question; "
                          f"read the upstream side for records by id")


def as_dict(sample: Sample) -> dict[str, Any]:
    """A question's identity, for the artifact: never the records themselves."""
    return {"moment": sample.as_of, "anchor": sample.key, "ids": list(sample.ids),
            "cache_age_seconds": sample.meta.get("cache_age_seconds")}
