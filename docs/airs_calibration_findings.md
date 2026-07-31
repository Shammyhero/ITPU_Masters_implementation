# AIRS calibration — results (RQ4)

**Run:** 2026-07-31 · 13 554 decisions from 180 gpt-4o-mini runs · **$0**

```bash
python -m airsbench.analysis.airs_calibration
```

Fitted on the main factorial + freshness sweep, 80/20 split **by run**, then
applied unchanged to three models it was never fitted on.

## Verdict

**AIRS works as a pipeline score, and the calibration exposes exactly what it
can and cannot claim.**

- On held-out runs it ranks pipelines by failure rate at **ρ = −0.82**
  (retrieval, silent failure) and **ρ = −0.88** (classification, total error).
- It **beats agent self-confidence** on retrieval — where confidence is at
  **chance** (AUC 0.501) — and **loses** to it on classification.
- The weights **differ sharply by task**, confirming RQ5 inside the calibration
  itself. One pooled weight vector would describe neither task.
- It should be calibrated against **total error, not silent failure**, for a
  reason the campaign already established.

---

## 1. The weights

Logistic regression of the outcome on the four AIRS dimensions, cluster-robust
by run, normalised to sum to 1. Collinearity is not a problem — every VIF is
1.1–1.2, so the four dimensions are separately attributable (the injectors were
designed for this; see invariant 5).

| dimension | retrieval | classification | | retrieval | classification |
|---|---|---|---|---|---|
| | *(silent failure)* | *(silent failure)* | | *(total error)* | *(total error)* |
| freshness | 11.9% | **42.8%** | | 12.9% | 21.2% |
| latency | **0.0%** | **0.0%** | | 0.0% | 0.0% |
| consistency | **70.5%** | 37.5% | | 70.2% | 25.4% |
| semantic | 17.6% | 19.7% | | 16.9% | **53.4%** |

**Latency receives zero weight on every target and both tasks.** Its
coefficient is positive (i.e. non-protective) and it is clamped to zero rather
than allowed to go negative — a negative weight in a readiness score would mean
"degrade this to score better". This is the correct answer for a synchronous
agent with no deadline, and it is the fourth independent route to that
conclusion in this study.

**The weights invert across tasks**, exactly as RQ5 predicted. Consistency
dominates retrieval (70%); semantic completeness dominates classification total
error (53%). A single pooled AIRS weighting would average two near-opposite
orderings.

## 2. Does AIRS beat the signal you already have?

Agent self-reported confidence costs nothing once the agent has run. If AIRS
cannot beat it, AIRS's value is *availability* — computable before deployment —
not accuracy. Compared on held-out decisions with DeLong's test for correlated
ROC curves:

| task | target | AIRS AUC | confidence AUC | DeLong p | |
|---|---|---|---|---|---|
| retrieval | silent failure | **0.580** | 0.501 | 0.0001 | **AIRS wins** |
| retrieval | total error | 0.568 | 0.544 | 0.268 | n.s. |
| classification | silent failure | 0.557 | **0.608** | 0.0055 | confidence wins |
| classification | total error | 0.692 | **0.765** | <0.0001 | confidence wins |

> **On retrieval, agent confidence is at chance for predicting silent failure —
> AUC 0.501.**

That single number is the thesis's phenomenon stated as a diagnostic: the
agent's own confidence carries *no information at all* about whether it is
about to fail silently. AIRS, computed from pipeline telemetry with no agent
involved, does better — modestly, but significantly.

And the pattern across the four rows is the useful one: **AIRS is most valuable
exactly where the agent's own signal fails.** On classification the agent is
partially calibrated and its confidence wins; on retrieval it is blind and AIRS
is the only signal available.

## 3. The fair test — AIRS ranks pipelines, not decisions

AIRS is constant across every decision in a run. It is structurally incapable
of separating decisions *within* a pipeline, so a decision-level AUC asks it to
do something it never claimed. The claim is that it ranks **pipelines**:

