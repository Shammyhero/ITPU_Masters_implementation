# Verifier agreement — results (RQs v2 §9, Fig 4.10)

**Run:** 2026-09-16 · 90 retrieval runs (main factorial + freshness sweep),
gpt-4o-mini, 6,714 logged decisions · **$0** — no model call, no API key.

```bash
python -m airsbench.analysis.verifier_agreement
python -m airsbench.analysis.verifier_agreement \
    --figure docs/figures/fig4_10_verifier_agreement.png
```

## The question

The Analyst answers live questions over a declared source and tells the user
whether each answer was right and, if not, whose fault it was. On a live pipeline
nothing can check that claim — which is the whole problem the thesis is about. So
the claim has to be earned somewhere the answer *is* known: on the corpus, where
302 runs already recorded what the agent chose, whether it was right, and whether
staleness had moved the correct answer.

**A live instrument that disagrees with the published one is measuring something
else.** This analysis is the admissibility argument for Chapter 5's product claims.

## Verdict

**The verifier reproduces the corpus exactly, decision by decision.**

| Check | Decisions | Disagreements |
|---|---|---|
| The question has a well-defined answer (verifiable) | 6,714 | **0** |
| `correct` — the runner's own grading | 6,714 | **0** |
| Silent failure — `runner/scoring.py::is_silent_failure` | 6,714 | **0** |
| `flipped` — `flip_partition.QueryOutcome.flipped` | 6,714 | **0** |
| Attribution partition (below) | 6,714 | **0** |
| Fault realizations regenerated from the config alone | 90 runs | **90/90** |

Nothing here is an aggregate: each is per-decision equality. The published RQ2
numbers come back out of the verifier's own correctness, not out of the logs:

| Condition | Recomputed | Published |
|---|---|---|
| freshness · mild — raw accuracy | +0.812 | +0.812 |
| freshness · severe — raw accuracy | +0.774 | +0.774 |
| schema drift · severe — raw accuracy | +0.689 | +0.689 |
| semantic stripping · severe — raw accuracy | +0.729 | +0.729 |
| freshness · mild — residual impairment | −0.003 | −0.003 |
| freshness · severe — residual impairment | −0.003 | −0.003 |
| schema drift · severe — residual impairment | −0.173 | −0.173 |
| semantic stripping · severe — residual impairment | −0.128 | −0.128 |

## What the four labels add

The published partition splits wrong answers by whether staleness moved the
answer key. The live verifier splits the *other* side too, using the records as
they were delivered: a wrong answer over a field that arrived missing, renamed,
retyped, altered or made opaque is **corrupted in transit**; a wrong answer over
records that arrived intact is **agent impairment**.

Share of all decisions, both pipelines pooled (Fig 4.10, right panel):

| Condition | correct | key moved | both | corrupted | impaired | abstain |
|---|---|---|---|---|---|---|
| fault-free | 84.9% | 3.8% | 0.6% | 0.0% | **9.7%** | 1.0% |
| freshness · mild | 81.2% | 6.5% | 1.4% | 0.0% | 9.6% | 1.3% |
| freshness · severe | 77.4% | **10.2%** | 1.9% | 0.0% | 8.8% | 1.8% |
| latency · mild | 84.7% | 3.8% | 0.5% | 0.0% | 9.7% | 1.3% |
| latency · severe | 84.9% | 3.7% | 0.8% | 0.0% | 9.7% | 1.0% |
| schema drift · mild | 80.4% | 4.0% | 0.5% | 7.0% | 7.6% | 0.5% |
| schema drift · severe | 68.9% | 2.2% | 1.6% | **25.0%** | 1.8% | 0.5% |
| semantic stripping · mild | 78.2% | 3.8% | 0.5% | 14.3% | 2.7% | 0.5% |
| semantic stripping · severe | 72.9% | 3.3% | 0.8% | **22.5%** | 0.2% | 0.3% |
| freshness sweep · 0.5 s | 87.0% | 1.7% | 0.6% | 0.0% | 9.0% | 1.7% |
| freshness sweep · 12 s | 72.3% | **15.3%** | 1.1% | 0.0% | 7.9% | 3.4% |

Three things this says, none of which the two-way partition could:

1. **Agent impairment is a floor, not a fault effect.** On a fault-free pipeline
   9.7% of all decisions are wrong with the records intact — the decision-level
   form of the gate result that ~75% of silent failure is agent-intrinsic
   ([`gate_findings.md`](gate_findings.md)). Latency, which changes no value,
   sits at the same 9.7%.
2. **Freshness only moves the key.** Across the sweep, `answer key moved` rises
   1.7% → 15.3% while impairment stays near 8–9%. That is RQ2's −0.003 residual
   restated one decision at a time.
3. **Under drift and stripping the wrong answers are over damaged records.**
   Corrupted-in-transit reaches 25.0% and 22.5% of all decisions. Impairment
   *falls* (to 1.8% and 0.2%) because there are hardly any intact records left to
   be wrong about — a share of a shrinking denominator, not the model improving.

**`corrupted_in_transit` is a statement about delivery, not causation.** It says a
field the question reads did not arrive as sent, and names it. Whether that change
is why the answer was wrong is not claimed, and on this corpus cannot be: the
counterfactual (the same model, the same question, undamaged records) is a
different run.

## How the delivered records were recovered

Run artifacts store the AIRS dimensions measured from the delivered records, not
the records. The realization is therefore replayed: the run's fault chain, one
`chain.apply` per record, queries in plan order, skipped queries consuming no
draws (invariant 3). A replay is **only accepted if it reproduces that run's
logged consistency and semantic scores exactly** — float equality, not a
tolerance. All 90 runs do.

**That check failed when it was first run, and it found a real defect.**
None of the 32 main-factorial drift/stripping runs regenerated, because they were
executed (26–28 July) before `_component_seed` arrived with the interaction arm
(17 August), so today's chain seeded their injectors differently from the runner
that produced them. The fault realization *is* the treatment (invariant 2), so
those runs could not be replayed from their own configs — the artifact claim that
any run reproduces in isolation was false for 88 runs across two arms. Fixed by
seeding a flat single-fault condition with `config.seed` and reserving
per-component streams for the nested shape the interaction arm writes; every
published number is unaffected, since the artifacts are canonical (invariant 7).
See **REVIEW F-E7** and `tests/test_fault_realization.py`.

## A measurement quirk this surfaced

Healthy runs score consistency **99.88, not 100**. Missing brands load from the
ESCI parquet as NaN, and NaN never equals itself, so `payload_consistency` counts
those fields as mismatched. It is under 0.2 points, identical across conditions
(the same products appear in every arm), and therefore moves no comparison; the
corpus measure is left exactly as the published results computed it. The demo
source stores the same absences as `null` and so scores 100 — the one place the
bundled demo and the corpus differ. See **REVIEW F-B5**.

## Limitations, stated

- **Retrieval only.** Classification's label is a property of the flight, not of
  the catalog, so there is no computable answer to re-check and no flip to
  partition (RQs v2 §9).
- **One question type.** The corpus asked `min_by(price, stock > 0)` and that is
  what is verified here. The other five plan types are exercised by unit tests,
  not against 6,714 logged decisions.
- **The labels are checked for consistency, not for truth.** Agreement proves the
  four labels partition the wrong answers exactly as the published split does; no
  external ground truth says a given wrong answer was *caused* by the corruption.
- The agreement covers `gpt-4o-mini`; the cross-model arm is not re-verified here.
