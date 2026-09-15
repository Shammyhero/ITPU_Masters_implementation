# Research questions, hypotheses, and analysis plan — revision 2

**Supersedes** the five research questions in the May 2026 research plan (§3.3)
and the statistical plan in Table 4.3.

**Why this revision exists.** The original questions were written before two
things happened: (a) the literature review established that the semantic-layer
accuracy effect was already published (Rumiantsau & Fokeev, 2026) and that
agent fault injection already exists (Gupta, 2026); and (b) the harness produced
its first evidence, which showed that the *failure mode* differs by fault type —
agents abstain under some faults and fail silently under others. The revision
moves the thesis's centre of gravity onto the claim that is genuinely
unclaimed, and retires the question that is weakest against related work.

Everything here is implemented and testable with the code as it stands.

---

## 1. Title

**Proposed:**

> **Detectability Determines Danger: How Data Infrastructure Faults Cause
> Silent Failure in Agentic AI Systems**

**Alternative** (closer to the approved proposal wording, if the supervisor
prefers continuity):

> **Characterizing the Data Infrastructure Gap for Agentic AI Systems: Fault
> Detectability and Silent Failure**

Both retain the approved subject matter. The first signals the contribution;
the second signals the lineage. The original title —
*"Characterizing the Data Infrastructure Gap for Agentic AI Systems"* —
describes the broad gap claim that the literature review showed is no longer
defensible as stated (see `literature_review.md` §7).

---

## 2. The revised research questions

| | Question | Output |
|---|---|---|
| **RQ1** | For each of the four fault types, at what severity does agent decision accuracy degrade by more than 10% relative to baseline — **and is that degradation monotonic in severity?** | Four threshold values with 95% CIs, plus a monotonicity test per fault |
| **RQ2** | Among freshness, latency, consistency and semantic completeness, which produces the largest accuracy degradation **at matched severity**? | Ranked ordering with effect sizes |
| **RQ3** | **Which faults cause agents to fail *silently* (commit confidently to a wrong answer) rather than abstain — and does the *detectability* of a fault in the delivered record predict its silent-failure rate?** | Per-fault abstention and silent-failure rates with a detectability classification |
| **RQ4** | Can a composite infrastructure score (AIRS) predict **silent failure**, and how does it compare against the agent's own reported confidence as a baseline detector? | Calibrated AIRS weights; precision/recall/AUC against a competing baseline |
| **RQ5** | Do the threshold and the ranking hold across agentic task families (retrieval, classification) and across model families? | Task- and model-specific comparisons |

**RQ3 is the thesis's principal contribution.** It is the question prior work
leaves open: Advani (2026) quantifies silent failure across 9,876 trajectories
but is purely observational and does not explain its causes; this study
manipulates conditions and can therefore make a causal claim.

### Demoted: architecture comparison

