# Fault interaction arm — design

**Status: COMPLETE 2026-09-10** — results in [`interaction_findings.md`](interaction_findings.md).
Built 2026-08-05, quarantined by seed block
(80 000–90 000) and barred from Postgres by `schema.sql`'s `fault_type` CHECK.
Nothing outside the arm depends on it. If it is cut, delete this file, the
`interaction` seed block, `build_interaction_arm`, `analysis/interaction.py` and
`tests/test_interaction_arm.py`; the composition support in `execute.py` is
harmless and tested either way.

## The question

Every AIRS composite in this study is a weighted **sum** over four dimensions:

```
AIRS = Σ wᵢ · scoreᵢ
```

The weights come from a logistic GLM fitted on the main factorial, in which
**exactly one dimension was ever degraded per run** — `fault_type` is a single
value and `execute.build_fault_chain` was an `if/elif` chain. `airs probe` and
`airs gate` then apply that composite to arbitrary pipelines, where several
dimensions may be degraded at once. That is the normal production case, and it
is outside the distribution the weights were fitted on.

The extrapolation fails in the unsafe direction. If two faults **compound**, the
composite under-predicts risk on precisely the pipelines that are worst, and
`gate.Policy`'s independent per-dimension floors are the wrong shape — a
pipeline could clear every individual floor and still be far more dangerous than
either fault alone.

**RQ6.** *Do two simultaneous infrastructure faults produce silent
failure additively, or does their combination exceed the sum of their parts?*

## Why the answer is interpretable

An interaction test is only meaningful if the treatments are separable. Here
they demonstrably are, and that was checked before any money was spent
(`tests/test_interaction_arm.py::test_composition_preserves_solo_marginals`,
verified end-to-end through the real runner on real data):

| condition | freshness | latency | consistency | semantic |
|---|---|---|---|---|
| none | 100.0 | 100.0 | 99.5 | 100.0 |
| freshness | **19.8** | 100.0 | 99.5 | 100.0 |
| latency | 100.0 | **16.7** | 99.5 | 100.0 |
| schema_drift | 100.0 | 100.0 | **74.6** | 100.0 |
| semantic_stripping | 100.0 | 100.0 | 99.5 | **17.1** |
| freshness+schema_drift | **19.8** | 100.0 | **74.6** | 100.0 |
| freshness+semantic_stripping | **19.8** | 100.0 | 99.5 | **17.1** |
| semantic_stripping+schema_drift | 100.0 | 100.0 | **74.6** | **17.1** |
| latency+schema_drift | 100.0 | **16.7** | **74.6** | 100.0 |

Every compound row is the exact element-wise combination of its solos, and the
untouched dimensions stay at baseline. **Invariant 5 holds under composition.**
The independent variable is therefore additive by construction, so any departure
from additivity in the *outcome* is behavioural rather than an artifact of the
injectors interfering.

## The trap this nearly walked into

Composition order is load-bearing, and only one order is valid.

`SchemaDriftInjector` renames payload keys (`price` → `price_v2`).
`SemanticStrippingInjector` opaquifies them (`price` → `f3`) through a
**stateful** map keyed on whatever name it is handed. Run drift first and the
stripper is handed `price_v2` on the records drift happened to touch and `price`
on the rest — so one semantic field acquires **two** opaque tokens, and the agent
sees `f3` and `f4` both meaning price within a single batch.

That is a third corruption neither fault produces alone, it is **invisible to
every AIRS dimension** (both orders yield identical AIRS vectors), and it would
have manufactured an "interaction" that was pure instrumentation artifact.

`COMPOSITION_ORDER` therefore applies semantic stripping **before** schema
drift, so the opaque map stays keyed on true field names. Pinned by
`test_drift_before_stripping_corrupts_the_opaque_map`.

## Design

**54 runs, self-contained**: 9 conditions × 2 tasks × 3 replications, streaming
only, severe severity, gpt-4o-mini, 80 queries per run. ~$0.59.

| conditions | |
|---|---|
| 1 | baseline, no fault |
| 4 | each fault alone |
| 4 | `freshness+schema_drift`, `freshness+semantic_stripping`, `semantic_stripping+schema_drift`, `latency+schema_drift` |

It carries its own solos rather than borrowing the main factorial's, for two
reasons. The contrast is then paired on **fault realization** as well as on
queries — within a replication every condition shares `seed`, so a pair and its
two solos corrupt the same records, and `_component_seed` splits that into a
distinct RNG stream per injector so the two faults do not hit a correlated
subset. And the arm drops as a unit.

**Streaming only.** Batch's inherent 3 s staleness would add a fifth degraded
dimension to every cell and confound the freshness pairs.

**Severe only.** The solo severe effects are known and moderate (silent failure
~24% against a ~14% baseline), leaving room to detect departure in either
direction. Mild effects would be too small to resolve an interaction; two severe
faults risk a ceiling. Stated as a limitation: the arm tests additivity at one
point in severity space, not a surface.

## Analysis

`python -m airsbench.analysis.interaction`

**Additivity is scale-dependent**, and the two relevant scales can disagree
without contradiction:

- **Logit.** What the AIRS calibration assumes — its weights come from a
  logistic GLM, so the composite extrapolates correctly to multi-fault pipelines
  exactly if the `a:b` term is zero on this scale. Estimated in closed form as
  ψ = logit p(AB) − logit p(A) − logit p(B) + logit p(0), with a paired
  bootstrap. A cluster-robust GLM was the original design and had to be
  dropped: with one run per condition per replication the interaction term is
  confounded with cluster identity, and it reported p = 0.000 for every pair
  including the latency control.
- **Risk difference.** What an operator experiences, and the scale
  `gate.replay`'s prevented/forfeited accounting is denominated in.
  δ = p(AB) − p(A) − p(B) + p(0), with a bootstrap over **paired queries**.

The bootstrap resamples paired queries rather than runs because there are only
three replications; the paired design supplies 240 aligned quadruples instead of
3 clusters. Alignment is *checked*, not assumed — `paired_cells` raises if the
conditions in a replication evaluated different numbers of decisions, which
would mean the contrast was comparing different questions.

## The latency control is weaker than it looks

`latency+schema_drift` is included as a **method** control: latency has no
measurable effect on any outcome anywhere in this study, so a correctly
specified interaction test must report no interaction there.

It validates the arithmetic, not the sensitivity. Latency runs in analytic mode
(`sleep=False`) and therefore cannot change what the agent reads, so this
control could only ever have come out one way. It is not evidence that the test
would detect a real interaction if one existed.

That gap is closed for the **statistic**, though not for the experiment, by a
planted-effect test: `test_estimator_recovers_a_planted_interaction` builds
cells with a known ψ ∈ {0, +0.8, −0.8} and requires the estimator to recover it,
to exclude zero when ψ ≠ 0, and to include zero when ψ = 0. So the estimator
demonstrably detects real departures from additivity and does not manufacture
false ones at this sample size.

What remains untested is whether *this study's faults* could interact through
some mechanism the design would miss. No synthetic control can settle that.

## Limitations

- **One severity point.** Additivity is tested at severe×severe only.
- **Two-way only.** Three- and four-fault combinations are untested, and any
  higher-order interaction is invisible here.
- **One model, one pipeline archetype.** gpt-4o-mini, streaming.
- **n = 3 replications.** The paired bootstrap mitigates this for the risk
  difference; the logit interval remains wide.
- **Absence of evidence.** With this n, "additive" means "no interaction large
  enough to detect", not "no interaction". The reportable quantity is the
  interval, not the p-value.
