# The AIRS gate — does enforcing a data contract actually help?

**Run:** 2026-08-01 · 180 gpt-4o-mini pipelines, 13 554 decisions · **$0**

```bash
python -m airsbench.gate.replay --task retrieval --sweep dimension
python -m airsbench.gate.replay --task retrieval --attribution
```

The campaign ended on a recommendation: *disclosure does not work, so enforce
the data contract outside the model.* That is a claim about consequences, and it
was never tested. `src/airsbench/gate/` makes it executable — `Policy` declares
what an agent may reason over, `Controller` refuses violating batches before the
agent is asked, and `replay` re-runs every logged decision under a policy to
count what would have changed.

## Verdict

**Enforcement works, and it is far more expensive than the recommendation
implied.** Three results, in descending order of how much they should change
what a practitioner does:

1. **Most silent failure is not infrastructure's fault.** 14.2% of retrieval
   answers are confidently wrong on a *fault-free* pipeline, against a 19.6%
   overall rate. Only **5.4 of those 19.6 points — 28% — are fault-attributable**
   and therefore reachable by any data gate at all.
2. **Every worthwhile policy destroys more correct answers than it saves.** Once
   a gate is credited only with the silent failure the fault actually caused,
   the price is **7–21 correct answers forfeited per silent failure genuinely
   prevented.** A gate is a trade, not a win.
3. **Which gate to use is task-dependent, and the RQ4 weights predict it.** On
   retrieval, gating on consistency is 2.5× cheaper than gating on staleness. On
   classification the ordering reverses. **The staleness budget — the rule the
   thesis originally recommended — is the wrong gate for retrieval.**

---

## 1. The un-gateable floor

A gate refuses degraded batches. It cannot make the agent right about a query it
was always going to get wrong, so the fault-free silent-failure rate is a level
no policy can remove:

| task | overall silent rate | fault-free baseline | fault-attributable |
|---|---|---|---|
| retrieval | 19.6% | 14.2% *(range 6.4–23.8% over 8 clean pipelines)* | **5.4 pp (28%)** |
| classification | 18.2% | 13.6% *(range 6.2–20.0% over 8 clean pipelines)* | **4.6 pp (25%)** |

Roughly **three-quarters of silent failure in this campaign is agent-intrinsic**
— the model being confidently wrong about a hard query on data that was never
degraded. No amount of data-quality enforcement touches it.

> A tight policy can print a residual *below* the baseline (AIRS ≥ 99 reaches
> 10.5% on retrieval). That is selection, not success: it admits 4 of the 8
> clean pipelines, and clean pipelines individually range from 6.4% to 23.8%.
> The range is reported beside the mean for exactly this reason.

## 2. The sweeps

Retrieval, calibrated weights (freshness 13%, latency 0%, consistency 70%,
semantic 17%). `cost` = correct answers forfeited per silent failure prevented.

| policy | coverage | prevented | forfeited | residual | cost |
|---|---|---|---|---|---|
| no gate | 100% | 0% | 0% | 19.6% | — |
| **consistency ≥ 90** | 91% | 15% | 8% | 18.4% | **2.26** |
| AIRS ≥ 85 | 86% | 21% | 12% | 17.9% | 2.35 |
| semantic ≥ 50 | 91% | 13% | 9% | 18.8% | 2.73 |
| semantic ≥ 50 + consistency ≥ 90 | 81% | 27% | 17% | 17.5% | 2.48 |
| freshness ≥ 50 | 43% | 63% | 56% | 16.9% | 3.59 |
| age ≤ 3.0 s | 75% | 25% | 24% | 19.3% | 3.84 |
| age ≤ 1.0 s | 35% | 69% | 63% | 17.1% | 3.73 |
| AIRS ≥ 99 | 17% | 91% | 81% | 10.5% | 3.63 |

**The staleness budget is the worst-value gate on retrieval.** `age ≤ 3.0 s`
forfeits 3.84 correct answers per silent failure prevented and moves the
residual rate by 0.3 pp. This is not a surprise — it is the flip-partition
result surfacing operationally. Freshness does not impair retrieval *reasoning*;
it moves the answer key. Refusing stale batches therefore discards mostly-good
answers.

On classification the ordering inverts, as RQ5 requires: `age ≤ 2.0 s` prevents
68% of silent failures and takes the residual from 18.2% to 13.7%, while
`consistency ≥ 90` is the most expensive policy in the whole study at 4.10.

## 3. Attribution — charging the gate honestly

The table above credits a policy with *every* silent failure inside a refused
batch. Most of those would have happened anyway. Crediting only the excess over
the fault-free rate gives the price a gate really pays:

**Retrieval** (fault-free silent rate 14.2%)