The original RQ5 (*"under which conditions does the streaming pipeline lose its
accuracy advantage over batch?"*) becomes a **secondary analysis**, not a
research question. Three reasons:

1. The research plan itself states that pipeline architecture is "the
   experimental vehicle, not the research question" (§2.3, §10.1).
2. Batch-versus-streaming comparison is the most thoroughly covered ground in
   the existing literature and the weakest position against related work.
3. The batch arm carries ~10 s of inherent staleness by construction, which
   **confounds** the other three faults in every batch condition (see
   `chapter3_methodology.md` §7.3). Primary fault effects are therefore
   reported on the streaming arm, with batch presented as an architecture
   contrast.

The batch runs are still executed and still reported — only their status in the
argument changes.

---

## 3. Hypotheses

- **H1 (monotonicity).** Accuracy degradation is *not* monotonic in severity
  for at least one fault type. *Rationale:* Shisher & Sun (MobiHoc 2022) prove
  prediction error need not be monotonic in Age of Information when the data
  sequence departs from a Markov chain. The retrieval ground truth here is the
  minimum over several independently-updating product prices — a maximum-type
  statistic over parallel random walks — which is not obviously Markovian.
  A monotonic result is equally reportable; the point is that the design can
  now tell the difference.

- **H2 (relative impact).** At matched severity, semantic completeness produces
  accuracy degradation at least as large as freshness. *Status:* this is the
  original working hypothesis. Rumiantsau & Fokeev (2026) have already
  established the underlying effect for LLM analytics; the contribution here is
  the *matched-severity ranking against three other dimensions*, not the
  discovery of the effect.

- **H3 (detectability — central).** **Faults that alter the delivered record in
  a way the agent can observe (semantic stripping, schema drift) produce
  comparatively high abstention and low silent failure. Faults that leave the
  record well-formed and plausible (freshness, latency) produce low abstention
  and high silent failure.** *Rationale:* a stale price is syntactically and
  semantically indistinguishable from a current one; an opaque field name is
  visibly wrong. The agent can only decline what it can detect.

- **H4 (AIRS beats self-report).** AIRS predicts silent failure with higher
  precision than the agent's own reported confidence at matched recall.
  *Rationale:* self-reported confidence is generated from the same corrupted
  evidence that caused the error, whereas AIRS is computed from pipeline
  telemetry the agent never sees.

- **H5 (generalization).** The *ranking* established in H2 and the
  detectability pattern in H3 hold across two model families and two task
  families, even where absolute thresholds differ.

---

## 4. Dependent variables

| Variable | Level | Definition |
|---|---|---|
| `accuracy` | run | Proportion of decisions matching ground truth |
| `f1_score`, `auc_roc` | run | Standard binary metrics; AUC uses reported confidence |
| **`abstention_rate`** | run | Proportion of decisions where the agent declined |
| **`silent_failure_rate`** | run | Proportion of decisions that were **committed, parseable and wrong** — no confidence threshold |
| `parse_failures` | run | Unusable outputs (counted as failures, never retried) |
| `airs_*` | run | Four dimension scores plus composite |
| `correct`, `confidence`, `abstained` | **decision** | Per-decision record — the unit for the primary models |

**Revised 2026-09-13.** Silent failure originally carried a `HIGH_CONFIDENCE =
0.7` threshold, and this section promised a sensitivity check across
0.5/0.6/0.7/0.8/0.9 that was never run — while the analyses applied no threshold
at all. The definition is now threshold-free everywhere
(`runner/scoring.py::is_silent_failure`), and the promised check exists:
`analysis/silent_definition.py`, reported in `silent_definition_findings.md`.
It shows the threshold was inert at 0.7 for the primary model but not robust
across the range: at 0.9 it would erase most classification silent failures.

---

## 5. Statistical analysis plan (supersedes Table 4.3)

The original plan applied ANOVA to every question. That is the wrong tool for
the two new dependent variables, which are **proportions**, and it discards the
per-decision data the harness already records.

| RQ | Method | Notes |
|---|---|---|
| RQ1 | Exhaustive changepoint search on the freshness sweep + **monotonicity test** (Spearman's ρ; isotonic fit vs unconstrained per-level means) | Threshold = **first crossing** of the −10% band; full curve reported. **Outcome changed:** monotonicity is tested on *exposure* and *unconditional silent failure*, not on accuracy — the flip partition showed accuracy under freshness traces the answer-flip rate, a property of catalog velocity rather than of the agent. The conditional rate is not tested at all where its denominator is too small to bear it. `ruptures` is unnecessary: at six levels an exhaustive single-split search is exact. See `freshness_sweep_findings.md`. |
| RQ2 | Two-way ANOVA on run-level accuracy with η² and Cohen's *d*; Kruskal–Wallis if normality fails (Shapiro–Wilk) | Unchanged from the original plan — accuracy at run level is continuous and approximately normal |
| **RQ3** | **Decision-level logistic regression** `silent_failure ~ condition + task + pipeline`, with **cluster-robust SEs grouped by `run_id`**; same model for `abstained`. Fitted separately per task. | Correct for binary outcomes; uses 11,412 decisions rather than 144 run means. **Substitution, declared:** the random intercept originally specified here is replaced by cluster-robust errors — statsmodels' only mixed logit is variational-Bayes, whose posterior SDs are not the frequentist SEs this plan reports. Both absorb within-run correlation; the cluster-robust form approximates no likelihood. See `statistical_analysis_findings.md`. |
| **RQ4** | Logistic regression of the outcome on the four AIRS dimensions, **fitted per task**, cluster-robust by run; validated on a held-out 20% split **by run**; ROC comparison against a confidence-only baseline (DeLong). Primary figure is the **run-level Spearman**, since AIRS is constant within a run. | **Target changed:** total error, not silent failure. The silent/refusal split is an agent property, not a pipeline one — semantic stripping degrades the data and the agent converts it to refusal, so silent failure alone under-predicts (ρ −0.32 vs −0.88 on classification). **Per task, not pooled:** the weights invert between tasks (RQ5). See `airs_calibration_findings.md`. |
| RQ5 | Task × fault and model × fault interaction terms in the RQ3 model; **rank correlation (Kendall's τ) of the fault ranking across models and tasks** | Rank correlation is the right test for "does the ordering hold", not mean comparison |
| All | 95% CIs on every reported quantity; effect sizes for all pairwise comparisons; negative and null results reported in full | Unchanged commitment |

**Dimension independence** is a precondition for RQ2 and RQ4: if two AIRS
dimensions move together, their coefficients cannot be attributed separately.
This is enforced in the instrument (semantic stripping records its opacity
mapping so the consistency measure can reverse it) and verified by
`tests/test_dimension_independence.py`. Observed collinearity is additionally
reported as a VIF table by `analysis/airs_calibration.py` (every VIF 1.1–1.2).

---

## 6. Power analysis (supersedes §4.4)

**Revised in W2.** This section originally gave a closed-form minimum detectable
effect of 8–10 pp, justified it as conservative because "the mixed-effects model
borrows strength across conditions", and required a clustering-aware simulation
"in the analysis notebook" before the results chapter. No mixed-effects model and
no notebook existed, and the simulation was never run. Its design counts (198
runs, 18 cross-model) were also superseded: 302 runs were executed, 54 of them
cross-model.

The simulation now exists (`analysis/power.py`, `power_findings.md`) and tests
the model the analyses actually use — a logistic GLM with run-clustered errors:

- **Clustering is negligible:** ICC 0.000–0.003, design effect ≤ 1.25. The
  closed-form 8–10 pp was approximately right.
- **The original test was anti-conservative with few clusters:** empirical
  type-I error 0.11–0.12 per cell, 0.07–0.08 pooled (REVIEW F-C7).
- **Corrected 13 Sep:** cell and pooled comparisons use CR2 errors with
  Bell–McCaffrey degrees of freedom (type-I error 0.045–0.058); three cell
  results lose significance. The decision-level models' p-values are calibrated
  by simulation (per-coefficient type-I error up to 0.10), and every published
  significant coefficient survives.
- **Minimum detectable effect, at nominal size:** ~10–12 pp for a single cell
  (4 v 4 runs), ~6 pp pooled (16 v 8), at 80% power.

---

## 7. Declared experimental parameters

These are properties of the simulated domain, fixed in advance and reported —
not tuned to produce a result. Stating them explicitly is the defence against
the configuration-sensitivity critique that *The Powerless Noise* (SIGIR 2026)
levelled at comparable work.

| Parameter | Value | Justification |
|---|---|---|
| Catalog update rate | 2000 updates/s over 20,000 products → **one update per product per ~10 s** | Models a high-velocity dynamic-pricing catalog. Raised from 1000/s during instrument calibration after a sensitivity check showed a severe fault flipping only 8.1% of answers; the change and its reason are reported. |
| Batch inherent staleness | 10 s (one update interval) | A real 10-minute DAG implies ~300 s and floors the batch arm in every condition, producing a floor effect that masks the other three faults. Stated as a limitation: real batch deployments fare *worse* on freshness than this study's batch arm. |
| Streaming inherent staleness | 0.05 s | Represents near-real-time delivery |
| High-confidence threshold | 0.7 | Sensitivity checked across 0.5–0.9 |

**Required for the defence:** RQ1 thresholds are reported **both** in absolute
seconds **and** as a ratio of staleness to mean inter-update interval, so the
finding transfers to domains with different velocities. One condition is
replicated at a second catalog velocity to demonstrate the relationship scales
rather than being an artifact of the chosen setting.

**Measured answer-flip rates at the declared velocity** (share of queries where
the stale catalog implies a *different* correct answer — computed offline with
no model calls, via `airsbench.dataprep.check_sensitivity`):

| Staleness | Flip rate |
|---|---|
| 0.05 s (streaming baseline) | 0.3% |
| 1.5 s (mild fault) | 5.3% |
| 5.0 s (severe fault) | 14.7% |
| 10 s (batch inherent) | 21.3% |

This establishes the *ceiling* on freshness-induced degradation independently
of the agent: no agent, however poor, can lose more than the flip rate to
staleness alone.

---

## 8. What changes in the artifacts

- [ ] Chapter 1: adopt the revised title; add the Anthropic self-service
      analytics case (claude.com/blog, 3 June 2026 — 21% → >95% attributed to
      skills including a semantic layer) as industry motivation, clearly
      labelled grey literature
- [ ] Chapter 2: gap statement per `literature_review.md` §7; cite Gupta (2026)
      and Rumiantsau & Fokeev (2026) prominently and differentiate
- [ ] Chapter 3: as drafted in `chapter3_methodology.md`
- [ ] AIRS calibration notebook: target `silent_failure`, not generic failure;
      add the confidence-only baseline and the DeLong comparison
- [ ] AIST demo: rebuild the act structure around detectability — the
      freshness slider producing confident wrong answers while AIRS goes red
      *before* the accuracy curve moves
- [ ] Results chapter: report the fault ranking as the headline, the
      detectability split as the interpretation, and architecture as secondary

---

## 9. Additions under the Analyst (adopted 14 Sep)

The Analyst (`docs/analyst_brief.md`, `docs/plan.md` Part 1b) adds no new research
question. It adds three analyses that bear on the existing ones, each declared here
before it is run.

| Analysis | Bears on | Hypothesis | Test | Output |
|---|---|---|---|---|
| **Verifier agreement** | RQ2, RQ3 — admissibility of the live instrument | H-V: the live verifier, run over the retrieval runs of the main factorial and the freshness sweep, reproduces each decision's correctness, the silent-failure rates and the flip-partition split **exactly** | Decision-level equality; any mismatch is a verifier defect, not a statistic | Fig 4.10, `verifier_agreement_findings.md` |
| **Refetch arm** (two conditions) | RQ3 (detectability), kill question 3 | H-R1: an agent given a `refetch(record_id)` tool refetches more on stale records than on fresh ones and loses fewer answers on flipped queries than without it. H-R2: gate-initiated refetch reduces silent failure on flipped queries at a lower exchange rate than refusal | Paired comparison within replication, closed-form paired bootstrap as in `interaction.py`; CR2 for any cell comparison | Fig 4.9, `refetch_findings.md` |
| **Live-source case study** | RQ4 and RQ5 — transfer beyond the two curated datasets | H-L: on a real source with genuine update velocity, AIRS ranks answers that fail above answers that do not; the attribution split is reported whatever it is | Rank correlation / AUC of AIRS against verified failure; descriptive lag and attribution distributions; a null is reportable | Fig 4.11, `live_case_study_findings.md` |

**Refined 15 Sep, before any agreement is computed.** H-V covers the verifier's four
labels (`docs/analyst_brief.md` corrections 16–18): answer_key_moved + both must equal
the wrong answers on flipped queries and corrupted_in_transit + agent_impairment the
wrong answers on unflipped ones, decision by decision. The corrupted/impairment split
needs each run's delivered records, which are regenerated by replaying the fault chain
with the run's seed; the regeneration is accepted only if it reproduces the run's logged
consistency and semantic scores exactly.

Declared constraints: classification is out of scope for the verifier (its label is a
property of the flight, not computable from the record); the Analyst's plan-returning
prompt is a different instrument from the corpus agent's, so live rates are not pooled
with corpus rates; live sessions never enter `results/runs/`.
