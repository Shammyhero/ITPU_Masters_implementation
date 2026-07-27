# Flip-partition analysis — results

**Run:** 2026-07-27 · 36 retrieval runs · 2 808 decisions · **$0, no API calls**

```bash
python -m airsbench.analysis.flip_partition
```

Retroactive over the 66 completed runs. Answers the question raised in
`campaign_status.md` §"Known weakness": how much of the freshness accuracy drop
is the agent failing, and how much is arithmetic?

**Answer: all of it is arithmetic.** Which is what makes the real finding
visible.

---

## 1. Why the reconstruction is admissible

Query sampling and query timestamps derive from `RunConfig.sample_seed`
(invariant 2), so replaying that seed regenerates the identical queries at the
identical simulated times. Each replayed query is checked against the logged
`ground_truth` before it is used; a divergence raises rather than being
silently realigned.

**Replay verified for all 36 retrieval runs, decision by decision.** Pinned by
`tests/test_flip_partition.py`, which also pins `CatalogIndex` against
`CatalogTimeMachine.state_at` (the index exists only to make ~5.7k lookups
affordable — it must answer identically).

Retrieval only: the classification label (`ArrDel15`) is a property of the
flight, not of the catalog, so staleness there attenuates a *feature* rather
than moving the correct answer. There is no flip to partition on.

---

## 2. The table

Pooled over both pipelines. **Residual** = accuracy on queries whose answer did
*not* flip, minus the same quantity at baseline. It is the part of the
degradation that is not mechanical — the part attributable to the agent being
impaired rather than to the answer key having moved.

| condition | raw acc | unflipped acc | **residual** | flip % | n flipped | abstain \| flip | silent \| flip |
|---|---|---|---|---|---|---|---|
| baseline | 0.830 | 0.860 | — | 3.5% | 11 | 0% | 100% |
| freshness / mild | 0.795 | 0.858 | **−0.003** | 7.7% | 24 | 8% | 88% |
| freshness / severe | 0.769 | 0.868 | **+0.008** | 12.5% | 39 | 3% | 90% |
| latency / mild | 0.830 | 0.860 | +0.000 | 3.5% | 11 | 9% | 91% |
| latency / severe | 0.830 | 0.860 | +0.000 | 3.5% | 11 | 0% | 100% |
| schema drift / mild | 0.804 | 0.834 | −0.027 | 3.5% | 11 | 0% | 100% |
| schema drift / severe | 0.683 | 0.701 | **−0.159** | 3.5% | 11 | 0% | 82% |
| semantic stripping / mild | 0.788 | 0.817 | −0.043 | 3.5% | 11 | 0% | 100% |
| semantic stripping / severe | 0.747 | 0.767 | **−0.093** | 3.5% | 11 | 0% | 82% |

The 3.5% flip rate in every non-freshness row is the **batch arm's inherent
3 s staleness** (7.1% within batch, 0% within streaming) — not noise. It is
present in the baseline too, which is itself informative (§5).

---

## 3. Finding 1 — freshness does not impair the agent at all

Accuracy on queries whose answer did *not* flip: baseline **0.860**, freshness
mild **0.858**, freshness severe **0.868**. Residual −0.003 and +0.008 — zero
within noise, and non-monotone, so not a suppressed effect.

> **Freshness costs accuracy exactly and only where it moved the correct
> answer.** The agent's reasoning is completely unimpaired by stale data.

The headline "freshness lowers accuracy by 12.9 points" is therefore a
measurement of the answer-flip rate, performed with a language model. It must
not be reported as a result about the agent. Chapter 3 gains this caveat;
Chapter 4 reports the flip-conditioned failure mode instead.

## 4. Finding 2 — the real freshness result, and it is worse than the raw number

On the 63 queries where staleness moved the correct answer, pooled across
severities:

| | |
|---|---|
| abstained | **5%** |
| silent failure (confident and wrong) | **89%** |
| chose the best answer *present in the data it was shown* | **71%** |
| mean confidence when wrong | **1.00** |

The agent is not making mistakes. It is **reasoning correctly over corrupt
input and reporting the result at maximal confidence.** 71% of the time it
returns precisely the answer the served data implied — the right answer to the
wrong question — and it does so with confidence 1.00, the top of the scale, on
answers that are wrong.

This is the study's central phenomenon stated as cleanly as it can be:
staleness is transmitted through the agent without attenuation and without
signal. The pipeline's defect is delivered verbatim to the user as a confident
answer. This is also exactly the cell the detectability arm manipulates, and it
gives that arm a sharp pre-registered baseline: **5% abstention, 89% silent
failure.** If `_record_age_seconds` does anything, it moves these two numbers.

## 5. Finding 3 — the baseline is not clean, and that is a result

The batch baseline — **no fault injected** — flips 7.1% of answers from its
inherent 3 s staleness alone, and silently fails on **100%** of them. A pipeline
nobody would describe as faulty already produces confident wrong answers at a
few percent of traffic, undetected. The thesis's limitation note applies with
force: a realistic 10-minute batch DAG implies ~300 s, two orders of magnitude
worse than this arm.

## 6. Finding 4 — the RQ2 damage ranking changes once arithmetic is removed

Phase 1 ranked faults by raw accuracy drop. That ranking mixes two
non-comparable quantities: how much a fault moves the answer key, and how much
it impairs the agent. Ranking on the residual instead:

| rank | fault (severe) | residual | raw drop | reading |
|---|---|---|---|---|
| 1 | schema drift | **−0.159** | −0.129 | genuinely impairs reasoning; **worse than the raw number suggests** |
| 2 | semantic stripping | **−0.093** | −0.230 | impairs reasoning, but most of its raw damage is *abstention*, which is safe |
| 3 | freshness | **+0.008** | −0.129 | does not impair reasoning at all; pure answer-key movement |
| 4 | latency | 0.000 | 0.000 | no effect by construction (analytic mode) |

Two corrections to the phase-1 reading:

- **Semantic stripping is not the most damaging fault.** It has the largest raw
  drop, but 23% of that is the agent *refusing to answer* — the desired
  behaviour under unusable data. Counting a refusal as damage equal to a
  confident wrong answer is precisely the conflation this thesis argues
  against.
- **Schema drift is the most damaging fault to reasoning**, and it pairs that
  with ~1% abstention. Largest residual impairment, almost no signal. It is the
  most dangerous fault in the study by the thesis's own detectability
  criterion, and it was predicted "visible".

This strengthens the H3 restatement already recorded in
`detectability_arm.md` §5: what matters is not whether corruption is visible,
but whether it is **legible as corruption**. A renamed field is visible and
illegible; opaque field names are visible and legible; staleness is not visible
at all.

---

## 7. Consequences

- **RQ1** — report freshness as flip rate × failure mode, never as raw accuracy.
  The monotonicity claim in the freshness sweep should be tested on the
  *flip-conditioned* silent-failure rate, not on accuracy.
- **RQ2** — rank faults by residual impairment; report the raw drop alongside
  it with the decomposition, not instead of it.
- **RQ3 / H3** — the detectability arm now has a pre-registered baseline to move
  (5% abstention, 89% silent failure on flipped queries).
- **AIRS calibration** — the target variable should be flip-conditioned silent
  failure. Raw accuracy is contaminated by the answer-flip rate, which AIRS's
  freshness dimension is measuring the *cause* of; calibrating against it would
  be partly circular.
- **Chapter 3** — gains §"flip partition" as a stated analysis procedure.
- **Chapter 4** — §2's table is a headline result, not an appendix.
