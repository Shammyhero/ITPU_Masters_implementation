# AIRS curve sensitivity — how much depends on four undocumented constants?

**Run:** 2026-09-13 · 13 554 decisions from 180 gpt-4o-mini runs · **$0**

```bash
python -m airsbench.analysis.curve_sensitivity --figure docs/figures/fig4_7_curve_sensitivity.png
```

## Why this analysis exists

RQ4 fits the AIRS weights instead of assuming them, and `airs/calculator.py`
states that as a methodological commitment: *"they are estimated, never
assumed."* The commitment holds one level up and is skipped one level down. The
weights are estimated **on top of** four constants that no document derives:

```python
DEFAULT_FRESHNESS_TARGET_S = 1.0      # why one second?
DEFAULT_LATENCY_TARGET_MS  = 500.0    # why half a second?
score = 100 * target / observed       # why a hyperbola?
```

Change any of them and every freshness and latency score in the study moves, the
weights are refitted against different predictors, and the composite reports a
different number for the same pipeline. A metric whose values depend on
undocumented choices is declared rather than measured. This analysis measures
how much actually depends on them.

## Verdict

**The conclusions that carry the thesis survive. The magnitudes do not, and one
task's ranking does not.**

- **Latency earns exactly 0.0% under all seven parameterisations, on both
  tasks** — including one under which it stops being a two-level factor. This
  is the strongest result here and it *strengthens* an existing claim.
- **Consistency dominates retrieval under every parameterisation** (61.2–72.2%).
  RQ2's headline is robust.
- **Freshness's weight is not reportable to one significant figure.** It ranges
  10.7–22.8% on retrieval and 16.4–44.7% on classification.
- **Classification's dominant dimension flips** from semantic to freshness under
  a 5 s target. RQ5's "the weights invert across tasks" survives as a direction;
  the specific classification ordering does not survive as a ranking.

## Method

Three choices make the comparison fair, and each closes a specific objection.

**Every curve is anchored at the same two points** — 100 at its target and 10 at
ten times its target. Without a shared anchor the alternatives could be steeper
or shallower than the shipped one, and the spread in fitted weights would
reflect that rather than the functional form. Anchored, what varies is only the
shape of the decay between the endpoints:

| ratio x/target | 1 | 2 | 3 | 5 | 10 | 20 |
|---|---|---|---|---|---|---|
| hyperbolic *(shipped)* | 100 | 50.0 | 33.3 | 20.0 | 10 | 5.0 |
| exponential | 100 | 77.4 | 59.9 | 35.9 | 10 | 0.8 |
| linear | 100 | 90.0 | 80.0 | 60.0 | 10 | 0.0 |
| logarithmic | 100 | 72.9 | 57.1 | 37.1 | 10 | 0.0 |

**Physical quantities come from the run configuration, never from inverting the
recorded score.** Inversion is the obvious approach and it is wrong:
`latency_score` returns exactly 100 for everything at or below target, so a
fault-free run at 0 ms and a mild-latency run at 500 ms both invert to 500 ms.
An earlier draft of this analysis did exactly that and silently treated every
clean pipeline as degraded. `value_staleness_s` and the injector's `spike_ms`
give the true values.
→ `tests/test_curve_sensitivity.py::test_physical_quantities_distinguish_baseline_from_mild_latency`

**Everything else is held identical to the published calibration** — same frame,
same run-level 80/20 split, same seed, same cluster-robust estimator, same
target variable (total error). Only the two transforms move. Refitting under the
shipped curve reproduces the exported weights exactly, which is what makes this
a sensitivity analysis of the *shipped* metric rather than of a lookalike.
→ `tests/test_curve_sensitivity.py::test_shipped_variant_reproduces_the_published_weights`

## 1. Retrieval

| parameterisation | freshness | latency | consistency | semantic | held-out ρ | dominant |
|---|---|---|---|---|---|---|
| **SHIPPED** hyperbolic, 1.0 s / 500 ms | 12.9% | 0.0% | **70.2%** | 16.9% | −0.748 | consistency |
| shape: exponential | 15.7% | 0.0% | **67.4%** | 16.9% | −0.762 | consistency |
| shape: linear | 17.8% | 0.0% | **65.3%** | 16.9% | −0.747 | consistency |
| shape: logarithmic | 15.8% | 0.0% | **67.4%** | 16.8% | −0.762 | consistency |
| target: 0.5 s / 250 ms | 10.7% | 0.0% | **72.2%** | 17.1% | −0.804 | consistency |
| target: 2.0 s / 1000 ms | 16.7% | 0.0% | **66.6%** | 16.8% | −0.694 | consistency |
| target: 5.0 s / 2000 ms | 22.8% | 0.0% | **61.2%** | 16.0% | −0.610 | consistency |
| | **10.7–22.8** | **0.0** | **61.2–72.2** | **16.0–17.1** | −0.61 to −0.80 | **consistency ×7** |

