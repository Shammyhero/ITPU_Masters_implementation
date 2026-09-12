# Adversarial review — AIRS / AIST thesis implementation

**Reviewed:** 2026-09-12, commit `a20f6b2`, against the repository as it runs today.
**Panel:** empirical-SE methodology reviewer · production data-platform engineer ·
composite-metrics skeptic · ITPU/EPAM defence examiner.

**Three of the five bracketed inputs were left unfilled** (defence date, weekly
hours, working weeks). Everything below assumes **8 internship weeks from
2026-09-10 → 2026-11-05 at ~20 h/week = ~160 h**, budget **$4.58 OpenAI /
$1.27 Anthropic**, laptop-only. If those are wrong the plan in Phase 4 changes
materially — see the questions at the end.

**Two premises in the review brief are stale and were not played along with.**
The brief says the demo is Streamlit (it is Next.js, `demo/`, 833 LOC, builds)
and implies there may be zero empirical data (there are 302 runs, 24 270
decisions, six answered RQs). The brief appears to have been written against a
much earlier state. The real risks are elsewhere and are listed below.

---

# Phase 0 — Ground-truth inventory

## What actually runs

| Module | LOC | State |
|---|---|---|
| `src/agentic_faults/` | 511 | **Runs.** Four injectors + verification mode. Stdlib only. The genuine technical core. |
| `src/airsbench/airs/` | 161 | **Runs.** Four scoring functions + weighted composite. See Phase 1B — this is the weakest 161 lines in the repo. |
| `src/airsbench/agents/` | 476 | **Runs.** One `.invoke()` per decision (`agents/llm.py:173`). No loop, no tools, no planning. |
| `src/airsbench/runner/` | 1 324 | **Runs.** Grid, staged execution, spend guard, scoring. Solid. |
| `src/airsbench/analysis/` | 3 533 | **Runs.** 12 modules, one per RQ, all re-run from committed artifacts at $0. |
| `src/airsbench/gate/` | 840 | **Runs.** Policy / Controller / replay / CLI. |
| `src/airsbench/pipelines/` | 222 | **Partially decorative.** Only `loader.py` (the catalog time machine) is used. `streaming.py` is imported by nothing. `airflow_dags/batch_load_dag.py` is never executed. |
| `tests/` | 3 750 | **350 pass in 22 s.** Lint clean. |
| `demo/` | 833 TSX | **Builds.** Static export, pre-baked `demo/src/data/aist.json` (29 KB). Four scripted acts. |

## Claimed stack vs. wired stack

| Component | Reality |
|---|---|
| Fault injectors | **Genuinely wired.** The real contribution. |
| AIRS calculator | **Wired**, but see 1B. |
| Statistical layer | **Genuinely wired.** Cluster-robust GLM, DeLong, isotonic, run-level held-out split, bootstrap. Better than most MSc work. |
| LangChain | Wired, thinly — `ChatOpenAI` / `ChatAnthropic` wrappers only. |
| **LangGraph** | **Declared in `pyproject.toml:agents`, imported nowhere.** Delete the dependency or use it. |
| **Kafka** | **Zero references** in `runner/`, `agents/`, `analysis/`. `docker-compose.yml` ships it. Experiments never touch it. |
| **Airflow** | **Zero references.** A DAG file exists; nothing runs it. |
| **Postgres** | **Nothing ever writes to it.** No `INSERT`, no `to_sql`. `schema.sql` is applied by hand and then unused. |
| Prometheus | Demo observability only, as documented. |
| Great Expectations | Not present at all (brief mentions it; it was never in this repo). |
| Streamlit | **Still declared** in `pyproject.toml` `demo` extra. The Streamlit app is gone. |

## Experimental results that exist today

Real and substantial. 302 runs, 24 270 decisions, 4 models, $5.15 spent.
RQ1–RQ5 answered with findings docs; RQ6 (fault interaction) completed
2026-09-10 and is **not yet written up** — `docs/interaction_arm.md` is a design
doc, there is no `interaction_findings.md`, and `README.md` still says the arm is
half-run.

**The headline risk is not "no data".** It is that a genuinely good dataset rests
on four hand-picked constants (1B) and is described with infrastructure language
the code does not implement (Phase 1 finding F-2).

## If this were defended tomorrow, exactly as it stands

It would pass, and it would take two clean hits that cannot currently be
parried. The empirical work is well above MSc bar — paired design, run-level held-out
validation, negative results reported, six traps caught and pinned by tests. But
the metrics skeptic asks "where does `DEFAULT_FRESHNESS_TARGET_S = 1.0` come
from?" and the repository contains no answer; and an industry examiner opens
`docker-compose.yml`, sees Kafka and Airflow, greps the experiment path, finds
neither, and concludes that the pipeline factor is a 3.0-versus-0.05-second
constant presented as infrastructure. Both hits are survivable, and both are
avoidable with roughly 14 h of work.

---

# Phase 1 — Audit

## A. Contribution and positioning

**The novel claim, in one sentence:** *infrastructure faults that impair an
agent's reasoning are a strict subset of those that change its answer, and the
agent's own confidence cannot distinguish the two — so readiness must be scored
on the pipeline, before deployment.*

