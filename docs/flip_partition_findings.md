# Flip-partition analysis — results

**Run:** 2026-07-28 · **full replication** — 72 retrieval runs · 5 652 decisions ·
**$0, no API calls**

*Originally computed at 2 replications after phase 1; re-run over the complete
144-run factorial. Every conclusion held and tightened. The 2-replication
figures are in git history if the progression is of interest.*

```bash
python -m airsbench.analysis.flip_partition
```

Retroactive over the completed factorial — no re-execution. Answers the question
raised in `campaign_status.md`: how much of the freshness accuracy drop is the
agent failing, and how much is arithmetic?

**Answer: all of it is arithmetic.** Which is what makes the real finding
visible.

---

## 1. Why the reconstruction is admissible

Query sampling and query timestamps derive from `RunConfig.sample_seed`
(invariant 2), so replaying that seed regenerates the identical queries at the
identical simulated times. Each replayed query is checked against the logged
`ground_truth` before it is used; a divergence raises rather than being
silently realigned.

**Replay verified for all 72 retrieval runs, decision by decision.** Pinned by
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

| condition | raw acc | unflipped acc | **residual** | n flipped | abstain \| flip | silent \| flip |
|---|---|---|---|---|---|---|
| baseline | 0.849 | 0.888 | — | 28 | 0% | 100% |
| freshness / mild | 0.812 | 0.885 | **−0.003** | 54 | 4% | 93% |
| freshness / severe | 0.774 | 0.886 | **−0.003** | 86 | 5% | 88% |
| latency / mild | 0.847 | 0.887 | −0.002 | 28 | 4% | 96% |
| latency / severe | 0.849 | 0.888 | +0.000 | 28 | 0% | 100% |
| schema drift / mild | 0.804 | 0.842 | −0.047 | 28 | 0% | 100% |
| schema drift / severe | 0.689 | 0.715 | **−0.173** | 28 | 0% | 86% |
| semantic stripping / mild | 0.782 | 0.817 | −0.072 | 28 | 0% | 96% |
| semantic stripping / severe | 0.729 | 0.760 | **−0.128** | 28 | 0% | 93% |

The 28 flipped queries in every non-freshness row are the **batch arm's inherent
3 s staleness** (7.1% within batch, 0% within streaming) — not noise. They are
present in the baseline too, which is itself informative (§5).

---

## 3. Finding 1 — freshness does not impair the agent at all

Accuracy on queries whose answer did *not* flip: baseline **0.888**, freshness
mild **0.885**, freshness severe **0.886**. Residual **−0.003 at both
severities** — indistinguishable from zero, and flat in severity where a real
effect would grow. At two replications this read −0.003 / +0.008; quadrupling
the data resolved it to the same number twice.

> **Freshness costs accuracy exactly and only where it moved the correct
> answer.** The agent's reasoning is completely unimpaired by stale data.

The headline "freshness lowers accuracy by 11.6 points" is therefore a
measurement of the answer-flip rate, performed with a language model. It must
not be reported as a result about the agent. Chapter 3 gains this caveat;
Chapter 4 reports the flip-conditioned failure mode instead.

## 4. Finding 2 — the real freshness result, and it is worse than the raw number

On the **140** queries where staleness moved the correct answer, pooled across
severities:

| | |
|---|---|
| abstained | **4%** |
| silent failure (confident and wrong) | **90%** |
| chose the best answer *present in the data it was shown* | **75%** |
| mean confidence when wrong | **1.00** |

The agent is not making mistakes. It is **reasoning correctly over corrupt
input and reporting the result at maximal confidence.** 75% of the time it
returns precisely the answer the served data implied — the right answer to the
wrong question — and it does so with confidence 1.00, the top of the scale, on
answers that are wrong.

This is the study's central phenomenon stated as cleanly as it can be:
staleness is transmitted through the agent without attenuation and without
signal. The pipeline's defect is delivered verbatim to the user as a confident
answer. This is also exactly the cell the detectability arm manipulates, and it
gave that arm a sharp pre-registered baseline: **4% abstention, 90% silent
failure.** The arm was run at $0.153 and moved neither — see
`detectability_findings.md`. Delivering the age is not the remedy; the number
without a policy is not actionable.

## 5. Finding 3 — the baseline is not clean, and that is a result

The batch baseline — **no fault injected** — flips 7.1% of answers from its
inherent 3 s staleness alone, and silently fails on **100%** of them. A pipeline
nobody would describe as faulty already produces confident wrong answers at a
few percent of traffic, undetected. The thesis's limitation note applies with
force: a realistic 10-minute batch DAG implies ~300 s, two orders of magnitude
worse than this arm.

## 6. Finding 4 — freshness's apparent damage disappears once arithmetic is removed

> **Corrected in W2.** An earlier version of this section paired the residuals
> below with a "raw drop" column copied from the phase-1 check, which pools
> *both tasks* (−0.112 drift, −0.218 stripping, −0.116 freshness). The residuals
> are retrieval only. Mixing the two populations manufactured a reordering: it
> appeared that semantic stripping had the largest raw drop and that ranking on
> the residual reversed the order. Within retrieval, both columns come from the
> same runs (§2) and give the same order. Caught by Figure 4.2's cross-check.

Ranking on the residual, beside the raw drop from the same retrieval runs (§2,
pooled over both pipelines):

| rank | fault (severe) | residual | raw drop | reading |
|---|---|---|---|---|
| 1 | schema drift | **−0.173** | −0.160 | genuinely impairs reasoning; slightly worse than the raw drop suggests |
| 2 | semantic stripping | **−0.128** | −0.120 | genuinely impairs reasoning; slightly worse than the raw drop suggests |
| 3 | freshness | **−0.003** | −0.075 | does not impair reasoning at all; its whole raw drop is answer-key movement |
| 4 | latency | 0.000 | 0.000 | no effect by construction (analytic mode) |

Within retrieval the two rankings **agree on order**. What the flip partition
changes is **magnitude**, and for one fault decisively: freshness looks like the
third-worst fault on raw accuracy (−0.075) and is in fact indistinguishable from
no fault at all (−0.003).

Two readings follow:

- **Semantic stripping's reputation as the most damaging fault is a cross-task
  effect.** Pooled over both tasks — the phase-1 view — it has the largest raw
  drop, because on classification it converts corruption into abstention, and
  refusals count as accuracy loss. Within retrieval it ranks second on both
  measures. Counting a refusal as damage equal to a confident wrong answer is
  the conflation this thesis argues against (H3; `airs_calibration_findings.md`
  §3).
- **Schema drift is the most damaging fault to reasoning** on both measures, and
  pairs that with ~1% abstention across both tasks. Largest impairment, almost
  no signal. It is the most dangerous fault in the study by the thesis's own
  detectability criterion, and it was predicted "visible".

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
- **RQ3 / H3** — this cell gave the detectability arm its pre-registered
  baseline (4% abstention, 90% silent failure on flipped queries). The arm
  moved neither, so H3's remedy is not disclosure but enforcement.
- **AIRS calibration** — the target variable should be flip-conditioned silent
  failure. Raw accuracy is contaminated by the answer-flip rate, which AIRS's
  freshness dimension is measuring the *cause* of; calibrating against it would
  be partly circular.
- **Chapter 3** — gains §"flip partition" as a stated analysis procedure.
- **Chapter 4** — §2's table is a headline result, not an appendix.
