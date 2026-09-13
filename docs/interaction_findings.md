# Fault interaction — results (RQ6)

**Run:** completed 2026-09-10 · 54 runs, gpt-4o-mini, streaming, severe · **~$0.55**
Design: [`interaction_arm.md`](interaction_arm.md)

```bash
python -m airsbench.analysis.interaction
python -m airsbench.analysis.interaction --outcome error
python -m airsbench.analysis.interaction --figure docs/figures/fig4_6_interaction.png
```

## The question

Every AIRS composite is a weighted **sum**, fitted on runs in which exactly one
dimension was ever degraded. `airs probe` and `airs gate` then apply it to
pipelines where several dimensions degrade at once — the normal production case.
If two faults **compound**, the composite under-predicts risk on precisely the
worst pipelines, and the gate's independent per-dimension floors are the wrong
shape. That failure would be in the unsafe direction, so it had to be tested.

## Verdict

**Faults never compound. They saturate.**

- **5 of 8 pairs are sub-additive** on the logit scale; the other 3 are additive;
  **none is super-additive.** The same five pairs saturate on total error as on
  silent failure.
- **AIRS therefore over-predicts multi-fault risk.** That is the conservative
  direction for a readiness score: a pipeline scored as dangerous is at least
  that dangerous, never more.
- **The gate's independent floors remain correctly shaped.** A joint rule would
  only be needed if faults compounded.
- **The latency control reads ψ = +0.00 [−0.13, +0.13]** on classification silent
  failure, as a correctly specified test must.

## Why the result is interpretable

An interaction test means nothing if the treatments are not separable. Before any
money was spent, the arm verified through the real runner that a compound
condition degrades each AIRS dimension by exactly its solo marginal and leaves
the others at baseline (`interaction_arm.md`, table 1). Invariant 5 holds under
composition, so the independent variable is additive by construction — **any
departure from additivity in the outcome is behavioural, not an artifact of the
injectors interfering.**

The estimator is separately validated: `test_estimator_recovers_a_planted_interaction`
plants ψ ∈ {0, +0.8, −0.8} in synthetic cells and requires the estimator to
recover each, to exclude zero when ψ ≠ 0, and to include it when ψ = 0.

## 1. Silent failure

`add.` = p(A) + p(B) − p(0), the additive prediction. `obs.` = both faults applied.
δ is the departure on the risk scale; ψ is the same contrast in log odds.

**Retrieval**

| pair | p(A) | p(B) | add. | obs. | δ [95% CI] | ψ [95% CI] | |
|---|---|---|---|---|---|---|---|
| freshness + drift | 18.4% | 25.2% | 32.5% | 34.2% | +1.7 [−2.6, +6.4] | −0.16 [−0.54, +0.19] | additive |
| freshness + semantic | 18.4% | 28.6% | 35.9% | 31.6% | −4.3 [−9.4, +0.9] | **−0.45 [−0.88, −0.07]** | **saturates** |
| semantic + drift | 28.6% | 25.2% | 42.7% | 38.0% | −4.7 [−11.1, +1.7] | **−0.57 [−1.01, −0.15]** | **saturates** |
| latency + drift *(control)* | 10.3% | 25.2% | 24.4% | 25.6% | +1.3 [−0.9, +3.8] | +0.11 [−0.07, +0.33] | additive |

**Classification**

| pair | p(A) | p(B) | add. | obs. | δ [95% CI] | ψ [95% CI] | |
|---|---|---|---|---|---|---|---|
| freshness + drift | 21.2% | 15.4% | 27.1% | 24.2% | −2.9 [−6.2, +0.0] | **−0.38 [−0.67, −0.13]** | **saturates** |
| freshness + semantic | 21.2% | 15.8% | 27.5% | 21.2% | **−6.3 [−12.1, −0.8]** | **−0.57 [−1.03, −0.17]** | **saturates** |
| semantic + drift | 15.8% | 15.4% | 21.7% | 15.4% | **−6.2 [−10.8, −1.7]** | **−0.57 [−1.01, −0.19]** | **saturates** |
| latency + drift *(control)* | 9.6% | 15.4% | 15.4% | 15.4% | +0.0 [−1.7, +1.7] | +0.00 [−0.13, +0.13] | additive |

3 replications · 234 paired queries per contrast · 4 000 bootstrap resamples over
paired queries.

## 2. Total error

The same five pairs saturate; none compounds.