That is defensible and, as far as the review in `docs/literature_review.md`
establishes, unoccupied. The lit review is the strongest document in the repo:
it names ReliabilityBench (Gupta 2026) as the nearest competitor, has an
explicit *"where they beat us"* section, cites Shisher & Sun's non-monotonicity
warning and **changed RQ1's design because of it**, and states plainly that the
four dimensions descend from Wang & Strong (1996) rather than claiming them as
novel. That honesty is worth preserving.

**F-A1 (serious) — two bodies of work an industry examiner will name are absent.**
`grep -ic "ISO.{0,6}25012|data contract|AgentBench|tau-bench|WebArena|data-centric"`
returns **0** across both `docs/literature_review.md` and
`docs/related_work_positioning.md`.

- **ISO/IEC 25012** is *the* data-quality standard. AIRS's four dimensions map
  onto its characteristics. Without a paragraph saying how AIRS differs
  (25012 grades data *in the abstract*; AIRS grades it *against a named
  consumer's decision quality*, with weights fitted to that consumer), "this is
  ISO 25012 with new names" is a hit with no available reply.
- **Data contracts** are what `airs gate` implements. Not citing the practice
  makes the gate look invented rather than formalised — and the gate is the
  strongest practitioner artifact here.
- AgentBench / tau-bench / WebArena matter as *benchmark-design precedent*:
  they stress the agent and hold data constant, which is the inverse of this
  design. A one-sentence differentiation, and it strengthens the positioning.

**Effort: 4 h.** Highest credibility-per-hour in the entire review.

**F-A2 (serious) — the four load-bearing papers are self-declared unread.**
`docs/literature_review.md:§9` — `[ ] Full-text deep read of the four
load-bearing papers (Shisher & Sun; Gupta; Rumiantsau & Fokeev; Advani)`. The
box is unchecked in the author's own tracking. A method-level question about
ReliabilityBench's reliability surface *R(k,ε,λ)* cannot be answered from an
abstract, and a panel will hear the difference. **Effort: 8 h.** Non-negotiable before defence.

## B. Construct validity of AIRS — the metrics skeptic's section

This is the most attackable part of the thesis and the audit found it worse than
the docs admit, then found the damage is partly containable.

**F-B1 (FATAL — ANALYSIS DELIVERED 2026-09-13, claims corrected) — the sub-score
curves are hand-picked, undocumented, and every fitted weight is conditional on
them.** Measured in `docs/sensitivity_findings.md`; figure at
`docs/figures/fig4_7_curve_sensitivity.png`. The constants remain underived —
that is a limitation the thesis must state — but what depends on them is now
quantified, and the affected claims in `airs_calibration_findings.md` and
`gate_findings.md` have been rewritten to report ranges instead of point values.

`src/airsbench/airs/calculator.py:38-52`:

```python
DEFAULT_FRESHNESS_TARGET_S = 1.0
DEFAULT_LATENCY_TARGET_MS  = 500.0
# score = 100 * target / observed
```

Three unjustified choices, none of which appears in any doc:

1. **Why 1.0 second?** Nothing cites it. Change it to 2.0 and every freshness
   score in the thesis doubles.
2. **Why 500 ms?** Same. And it is load-bearing in a way the others are not —
   it is the only thing separating the two latency severities.
3. **Why a hyperbola?** `100·T/x` is one of infinitely many monotone decreasing
   maps. Exponential, linear and log are equally defensible a priori.

The docstring's defence — *"weights are estimated, never assumed — this is a
core methodological commitment"* — is **true about the weights and silent about
the transforms the weights are fitted on top of.** The commitment is honoured one
level up and skipped one level down: the weights were correctly refused as
hand-picked parameters, while the coordinate system those weights live in was
hand-picked and never revisited. The result is a metric that is empirical in its
coefficients and arbitrary in its units.

**I measured the damage.** Refitting the RQ4 weights under seven variants
(scratchpad only, repo untouched), target = total error, gpt-4o-mini:

| Variant | fresh | laten | consis | seman | held-out ρ | top |
|---|---|---|---|---|---|---|
| **SHIPPED** hyperbolic 1.0 s / 500 ms | 12.9% | 0.0% | **70.2%** | 16.9% | −0.748 | consistency |
| hyperbolic 0.5 s / 250 ms | 22.9% | 0.0% | **62.2%** | 14.9% | −0.748 | consistency |
| hyperbolic 2.0 s / 1000 ms | 16.7% | 0.0% | **66.6%** | 16.8% | −0.694 | consistency |
| hyperbolic 5.0 s / 2000 ms | 22.8% | 0.0% | **61.2%** | 16.0% | −0.610 | consistency |
| exponential 1.0 s / 500 ms | 10.5% | 0.0% | **72.3%** | 17.2% | −0.748 | consistency |
| linear 1.0 s / 500 ms | 16.8% | 0.0% | **66.1%** | 17.1% | −0.752 | consistency |
| log 1.0 s / 500 ms | 22.3% | 0.0% | **62.2%** | 15.5% | −0.762 | consistency |

Classification, same variants:

| Variant | fresh | laten | consis | seman | held-out ρ | top |
|---|---|---|---|---|---|---|
| **SHIPPED** | 21.2% | 0.0% | 25.4% | **53.4%** | −0.882 | semantic |
| 0.5 s / 250 ms | 34.9% | 0.0% | 21.0% | **44.1%** | −0.882 | semantic |
| 2.0 s / 1000 ms | 29.1% | 0.0% | 28.1% | **42.8%** | −0.854 | semantic |
| **5.0 s / 2000 ms** | **44.7%** | 0.0% | 23.1% | 32.2% | −0.720 | **freshness ⚠ FLIPS** |
| exponential | 16.7% | 0.0% | 24.9% | **58.4%** | −0.882 | semantic |
| linear | 29.7% | 0.0% | 30.5% | **39.8%** | −0.882 | semantic |
| log | 36.2% | 0.0% | 24.5% | **39.3%** | −0.876 | semantic |

**What survives, and it is most of the thesis:**

- **Consistency dominates retrieval under every variant** (61.2–72.3%). RQ2's
  headline is robust.
- **Latency is 0.0% under every variant, on both tasks.** The latency null is
  not a curve artifact. This is the single most reassuring number in the review.
- Held-out ρ stays −0.61 to −0.88 throughout. AIRS ranks pipelines regardless of
  parameterisation.

**What does not survive:**

- **Freshness weight ranges 10.5%–22.9% on retrieval — a 2.2× swing.** Any
  sentence of the form *"freshness carries 13% of retrieval risk"* is
  indefensible to one significant figure. It must become *"10–23% depending on
  parameterisation."*
- **Classification's top dimension flips** from semantic to freshness at a 5 s
  target. RQ5's "weights invert across tasks" is safe as a *direction*; the
  specific classification ordering is not safe as a *ranking*.

**The fix is not to justify the constants — it is to publish this table.** A
sensitivity analysis converts the thesis's largest vulnerability into a
methodological strength, and it needs no new data and no API spend.
**Effort: 6 h** (module + tests + findings doc + a paragraph in Ch. 3).

**F-B2 (serious — PARTLY RESOLVED 2026-09-13) — latency's zero weight is
estimated from a two-level binary.** The 250 ms parameterisation separates the
three conditions properly (100 / 50.0 / 8.3) and the fitted weight is still
exactly 0.0%, so the null survives a specification under which latency *can*
earn weight. The overclaim has been removed from `gate_findings.md` and
`airs_calibration_findings.md`: these are not independent routes to one
conclusion, because analytic-mode latency shares a single cause.
Across the whole campaign the latency dimension takes exactly **two** values:
`16.7` and `100.0`. Freshness takes 9, consistency 28, semantic 29. A
two-level factor with both levels fixed by an arbitrary 500 ms constant cannot
support "latency does not matter" as a general claim — only "the two latency
levels this design produced did not separate." Calling this *"a fifth
independent route to the null"* (as `docs/gate_findings.md` and `campaign_status`
do) is **overclaiming: they are five views of one two-level contrast under one
analytic-mode design that cannot, by construction, affect what the agent reads.**
Demote to a design note. **Effort: 1 h** of honest rewriting.

