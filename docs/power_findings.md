# Power under clustering — results

**Run:** W2 · **corrected 13 Sep, before W3 (REVIEW F-C7)** · gpt-4o-mini · main
factorial · 2 000 simulated studies per point · **$0**

```bash
python -m airsbench.analysis.power --figure docs/figures/fig3_1_power.png
python -m airsbench.analysis.pvalue_calibration
```

## Why this exists

`research_questions_v2.md` §6 gave a closed-form minimum detectable effect of
"roughly 8–10 percentage points" and marked a simulation accounting for run-level
clustering as **required before the results chapter**. It was never run, and the
notebook it was meant to live in never existed (REVIEW F-C6). §6 also justified
its bound as conservative because "the mixed-effects model borrows strength" —
**no mixed-effects model exists**; every analysis fits a logistic GLM with
cluster-robust errors. The simulation therefore tests the model actually used.

The simulation's speed comes from closed forms: the MLE and sandwich of the
two-group logistic model, and CR2 errors with Bell–McCaffrey degrees of freedom
for the linear one. `tests/test_power.py` pins the first to statsmodels fitted on
decision-level data (1e-6) and the second to its matrix definition (1e-9).

> **Corrected 13 Sep 2026 (REVIEW F-C7).** The first version of this document
> found the study's cluster-robust test anti-conservative and left the
> correction open. Cell and pooled comparisons now use **CR2 errors with
> Bell–McCaffrey degrees of freedom**, chosen over a wild cluster bootstrap and a
> t(G−1) reference on simulated size, before being applied to any observed
> cell. The uncorrected test is still simulated on the same studies and
> reported beside it. Three cell results lose significance, cell MDEs rise by
> 2 pp, and the claim that retrieval freshness sits "well above every MDE" —
> true only of the uncorrected test — is withdrawn. The decision-level models
> were calibrated separately (§ Decision models); every significant result they
> publish survives.

## Verdict

1. **Clustering is negligible.** ICC 0.000–0.003, design effect 1.00–1.25. §6's
   concern that clustering would inflate the MDE does not materialise; its closed
   form was approximately right.
2. **The study's original test was anti-conservative with few clusters.** With
   no true effect, the cluster-robust logistic test rejects **11–12% of the
   time** for a single cell (4 v 4 runs, 8 clusters) and **7–8%** pooled
   (16 v 8). The corrected test rejects **4.8–5.8%** per cell and **4.5–5.5%**
   pooled, on the same simulated studies.
3. **Detectable effects, at nominal size:** about **10–12 pp** for a single
   cell, **6 pp** pooled. The uncorrected test's 8–10 pp was partly bought with
   its excess false positives.

| task · outcome | baseline | ICC | DE | cell MDE | cell α | cell α uncorrected | pooled MDE | pooled α | pooled α uncorrected |
|---|---|---|---|---|---|---|---|---|---|
| retrieval · total error | 11.5% | 0.000 | 1.00 | 10 pp | 0.048 | 0.111 | 6 pp | 0.051 | 0.074 |
| retrieval · silent failure | 10.5% | 0.000 | 1.00 | 10 pp | 0.058 | 0.123 | 6 pp | 0.055 | 0.077 |
| classification · total error | 12.2% | 0.001 | 1.05 | 12 pp | 0.056 | 0.123 | 6 pp | 0.045 | 0.075 |
| classification · silent failure | 12.2% | 0.003 | 1.25 | 12 pp | 0.050 | 0.119 | 6 pp | 0.052 | 0.075 |

MDEs are simulated under the corrected test on a 2 pp grid. Bell–McCaffrey df is
6.0 per cell and 14.1 pooled. With 2 000 studies each α carries a standard error
of about 0.005, so 0.058 is within noise of 0.05. Naive and clustered closed
forms agree within 1 pp.

## What it means for the results

**Large effects are unaffected.** Severe schema drift (+19.7 / +20.1 pp,
retrieval) and severe semantic stripping (+14.3 / +15.0 pp retrieval, +39.1 pp
classification total error) sit above every MDE with p ≤ 0.001.

**Severe freshness is significant, but at the edge of what one cell detects.**
On retrieval, +9.9 pp total error (p = 0.004) and +9.2 pp silent failure
(p = 0.003) sit just below the 10 pp cell MDE; on classification, +9.4 pp
(p = 0.023) is below the 12 pp MDE. The effect was detected, but a single cell
was not powered to detect an effect this size reliably. The decision-level
models, with more runs behind each estimate, are the stronger evidence for it.