| task | pair | add. | obs. | δ [95% CI] | ψ [95% CI] |
|---|---|---|---|---|---|
| retrieval | freshness + drift | 35.5% | 35.0% | −0.4 [−4.7, +4.3] | −0.25 [−0.58, +0.07] |
| retrieval | freshness + semantic | 37.6% | 32.5% | −5.1 [−10.3, +0.0] | **−0.47 [−0.83, −0.12]** |
| retrieval | semantic + drift | 43.6% | 38.5% | −5.1 [−11.1, +0.9] | **−0.53 [−0.93, −0.17]** |
| retrieval | latency + drift *(control)* | 26.5% | 26.9% | +0.4 [−0.0, +1.3] | +0.04 [+0.00, +0.13] |
| classification | freshness + drift | 27.1% | 24.6% | −2.5 [−5.4, +0.4] | **−0.35 [−0.64, −0.12]** |
| classification | freshness + semantic | 62.9% | 52.9% | **−10.0 [−15.4, −5.0]** | **−0.87 [−1.28, −0.52]** |
| classification | semantic + drift | 57.1% | 54.6% | −2.5 [−7.1, +2.1] | **−0.41 [−0.77, −0.10]** |
| classification | latency + drift *(control)* | 15.4% | 15.4% | +0.0 [−1.7, +1.7] | +0.00 [−0.13, +0.13] |

The largest effect in the study is here: on classification, freshness plus
semantic stripping does **10 points less** total harm than the sum predicts.

## 3. What saturation looks like: the combination tracks the worse fault

On classification the pattern is stark enough to read straight off the table.

- **Freshness + semantic stripping: observed 21.2%. Freshness alone: 21.2%.**
  Adding semantic stripping on top of a stale pipeline added **no** silent
  failure at all.
- **Semantic stripping + drift: observed 15.4%. Drift alone: 15.4%.** Again,
  semantic stripping contributed nothing further.

The combined rate sits at the *worse* single fault rather than at the sum. On
retrieval it falls between the two. This is consistent with H3: semantic
stripping on classification converts corruption into **abstention**
(`airs_calibration_findings.md` §3) — it removes answers rather than falsifying
them, so it cannot add confident errors to a pipeline that is already producing
them. Its total-error cost is large (p = 51.2% alone); its silent-failure cost
does not stack.

## 4. The mechanism: faults fail the same questions

Formally tested in `fragility_findings.md`. Silent failure is concentrated on a
pool of fragile questions — 11.8× (retrieval) and 16.4× (classification) the
concentration expected under a within-run permutation null, p < 0.0005 — and
different faults fail the same ones: Jaccard overlap between fault pairs is
1.6–2.5× the null on retrieval and 3.6–4.0× on classification. Re-asking identical
inputs reproduces the same silent failures almost exactly (J = 0.91 retrieval,
1.00 classification), so fragility is a stable property of the question.

Two faults therefore compete for the same fragile questions rather than creating
new failures, and sub-additivity follows.

## 5. Consequences

**For AIRS.** The linear composite is conservative on multi-fault pipelines. The
extrapolation from single-fault calibration to multi-fault deployment is now
evidenced rather than assumed, and it errs in the safe direction.

**For the gate.** Independent per-dimension floors are the right shape. There is
no case for a joint rule.

**For the product.** Because combined harm tracks the worse fault more closely
than the sum, a practitioner is better served by seeing their **weakest
dimension** alongside the weighted composite. The composite answers "how ready
overall"; the weakest dimension answers "what will actually hurt", and on a
multi-fault pipeline the second is the more accurate forecast. This should shape
Mode A's scoring view.

## 6. Limitations

- **One severity point.** Severe × severe only. Mild pairs might add; the result
  is not a surface.
- **Two-way only.** Three- and four-fault combinations are untested.
- **One model, one pipeline archetype** (gpt-4o-mini, streaming).
- **n = 3 replications.** The paired bootstrap over 234 queries mitigates this;
  intervals are nonetheless wide and several δ intervals touch zero. The
  reportable quantity is the interval.
- **No multiple-comparison correction** across the 8 contrasts. Treat the
  classification of individual pairs as exploratory; the aggregate direction —
  five departures, all negative, none positive — is the robust finding.
- **The latency control is weaker than it looks.** Analytic-mode latency cannot
  change what the agent reads, so this control could only ever have come out one
  way; it checks the arithmetic, not the test's sensitivity. On retrieval total
  error its lower bound sits exactly at +0.00. The planted-effect test is the
  real check on sensitivity.
- **"Additive" means "no interaction large enough to detect"** at this n, not the
  absence of one.