**F-B3 (polish) — AIRS decomposes well; say so.** `probe` already reports
per-dimension scores, evidence strings, and refuses to score an unmeasured
dimension as 100 (`src/airsbench/probe.py:106-192`). A practitioner *can* read
the score and know what to fix. This is a genuine strength that no document
claims. Add two sentences.

**F-B4 (polish) — edge behaviour is sane but untested.** `freshness_score`
→ 0 asymptotically, never negative; `semantic_score` raises outside [0,1];
`consistency_score` raises on `total<=0`. No adversarial-config test exists.
1 h.

## C. Experimental design

Strong, and stronger than the brief assumes.

**Genuine strengths** — these deserve to be stated explicitly at the defence: paired design with
`sample_seed = f(task, replication)` only (`runner/config.py`); run-level 80/20
split, not decision-level (`analysis/airs_calibration.py:99-113`); cluster-robust
SEs by `run_id` throughout; DeLong for correlated ROCs; VIF checked (1.1–1.2);
Wilson intervals and rule-of-three; the flip partition, which separates
mechanical answer-key movement from agent impairment and is the actual
intellectual contribution.

**F-C1 (serious) — RQ6 is answered and unwritten.** `analysis/interaction.py`
now reports: **5 of 8 pairs saturate, none compounds, latency control ψ = 0.00
[−0.13, +0.13]**. Faults are sub-additive, so AIRS *over*-predicts multi-fault
risk — the conservative, safe direction, and a good result. There is no findings
doc. `README.md` still says "roughly half its runs are on disk." **Effort: 3 h.**

**F-C2 (should-have) — a free result is sitting in the data.** Running the arm's
paired structure through a Jaccard overlap of silent-failure sets:

| task | pair | observed J | chance J | ratio |
|---|---|---|---|---|
| retrieval | freshness+drift | 0.25 | 0.12 | **2.2×** |
| retrieval | freshness+semantic | 0.29 | 0.12 | **2.3×** |
| retrieval | drift+semantic | 0.30 | 0.15 | **2.0×** |
| classification | freshness+drift | 0.35 | 0.10 | **3.6×** |
| classification | drift+semantic | 0.37 | 0.08 | **4.4×** |

and **30% (retrieval) / 48% (classification) of fault-condition silent failures
were already silent at baseline.** Different faults fail *the same queries*.
That is the mechanism behind saturation, it explains the ~75% agent-intrinsic
floor from `gate_findings.md`, and it is a new construct — **query-level
fragility** — complementing pipeline-level AIRS. No new runs, no spend.
**Effort: 8 h** for a defensible module + tests + write-up.