**Three cell-level results are not significant:**

| cell | effect | p | p uncorrected |
|---|---|---|---|
| retrieval · freshness/mild · total error | +5.1 pp | 0.074 | 0.031 |
| retrieval · freshness/mild · silent failure | +5.4 pp | 0.059 | 0.019 |
| classification · schema drift/severe · total error | +7.5 pp | 0.094 | 0.049 |

**Six stay significant with much less margin**, and must be quoted with their
corrected p:

| cell | effect | p | p uncorrected |
|---|---|---|---|
| retrieval · schema drift/mild · total error | +6.4 pp | 0.016 | 0.003 |
| retrieval · schema drift/mild · silent failure | +6.4 pp | 0.012 | 0.002 |
| retrieval · semantic stripping/mild · total error | +8.0 pp | 0.015 | 0.001 |
| retrieval · semantic stripping/mild · silent failure | +8.3 pp | 0.019 | 0.001 |
| classification · freshness/severe · total error and silent failure | +9.4 pp | 0.023 | 0.008 |
| classification · semantic stripping/mild · total error | +13.8 pp | 0.010 | 0.001 |

**Classification silent-failure cells are all below the cell MDE** (0–9.4 pp).
Severe semantic stripping raises classification *total error* by 39 pp but
*silent failure* by only 4.4 pp, because it converts into abstention (H3). That
4.4 pp is not detectable at cell level — consistent with, not contrary to, H3.

**Latency's null is bounded, not zero.** Observed effects are within ±0.3 pp.
The design rules out latency effects larger than ~10–12 pp in a single cell and
~6 pp pooled — not all effects.

## Decision models

`decision_models.py` keeps its cluster-robust logistic fits, but each condition
coefficient rests on eight (per-task models) or sixteen (pooled models) runs
against as many baseline runs — the same few-cluster problem, never measured
until now. `pvalue_calibration.py` measures it: for every condition coefficient,
2 000 studies simulated from the fitted model with that coefficient removed, on
the real runs, run sizes and ICC. Its batched fit reproduces statsmodels on the
real data to within 1e-10.

| model | runs | empirical α at 0.05, per coefficient |
|---|---|---|
| silent failure · primary, answerable decisions | 144 | 0.059–0.077 |
| silent failure · pooled, all decisions | 144 | 0.058–0.074 |
| silent failure · retrieval, answerable | 72 | 0.077–0.102 |
| silent failure · classification | 72 | 0.073–0.098 |
| abstention | 144 | 0.042–0.080 |

**Every result `statistical_analysis_findings.md` reports as significant
survives calibration.** The narrowest margins:

| model · term | OR | p | calibrated p |
|---|---|---|---|
| retrieval, answerable · schema drift mild | 1.60 | 0.0005 | 0.008 |
| classification · schema drift severe | 1.53 | 0.0074 | 0.022 |
| classification · freshness severe | 2.63 | <0.0001 | 0.001 |

**One printed coefficient does not survive:** freshness mild in the *pooled*
silent-failure model (OR 1.25, p 0.042 → calibrated 0.063). The report already
labels that model as inflated by answer-key movement and "not a claim about the
agent", and no document quotes it. No non-significant coefficient becomes
significant. Calibrated p-values have a floor of 1/2001 ≈ 0.0005.

## Consequences

- **Chapter 3** reports the original test's empirical α, the correction and its
  size, the corrected MDEs, and the calibration of the decision models.
- **Chapter 4** quotes cell comparisons with the corrected p-values and
  decision-model coefficients with both the published and the calibrated p; the
  three cells above are reported as not significant.
- **References to verify before Chapter 3** (CLAUDE.md citation hygiene): the
  CR2 bias-reduced linearisation estimator, the Bell–McCaffrey degrees of
  freedom, and the few-cluster literature that motivates both.

## Limitations

- **The decision models are calibrated, not re-estimated.** Odds ratios stand,
  but their CR1 intervals are somewhat too narrow for the same reason the
  p-values were too small; only the p-values are corrected.
- **Two scales.** Cell comparisons test a difference in proportions (CR2 is
  defined for the linear model); the decision models test log-odds. Each is
  reported on the scale it was fitted on.
- **Beta-binomial data-generating model** with the observed ICC; if between-run
  variation has heavier tails, power is overstated and calibrated p-values are
  too small.
- **ICC intervals are approximate** — bootstrapping four runs per condition.
- **gpt-4o-mini main factorial only.** The interaction arm carries its own
  inference — a paired query bootstrap, which does not depend on cluster counts.
