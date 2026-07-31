# Cross-model generalisation — results (RQ5)

**Run:** 2026-07-31 · 54 runs across three non-primary models ·
5 400 agent calls · **$2.73** · zero failures

Two locally-served open-weight models (llama3.1:8b, qwen2.5:14b-instruct, $0.00)
and one hosted model (claude-haiku-4-5, $2.73).

```bash
python -m airsbench.analysis.cross_model
```

RQ5 asks whether the **ranking** of infrastructure properties by damage
transfers across model classes. Only the ranking is claimed to generalise, never
the absolute thresholds.

Models: `gpt-4o-mini` (hosted, the primary instrument), `claude-haiku-4-5`
(hosted, a second lab), `llama3.1:8b` and `qwen2.5:14b-instruct` (open weights,
served locally via Ollama). Comparable slice only — streaming, severe, each
model against its **own** baseline.

## Verdict

**The ranking transfers across models. It does NOT transfer across tasks.**

Mean Kendall's τ across the seven comparable model pairs: **+0.762**. On
retrieval the damaging partition is **identical in all four models**. But the
ranking itself inverts between tasks — freshness is a null on retrieval
(OR 0.88–1.33) and the *worst* fault on classification (OR 1.98–2.27) — so the
ranking is a property of the **(pipeline, task) pair**, not of the pipeline
alone.

The two hosted models, from different labs, produce an **identical** retrieval
ranking (τ = +1.000).

---

## 1. Baseline health, and an arm that had to be refused

| model | task | baseline acc | parse failures | |
|---|---|---|---|---|
| gpt-4o-mini | retrieval | 0.885 | 0.0% | |
| gpt-4o-mini | classification | 0.878 | 0.0% | |
| claude-haiku-4-5 | retrieval | 0.845 | 1.0% | |
| claude-haiku-4-5 | classification | 0.900 | 0.0% | |
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

| DepDelay | llama3.1:8b | qwen2.5:14b | gpt-4o-mini | claude-haiku-4-5 |
|---|---|---|---|---|
| 0 min | not delayed (1.0) | not delayed (0.9) | not delayed (0.8) | not delayed (0.70) |
| 30 min | not delayed (1.0) | not delayed (0.9) | **delayed** (0.9) | **delayed** (0.72) |
| 120 min | not delayed (1.0) | not delayed (0.9) | **delayed** (1.0) | **delayed** (0.85) |
| 300 min | not delayed (1.0) | not delayed (0.9) | **delayed** (0.9) | **delayed** (0.92) |

Both hosted models track the feature; both open-weight models do not. Haiku's
confidence also scales with the delay magnitude (0.70 → 0.92), which neither
open-weight model manages at all.

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
| **claude-haiku-4-5** | 0.88 | 0.99 | **4.75** | **3.75** |
| llama3.1:8b | 1.11 | 1.26 | **2.14** | **2.93** |
| qwen2.5:14b-instruct | 1.33 | 1.36 | **2.54** | **3.70** |

| model | rank order (1 = worst) |
|---|---|
| gpt-4o-mini | schema drift > semantic stripping > latency > freshness |
| **claude-haiku-4-5** | **schema drift > semantic stripping > latency > freshness** |
| llama3.1:8b | semantic stripping > schema drift > latency > freshness |
| qwen2.5:14b-instruct | semantic stripping > schema drift > latency > freshness |

**Two camps, not noise.** The two hosted models agree perfectly with each other
(τ = +1.000) and the two open-weight models agree perfectly with each other
(τ = +1.000); the camps differ only by swapping the top two (τ = +0.667). Every
cross-camp pair sits at +0.667, so the disagreement is a single consistent
transposition rather than scatter.

**Two results, of different strengths.**

*The coarse partition is identical.* Every model marks exactly
`{schema drift, semantic stripping}` as damaging and exactly
`{freshness, latency}` as not. The observed odds ratios cluster far apart —
0.89–1.36 versus 2.14–3.75 — so the partition does not depend on where in that
gap the line is drawn.

*The fine ordering is not.* Schema drift is worst for both hosted models;
semantic stripping is worst for both local ones. That the split falls exactly
along hosted/open-weight lines is suggestive, but with four models it is an
observation, not a finding.

## 3. Why the p-values are not the evidence