**F-C3 (serious) — n = 3–4 replications is thin and the docs know it.** Not
fixable within budget. Handle it in threats-to-validity, not by running more.

**F-C4 (polish) — no multiple-comparison correction** across the 8 interaction
pairs. Report Holm-adjusted intervals or state explicitly that the analysis is
exploratory. 1 h.

## D. Generalization

Better than the brief assumes: **four models already run** — gpt-4o-mini,
claude-haiku-4-5, llama3.1:8b, qwen2.5:14b — with the ranking transferring
(mean τ +0.778) and both open-weight models flooring on classification, which is
honestly reported. Two task domains (e-commerce retrieval, aviation
classification). Two "pipeline archetypes."

Ranked by evidence gained per hour:

1. **Second agent *topology* (multi-step) — the only real gap.** ~30 h + ~$1.50.
   This is the answer to "in what sense is this agentic?" See Phase 4; it is a
   *should-have*, not a must-have, and it is the first thing to cut if week-4
   checkpoint slips.
2. Third task family — **not worth it.** ~25 h for a third point on a line already
   established as inverting.
3. Fifth model — **not worth it.** Diminishing returns; four are already run.

**F-D1 (FATAL, and it is a framing problem not a science problem) — "pipeline
architecture" is two constants.** `runner/execute.py:67-68`:

```python
BATCH_INHERENT_STALENESS_S     = 3.0
STREAMING_INHERENT_STALENESS_S = 0.05
```

That is the entire difference between the "batch pipeline" and the "streaming
pipeline." Meanwhile the repo ships a 6-service `docker-compose.yml`, a Kafka
setup, `pipelines/streaming.py` (imported by nothing), and
`pipelines/airflow_dags/batch_load_dag.py` (executed by nothing).

As *science* this is defensible and arguably correct: it isolates the one
variable that reaches the agent, and a real Kafka would add noise without
adding signal. **As presentation it is a trap.** An examiner who greps for
`kafka` in the experiment path gets zero hits, and the credibility of every
other number drops with it. Compounding it, `CLAUDE.md` invariant 7 says *"Postgres
`benchmark_runs` is the canonical dataset"* — **nothing in the repo ever writes
to Postgres.** The canonical dataset is 302 JSON files.

**Fix by subtraction and honesty, not by building Kafka.** ~6 h: rename the
factor to `staleness_regime` or state in Ch. 3 §1 that pipeline archetypes are
*simulated as their inherent-staleness signature, deliberately*; move
`docker/`, `streaming.py` and the Airflow DAG under `infra_unused/` with a
README saying they are scaffolding retained from the original plan and not used
in any result; and rewrite invariant 7 to say JSON artifacts are canonical.
**Do not build the real pipeline. It buys no science and costs 40 h.**

## E. Reproducibility and artifact quality

| Requirement | State |
|---|---|
| Raw results committed | **Yes** — 302 artifacts, 6.3 MB. Better than most published work. |
| Analyses re-run at $0 | **Yes**, no API key needed. Genuinely strong. |
| Seeded determinism | **Yes**, with seed-block provenance per arm. |
| LICENSE | Yes (MIT). |
| One-command reproduction | **No.** `make test`, `make grid` exist; there is no `make reproduce` that regenerates every published number. |
| **Pinned dependencies** | **No lockfile. `dependencies = []`** — the core package declares nothing; everything is in extras, unpinned to majors. A fresh clone in 2027 will not reproduce. |
| **Figure regeneration** | **No figures exist, and no plotting code exists anywhere.** |
| CITATION.cff / DOI | **Neither.** |
| Artifact README | Good, but claims things that are not true (see F-E2). |

**F-E1 (serious) — there are zero figures in the entire repository.**
`find` for `*.png|*.pdf|*.svg` returns nothing; `grep` for `matplotlib|savefig|plt.`
returns nothing. Every result is an ASCII table in terminal output. **Chapter 4 cannot be written without figures**, and they are equally required
on a projector at the defence. Minimum viable set: (1) freshness sweep — exposure × conditional
rate; (2) flip partition — raw vs residual by fault; (3) AIRS vs silent-failure
rate at run level with the held-out ρ; (4) ROC: AIRS vs agent confidence, the
0.501 slide; (5) gate coverage/residual trade-off curve; (6) interaction —
observed vs additive prediction; (7) the F-B1 sensitivity table as a tornado
plot. **Effort: 12 h** including a `make figures` target. Do this early — building figures is also the most reliable way to surface
errors in one's own results.

**F-E2 (resolved 2026-09-13) — the documented CI had never run, and was wrong
anyway.** `CLAUDE.md` claimed *"must stay green — CI runs it on every commit"*.
The workflow had executed **once**, on `a20f6b2`, failing in 3 s to an
account-level billing lock. That failure masked a second defect: the job
installed `.[dev]` (pytest + ruff only) while `tests/test_airs_calibration.py`
imports numpy at module scope, so collection would have died before a single
test ran. The workflow had therefore never been capable of passing.

**Reassessed:** filing this under must-have was an aesthetic judgement — a red
badge looks bad — presented as a rigour one. With a single developer, no pull
requests, and 350 local tests in 22 s, the only thing CI offered that local
testing cannot is proof the project installs and passes on a machine that is
not the author's. That benefit is obtainable without GitHub.

**Resolved by** deleting `.github/workflows/` and adding `make ci`, which builds
a throwaway venv, installs only what `pyproject.toml` declares, and runs lint
plus the full suite. It immediately earned its keep — see F-E6.

