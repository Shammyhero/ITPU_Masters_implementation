# Query fragility — results

**Run:** W2 · gpt-4o-mini · arms main, freshness sweep, interaction, detectability · **$0**

```bash
python -m airsbench.analysis.fragility --figure docs/figures/fig4_8_fragility.png
```

## The question

RQ6 found that two faults together never compound. A preliminary look suggested
why — different faults fail the same queries — and `gate_findings.md` found most
silent failure already present on a fault-free pipeline. Both point at one
hypothesis: **silent failure is concentrated on a pool of fragile questions**
rather than spread evenly. This tests it formally.

## Why the test is sound

- **Pooling across arms is legitimate.** The query sample depends only on
  (task, replication), so every arm asks the same questions within a
  replication. Verified by content, not position: 264 condition pairs, zero
  mismatches. Questions are keyed by position in the main sequence, so a flight
  that appears twice is never counted twice. Median **32 faulted observations
  per question**.
- **The null cannot mistake condition severity for fragility.** Silent-failure
  labels are permuted across questions *within each run*: every run keeps its
  own failure count, so a harsher condition stays harsher, and only the link
  between a failure and a particular question is broken. 2 000 permutations.
- **The test can return a null.** `tests/test_fragility.py` plants a fragile
  pool and requires detection, and feeds independent failures and requires none.

## Verdict

**Silent failure is strongly concentrated, on both tasks.**

| | classification | retrieval |
|---|---|---|
| questions | 320 | 314 |
| concentration vs null | **16.4×** (p < 0.0005) | **11.8×** (p < 0.0005) |
| most fragile 10% carry | **46.9%** of faulted silent failures | **38.6%** |
| — expected under null | 14.6% [13.1, 16.3] | 15.8% [14.7, 16.9] |
| questions silent at fault-free baseline | 12.2% | 10.5% |
| — share of faulted silent failures they carry | **52.8%** | **36.7%** |
| — expected under null | 11.5% [10.2, 12.9] | 11.1% [9.8, 12.3] |

Figure 4.8 shows the concentration curves: the observed curve rises far above
the null band on both tasks.

## Overlap between faults

Jaccard overlap of silent-failure sets, main arm, streaming, severe, pooled over
replications. All p < 0.0005 except retrieval freshness + drift (p = 0.005).

| pair | classification J (null) | ratio | retrieval J (null) | ratio |
|---|---|---|---|---|
| freshness + schema drift | 0.45 (0.11) | 4.0× | 0.22 (0.14) | 1.6× |
| freshness + semantic stripping | 0.39 (0.11) | 3.6× | 0.31 (0.13) | 2.5× |
| schema drift + semantic stripping | 0.39 (0.10) | 3.8× | 0.30 (0.16) | 1.9× |
| **re-ask: baseline vs latency** | **1.00** (0.08) | 13.0× | **0.91** (0.06) | 15.6× |

The last row is the most informative. Latency changes nothing the agent reads,
so it is the identical question asked again. On classification (temperature 0)
the silent-failure sets are **identical**; on retrieval (temperature 0.2) they
overlap 91%. **Silent failure on a given question is close to deterministic** —
fragility is a stable property of how the model responds to that question, not
sampling noise.

## What this explains

- **RQ6 saturation.** Faults compete for the same fragile questions instead of
  creating independent failures, so their combination falls short of the sum.
  This replaces the preliminary mechanism in `interaction_findings.md` §4.
- **The un-gateable floor.** About three quarters of silent failure is present
  on a clean pipeline (`gate_findings.md`); those same questions also carry a
  disproportionate share of fault-induced failures. A data gate can remove the
  fault; it cannot make a fragile question easy.
- **Why AIRS ranks pipelines but not decisions.** AIRS is constant within a
  run; fragility varies within it. Decision-level risk has a large per-question
  component no pipeline score can see.

## Implications

**For the thesis:** silent failure has two sources that must be reported
separately — pipeline-caused (what AIRS measures) and question-caused
(fragility). The claim "infrastructure causes silent failure" is true for the
excess over baseline, not for the total.

**For the product:** pipeline readiness is necessary but not sufficient. A
future version could flag fragile question *types*; this analysis does not yet
test whether fragility is predictable from question features.

## Limitations

- **One model.** Fragility is shown for gpt-4o-mini; whether the same questions
  are fragile for other models is untested (the cross-model arm shares the
  question sequence and could answer it).
- **Not predictive.** Fragility is identified after the fact; no question
  features were tested as predictors.
- **12 retrieval decisions unmapped** — sweep-arm questions absent from the main
  reference sequence; excluded, negligible against ~11 000 observations.
- **Baseline is a single run** per replication (main, streaming); carry-over is
  measured against one clean realisation.