Consistency dominates everywhere, by a margin no parameterisation closes.
Semantic is the most stable dimension in the study — 1.1 pp of total spread.
Freshness moves by 12.1 pp, which is most of its own magnitude.

## 2. Classification

| parameterisation | freshness | latency | consistency | semantic | held-out ρ | dominant |
|---|---|---|---|---|---|---|
| **SHIPPED** hyperbolic, 1.0 s / 500 ms | 21.2% | 0.0% | 25.4% | **53.4%** | −0.882 | semantic |
| shape: exponential | 27.1% | 0.0% | 28.7% | **44.2%** | −0.876 | semantic |
| shape: linear | 30.9% | 0.0% | 29.9% | **39.2%** | −0.882 | semantic |
| shape: logarithmic | 27.1% | 0.0% | 28.0% | **44.9%** | −0.876 | semantic |
| target: 0.5 s / 250 ms | 16.4% | 0.0% | 22.6% | **61.0%** | −0.860 | semantic |
| target: 2.0 s / 1000 ms | 29.1% | 0.0% | 28.1% | **42.8%** | −0.854 | semantic |
| **target: 5.0 s / 2000 ms** | **44.7%** | 0.0% | 23.1% | 32.2% | −0.720 | **freshness ⚠** |
| | **16.4–44.7** | **0.0** | **22.6–29.9** | **32.2–61.0** | −0.72 to −0.88 | 6× semantic, 1× freshness |

Semantic and freshness trade nearly 29 pp of weight between them depending on
parameterisation, and at a 5 s freshness target they swap places. Consistency is
the stable dimension here (7.3 pp).

The flip is not arbitrary. A 5 s target declares five-second-old data *fully
fresh*, which is past the 5.05 s threshold the freshness sweep located — so the
scoring function is being told to ignore exactly the degradation the experiment
measured. That such a target is obviously wrong is the point: **the shipped 1.0 s
is equally undefended, and nothing in the repository ruled the 5 s version out.**

## 3. Latency: the one result this analysis makes stronger

Latency's zero weight was previously vulnerable to a specific objection. Across
the whole campaign the latency dimension takes exactly **two** values, 16.7 and
100.0, because `latency_score(500) = 100` exactly — the mild severity sits on
the target and is therefore indistinguishable from a fault-free pipeline. A
two-level factor cannot support a general claim.

The 250 ms parameterisation removes that objection. Under it the three
conditions separate properly — baseline 100, mild 50.0, severe 8.3 — and the
fitted weight is **still exactly 0.0%**, on both tasks. Latency earns no weight
even when the metric is re-specified so that it *can*.

That strengthens the null. It does not rescue the claim that this is
*"independent evidence"*: latency runs in analytic mode and cannot change what
the agent reads, so every route to this null shares one cause. The correct
statement is that the null is robust to parameterisation, not that it is
independently replicated.

## 4. What must change in the other documents

| Document | Change |
|---|---|
| `airs_calibration_findings.md` §1 | Weight table reports point values. Add the range column; freshness in particular cannot be quoted as "12.9%". |
| `airs_calibration_findings.md` §5 | Limitations claim the split's sensitivity is untested. The *curve's* sensitivity was also untested; now it is. |
| `gate_findings.md` §3 | "carries 70% of the calibrated weight" → "61–72% depending on parameterisation". The ranking argument is unaffected. |
| `cross_model_findings.md` (RQ5) | "The weights invert across tasks" holds as a direction. The classification *ordering* is parameterisation-dependent and must be stated as such. |
| `chapter3_methodology.md` | Must state that the sub-score transforms are design parameters, not measurements, and point here. |
| `CLAUDE.md` / `gate_findings.md` | Drop "a fifth independent route to the null" for latency. Replace with "robust to parameterisation". |

## 5. Limitations

- **Seven parameterisations, not a continuum.** Four shapes at the shipped
  targets and three target pairs at the shipped shape. The interaction between
  shape and target is not explored.
- **The anchor ratio is itself a choice.** Every curve meets at 10× target = 10;
  a different anchor would change the spread, though not which dimensions are
  stable.
- **Consistency and semantic transforms are untouched.** Both are already
  proportions (matched fields, present context categories) with no target
  constant to vary, so there is nothing analogous to test — but that also means
  this analysis says nothing about *their* construct validity.
- **One split, one model, one target variable**, inherited from the calibration
  so the comparison stays controlled. Sensitivity to the split seed remains
  untested, as `airs_calibration_findings.md` §5 already notes.
- **This does not make the constants correct.** It shows which conclusions
  survive them. A defensible 1.0 s would still need an argument from the
  deployment context, and the thesis does not have one.