**F-E6 (serious, found and fixed by `make ci` on 2026-09-13) — the package
under-declared its own dependencies.** `agents/llm.py` imports
`langchain_anthropic` for every `claude-*` model, and **no extra declared it**:
the Haiku cross-model arm could not be reproduced from a clean install. Seven
tests failed on a clean venv while passing in the developer's. Also corrected:
`langgraph` was declared and never imported, `scikit-learn` sat in `agents`
rather than `analysis`, and `streamlit` was still declared for a demo rebuilt in
Next.js six weeks earlier. This is exactly the class of defect that makes an
artifact irreproducible a year later, and it was invisible to `make test`.

**F-E3 (serious) — no lockfile.** Add `requirements-lock.txt` from the working
venv. **Effort: 1 h.** Without it the artifact is not reproducible and an
artifact-evaluation reviewer fails it on that alone.

**F-E4 (polish) — stale dependency declarations.** `pyproject.toml` declares
`streamlit` for a demo that is Next.js, and `langgraph`, which is imported
nowhere. 0.5 h.

**F-E5 (polish) — no DOI.** A Zenodo release takes 30 min and gives a citable
artifact. Do it the week of submission, not before.

## F. Engineering quality

Genuinely good, and unusually well-targeted: the tests that exist mostly protect
the *claims*, not the code.

**Tests that protect the thesis** — keep and cite in Ch. 3:
`test_dimension_independence.py` (invariant 5 — without it RQ2/RQ4 go
collinear); `test_paired_design.py`; `test_freshness_accounting.py` (pins the
double-count bug that would have halved every freshness score);
`test_interaction_arm.py::test_composition_preserves_solo_marginals`;
`test_gate.py::test_controller_and_replay_agree` (two implementations, one
publishes the numbers); `test_interaction_analysis.py::test_estimator_recovers_a_planted_interaction`
(a real positive control for the statistic).

**Busywork** — `test_policy_round_trips`, most of `test_policy_rejects_nonsense`.
Harmless, but they are not evidence of rigour and should not be cited as such.

**F-F1 (serious) — no test pins the AIRS scoring curves.** The most
consequence-bearing constants in the thesis (`DEFAULT_FRESHNESS_TARGET_S`,
`DEFAULT_LATENCY_TARGET_MS`) have no test asserting their values or documenting
their provenance. A silent edit changes every published number and 350 tests
stay green. **Effort: 1 h**, and it pairs with F-B1.

**F-F2 (polish)** — no type checking (`mypy`/`pyright` absent). Not worth hours
before a defence.

## G. Threats to validity — the section the thesis needs

**Construct.** (i) The AIRS composite is one parameterisation among many; weights
are fitted *conditional on* hand-chosen sub-score transforms whose sensitivity is
reported in [the new sensitivity doc] — freshness weight varies 10.5–22.9% and
classification's top dimension flips under a 5 s target. (ii) Latency is a
two-level factor in analytic mode and cannot, by construction, affect what the
agent reads; its null weight is a property of the design, not a finding about
latency. (iii) "Pipeline archetype" is operationalised solely as inherent
staleness; no Kafka or Airflow is exercised. (iv) Semantic stripping's
field-name opacity models schema-registry loss; whether real pipelines degrade
this way is unevidenced.

**Internal.** (i) One 80/20 split, seeded, un-cross-validated. (ii) Injector
realisations vary by condition by design; fault realisation is confounded with
condition within a replication in the main factorial (the interaction arm fixes
this, the main one does not). (iii) Ground truth for retrieval is derived from
the same time machine that serves stale values — a bug there would be invisible
to every analysis (mitigated by `Replayer` raising on divergence).

**External.** (i) Synthetic faults, injected by the experimenter, in-distribution
to their own generator. (ii) Two task families, one catalog, one flight dataset.
(iii) Single-call agents; nothing about multi-step orchestration follows. (iv)
n = 3–4 replications; intervals are wide. (v) Prices and models of 2026.

**Conclusion.** (i) Decision-level AUCs (0.56–0.69) are bounded by a
run-constant predictor and should not be read as decision-level discrimination.
(ii) No multiple-comparison correction across the 8 interaction contrasts.
(iii) "Additive" under this n means "no interaction large enough to detect."
(iv) The ~75% agent-intrinsic floor is estimated from 8 fault-free pipelines
whose individual rates span 6.4–23.8%.

---

# Phase 2 — The twelve kill questions

Ordered by probability of being asked.

**1. "Where does the number 1.0 second come from?"** — *Cannot answer today.*
Needs F-B1. After it: *"It is a target, not a threshold, and here is the table
showing which conclusions depend on it — consistency's dominance and latency's
null do not; freshness's magnitude does."*

**2. "You show me Kafka and Airflow in the repo. Which experiment used them?"**
— *Cannot answer today.* Needs F-D1. After: *"None, deliberately — archetypes
are simulated as their staleness signature; the unused scaffolding is quarantined
under `infra_unused/`."*

**3. "In what sense is this agentic? It's one API call."** — *Partially.* Today:
*"The pipeline is the subject, the agent the instrument, held constant by
invariant 1."* — is honest, and it is also a deflection. Only a multi-step arm
converts it into an answer.

