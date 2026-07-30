# Decision-level statistical analysis — RQ2 and RQ3

**Run:** 2026-07-28 · 11 412 decisions from 144 main-factorial runs · **$0**

```bash
python -m airsbench.analysis.decision_models
```

Logistic GLM at the level of the individual decision, with **cluster-robust
standard errors grouped by `run_id`**. Reference condition is the no-fault
baseline.

## Methodological substitution, declared

`research_questions_v2.md` §5 specifies a run-level random intercept,
`outcome ~ fault * severity + task + (1 | run_id)`. statsmodels' only mixed
logit is `BinomialBayesMixedGLM`, a variational-Bayes approximation whose
posterior SDs are not the frequentist standard errors the plan reports. The
same fixed-effects model is therefore fitted with cluster-robust SEs.

Both address the identical problem — decisions within a run are correlated, so
naive SEs are too small. Cluster-robust inference does it without approximating
the likelihood; it does not estimate the variance component, which no RQ asks
for. Verified by test: clustering **widens** every interval and leaves the
coefficients untouched.

---

## 1. RQ3 — silent failure, split by task

Freshness reaches the two tasks by different routes, and a pooled coefficient
averages a null and a real effect into a misleading middle. The split is the
finding.

**Retrieval, answerable decisions only** (n = 5 316 — mechanically unanswerable
queries removed):

| condition | OR | 95% CI | p |
|---|---|---|---|
| freshness mild | 1.03 | [0.73, 1.46] | 0.86 |
| **freshness severe** | **1.00** | [0.73, 1.36] | **0.998** |
| latency mild / severe | 1.00 | [0.71, 1.41] | 1.00 |
| schema drift mild | 1.60 | [1.23, 2.09] | <0.001 \*\*\* |
| **schema drift severe** | **3.44** | [2.69, 4.40] | <0.0001 \*\*\* |
| semantic stripping mild | 1.92 | [1.47, 2.50] | <0.0001 \*\*\* |
| semantic stripping severe | 2.74 | [2.12, 3.54] | <0.0001 \*\*\* |

> **Freshness severe: OR = 1.00, p = 0.998.** Once staleness's mechanical
> component is removed, its effect on retrieval silent failure is not merely
> small — it is *exactly* the null, under decision-level inference with
> cluster-robust errors on 5 316 decisions.

This reproduces the flip partition's −0.003 residual by an entirely independent
route, and it is the strongest single piece of evidence for the study's central
claim: **freshness does not impair the agent's reasoning. It moves the answer
key.**

**Classification** (n = 5 760):

| condition | OR | 95% CI | p |
|---|---|---|---|
| **freshness severe** | **2.63** | [1.94, 3.57] | <0.0001 \*\*\* |
| schema drift severe | 1.53 | [1.12, 2.09] | 0.007 \*\* |
| semantic stripping severe | 1.28 | [0.87, 1.88] | 0.22 |
| latency mild / severe | 1.00 | [0.69, 1.45] | 1.00 |

Freshness *does* impair classification — but by a different mechanism.
Staleness attenuates the `DepDelay` feature rather than moving the label, so
the damage is genuine rather than arithmetic. **The same fault name denotes two
different phenomena across the two tasks**, and reporting a single pooled
freshness coefficient would misdescribe both.

Semantic stripping is *not* significant for classification silent failure
(OR 1.28, p = 0.22) — because it converts into abstention instead (§2).

## 2. RQ3 — abstention: one fault, and only one

n = 11 412, all decisions:

| condition | OR | 95% CI | p |
|---|---|---|---|
| **semantic stripping severe** | **51.93** | [17.15, 157.30] | <0.0001 \*\*\* |
| **semantic stripping mild** | **13.47** | [4.51, 40.24] | <0.0001 \*\*\* |
| freshness severe | 1.84 | [0.45, 7.55] | 0.39 |
| schema drift severe | 1.84 | [0.54, 6.30] | 0.33 |
| latency severe | 1.00 | [0.20, 4.89] | 1.00 |
| task = retrieval | 0.13 | [0.07, 0.25] | <0.0001 \*\*\* |

**H3 in a single table.** Semantic stripping raises the odds of abstention
**52-fold**. Every other fault's interval contains 1.0. The agent can decline
only when the corruption is legible *inside the record it was handed* — opaque
field names are, and a plausible rename, a well-formed stale value, and an
on-time slow delivery are not.

Note `task = retrieval`, OR 0.13: the retrieval agent abstains ~8× less readily
than the classification agent under otherwise identical treatment. Task framing
affects willingness to decline independently of data quality — an interaction
worth a sentence in the discussion.

## 3. RQ2 — fault ranking

Run-level accuracy, 144 runs (16 baseline, 128 factorial). Shapiro–Wilk
W = 0.895, p < 0.0001 → non-normal, so Kruskal–Wallis is reported alongside.

| effect | F | p | η² |
|---|---|---|---|
| **fault** | 39.22 | 1.2e−17 | **0.373** |
| **severity** | 43.36 | 1.3e−09 | **0.137** |
| fault × severity | 6.38 | 4.8e−04 | 0.061 |
| pipeline | 14.03 | 2.8e−04 | 0.044 |
| task | 3.62 | 0.060 | 0.011 |

Kruskal–Wallis across faults: H = 51.29, p = 4.2e−11.

Cohen's d vs baseline at severe: freshness −1.92, schema drift −2.01, semantic
stripping −2.42, latency 0.00 — all large except latency, which is exactly zero.

**Caveat carried forward:** d and η² here are computed on *raw* accuracy, so the
freshness figure mixes answer-key movement (retrieval) with feature attenuation
(classification). It is not a clean impairment estimate. The decision-level
models in §1 are, and they should be the ones quoted for RQ2's ranking.

## 4. Latency as an estimated null

Latency's odds ratio is 1.00 with p = 1.0000 in every model, on both tasks, at
both severities. This is not a term that was omitted — it is estimated, and it
lands on the null.

That is the correct answer for a synchronous agent with no deadline: analytic
latency cannot change what the agent reads, so it cannot change what the agent
concludes. It also functions as a **negative control for the whole harness**: a
condition that ought to produce exactly no effect, and does. If the pipeline
were leaking any difference between conditions, latency is where it would show.
A test pins it.

## 5. Consequences

- **RQ2's ranking should be quoted from the decision-level models**, not from
  Cohen's d on raw accuracy. On retrieval impairment: schema drift (3.44) >
  semantic stripping (2.74) > freshness (1.00) = latency (1.00).
- **RQ3 is answered on both halves.** Silent failure is driven by schema drift
  and semantic stripping in retrieval and by freshness in classification;
  abstention is driven by semantic stripping and nothing else.
- **"Freshness" is not one phenomenon.** Chapter 4 should name the two
  mechanisms separately rather than reporting a pooled coefficient.
- `research_questions_v2.md` §5 records the cluster-robust substitution.
