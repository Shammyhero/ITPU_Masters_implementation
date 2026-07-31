# Cross-model generalisation — results (RQ5)

**Run:** 2026-07-31 · 36 runs on two locally-served open-weight models ·
3 600 agent calls · **$0.00** · zero failures

```bash
python -m airsbench.analysis.cross_model
```

RQ5 asks whether the **ranking** of infrastructure properties by damage
transfers across model classes. Only the ranking is claimed to generalise, never
the absolute thresholds.

Models: `gpt-4o-mini` (hosted, the primary instrument), `llama3.1:8b` and
`qwen2.5:14b-instruct` (open weights, served locally via Ollama). Comparable
slice only — streaming, severe, each model against its **own** baseline.

## Verdict

**The ranking transfers. The coarse partition transfers perfectly.**

Mean Kendall's τ across the three model pairs: **+0.778**. And the more useful
claim — *which* properties an operator must guard — is **identical in all three
models**.

---

## 1. Baseline health, and an arm that had to be refused

| model | task | baseline acc | parse failures | |
|---|---|---|---|---|
| gpt-4o-mini | retrieval | 0.885 | 0.0% | |
| gpt-4o-mini | classification | 0.878 | 0.0% | |
| llama3.1:8b | retrieval | 0.763 | 0.0% | |
| **llama3.1:8b** | **classification** | **0.460** | 0.0% | ← **floored**, not ranked |
| qwen2.5:14b-instruct | retrieval | 0.866 | 0.0% | |
| **qwen2.5:14b-instruct** | **classification** | **0.510** | 0.0% | ← **floored**, not ranked |

Both open-weight models sit at or below chance (0.50) on the aviation task, so
neither can be ranked there: a fault cannot degrade what is already at the
floor, and a rank correlation computed from noise would look like an answer.
The analysis excludes them automatically rather than reporting a number.

**Why they floor — diagnosed, not assumed.** Both emit a *constant* prediction.
Holding everything fixed and varying only `DepDelay`:

| DepDelay | llama3.1:8b | qwen2.5:14b | gpt-4o-mini |
|---|---|---|---|
| 0 min | not delayed (1.0) | not delayed (0.9) | not delayed (0.8) |
| 30 min | not delayed (1.0) | not delayed (0.9) | **delayed** (0.9) |
| 120 min | not delayed (1.0) | not delayed (0.9) | **delayed** (1.0) |
| 300 min | not delayed (1.0) | not delayed (0.9) | **delayed** (0.9) |

A flight five hours late is still "not delayed" at maximal confidence. The
primary model tracks the feature correctly on the **identical prompt and
record**, so this is a model-capability limit, not a defect in the instrument.
The prompt was not adjusted: it is a control variable, and tuning it for one
model would destroy the comparison.

This is worth reporting in its own right. Both models produce **well-formed,
maximally confident, entirely uninformative output** — zero parse failures, zero
abstentions, 100% one class. It is the most extreme silent failure observed
anywhere in this study, and it originates in the *model* rather than in the
pipeline. The thesis should name that distinction explicitly: infrastructure is
one source of silent failure, and consumer capability is another.

## 2. The ranking, on retrieval

Silent-failure odds ratio against each model's own baseline, answerable
decisions only:

| model | freshness | latency | schema drift | semantic stripping |
|---|---|---|---|---|
| gpt-4o-mini | 0.89 | 0.97 | **3.75** | **2.91** |
| llama3.1:8b | 1.11 | 1.26 | **2.14** | **2.93** |
| qwen2.5:14b-instruct | 1.33 | 1.36 | **2.54** | **3.70** |

| model | rank order (1 = worst) |
|---|---|
| gpt-4o-mini | schema drift > semantic stripping > latency > freshness |
| llama3.1:8b | semantic stripping > schema drift > latency > freshness |
| qwen2.5:14b-instruct | semantic stripping > schema drift > latency > freshness |

**Two results, of different strengths.**

*The coarse partition is identical.* Every model marks exactly
`{schema drift, semantic stripping}` as damaging and exactly
`{freshness, latency}` as not. The observed odds ratios cluster far apart —
0.89–1.36 versus 2.14–3.75 — so the partition does not depend on where in that
gap the line is drawn.

*The fine ordering is not.* The two open-weight models agree with each other
perfectly (τ = +1.000) but swap the top two relative to gpt-4o-mini
(τ = +0.667 for both). Schema drift is worst for the hosted model; semantic
stripping is worst for both local ones.

## 3. Why the p-values are not the evidence

| pair | τ | p |
|---|---|---|
| gpt-4o-mini vs llama3.1:8b | +0.667 | 0.333 |
| gpt-4o-mini vs qwen2.5:14b | +0.667 | 0.333 |
| llama3.1:8b vs qwen2.5:14b | +1.000 | 0.083 |

**With four faults, the smallest attainable two-sided p is 0.083.** Perfect
agreement — τ = +1.000, an identical ordering — still cannot reach p < 0.05. No
pairwise comparison in this arm could ever have been significant, however
cleanly the ranking transferred.

Reporting these p-values without saying so would invite exactly the wrong
reading: *"not significant, therefore it does not generalise."* The τ point
estimates and the partition stability are the evidence. The p-values are an
artifact of ranking only four items, and the analysis prints the floor
alongside them. (This is the same class of error caught in the freshness sweep
and in the detectability arm's power note.)

## 4. Freshness replicates as a null across all three models

Freshness odds ratios on answerable retrieval decisions: **0.89, 1.11, 1.33** —
all within noise of 1.0, in three models spanning a hosted API and two
open-weight architectures at 8B and 14B.

The study's central claim therefore does not rest on one model's behaviour.
Staleness moves the answer key; it does not impair the agent's reasoning — and
that holds wherever it has been tested.

## 5. Consequences

- **RQ5 is answered, with the right scope.** *Which* infrastructure properties
  cause silent failure is a property of the pipeline, not of the consumer. The
  precise ordering of the two damaging faults is model-specific.
- **AIRS weights are partially portable.** The dimensions that matter transfer;
  their relative weights should be recalibrated per deployment. That is a
  usable claim and an honest one — report both halves.
- **Classification generalisation is untested**, and cannot be tested on models
  of this class. A larger open-weight model, or a second hosted model, is
  required. The Haiku arm (~$1.68) would supply exactly that and is the
  strongest remaining use of the budget.
- **Silent failure has two sources.** Infrastructure faults, which this thesis
  measures, and consumer capability, which §1 documents incidentally. AIRS
  scores the first and is silent about the second — a limitation worth stating
  plainly, since a perfect AIRS score cannot rescue a model that emits
  constants.