**4. "How is AIRS different from ISO/IEC 25012?"** — *Cannot answer today.*
Needs F-A1. 4 h fixes it permanently.

**5. "Your agent's confidence is at chance — is that not just a bad model?"** —
*Can answer.* Four models, ranking transfers, τ +0.778.

**6. "Is AIRS predictive out of sample?"** — *Can answer well.* Run-level
held-out ρ −0.75 to −0.88, split by run not decision, DeLong vs confidence.
One of the strongest points available.

**7. "You conclude enforcement works. What does it cost?"** — *Can answer
unusually well.* 7–21 correct answers per silent failure prevented; ~75%
agent-intrinsic. An engineering answer rather than a student one, and the
repository already supports it in full.

**8. "Why should I believe staleness doesn't hurt, when accuracy clearly drops?"**
— *Can answer.* The flip partition, three independent ways. This is the
strongest material in the thesis and also the subtlest; it needs rehearsing
rather than improvising.

**9. "Show me the results."** — *Cannot answer today.* No figures exist (F-E1).

**10. "What happens when two things break at once?"** — *Can answer as of
2026-09-10*, once written up: sub-additive, 5 of 8 pairs, latency control
ψ = 0.00.

**11. "Could someone else install and run this?"** — *Can answer as of
2026-09-13.* `make ci` verifies a clean-venv install from the declared extras.
It found that `langchain-anthropic` was never declared (F-E6).

**12. "Could I reproduce this next year?"** — *Half.* Artifacts and analyses
yes; environment no (F-E3).

---

# Phase 3 — The product

> **Revised 2026-09-12 after the author's framing correction:** this is not a
> defence prop. It is a tool a data engineer could use on their own pipeline,
> which happens to also be shown at a defence. Offline operation is a *property*
> of the product, not a fallback for a flaky venue.

## The insight that makes this a real product

`airs probe` and `airs gate` are **pure arithmetic over telemetry**. No model
call, no API key, no ground truth, no network (`src/airsbench/probe.py`,
`src/airsbench/gate/`). A user can therefore score their own pipeline with
nothing but a sample of records — and get a result that is deterministic,
private, and instant.

That is the product. Everything else is evidence that the number means something.

## Tech choice, argued

**Ship a Python package with a bundled web console: `pip install airs-bench`,
then `airs serve` opens `localhost:8000`.**

- **FastAPI backend, Next.js frontend, static-exported and served by FastAPI.**
  One process, one command, no separate deployment.
- **Why a backend at all:** the scoring logic must not be reimplemented in
  TypeScript. The repo already learned this lesson — `test_gate.py::test_controller_and_replay_agree`
  exists precisely because two implementations of one rule drift apart. A JS
  port of `probe.measure` would be the same mistake with no test to catch it.
- **Why `pip install` is the right distribution:** the users are data engineers.
  They have Python. They do not want to deploy a web app to try a metric. A
  local tool that never sends their data anywhere is a *feature* for anyone
  whose pipeline carries customer records.
- **Why Next.js and not Streamlit:** 833 LOC already exist and build; Streamlit
  cannot express the trace view or the report; and Streamlit's re-run model
  fights the live stream. Rewriting is ~20 h to go backwards.
- **Why not a hosted SaaS:** it would mean handling other people's production
  data. Out of scope for a thesis, and a liability.

**Defence path:** the same `airs serve` running locally. Plus a static export on
a USB stick and a Vercel URL for Mode B only, and a 3-minute recording. Four
independent paths, none of which is the product's primary mode.

## Three modes

### Mode A — "Score my pipeline" *(the product)*

The default screen. A user arrives with a JSONL sample of records as their
pipeline delivers them, and optionally the same records upstream.

1. **Input.** Drop two files, paste JSON, or point at a directory. A
   *"generate a sample from my pipeline"* snippet is shown for the three common
   cases (Kafka consumer, Postgres query, Parquet read) — ~15 lines each. This
   is the adoption barrier and it is worth solving properly.
2. **Score.** Per-dimension bars with the evidence string beneath each
   (*"mean age 6.50 s over 60 of 60 records"*), composite, band, and an explicit
   **weight-coverage warning** when a dimension could not be measured. The
   refusal to score an unmeasured dimension as 100 is the most trustworthy thing
   about the tool — surface it, don't bury it.
3. **Task profile.** The user picks retrieval-like or classification-like. The
   weights invert, and the tool says so out loud rather than silently applying
   one.
4. **Recommended policy.** Generated from the calibration + attribution: *"For a
   retrieval-like task, gate on consistency ≥ 90 first — it carries 70% of the
   weight and is the cheapest gate measured at 7.0 correct answers per silent
   failure prevented. A staleness budget would cost you 17.7 for the same task."*
5. **Predicted cost.** The exchange rate they should expect, with the honest
   caveat that ~75% of silent failure is agent-intrinsic and no gate reaches it.
6. **Export.** One-page report, print-to-PDF.

This mode needs **no LLM and no internet**, and it is the reason someone would
install the tool twice.

### Mode B — "Why should I believe this?" *(the evidence)*

An interactive walkthrough over the 302 committed runs. This is where the
defence experience lives, and it doubles as the thing that convinces a sceptical
engineer the score is not numerology. The sequence:

1. Run the pipeline clean. Baseline accuracy.
2. Drag staleness to 5 s. Accuracy falls. Obvious.
3. **The trap:** confidence is unchanged. The user is invited to pick which
   answers are wrong. **They fail.** That is AUC 0.501, experienced rather than
   asserted, and it is worth more than any chart.
