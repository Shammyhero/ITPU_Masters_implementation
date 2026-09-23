# The live-source case study (A11) — results

**Run:** 23 Sep 2026 · Vélib' Métropole (Paris), recorded 13:57–16:57 UTC · 4 paid runs,
200 questions · **$0.1940** (dry-run $0.2389, cap $0.40) · gpt-4o-mini + claude-haiku-4-5
· design: `live_case_study.md` · recording: `results/livecase/` (Licence Ouverte)

```bash
python -m airsbench.analysis.livecase --figure docs/figures/fig4_11_livecase.png
```

Every other result in the thesis rests on the study's own datasets with staleness
*simulated*. This one does not: a real public feed, a real caching pipeline in front of
it, and the same Analyst loop, verifier and AIRS measurement the product runs.

## Verdict: the lag is real and it doubles silent failure; AIRS, as calibrated, does not see it coming

1. **A slower cache doubles silent failure, for both models.** The same 50 questions,
   the same moments, only the pipeline's refresh interval changed: gpt-4o-mini 4% → 10%,
   claude-haiku-4-5 8% → 16%. Paired, every discordant question moved the same way
   (3/0 and 4/0; Haiku +8.0 pp [+2.0, +16.0]).
2. **The mechanism is exposure, as in the corpus.** With no model at all, the 15-minute
   cache moved the answer on **11.0%** of 600 questions against **5.7%** for the
   5-minute cache — twice as often, like-for-like (RQ1's *exposure × conditional rate*,
   now on real data).
3. **H-L is null for AIRS on this source**: AUC **0.557 [0.435, 0.675]** for ranking silent
   failures first. The signal is there — the records' age alone ranks them at **0.690
   [0.547, 0.827]** — but AIRS's calibrated freshness curve flattens minute-scale ages to
   nearly nothing, so its composite is carried by a consistency term that, here, measures
   gaps in the reference rather than anything the pipeline did (§4). This is REVIEW F-B1
   — AIRS's constants are underived — meeting real data, and it is the case study's most
   useful result for the thesis: **a readiness score's timescale has to be the source's.**

---

## 1. The source and the recording

- **The feed** (GBFS, keyless, Etalab Licence Ouverte): 1,517 stations; it republished
  about once a minute, and **341 station changes a minute** were recorded (counts, and
  report times). Recording: 180 minutes, 264 polls, **0 errors**; the recorder saw **213
  distinct publications**. Two caching pipelines took 36 (every 5 min) and 12 (every 15
  min) full copies.
- **How old were the answers' records?** The cache's own age at a question was a median
  **2.6 min** (5-min cache) and **7.9 min** (15-min cache). The records' own report time
  was a median **32.9 / 38.1 min** old (p90 58.9 / 65.6): a quiet station reports rarely,
  so its `last_reported` ages even while its numbers stay current. Report time is the
  feed's clock, and it measures reporting cadence as much as staleness.

## 2. Exposure at scale — no model, $0 (Fig 4.11 A)

The literal answer — the question's plan executed on the served records at face value —
over 600 questions per cache, the first 50 of which are the paid questions:

| question | cache 5 min | cache 15 min |
|---|---|---|
| most bikes nearby | 7.0% [3.9, 11.5] | **15.0%** [10.4, 20.7] |
| most free docks nearby | 4.5% [2.1, 8.4] | 6.5% [3.5, 10.9] |
| how many nearby are empty | 5.5% [2.8, 9.6] | 11.5% [7.4, 16.8] |
| **all** | **5.7%** [4.0, 7.8] (34/600) | **11.0%** [8.6, 13.8] (66/600) |

Share of questions whose answer the lag moved; exact 95% intervals. "Where can I get a
bike?" is the question the lag hurts most.

## 3. The paid cells (Fig 4.11 B)

Same 50 questions in every row; verifiable questions; graded against the
version-aligned reference (§4).

| model | cache | correct | silent | abstained | flipped | key moved / both / in transit / agent | $ |
|---|---|---|---|---|---|---|---|
| gpt-4o-mini | 5 min | 48 | **2** | 0 | 2 | 1 / 1 / 0 / 0 | 0.0099 |
| gpt-4o-mini | 15 min | 45 | **5** | 0 | 3 | 3 / 0 / 0 / 2 | 0.0098 |
| claude-haiku-4-5 | 5 min | 45 | **4** | 1 | 2 | 1 / 1 / 1 / 1 | 0.0866 |
| claude-haiku-4-5 | 15 min | 41 | **8** | 1 | 3 | 2 / 1 / 1 / 4 | 0.0877 |

- **Silent failure, 15-min − 5-min cache, paired:** gpt-4o-mini **+6.0 pp** [+0.0, +14.0],
  discordant 3/0; claude-haiku-4-5 **+8.0 pp** [+2.0, +16.0], discordant 4/0.
- Of the 19 silent failures, **10 are the pipeline's** (answer key moved, or both) and 7
  the models' own on intact records; 2 sit on copies the reference could not match (§4).
- Almost no abstention (2 of 200): as in the corpus, the models answer, confidently.

## 4. The consistency reference — corrected after the run, at $0

The runs graded consistency against upstream as the recorder held it at the moment a
cache took its copy (the *clock* reference). The recorder polled about every 41 s — its
target was 20 s; each request took ~20 s — against a feed that publishes every ~60 s, so
at most copy moments it still held the **previous** publication (23 of 36 5-min copies,
10 of 12 15-min ones). Consistency fell below 100 on 96 of 200 questions and four
answers read `corrupted_in_transit`, although the caches copy the feed exactly.

The fix grades against **the publication the cache copied**. Two things measured on the
way:

- **The feed stamps one publication up to a second apart on different requests**
  (…840 and …841) — it is served by more than one node. Publications are matched within
  2 s.
