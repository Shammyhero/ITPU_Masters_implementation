# Power under clustering — results

**Run:** W2 · gpt-4o-mini · main factorial · 2 000 simulated studies per point · **$0**

```bash
python -m airsbench.analysis.power --figure docs/figures/fig3_1_power.png
```

## Why this exists

`research_questions_v2.md` §6 gave a closed-form minimum detectable effect of
"roughly 8–10 percentage points" and marked a simulation accounting for run-level
clustering as **required before the results chapter**. It was never run, and the
notebook it was meant to live in never existed (REVIEW F-C6). §6 also justified
its bound as conservative because "the mixed-effects model borrows strength" —
**no mixed-effects model exists**; every analysis fits a logistic GLM with
cluster-robust errors. The simulation therefore tests the model actually used.

The simulation's speed comes from a closed-form MLE and sandwich for the
two-group logistic model; `tests/test_power.py` pins it to statsmodels fitted on
decision-level data to 1e-6.

## Verdict

1. **Clustering is negligible.** ICC 0.000–0.003, design effect 1.00–1.25. §6's
   concern that clustering would inflate the MDE does not materialise; its closed
   form was approximately right.
2. **The study's test is anti-conservative with few clusters.** With no true
   effect, the cluster-robust test rejects **11–12% of the time** for a single
   cell (4 v 4 runs, 8 clusters) and **7–8%** pooled (16 v 8). Nominal α = 0.05
   is not achieved.
3. **Detectable effects:** about **8–10 pp** for a single cell, **6 pp** pooled.

| task · outcome | baseline | ICC | DE | cell MDE (sim) | cell α | pooled MDE (sim) | pooled α |
|---|---|---|---|---|---|---|---|
| retrieval · total error | 11.5% | 0.000 | 1.00 | 8 pp | 0.111 | 6 pp | 0.074 |
| retrieval · silent failure | 10.5% | 0.000 | 1.00 | 8 pp | 0.123 | 6 pp | 0.077 |
| classification · total error | 12.2% | 0.001 | 1.05 | 10 pp | 0.123 | 6 pp | 0.075 |
| classification · silent failure | 12.2% | 0.003 | 1.25 | 10 pp | 0.119 | 6 pp | 0.075 |

MDEs are on a 2 pp grid. Naive and clustered closed forms agree within 1 pp.

## What it means for the results

**Strong effects are unaffected.** Severe schema drift (+19.7 pp retrieval),
severe semantic stripping (+14.3 / +39.1 pp), and severe freshness on retrieval
(+9.9 pp) sit well above every MDE with p < 0.001.

**Three cell-level results should not be called significant.** Given α ≈ 0.12,
p-values between 0.01 and 0.05 from single-cell comparisons overstate the
evidence:

| cell | effect | p |
|---|---|---|
| retrieval · freshness/mild · total error | +5.1 pp | 0.031 |
| retrieval · freshness/mild · silent failure | +5.4 pp | 0.019 |
| classification · schema drift/severe · total error | +7.5 pp | 0.049 |

**Classification silent-failure cells are all below the cell MDE** (0–9.4 pp).
Severe semantic stripping raises classification *total error* by 39 pp but
*silent failure* by only 4.4 pp, because it converts into abstention (H3). That
4.4 pp is not detectable at cell level — consistent with, not contrary to, H3.

**Latency's null is bounded, not zero.** Observed effects are within ±0.3 pp.
The design rules out latency effects larger than ~8–10 pp in a single cell and
~6 pp pooled — not all effects.

## Consequences

- **Chapter 3** must report the empirical α and the MDEs, and drop the
  mixed-effects justification.
- **Chapter 4** should report cell-level p-values only alongside this caveat,
  and prefer pooled comparisons.
- **Open (REVIEW F-C7):** a small-cluster correction — wild cluster bootstrap or
  CR2 errors — would restore nominal α for cell comparisons. Not yet applied.

## Limitations

- **Two-group comparisons only.** The GLMs in `decision_models.py` pool many
  conditions with more clusters; their α is likely closer to nominal but is not
  simulated here.
- **Beta-binomial data-generating model** with the observed ICC; if between-run
  variation has heavier tails, power is overstated.
- **ICC intervals are approximate** — bootstrapping four runs per condition.
- **gpt-4o-mini main factorial only.**