| task | pair | τ | p |
|---|---|---|---|
| retrieval | gpt-4o-mini vs claude-haiku-4-5 | **+1.000** | 0.083 |
| retrieval | llama3.1:8b vs qwen2.5:14b | **+1.000** | 0.083 |
| retrieval | gpt-4o-mini vs llama3.1:8b | +0.667 | 0.333 |
| retrieval | gpt-4o-mini vs qwen2.5:14b | +0.667 | 0.333 |
| retrieval | claude-haiku-4-5 vs llama3.1:8b | +0.667 | 0.333 |
| retrieval | claude-haiku-4-5 vs qwen2.5:14b | +0.667 | 0.333 |
| classification | gpt-4o-mini vs claude-haiku-4-5 | +0.667 | 0.333 |

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

## 4. Classification — and the ranking inverts between tasks

Both hosted models are rankable here; neither open-weight model is.

| model | freshness | latency | schema drift | semantic stripping |
|---|---|---|---|---|
| gpt-4o-mini | **1.98** | 1.00 | **1.56** | 1.43 |
| claude-haiku-4-5 | **2.27** | 1.07 | 1.35 | 0.80 ⚠ |

τ = +0.667. **Freshness is the worst fault on both models** — the exact reverse
of retrieval, where it is a null on all four.

| fault | retrieval OR | classification OR |
|---|---|---|
| freshness | 0.88 – 1.33 (null) | **1.98 – 2.27 (worst)** |
| semantic stripping | **2.91 – 3.75 (worst or 2nd)** | 0.80 – 1.43 |

**So the ranking is a property of the (pipeline, task) pair, not of the pipeline
alone.** This is the sharpest correction RQ5 makes to the framework: AIRS
weights transfer across *models* but must be recalibrated per *task*. It also
has a clean mechanism behind it — §1 of `statistical_analysis_findings.md`
showed freshness reaches the two tasks by different routes (answer-key movement
in retrieval, feature attenuation in classification), and the cross-model data
now shows that difference is a property of the task rather than of gpt-4o-mini.

### ⚠ The 0.80 is not evidence of safety

Haiku's semantic-stripping OR of **0.80** — below 1, i.e. *less* silent failure
than baseline — hides the most destructive single result in the arm:

| | accuracy | abstention | silent failure |
|---|---|---|---|
| baseline | 0.900 | 2% | 8% |
| **semantic stripping** | **0.290** | **64%** | **6%** |

Accuracy collapses by 61 points, and silent failure *falls* — because Haiku
converts the fault into **refusal** rather than into a confident wrong answer.
Ranking on silent failure alone would call the most damaging fault the safest.

This is the same conflation the flip partition removed, reappearing from the
opposite direction, and it is now guarded: the analysis prints accuracy and
abstention beside every odds ratio and flags any low OR paired with collapsed
accuracy as `<- masked by refusal`.

It is also **H3's strongest single data point**. Semantic stripping is the fault
whose corruption is legible *inside the delivered record*, and the agent that
can read it declines on 64% of queries rather than guessing — against 5%
abstention under freshness, whose corruption is not legible at all.

## 5. Freshness replicates as a null across all four models

Freshness odds ratios on answerable retrieval decisions: **0.88, 0.89, 1.11,
1.33** — all within noise of 1.0, across two hosted APIs from different labs and
two open-weight architectures at 8B and 14B.

The study's central claim therefore does not rest on one model's behaviour.
Staleness moves the answer key; it does not impair the agent's reasoning — and
that holds wherever it has been tested.

## 6. Consequences

- **RQ5 is answered, with the scope tightened.** *Which* infrastructure
  properties cause silent failure transfers across model classes — but only
  **within a task**. Across tasks the ranking inverts.
- **AIRS weights are portable across models, not across tasks.** The retrieval
  partition is identical in all four models; the retrieval and classification
  rankings are near-opposite. Calibrate per task family, and the calibration
  should then survive a model swap. That is a more useful claim than the one
  the arm set out to test.
- **Rank on more than silent failure.** A fault that drives refusal lowers the
  silent-failure rate while destroying accuracy (§4). Any ranking — including
  AIRS's own weighting — must read accuracy and abstention alongside it.
- **Silent failure has two sources.** Infrastructure faults, which this thesis
  measures, and consumer capability, which §1 documents incidentally. AIRS
  scores the first and is silent about the second — a limitation worth stating
  plainly, since a perfect AIRS score cannot rescue a model that emits
  constants.
- **Remaining gap:** classification generalisation rests on two hosted models.
  A capable open-weight model (≥30B, or an instruct-tuned model that tracks
  numeric features) would test whether the task-dependence is about capability
  or about the task itself.