| refuse all | silent | excess | correct | true cost | RQ4 weight |
|---|---|---|---|---|---|
| schema_drift | 24.8% | 10.7% | 74.7% | **7.0** | 70% |
| semantic_stripping | 24.0% | 9.9% | 75.6% | 7.7 | 17% |
| freshness | 18.7% | 4.5% | 79.6% | 17.7 | 13% |
| latency | 14.1% | −0.1% | 84.8% | **never** | 0% |

**Classification** (fault-free silent rate 13.6%)

| refuse all | silent | excess | correct | true cost | RQ4 weight |
|---|---|---|---|---|---|
| freshness | 23.0% | 9.4% | 77.0% | **8.2** | 21% |
| semantic_stripping | 17.0% | 3.4% | 59.8% | 17.4 | 53% |
| schema_drift | 17.5% | 3.9% | 81.9% | 21.0 | 25% |
| latency | 13.6% | 0.0% | 86.4% | **never** | 0% |

Three things fall out of these two tables.

**The retrieval ranking matches the calibrated weights exactly.** The fault
worth gating on first (schema drift, 7.0) is the one carrying ~70% of the
weight (61–72% across parameterisations, `sensitivity_findings.md`);
the fault worth gating on last (latency) carries 0%. The RQ4 calibration was fit
to predict failure; it turns out to also rank *interventions*, which is a
stronger claim than it was asked to support.

**Latency is "never" on both tasks.** Refusing a batch for slow delivery
prevents no excess silent failure whatsoever, so it is pure loss at any
threshold. Latency has zero weight from the GLM, no effect in the flip
partition, no decision-level odds ratio, no accuracy effect in the main
factorial, and no gateable harm here — and `sensitivity_findings.md` §3 shows
the zero weight survives every reparameterisation of the scoring curve,
including one under which latency stops being a two-level factor.

These are **not five independent routes to one conclusion.** Latency runs in
analytic mode and cannot change what the agent reads, so every route shares a
single cause. The defensible statement is that the null is robust to
parameterisation, not that it has been independently replicated.

**Classification's divergence is H3, not a contradiction.** Semantic stripping
carries 53% of classification weight but ranks second-worst as a gate. The
reason is visible in the `correct` column: it drops to **59.8%**, ~20 pp below
every other fault, while silent failure rises only 3.4 pp. Semantic stripping on
classification converts into *abstention*, not confident error — exactly what
`airs_calibration_findings.md` §3 established when it recommended calibrating
against total error. The weights predict total harm; the gate ranking predicts
*silent* harm. They differ precisely where the agent refuses instead of lying.

## 4. What this means for the recommendation

The thesis's practitioner conclusion needs restating. Not:

> ~~Ship the record's age and enforce a staleness budget outside the model.~~

but:

> **Enforce a data contract outside the model, on the dimension your task is
> actually sensitive to — and price the trade before you deploy it.** A gate
> buys a reduction in confident wrongness at a measured cost of roughly 7–21
> correct answers per silent failure genuinely prevented. Whether that is worth
> paying is a domain question: in a clinical or financial setting the asymmetry
> between a confident error and a decline is enormous and the trade is obvious;
> for a shopping assistant it is very likely not. What changed here is that the
> exchange rate is now a measured number rather than a guess.

The staleness budget survives, but only for classification-like tasks where
freshness genuinely impairs reasoning. For retrieval it is close to a no-op with
a real price attached — the worst kind of control, because it looks like
diligence.

## 5. Design notes

- **`unmeasured` is a violation by default.** A policy naming a dimension the
  probe could not measure refuses the batch. Admitting on an absent measurement
  is the failure mode that makes a gate worse than none: a clean bill of health
  issued precisely because nobody looked. → `tests/test_gate.py`
- **The controller and the replay are separate implementations** — one measures
  raw records, one reads scored runs — so their agreement is pinned by a
  parametrised test. Everything in this document comes from the replay path.
- **Shadow mode** (`Policy.shadow()`) admits but records, so a candidate policy
  can be priced against live traffic before it gates anything.
- **No model call, no API key, $0.** The gate is arithmetic over telemetry and
  cannot itself hallucinate.

## 6. Limitations

- **The corpus is a factorial, not production traffic.** 82 of 90 pipelines per
  task carry an injected fault. Coverage and forfeited-share therefore reflect
  the experimental design, not a realistic fault prior. The *attribution* table
  in §3 is the transportable result, because it is a within-fault ratio.
- **Batch-level granularity.** A run is admitted or refused whole. A real gate
  would evaluate per request and could be more surgical; these numbers are a
  lower bound on achievable precision.
- **One model.** The replay is gpt-4o-mini only. The cross-model arm was not
  replayed because the open-weight models floor on classification.
- **Thresholds are not tuned.** They span the measured range; no threshold was
  selected against a held-out split, so the best-policy figures are optimistic
  in the usual selection-on-test way.
- **Silent failure is the only harm counted.** An abstention is scored as a
  forfeited answer, which is right for availability and wrong for any setting
  where a decline is itself costly.
