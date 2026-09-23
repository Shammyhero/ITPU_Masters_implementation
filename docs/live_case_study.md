# The live-source case study (A11) — design

**Status: COMPLETE 23 Sep 2026** — results in
[`live_case_study_findings.md`](live_case_study_findings.md), Fig 4.11. Recorded 13:57–16:57
UTC (180 min, 0 errors), archived in `results/livecase/`; 4 paid runs, **$0.1940**. The
consistency reference was corrected after the run, at $0, by re-grading the logged answers
(§7 and the findings §4). Was: recording from 13:57 UTC, 180 min — Paris's evening
commute. **Built while it records ($0, 949 tests):** the recorder
(`livecase/record.py`), the replay (`livecase/replay.py`), the questions
(`livecase/questions.py`), the runner with its exact dry-run (`livecase/run.py`), the
analysis and Fig 4.11 (`analysis/livecase.py`). Dry-run on the first minutes: **≈ $0.24**
for the four paid cells. Design approved by the author on 23 Sep (record, then replay; GBFS; models
gpt-4o-mini + claude-haiku-4-5 within ≈ $0.25, ceiling $0.40; real-world questions).
Nothing paid yet. Results will go in `live_case_study_findings.md`, Fig 4.11.

## 1. The question

Every result so far comes from the study's own datasets, with staleness *simulated*
(the ESCI catalog's update stream, the BTS flights). RQs v2 §9 declares one test of
transfer (H-L): *on a real source with genuine update velocity, does AIRS rank the
answers that fail above the answers that do not?* — and the attribution split, the
lag distribution and a null are all reportable.

## 2. The source: Vélib' Métropole (Paris), live

- **Why this feed.** GBFS is an open standard ([gbfs.org](https://gbfs.org/get-started/),
  MobilityData's `systems.csv` registry). Vélib' publishes it keyless, as JSON,
  refreshed about every minute, under the Etalab Licence Ouverte
  ([Vélib' open data](https://www.velib-metropole.fr/donnees-open-data-gbfs-du-service-velib-metropole)).
  It is the largest system in the registry's candidates (1,517 stations), and
  recording starts at 16:00 Paris time, into the evening commute.
- **Measured before recording (23 Sep, $0):** the feed republishes every ~60 s;
  **~190 of 1,517 stations (12.5%) change their counts every minute**, 21% over two
  minutes. Stations' `last_reported` is a median **149 s** old (p90 389 s), and a
  handful report timestamps years old (likely offline stations). The feed answers
  **403 to Python's default User-Agent**. *Corrected in session:* an earlier probe
  suggested a one-hour clock offset; measured directly against UTC there is none.
- Rider-facing fields kept: station name, bikes available (mechanical, e-bike), free
  docks, whether it is renting and returning.

## 3. The pipeline: record, then replay

Recording (`airsbench/livecase/record.py`, one SQLite file, WAL):

| table | written by | what it is |
|---|---|---|
| `upstream` | the **recorder**, every 20 s | each station's state, appended only when it changes — the system of record *as observed* |
| `cache_5` | a **pipeline** job, every 5 min | its own fetch, the whole snapshot — what an agent is served |
| `cache_15` | a second pipeline, every 15 min | the same, less often |
| `stations`, `polls` | the recorder | names, coordinates, capacity; every request's outcome |

Two clocks per row, kept apart: **`last_reported`**, the station's own report time — the
event time freshness measures — and **`recorded_at`**, when the copy was taken — the
version time "as of" orders by (`version_field`, added to A10 for this). The caches
are real copies taken on a real schedule, never derived from the recorder (brief
correction 12: the data and its velocity are real; the pipeline's design is ours).

**Why replay instead of asking live:** an http upstream has no history, so a lagging
cache's wrong answer would read `corrupted_in_transit` rather than `answer_key_moved`
(found running A10). With the feed recorded, upstream can be read *as of* any moment,
and consistency and attribution are scored exactly as in the corpus.

## 4. Questions a rider asks

Each question is drawn at a seeded moment *t* in the recording (after both caches have
their first snapshot) around a seeded **anchor station** — a station installed at *t* —
with its five nearest installed neighbours by distance: the six stations a rider's app
shows. Three question types, rotated (question *i* gets type *i* mod 3):

| type | wording | checkable plan |
|---|---|---|
| `bikes` | "I'm at {anchor}. Which of these nearby stations has the most bikes available right now?" | max_by `num_bikes_available`, where `is_renting` = 1 |
| `docks` | "I need to return a bike near {anchor}. Which of these nearby stations has the most free docks right now?" | max_by `num_docks_available`, where `is_returning` = 1 |
| `empty` | "How many of these stations near {anchor} have no bikes available right now?" | count_where `num_bikes_available` = 0 |

Invariant 1 holds: nothing in a question or the prompt mentions data quality or age.

## 5. Design

- **Paired (invariant 2).** A question — moment, anchor, the six stations — depends
  only on its seed, never on the cache or the model, so every cell answers the same
  questions. Question *i* uses seed `sample_seed × 1 000 + i`.
- **Cells (paid):** {gpt-4o-mini, claude-haiku-4-5} × {cache 5 min, cache 15 min}, **50
  questions each** — 100 per model, 200 in all. Estimated ≈ $0.03 + $0.20; the dry-run
  counts every prompt before anything is spent, `--max-cost 0.40`.
- **Exposure at scale ($0):** the literal answerer — the plan executed on the served
  records at face value — over many more questions (≈ 600 per cache), giving the flip
  rate by cache interval and question type with no model involved, as the freshness
  sweep's exposure did.
- **Artifacts:** one JSON per (model, cache) in `results/runs/`, a new seed block
  **`livecase`, 110 000–120 000**, in `NEVER_POOLED` — real data and the plan-returning
  prompt are a different instrument from the corpus. `RunConfig`: `pipeline =
  velib-cache-<K>min`, `fault_type = none` (nothing is injected — the lag is the
  pipeline's own), `dataset = velib_live`.
- **Semantic** stays UNMEASURED (no reviewed manifest); AIRS rests on freshness and
  consistency, and says so. Latency is UNMEASURED (no delivery telemetry).

## 6. Analysis — H-L and Fig 4.11

- **Lag:** the cache's age at question time and each record's age (`t − last_reported`),
  per cache.
- **Exposure:** the share of questions whose answer key moved between the cache's
  snapshot and *t*, by cache interval and question type (literal, $0; and in the paid
  cells).
- **Outcomes and attribution:** correct / silent / abstained, and the four labels, per
  model and cache.
- **H-L:** the AUC of AIRS (lower = riskier) for separating silent failures from the
  rest, with a bootstrap interval; freshness alone and the model's confidence beside it
  (RQ4's comparison, on real data). A null is reportable.

## 7. Found building it (23 Sep)

- **A history needs two clocks.** A10's history ordered versions by the event time;
  here the event (`last_reported`) and the version (`recorded_at`) differ, so A10 gained
  `version_field`. Also `columns` (read only named columns — the recorder's own
  `published_at` must never reach the agent, or a timestamp would be the detectability
  treatment by accident) and an id filter pushed down to SQL (≈ 90 000 rows would
  otherwise be read several times per question).
- **A replayed record must be read at the question's moment**, not today; left to the
  source's clock, every record would be hours old.
- **A pre-existing defect, fixed:** the loop's gate never received the semantic
  two-state rule, so every source without a reviewed manifest (files, inline, SQLite,
  HTTP) scored semantic **0** in the loop, API and console — lowering AIRS and able to
  make a semantic policy refuse — while `airs analyst ask` said UNMEASURED. Since A6.
  `Controller.evaluate(semantic_unmeasured=…)`, and a regression test.
- **AIRS's freshness curve floors on real ages.** `100 × 1 s / mean age`: minute-scale
  records score 0.1–0.3, so freshness still *ranks* questions by age but contributes
  almost nothing to the composite, which on this source is driven by consistency. That
  is the underived-constants limitation (REVIEW F-B1) meeting real data; the analysis
  reports record age beside AIRS so it cannot hide.
- **First look ($0, 60 literal questions on 11 minutes):** the lag moved the answer on
  5% of questions with the 5-min cache and 8% with the 15-min one; "how many stations
  are empty?" moves most. Not a result.

- **Corrected after the run: the consistency reference.** Graded by wall-clock moment, the
  recorder (polling every ~41 s, not the 20 s targeted) usually held the feed's PREVIOUS
  publication when a cache took its copy. Graded by the publication the cache copied —
  matched within 2 s, because the feed stamps one publication a second apart on different
  requests — copies agree with the recorder on 100% of stations wherever it saw them (28
  of 48 copies). The logged answers were re-graded at $0; under the old reference the
  re-grading reproduces all 200 logged decisions exactly.
- **The records' `last_reported` is not their data's age**: a quiet station reports
  rarely. Median record age 33–38 min while the caches were 2.6 / 7.9 min old.

## 8. Limitations (known before running)

- One city, one evening, three hours; one question family.
- The pipelines are ours (cron-like caches), not an operator's production pipeline.
- `upstream` is the feed *as observed* every 20 s, so "truth" can itself lag by up to
  one poll plus the feed's own minute.
- Semantic and latency are unmeasured, so AIRS rests on two dimensions.
