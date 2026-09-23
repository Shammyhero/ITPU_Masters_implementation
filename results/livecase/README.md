# The live case study's recording (A11)

`velib-2026-09-23.db.gz` — a SQLite database, gzip-compressed: three hours of the
**Vélib' Métropole** (Paris) bike-share feed, recorded on 23 September 2026 from
13:57 UTC (the evening commute), with the two caching pipelines the case study
serves its questions from.

**Source and licence.** Data from Vélib' Métropole's open GBFS feed
(<https://www.velib-metropole.fr/donnees-open-data-gbfs-du-service-velib-metropole>),
published under the Etalab **Licence Ouverte / Open Licence**, which permits reuse and
redistribution with attribution. Attribution: *Vélib' Métropole — données ouvertes
GBFS, 23 septembre 2026*. The recording is the feed as observed; nothing in it is
altered.

**What is in it.** `upstream` (every station's state, appended when it changed,
polled every 20 s), `cache_5` and `cache_15` (full snapshots taken by two independent
pipelines every 5 and 15 minutes), `stations` (names, coordinates, capacity) and
`polls` (every request's outcome). Design: `docs/live_case_study.md`.

**Using it.** The runner and the analysis restore it to `data/livecase/velib.db` on
first use (`airsbench.livecase.replay.recording_path`):

```bash
python -m airsbench.analysis.livecase --figure docs/figures/fig4_11_livecase.png
```

It is committed because every published number must regenerate from the repository
(invariant 7) — the run artifacts in `results/runs/` store question ids and seeds,
never records, and this is where the records come from.