4. Turn the gate on. Silent failures caught. Relief.
5. **The bill:** the exchange-rate meter shows 7–21 correct answers destroyed
   per silent failure prevented. No setting wins.
6. **The inversion:** switch to the staleness policy on retrieval — catches
   almost nothing, still costs. Task-dependence, felt.

### Mode C — "Watch it live" *(optional)*

Real `gpt-4o-mini` calls against a live-degrading stream. Costs ~$0.06 per
15-minute session, hard-capped, requires a key. **Genuinely optional.** Build
only if Milestone 1 lands early.

## The trace view — what makes it a research tool

On any decision, expand to a three-column diff:

```
  upstream held          pipeline delivered       agent answered
  price: 24.99           price: 24.99             "B07X — $24.99"
  stock: 4               stock: 0    ← corrupted   truth: B09K
                                                   ✗ SILENT FAILURE
  AIRS at this moment: fresh 19.8 · lat 100 · cons 74.6 · sem 100
  Classification: ANSWER-KEY MOVED (not agent impairment)
```

That last line is the flip partition made operational, and nothing else in this
space can produce it.

## Data contract

One message shape, identical across all three modes, so the UI never branches:

```
Tick { t, config{fault,severity,pipeline,task},
       airs{freshness,latency,consistency,semantic,total,covered},
       record{id, upstream{}, delivered{}, corrupted_fields[]},
       decision{answer, truth, correct, abstained, confidence, flipped},
       gate{admitted, violations[], reason},
       running{n, correct, silent, prevented, forfeited, exchange_rate} }
```

Mode A emits one `Tick` per batch with `decision` null. Mode B replays a
pre-baked array. Mode C streams over a WebSocket.

## Build cost

| Component | h |
|---|---|
| FastAPI backend: `/score`, `/policy`, `/replay`, static serving, `airs serve` entry point | 12 |
| **Mode A** — input, scoring, policy recommendation, cost prediction | 16 |
| **Mode B** — the six-step walkthrough + trace view | 20 |
| Report export (printable one-pager) | 6 |
| Packaging: bundled demo data, README, `pip install` path, offline verification | 6 |
| **Subtotal (Modes A+B, shippable product)** | **60** |
| Mode C live stream — WebSocket, spend cap, key handling | 12 |

---

# Phase 4 — The revised plan

**Recalculated 2026-09-12 against the author's real timeline.**
~240 h at 20 h/week, split by two hard milestones:

- **M1 — Fri 2026-10-16 (hard):** internship ends. Product running, results
  collected, supervisor presentation.
- **M2 — early Dec 2026:** thesis submitted and defended.

Implementation capacity ends ~Fri 2026-11-06. November is writing.

**Standing rule for October, per the author's instruction:** every analysis
touched between now and mid-October must emit **the figure and the table
Chapter 4 will use**, at the time it is touched. Figures are not a task at the
end; they are the output format of the work. A finding without its figure is not
done.

## Stage 1 — Survival (wk 1: Sep 14–18, 20 h)

Nothing else starts until these land. They remove two of the three kill
questions that are currently unanswerable.

| Item | h |
|---|---|
| **AIRS curve sensitivity** (F-B1) — module, test pinning the constants (F-F1), findings doc, **tornado figure** | 8 |
| **RQ6 write-up** (F-C1) — `interaction_findings.md`, README/status correction, **observed-vs-additive figure** | 4 |
| **Infrastructure honesty** (F-D1) — `infra_unused/` + README, rewrite invariant 7, rename the pipeline factor in docs | 6 |
| **Lockfile, CI billing, stale deps** (F-E2/3/4) | 2 |

## Stage 2 — Evidence and figures (wk 2: Sep 21–25, 20 h)

| Item | h |
|---|---|
| **Query-level fragility** (F-C2) — module, tests, findings doc, overlap figure. New construct; explains saturation *and* the 75% floor | 10 |
| **`make figures`** — the remaining Ch. 4 set: freshness sweep decomposition, flip partition, AIRS-vs-failure with held-out ρ, the 0.501 ROC, gate trade-off curve | 10 |

**End of wk 2: Chapter 4's entire figure set exists.** That is the point.

## Stage 3 — The product (wk 3–5: Sep 28 – Oct 16, 60 h)

Modes A + B + report + packaging, per Phase 3. Ends at **Milestone 1**.

| Week | Focus | h |
|---|---|---|
| wk 3 | FastAPI backend, `airs serve`, Mode A input + scoring | 20 |
| wk 4 | Mode A policy recommendation + cost prediction; report export | 20 |
| wk 5 | Mode B walkthrough + trace view; packaging; **supervisor presentation** | 20 |

## Stage 4 — The refetch arm (wk 6–7: Oct 19–30, 40 h)

**Decision on the multi-step arm: keep it, but reshape it.** A generic 2-hop
agent is 30 h that answers only "is this agentic?". The same hours buy far more
as a **refetch arm**, which answers three things at once:

> Give the agent a `refetch(record_id)` tool. Does the ability to *act* on
> suspicion succeed where *being told* the age failed (the detectability null)?

- It is genuinely multi-step — decide → refetch → decide — so it answers the
  "agentic" question by construction.