- **Where the recorder saw the same publication, the copies agree on 100% of stations**
  (11,200 of 11,200 checked). The source is consistent, and the pipelines copy it
  exactly. The recorder missed **20 of the 48** publications the caches copied, and those
  fall back to the clock.

**The re-grading is licensed by reproduction.** Every question regenerates from the
committed recording and its seed, and the models' logged answers are replayed into the
same loop — no model is called. Under the clock reference the runs used, this reproduces
**200 of 200** logged decisions exactly (correctness, silent failure, attribution, flip,
AIRS). Under the version-aligned reference: consistency = 100 on **146/200** questions
(from 104), `corrupted_in_transit` 4 → 2, and silent failure unchanged (19) — correctness
is graded against the truth at the question's moment, which the reference does not
touch. The artifacts keep the run's own labels; this document reports the corrected ones,
and the analysis prints both.

## 5. H-L — does AIRS rank the failures first? (Fig 4.11 C)

200 answers, 19 silent failures, AUC with a 95% bootstrap interval (higher = the signal
put failures first):

| signal | version-aligned | as run (clock) |
|---|---|---|
| **AIRS** (100 − composite) | **0.557** [0.435, 0.675] | 0.567 [0.452, 0.681] |
| the records' age (what AIRS freshness is built from) | **0.690** [0.547, 0.827] | 0.690 [0.547, 0.827] |
| the cache's age (the pipeline's lag — *not available to AIRS*) | 0.612 [0.506, 0.714] | 0.612 [0.506, 0.714] |
| the model's confidence (1 − confidence) | 0.623 [0.490, 0.753] | 0.623 [0.490, 0.753] |

**AIRS is not distinguishable from chance here**, and the reasons are identifiable rather
than mysterious:

- **The freshness curve floors.** `100 × 1 s / mean age`: records minutes old score
  0.1–0.3 out of 100. Age still *ranks* the questions — hence the records' age at 0.690 —
  but freshness then contributes almost nothing to a composite whose weights were fitted
  on seconds of simulated staleness.
- **The composite is carried by consistency** — 0.702 of the 0.831 weight measured here —
  which on this source measures only whether the recorder saw the cache's publication
  (§4), nothing the pipeline did.
- **19 silent failures is little evidence.** The intervals are wide for every signal; only
  the records' age clears 0.5 clearly, and the cache's age barely (0.506).

The honest reading: the ingredients of AIRS transfer — age ranks real failures — but
AIRS's *calibration* does not, because its freshness target (1 s) and weights were set on
the study's timescale, not this source's. That is F-B1 made concrete. A practitioner
would set the freshness target to the source's own cadence (here, minutes), and it is a
declared parameter (`DEFAULT_FRESHNESS_TARGET_S`), not a constant to trust.

### 5a. Exploratory: the same answers, scored with the source's own freshness target

Declared **before** it was computed (24 Sep), so the target is not tuned to the
outcome: a source's freshness target is **its own publication interval** — for Vélib',
**60 s**, the feed's measured cadence (§1). The logged answers are re-graded at $0 with
that target (the per-source `freshness_target_s`, added for this lesson), against the
version-aligned reference. Only how age is *scored* changes; the answers, the truth and
every other dimension are the same.

| freshness target | median freshness score | AIRS AUC |
|---|---|---|
| 1 s (calibrated) | 0.04 | 0.557 [0.435, 0.675] |
| **60 s** (the feed's cadence, declared in advance) | 2.70 | **0.558** [0.435, 0.677] |

**No change.** The target is necessary but, on this source, not sufficient, for two
reasons the numbers show. The event clock is the stations' `last_reported`, a median
~33 min old (§1), so even at 60 s freshness sits near its floor. And the composite's
weights — consistency 0.702, freshness 0.129 on the retrieval profile — were fitted on
the corpus, so freshness could not move AIRS much at any target. No other target was
tried: choosing one to fit this data (≈ 30 min) would be tuning on the outcome. The
honest conclusion for Chapter 5 is sharper than "retune one constant": **transferring
AIRS needs the event clock, the target and the weights set for the source** — the
records' raw age already ranks these failures (0.690); the calibrated composite does not.

## 6. What this adds to the thesis

- **External validity for RQ1's mechanism.** On real data at real velocity, silent failure
  scales with exposure, and exposure with the pipeline's lag — the corpus's decomposition
  holds outside the corpus.
- **External validity for the attribution.** With the source recorded, the verifier
  separates the pipeline's failures (10) from the models' (7) exactly as it does on the
  corpus, on a source it was not built for.
- **A limit on RQ4.** AIRS's ranking power (ρ −0.75 to −0.88 held out, in the corpus) does
  not carry over untuned. Its components do; its calibration does not.
- **Two first-hand observations of real data infrastructure**, measured rather than cited:
  a public feed stamps one publication differently on different requests, and a station's
  report time is not its data's age.

## 7. Limitations

- One city, one evening, three hours; three question types; two models; 50 questions per
  cell. The case study is descriptive and the intervals say so.
- The pipelines are ours (cron-like caches), though the data and its velocity are real
  (brief correction 12).
- The reference is the feed *as observed*: polled every ~41 s, it missed 20 of the 48
  publications the caches copied, and "truth" at a moment can lag the live feed by up to
  one poll plus the feed's own minute.
- Semantic is UNMEASURED (no reviewed manifest) and latency UNMEASURED (no delivery
  telemetry): AIRS rests on freshness and consistency only — 0.831 of the retrieval
  profile's weight, of which consistency alone is 0.702 (latency carries none).
- The Analyst's plan-returning prompt is a different instrument from the corpus agent's:
  the rates compare within the case study, never with the corpus.