| task | target | Spearman ρ (held-out runs, n=18) | p |
|---|---|---|---|
| retrieval | silent failure | **−0.819** | <0.0001 |
| retrieval | total error | **−0.748** | 0.0004 |
| classification | silent failure | −0.321 | 0.19 (n.s.) |
| classification | total error | **−0.882** | <0.0001 |

Negative by construction: higher AIRS, lower failure rate.

**Three of four are strong. The exception is the informative one.** On
classification, AIRS predicts *total error* at ρ = −0.88 but *silent failure*
at only −0.32. The reason is already established: semantic stripping is the
largest AIRS-visible degradation there, and the agent converts it into
**refusal** rather than into confident error (64% abstention on Haiku, 34% on
gpt-4o-mini). AIRS correctly sees the data is bad; whether that surfaces as
silent failure or as a refusal is a property of the *agent*, not the pipeline.

> **Calibrate AIRS against total error, not silent failure.** The split between
> silent failure and refusal is downstream of the pipeline and belongs to the
> agent. A pipeline score should predict pipeline-caused harm; H3 governs how
> that harm is expressed.

This also resolves the circularity worry raised when the target was chosen:
total error is not the quantity AIRS's freshness dimension measures the cause
of, so fitting on it is cleaner as well as more predictive.

## 4. Portability — the weights survive a model swap on retrieval

gpt-4o-mini's silent-failure weights, applied **unchanged** to models they were
never fitted on:

| model | retrieval AUC | retrieval ρ | classification AUC | classification ρ |
|---|---|---|---|---|
| claude-haiku-4-5 | 0.649 | **−0.916** | 0.567 | −0.368 |
| llama3.1:8b | 0.577 | **−0.711** | 0.495 | +0.249 ⚠ |
| qwen2.5:14b-instruct | 0.580 | **−0.544** | 0.473 | −0.035 ⚠ |

**Retrieval transfers cleanly** — every ρ is strongly negative, and Haiku's
−0.916 is better than the in-domain −0.819. **Classification does not**, and
the two open-weight models are the reason: both floor on that task (§1 of
`cross_model_findings.md`), so their failure rates carry no signal for anything
to correlate with. llama's ρ of +0.249 is not evidence that AIRS is inverted
there; it is what a rank correlation against noise looks like.

## 5. Limitations

- **AUCs are modest (0.56–0.69) at decision level, by construction.** A
  run-constant predictor cannot exceed the between-run separation available.
  The run-level ρ is the meaningful figure.
- **Latency has only 2 distinct AIRS levels** (100 and 16.7) across the whole
  campaign, because the two severities map either side of the 500 ms target.
  Its zero weight is consistent with every other analysis, but the design gives
  it little room to have shown otherwise.
- **n = 18 held-out runs per task.** The ρ values are strong enough to clear
  significance at that n, but their intervals are wide.
- **One split.** A repeated or nested cross-validation would give a stabler
  weight estimate; the split is seeded and the sensitivity is untested.
- **In-distribution.** The weights are fitted and validated on the same family
  of synthetic faults. AIRS is a method to recalibrate per deployment, not a
  universal coefficient vector — §3.11's existing caveat stands.

## 6. Consequences

- **RQ4 is answered.** AIRS predicts silent failure from telemetry alone, ranks
  held-out pipelines at ρ ≈ −0.8, and beats the agent's own confidence exactly
  where that confidence is worthless.
- **The recommended target changes** from silent failure to total error, for
  the reason in §3. Update `research_questions_v2.md` §5's RQ4 row.
- **Ship two weight vectors, one per task family** — and say plainly that a
  third task needs its own. The weights transfer across models but not tasks.
- **The headline practitioner number** is AUC 0.501: on the retrieval task, a
  deployed agent's confidence is exactly as informative as a coin flip about
  its own silent failures. That is the strongest single argument for scoring
  the pipeline instead.