- It directly extends the detectability null, which is currently a dead end in
  the narrative. Metadata didn't work; does an action?
- It gives the **gate a third verdict — refuse / refetch / admit** — and each has
  its own exchange rate. The 7–21 figure becomes a menu, which is exactly what
  the product needs.
- It reuses the existing task, data, scoring and agent scaffolding.

| Item | h | $ |
|---|---|---|
| Refetch tool + 2-step agent loop + arm design doc | 14 | — |
| Dry-run, execute (~36 runs), analyse, **figures** | 12 | ~$1.50 |
| Third gate action + replay pricing | 10 | — |
| Write-up | 4 | — |

**Hard cut date: Fri 2026-10-30.** If the runs are not executed by then, cut the
arm entirely and keep the hours. It must not touch November.

## Stage 5 — Integration and freeze (wk 8: Nov 2–6, 20 h)

| Item | h |
|---|---|
| Integrate refetch results into the product; Mode C live stream *if* ahead | 8 |
| Positioning: ISO/IEC 25012, data contracts, agent benchmarks (F-A1) | 4 |
| Full-text read of the four load-bearing papers (F-A2) | 8 |

**Fri 2026-11-06: implementation freezes.** No new features after this date.

## Stage 6 — The thesis document (wk 9–12: Nov 9 – Dec 4, 80 h)

Written together. Real budget, as requested:

| Chapter | h | Starting material |
|---|---|---|
| **Ch. 1 Introduction** | 10 | `research_plan_original.md` Ch. 1–2; needs 2026 framing and the contribution stated in one sentence |
| **Ch. 2 Literature review** | 16 | `literature_review.md` is strong raw material; needs chapter prose + ISO 25012 + data contracts + agent-benchmark precedent |
| **Ch. 3 Methodology** | 12 | `chapter3_methodology.md` drafted (5.3 k words); needs gate, probe, interaction arm, sensitivity analysis, and the honest simulation framing |
| **Ch. 4 Results** | 20 | Eight findings docs + **every figure already built in October**. This is assembly and prose, not analysis. |
| **Ch. 5 Discussion & conclusion** | 12 | The restated recommendation, threats to validity (Phase 1G), future work |
| Front/back matter, template formatting, reference verification | 10 | Citation hygiene rule in `CLAUDE.md` applies — every source verified |

**Buffer: Dec 7 onward** — defence rehearsal, slides, the product demo run cold.

## Cut list — and why each is hard to let go

- **A real Kafka/Airflow pipeline.** 40 h, zero new science. The unused
  `docker-compose.yml` looks like proof of data-engineering depth and currently
  demonstrates the opposite, because nothing executes it. Quarantine it
  (Stage 1).
- **The leading-indicator / AIRS-drift arm.** 20 h, needs a time-series design
  that does not exist here, and answers a question the RQs never asked. **Cut.**
- **A third task domain or fifth model.** 25 h for a third point on an
  established line. **Cut.**
- **`airs lint`.** "First to cut" for two months. **Formally cut** so it stops
  occupying planning space.
- **A generic multi-step agent.** Superseded by the refetch arm, which costs the
  same and answers more.
- **Rewriting the demo in Streamlit.** 20 h to go backwards.
- **Hosting the product as a SaaS.** It would mean handling other people's
  production data. Out of scope, and a liability.

## Checkpoints

| Date | Gate | If missed |
|---|---|---|
| **Fri 2026-09-18** | Stage 1 complete | Stop everything else. These are survival. |
| **Fri 2026-09-25** | Chapter 4's full figure set exists | Drop the refetch arm now, not in October. |
| **Fri 2026-10-09** | Mode A works end to end on a user's own JSONL | Cut Mode B to a static explainer; the product ships without the walkthrough. |
| **Fri 2026-10-16** | **MILESTONE 1** — `airs serve` runs, supervisor sees it | Non-negotiable; internship ends. |
| **Fri 2026-10-30** | Refetch runs executed | **Hard cut the arm.** Keep the hours. |
| **Fri 2026-11-06** | Implementation freeze | Freeze regardless of state. |
| **Fri 2026-11-27** | Ch. 1–4 drafted | Drop Ch. 5 depth; prioritise a complete document over a deep one. |
| **early Dec** | **MILESTONE 2** — submission | — |

## Risk register

| Risk | P | Impact | Mitigation |
|---|---|---|---|
| **Writing slips into December** | **High** | **Fatal** | 80 h budgeted, figures pre-built in October, hard freeze Nov 6. The wk-12 checkpoint drops Ch. 5 depth rather than shipping an incomplete document. |
| Product scope creeps past Milestone 1 | **High** | High | Mode C is explicitly optional; Mode B degrades to a static explainer at the Oct 9 checkpoint. |
| Refetch arm over-runs or returns a broken design | Med | Med | Hard cut Oct 30. It is Stage 4 precisely so its failure costs nothing downstream. |
| Sensitivity analysis undermines a headline | Med | Low | Already measured: retrieval and latency survive; freshness magnitude and the classification ordering get softened. Found now, not at the defence. |
| Budget exhausted | Low | Med | $4.58 left, refetch needs ~$1.50, dry-run mandatory. |
| Thesis template arrives late and forces reformatting | Med | Med | Write in Markdown, convert at the end. Do not author in the template. |
| Laptop sleeps mid-run | Med | Low | Known; `--offset` resume. Happened 2026-08-17. |
