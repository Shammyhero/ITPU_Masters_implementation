# Week-by-week plan — internship implementation and thesis document

**Author:** Shamsiddin Khamidov · **Written:** 2026-09-12 · **Revised 2026-09-14:
the Analyst adopted** (`docs/analyst_brief.md`) — everything from "Part 1b" on is
new. **Supersedes** the roadmap in `campaign_status.md`.

**Capacity:** 20 h/week, 14 weeks, **~260 h total.**
**Evidence base for this plan:** `REVIEW.md` (adversarial audit, 2026-09-12) and the
Analyst brief as corrected on 14 Sep.

## Two hard milestones

| | Date | What must be true |
|---|---|---|
| **M1** | **Fri 16 Oct 2026** | Internship ends. On the supervisor's screen, `airs serve` runs **the Analyst**: a question against the bundled source, gated, answered by a free local model or a keyed hosted one, verified against upstream and attributed. **Fig 4.10** (verifier agreement) exists, and so does every corpus figure (4.1–4.8, 3.1). The refetch arm and the live case study follow M1, as the refetch arm always did. |
| **M2** | **Fri 04 Dec 2026** | Thesis document submitted. |

Implementation **freezes Fri 06 Nov**. November is writing. December is defence.

## Rules that govern every week below

1. **Every analysis emits its Chapter 4 figure the day it is written.** A
   finding without its figure is not done. This is why Chapter 4 costs 20 h in
   November instead of 50 h.
2. **No paid run without `--dry-run` first.** $4.58 OpenAI / $1.27 Anthropic
   remain. Every paid path takes a spend cap enforced before the call.
3. **Write in Markdown, convert to the template at the end.** Do not author
   inside the institutional template — it will arrive late and reformatting
   costs days.
4. **The verifier before the interface.** No Analyst UI work starts until the
   verifier reproduces the corpus exactly (A4). If it does not, the UI is a chat box.
5. **Keep every document current after each step** — this plan's progress notes,
   `docs/handoff/`, README, CLAUDE.md, findings docs — in that step's commit.

## Budget summary

| Stage | When | Hours | API cost | State |
|---|---|---|---|---|
| Survival fixes | W1 | 20 | $0 | **done** |
| Evidence, figures & power | W2 | 21 | $0 | **done** |
| F-C7 small-cluster correction | 13 Sep | ~3.5 | $0 | **done** |
| Product core — CLI, API, console, packaging | W3 | 20 | $0 | **done 14 Sep** |
| **The Analyst A1–A9** | 14 Sep → 23 Oct | 101 | ~$0.40 (development calls; estimate) | |
| Adapters A10 · live case study A11 | 19 Oct → 6 Nov | 14 | ~$0.05 | |
| Refetch arm, two conditions | 19 → 30 Oct | 28 | ~$2.20 | |
| M1 presentation | 16 Oct | 2 | $0 | |
| Positioning, papers, DOI | 2 → 6 Nov | 14 | $0 | |
| Thesis document | W9–W12 | 80 | $0 | |
| Defence | W13–W14 | 20 | $0 | |
| **Total** | | **~324** | **~$2.65** | |

**The honest arithmetic.** From Mon 14 Sep to the freeze on Fri 6 Nov is eight weeks,
~160 h. The work scheduled into that window is **159 h — no buffer.** The author chose
(14 Sep) to keep everything that makes the product better rather than pre-cut. The
buffer is the pace: W1–W3 ran far under their estimates. If a checkpoint below is
missed, cut in this order and no other: **A10 adapters → A11 case study → A9 report →
A2 manifest inference (committed manifests only) → A8 semantic toggle.** Never cut:
A3 verifier, A4 agreement, A6 loop (shared with the arm), the quarantine and credential
tests. The writing budget in November is not a source of hours.

---

# Part 1 — Internship (W1–W8, Mon 14 Sep – Fri 06 Nov)

## W1 · Mon 14 – Fri 18 Sep · Survival fixes · 20 h · $0

> **Progress 13 Sep:** sensitivity analysis, its test suite, its figure and the
> downstream claim corrections are done (rows 1–3). CI removed in favour of
> `make ci`, which found an undeclared `langchain-anthropic` dependency.
> RQ6 written up (`interaction_findings.md`, Fig. 4.6): faults saturate, never
> compound — 5 of 8 pairs sub-additive. README and arm status corrected.
> Infrastructure quarantined to `infra_unused/` with a README; compose
> validated from its new location; invariant 7 rewritten (JSON artifacts are
> canonical, not Postgres); Chapter 3 now describes the archetypes as
> simulated and no longer claims CI or containers. Silent failure unified to one
> threshold-free definition, and the 0.5–0.9 sensitivity check the methodology
> promised — but never ran — implemented. Lockfile pinned (`make lock`, 99
> packages) and verified in a clean environment: `pip check` clean, versions
> identical to the results environment, 382 tests green. **W1 complete.**

| Task | h | Output |
|---|---|---|
| **AIRS curve sensitivity analysis** — `analysis/curve_sensitivity.py`, refit weights under 7 target/shape variants | 5 | `docs/sensitivity_findings.md` + **Fig. 4.7 tornado plot** |
| Test pinning `DEFAULT_FRESHNESS_TARGET_S` / `DEFAULT_LATENCY_TARGET_MS` and their provenance | 1 | `tests/test_airs_curves.py` |
| Rewrite the AIRS claims that the sensitivity table breaks — freshness magnitude, classification ordering | 2 | edits to 3 findings docs |
| **RQ6 write-up** — the interaction arm completed 10 Sep and is unclaimed | 3 | `docs/interaction_findings.md` + **Fig. 4.6 observed-vs-additive** |
| Fix `README.md` ("half-run") and `campaign_status.md` | 1 | — |
| **Infrastructure honesty** — move `docker/`, `pipelines/streaming.py`, `airflow_dags/` to `infra_unused/` with a README | 3 | quarantine + README |
| Rewrite `CLAUDE.md` invariant 7 (Postgres is *not* canonical; JSON artifacts are) and rename the pipeline factor in docs | 3 | — |
| Lockfile; `make ci` clean-install verification; fix under-declared deps (`langchain-anthropic` was missing entirely) | 2 | `requirements-lock.txt`, `make ci` green |

## W2 · Mon 21 – Fri 25 Sep · Evidence, figures & power · 21 h · $0

> **Progress W2:** fragility analysis done (Fig. 4.8) — silent failure concentrates
> 12–16× beyond the null and is near-deterministic on re-ask. Power analysis done
> (Fig. 3.1) — clustering negligible, but the cell-level test is anti-conservative
> (α ≈ 0.12, REVIEW F-C7 — resolved 13 Sep, see W3). Figures 4.1–4.5 built, every
> published value reproduced. Figure 4.2's printed cross-check exposed a published
> RQ2 table mixing two populations (REVIEW F-C8); corrected in
> `flip_partition_findings.md` §6 and Chapter 3, which also lost two false
> mixed-effects claims. **W2 gate met** ahead of schedule.

| Task | h | Output |
|---|---|---|
| **Query-level fragility** — module + tests + write-up | 10 | `analysis/fragility.py`, `docs/fragility_findings.md` + **Fig. 4.8** |
| Remaining Chapter 4 figures — 4.6 and 4.7 were built in W1 | 6 | **Figs. 4.1–4.5** |
| **Simulation-based power analysis** (REVIEW F-C6) | 5 | `analysis/power.py`, Ch. 3 table, RQs v2 §6 rewritten |

**The Chapter 4 figure set:**

| Fig | Content | Source | State |
|---|---|---|---|
| 3.1 | Power under clustering (CR2-corrected) | `power.py` | built |
| 4.1 | Freshness sweep — exposure × conditional rate | `freshness_sweep.py` | built |
| 4.2 | Flip partition — raw vs residual impairment by fault | `flip_partition.py` | built |
| 4.3 | AIRS vs silent-failure rate, run level, held-out ρ | `airs_calibration.py` | built |
| 4.4 | **ROC: AIRS vs agent confidence (AUC 0.501)** — the headline slide | `airs_calibration.py` | built |
| 4.5 | Gate coverage vs residual trade-off curve | `gate/replay.py` | built |
| 4.6 | Interaction — observed vs additive prediction | `interaction.py` | built |
| 4.7 | AIRS curve sensitivity tornado | `curve_sensitivity.py` | built |
| 4.8 | Query fragility — overlap vs chance | `fragility.py` | built |
| 4.9 | Refetch arm — agent-initiated vs gate-initiated vs none | refetch analysis | Oct |
| **4.10** | **Verifier agreement — the live verifier reproduces the corpus** | A4 | **by 2 Oct** |
| 4.11 | Live-source case study — lag, attribution split, AIRS ranking | A11 | Nov |

## W3 · Mon 28 Sep – Fri 02 Oct · Product: backend + Mode A core · 20 h · $0

> **Pre-work 13 Sep (W2's slack, ~3.5 h, $0): REVIEW F-C7 resolved.** Cell and
> pooled comparisons now use CR2 errors with Bell–McCaffrey df (α 0.045–0.058,
> was 0.11–0.12); three cell results lose significance and cell MDEs rise to
> 10–12 pp. Decision-model p-values are calibrated by simulation
> (`analysis/pvalue_calibration.py`); every published significant coefficient
> survives. Fig. 3.1 regenerated.
> **Product design approved 13 Sep:** FastAPI `/api/{meta,samples,score,gate,replay}`;
> `airs` console script (`serve`, `probe`, `gate`); the static Next.js export built
> into package data by `make web`, verified from a non-editable wheel by
> `make dist-check`; fastapi and uvicorn as core dependencies, with `probe` and `gate`
> import-isolated from them; the Tick contract's `airs` block extended to
> `{score | null, detail, weight}` plus band, in all modes; local files reach the
> tool only through CLI flags, never an HTTP path parameter.
>
> **Progress 14 Sep — W3 complete, two weeks ahead of its dates.** Six steps, each
> committed and pushed: **(1)** the `airs` console script, and a wheel that ships its
> calibrated weights — a built wheel had not — verified by the new `make dist-check`;
> **(2)** input hardening: one validator for every caller, line-numbered refusals that
> name the fix, ISO-8601 timestamps with a timezone, millisecond and
> duplicate-upstream-id guards, no NaN in JSON output; **(3)** `airs serve`: FastAPI
> `/api/{meta,samples,score,gate}`, loopback with a Host-header allowlist; **(4)**
> `/api/replay` over a baked corpus that reproduces `gate_findings.md` (19.6% /
> 14.2%); **(5)** Mode A in the browser — `/` scores through the API, the TypeScript
> scorer is deleted, `/evidence/` keeps the argument; **(6)** `make web` builds the
> console into the wheel, `aist.json` is regenerated from all 302 runs and committed,
> and `make dist-check` requires the installed `airs serve` to serve the console.
> 501 tests. Found and fixed on the way: an unanchored `data/` rule in `.gitignore`
> that kept `server/data/` and `aist.json` out of git.
> **Carried forward:** the task-profile switch, the recommended policy and the
> predicted exchange rate (raw sweep rate 2.26 vs attribution true cost 7.0 for
> consistency ≥ 90 on retrieval) → A9; the Kafka/Postgres/Parquet snippets → replaced
> by the A10 adapters; Starlette's test client warns to move from `httpx` to `httpx2`;
> the Browser pane cannot launch `airs serve` on this machine (macOS blocks the
> python.org interpreter from reading `~/Documents`), so browser checks need the API
> started from a terminal.

| Task | h |
|---|---|
| FastAPI backend: `/score`, `/policy`, `/replay`; serve the static Next.js build | 8 |
| `airs serve` console entry point; `pip install` path verified in a clean venv | 4 |
| **Mode A input** — drop/paste JSONL, validation errors that name the fix | 4 |
| **Mode A scoring view** — per-dimension bars, evidence strings, weight-coverage warning | 4 |

---

# Part 1b — The Analyst (adopted 14 Sep; replaces the old W4–W8)

**What it is** (`docs/analyst_brief.md`): live, AIRS-gated question answering over a
declared data source. On every question the tool samples what the pipeline delivers,
scores it with `probe`, routes it through the gate — **admit / refetch / refuse** —
lets a model answer from exactly those records with a structured answer plan, re-reads
the same records upstream, executes the plan on both reads, and attributes every wrong
answer: **answer key moved** (the pipeline), **agent impairment** (the model), or
**both**. It is the flip partition running live, and it is what the thesis offers as
external validity.

**What it replaces:** Mode A's paste box as the headline input (paste stays as an
inline source); Mode B's planned six-step walkthrough (replay becomes a feed into the
same renderer); Mode C (absorbed). **What it keeps:** every W3 property — no scoring rule
implemented twice, no file or connection opened on an HTTP request, one error shape,
the approved Tick extension.

**Author decisions of 14 Sep** (detail in the brief's header):
- **Sources are declared locally** — `sources.yaml` or CLI flags, credentials from
  environment variables; the console selects, tests and describes declared sources only.
- **The refetch arm has two conditions sharing one loop:** agent-initiated
  `refetch()` (the treatment; answers kill question 3) and gate-initiated refetch (prices
  the third gate verdict).
- **Two model options:** *Free* — any model already in the user's local Ollama,
  discovered from Ollama; *API key* — OpenAI, Anthropic or Google Gemini, model chosen
  from the provider, key from the environment or entered for the session (memory only).
- **W4's Mode A work is kept and redesigned into the Analyst** (A9).

**Corrections already made to the brief** (verified against the code): correctness is
tested against upstream before attribution; the semantic rule has two states (no
reviewed manifest → UNMEASURED; reviewed → the probe's rule, absent context = 0); the
semantic toggle applies the real stripping injector, opaque names included; no upstream
loses consistency and the verifier, not freshness; aggregates verify the same ids;
Fig 4.10 is retrieval-only and exact; live artifacts never enter `results/runs/`; the
plan-returning prompt is a different instrument and Chapter 3 says so.

## The stages

### A1 · Sources — protocol, `demo`, `files`, declaration · 12 h

`src/airsbench/sources/`: the four-method `Source` protocol (`sample`, `fetch`,
`describe`, `name`), `SourcePair(delivered, upstream | None, manifest)`, and a read-only
guarantee enforced at the adapter.
- **`demo`** — a bundled ESCI slice with its update stream (sized to keep the wheel
  small; the full `updates.jsonl` is 11 MB), serving delivered records at a configurable
  staleness through the existing catalog time machine. The fault chain is applied once,
  by the source (invariant 3). Built first; everything else is developed against it.
- **`files`** — CSV / Parquet / JSONL, a file or a directory, declared, never requested.
- **Declaration** — `airs serve --sources sources.yaml` (plus `--records/--source` kept
  as a shorthand); credentials only from environment variables named in the file.
- The console's paste box becomes the `inline` source, so the W3 path keeps working.
- Tests: protocol conformance per adapter; no adapter writes; a declared source with a
  missing environment variable is refused with the variable's name; no path, DSN or URL
  is accepted over HTTP.

### A2 · The semantic manifest · 8 h

`manifest.yaml` schema (field roles: id, measure, label, updated_at; unit; definition;
`checkable_questions`); loading a committed manifest with no model call; a review/approve
flow; **inference** — one costed model call proposing roles from `describe()`, each
field approved by the user. The two-state semantic rule: **no reviewed manifest →
semantic UNMEASURED**; a reviewed manifest renders context into the records and the
probe's existing rule scores it (fields left undescribed lower completeness; no context
at all = 0). Tests pin both states against the probe's own tests.
*Cut gate:* committed manifests only, inference dropped.

### A3 · The verifier and live attribution · 14 h · **non-negotiable**

`src/airsbench/analyst/verifier.py`: the answer-plan schema and the checkable question
types (`min_by`, `max_by`, `count_where`, `sum_where`, `lookup`, `top_k`), executed
deterministically in Python over the delivered read (t0) and the upstream read of **the
same ids** (t1). `RetrievalAgent.ground_truth` becomes the `min_by` case, generalised,
not replaced. Correctness against upstream first; then attribution —
`answer_key_moved`, `agent_impairment`, `both`, or none for abstained / parse-failed
answers. Silent failure is `runner/scoring.py::is_silent_failure`, imported. Built
against the `demo` source with **no frontend**: Ticks printed to stdout. Unverifiable
question types are answered and labelled unverified, never guessed at.

### A4 · Verifier agreement — Fig 4.10 · 6 h · **non-negotiable, immediately after A3**

Run the verifier over the retrieval runs of the main factorial and the freshness sweep:
it must reproduce, **exactly**, each decision's correctness, the published silent-failure
rates, and the flip-partition split (ANSWER KEY MOVED + BOTH = wrong on flipped queries;
AGENT IMPAIRMENT = wrong on unflipped). Classification has no computable answer and is
out of scope, stated. Output: `analysis/verifier_agreement.py`, **Fig 4.10**,
`docs/verifier_agreement_findings.md`, and a test. Any disagreement is a verifier bug
and stops UI work.

### A5 · Model options — free local, or your API key · 8 h

- **Free:** discover the models in the user's Ollama (`/api/tags`); none installed →
  the option explains how to get one, and scoring/replay still work.
- **API key:** OpenAI, Anthropic, **Google Gemini** — Gemini is new routing in
  `agents/llm.py` (new optional dependency, pricing, tests; a live smoke call only if a
  key is available). The model list comes from the provider; the key from the
  environment or the console, held in memory for the session, never persisted, logged,
  or put in a Tick, artifact or URL.
- **Spend caps in the request path:** per session and per day, enforced before each call,
  returning a typed refusal; `estimate=true` returns the projected cost with no call.
- **Trap to close:** `llm.py` prices any model absent from `PRICING` at $0 — safe while
  only Ollama models were absent. A hosted model without a price must be refused (or
  priced), never budgeted as free. Only `ollama/` is free.
- The console states where records go: "stays on this machine" (local) or "sent to
  <provider>" (hosted).

### A6 · Router and the shared two-step loop · 12 h · shared with the refetch arm

`src/airsbench/analyst/loop.py`, called by both the API and the batch runner: sample →
`probe.measure` → `Controller.evaluate(policy)` → **ADMIT** (answer) / **REFETCH**
(gate-initiated: `upstream.fetch` → re-score → answer) / **REFUSE** (no model call,
rule + observed value, $0). The same loop offers the agent a `refetch(record_id)` tool
for the arm's agent-initiated condition. Tool-call accounting, loop termination,
invariant 1 (the prompt never mentions faults), and the paired design preserved in batch
mode — tested.

### A7 · The Analyst API and the firewalls · 8 h

`GET /api/sources`, `POST /api/sources/{id}/test` (describe a *declared* source),
manifest propose/approve, `GET /api/models` (Ollama + configured providers),
`POST /api/session` (model, policy, caps), **`POST /api/ask`** streaming Ticks over SSE
(gate → answer → verification, in that order), `GET /api/session/{id}` (the meter),
`/api/replay` unchanged. Firewalls: live artifacts written to `~/.airs/sessions/`, never
`results/runs/`; arm `live`, seed block 100 000–110 000; `tests/test_live_quarantine.py`
(every analysis entry point excludes live runs); a credential test (no key or DSN pattern
in any Tick, artifact, log line or URL). One error shape throughout; connection failures
name the adapter and the fix.

### A8 · The conversation console · 18 h

Replaces the paste-first page as `/` (paste remains the `inline` source): **source picker**
(declared sources, test, `describe()`, the visible "no upstream" path and what it costs);
**manifest review** (unreviewed fields shown UNMEASURED live); **model choice** (free
local / API key); **conversation** (question, gate badge, streamed answer, then the
verifier resolving; confidence greyed with "AUC 0.501" beside it); the **trace panel**
(upstream / delivered / answered, changed fields, lag, AIRS at that moment, attribution);
the **meter** (answered, refused, refetched, correct, silent caught, forfeited, live
exchange rate); the **semantic toggle** (applies the real stripping injector). **Replay**
is a Tick feed from the corpus into the same renderer — Mode B without a bespoke UI.
`ScoreView` is kept. Styling stays `globals.css`, no component library.
*Cut gate:* drop the toggle, keep the trace.

### A9 · Mode A, redesigned into the Analyst · 15 h

- **Task-profile switch** (retrieval-like / classification-like), the weight inversion
  stated out loud where it changes the score (3 h).
- **Recommended policy** generated from the calibration + attribution table and the
  session's own measured AIRS; one click applies it to the router (6 h).
- **The meter's prior:** the predicted exchange rate from `/api/replay`, labelled raw
  sweep rate vs attribution true cost, with the ~75% agent-intrinsic floor stated; the
  live rate is shown against it as the session runs (inside the 6 h above + A8).
- **Printable readiness report:** AIRS, coverage, the policy, and the session's
  attribution split — one page, print-to-PDF (6 h). *Cut gate:* a print stylesheet only.

### A10 · `postgres`, `duckdb`/`sqlite`, `http` adapters · 8 h · cut first

Declared, read-only, each tested against a real instance (a local Postgres, a DuckDB
file, a local HTTP fixture). The README states the protocol is four methods and that
warehouses (Snowflake, BigQuery, Databricks) are not supported — nothing untested is
claimed.

### A11 · Live-source case study — Fig 4.11 · 6 h · ~$0.05 · cut second

One real source with genuine update velocity that is not ESCI or BTS, behind a real
caching or polling pipeline set up for the study (say so: the data and its velocity are
real; the pipeline's design is ours). 50–100 questions, one declared model, dry-run and
cap first. Report AIRS, the lag distribution, the attribution split, and whether AIRS
ranked the risky moments above the safe ones — a null is reportable.
`docs/live_case_study_findings.md` + **Fig 4.11**.

## The refetch arm — two conditions, one loop · 28 h · ~$2.20

Built on A6's loop. *Metadata did not make the agent cautious (the detectability null) —
does the ability to act on suspicion?*

| Task | h |
|---|---|
| Arm design doc — hypotheses for both conditions, conditions, seed block 90 000–100 000, quarantine | 4 |
| Batch-runner integration + tests: tool-call accounting, termination, paired design, invariant 1 | 4 |
| Dry-run, cost estimate (~54 runs), grid inspection | 2 |
| Execute (monitored; `--offset` resume if the laptop sleeps) | 4 |
| Analysis — agent-initiated vs gate-initiated vs no refetch — + **Fig 4.9** | 6 |
| Third gate verdict priced in `gate/replay.py` — refuse / refetch / admit, each with its exchange rate | 4 |
| `docs/refetch_findings.md` | 4 |

**► HARD CUT — Fri 30 Oct:** if the runs are not executed, cut the arm entirely. The
router's REFETCH stays in the product without an experimental claim behind it.

## Calendar — Mon 14 Sep to the freeze

| Week | Work | h |
|---|---|---|
| **14–18 Sep** | A1 sources (12) · A3 verifier, start (8) | 20 |
| **21–25 Sep** | A3 finish (6) · **A4 Fig 4.10** (6) · A2 manifest (8) | 20 |
| **28 Sep–2 Oct** | A5 model options (8) · A6 router + shared loop (12) | 20 |
| **5–9 Oct** | A7 API + firewalls (8) · A8 console, part 1 (12) | 20 |
| **12–16 Oct** | A8 part 2 (6) · A9, part 1 (12) · **M1 presentation** (2) | 20 |
| **19–23 Oct** | A9 part 2 (3) · refetch arm: design, integration, dry-run (10) · A10 adapters (7) | 20 |
| **26–30 Oct** | refetch arm: run, analysis + Fig 4.9, third verdict, write-up (18) · A10 finish (1) | 19 |
| **2–6 Nov** | A11 case study + Fig 4.11 (6) · positioning: ISO/IEC 25012, data contracts, agent benchmarks (4) · full-text read of the four load-bearing papers (8) · Zenodo DOI + `CITATION.cff` (2) | 20 |

### ► MILESTONE 1 — Fri 16 Oct 2026
Internship ends. `airs serve` runs the Analyst end to end on the bundled and `files`
sources, with both model options, gated, verified and attributed. Fig 4.10 exists.

### ► IMPLEMENTATION FREEZE — Fri 06 Nov 2026
No new features after this date, regardless of state.

## Acceptance criteria for the Analyst (as corrected)

1. `pip install .` (after `make web`) → `airs serve`, **with a local Ollama model and no
   key or network**: select the bundled source, approve its manifest, ask a question, see
   a verified answer with its attribution, at $0. With an API key instead: the same flow.
   With neither: scoring and replay.
2. Declared Postgres delivered/upstream tables (A10): same flow, real lag, real attribution.
3. The verifier reproduces the published retrieval silent-failure rates and flip-partition
   split exactly (Fig 4.10).
4. A refused batch names the rule and the observed value, with no model call and no cost.
5. `make ci`, `make dist-check`, the live-quarantine test and the credential test green.

---

# Part 2 — Thesis document (W9–W12, Mon 09 Nov – Fri 04 Dec, 80 h)

Written together. Markdown first, template conversion last.

## Chapter-to-source map

| Chapter | h | What it is built from |
|---|---|---|
| **1 Introduction** | 10 | `research_plan_original.md` Ch. 1–2 · 2026 framing, the contribution in one sentence, grey literature clearly labelled |
| **2 Literature review** | 16 | `literature_review.md` + `related_work_positioning.md` · **must add** ISO/IEC 25012, data contracts, agent-benchmark precedent |
| **3 Methodology** | 12 | `chapter3_methodology.md` · **must add** probe, gate, interaction arm, sensitivity, F-C7, the refetch arm's two conditions, **the Analyst: verifier, attribution, live quarantine, the plan-returning prompt as a different instrument**, and the "archetypes are simulated" framing |
| **4 Results** | 20 | Findings docs + Figs. 4.1–4.11 and 3.1 · assembly and prose, not analysis |
| **5 Discussion & conclusion** | 12 | Restated recommendation, threats to validity (`REVIEW.md` Phase 1G), the case study as external validity, future work |
| Front/back matter, template, references | 10 | Citation hygiene rule in `CLAUDE.md`: every source verified against publisher or arXiv |

## W9 · Mon 09 – Fri 13 Nov · Ch. 3 + Ch. 4 skeleton · 20 h

| Task | h |
|---|---|
| **Ch. 3 Methodology** — revise the existing draft for everything built since July | 12 |
| **Ch. 4 skeleton** — section structure, place every figure with captions | 8 |

## W10 · Mon 16 – Fri 20 Nov · Ch. 4 Results · 20 h

| Task | h |
|---|---|
| **Ch. 4 §1–3** — RQ1 freshness, RQ2 flip partition, RQ3 decision models | 10 |
| **Ch. 4 §4–6** — RQ4 calibration + sensitivity, RQ5 cross-model, RQ6 interaction + fragility | 10 |

## W11 · Mon 23 – Fri 27 Nov · Ch. 4 close + Ch. 2 · 20 h

| Task | h |
|---|---|
| **Ch. 4 §7** — the gate and its price, the refetch arm, the verifier agreement, the case study | 6 |
| **Ch. 2 Literature review** — raw material into chapter prose | 14 |

**Gate — Fri 27 Nov:** Chapters 2, 3, 4 drafted. **If missed, reduce Ch. 5 to a
short conclusion** — a complete document beats a deep one.

## W12 · Mon 30 Nov – Fri 04 Dec · Ch. 1, Ch. 5, submission · 20 h

| Task | h |
|---|---|
| **Ch. 1 Introduction** — written last, so it promises exactly what was delivered | 8 |
| **Ch. 5 Discussion & conclusion** — including the full threats-to-validity section | 8 |
| Front/back matter, template conversion, reference verification, full read-through | 4 |

### ► MILESTONE 2 — Fri 04 Dec 2026 · Submission

---

# Part 3 — Defence (W13–W14, Mon 07 – Fri 18 Dec, 20 h)

| Task | h |
|---|---|
| Slides — findings first, method second; the 0.501 ROC is the anchor slide, Fig 4.10 the admissibility slide | 8 |
| **Product demo rehearsed cold** on the venue machine, local model pre-pulled: the three moments — a confident wrong answer attributed to the pipeline; REFETCH running on a degraded source; the meter's forfeited answers. USB static export + a 3-minute recording as independent paths | 6 |
| Kill-question rehearsal — the twelve in `REVIEW.md` Phase 2, out loud | 6 |

---

# Checkpoint summary

| Date | Gate | If missed |
|---|---|---|
| Fri 18 Sep | W1 survival fixes complete | **met** |
| Fri 25 Sep | Figs. 4.1–4.8 exist, `make figures` works, power analysis done | **met** |
| **Fri 25 Sep** | **A3: the verifier prints attributed Ticks on the `demo` source (no UI)** | Pause A2/A5; finish A3 first |
| **Fri 02 Oct** | **A4: Fig 4.10 — exact agreement with the corpus** | No UI work until it agrees |
| Fri 09 Oct | `/api/ask` end to end with the free local model: verdict, answer, verification, attribution | Cut A9's report to a print stylesheet |
| **Fri 16 Oct** | **M1 — the Analyst on the supervisor's screen** | Non-negotiable |
| Fri 23 Oct | Refetch arm dry-run done | Cut A10 |
| Fri 30 Oct | Refetch runs executed | **Hard cut the arm** |
| **Fri 06 Nov** | **Implementation freeze** | Freeze regardless of state; cut A11 if not run |
| Fri 27 Nov | Ch. 2, 3, 4 drafted | Shorten Ch. 5 |
| **Fri 04 Dec** | **M2 — submission** | — |

# Risk register

| Risk | P | Impact | Mitigation |
|---|---|---|---|
| **Writing slips past early December** | High | **Fatal** | 80 h budgeted; figures pre-built; hard freeze 06 Nov; November hours are never borrowed for implementation |
| **The Analyst fills the window with no buffer** | High | High | Rule 4 (verifier first); the fixed cut order A10 → A11 → A9 report → A2 inference → A8 toggle; W1–W3's pace |
| The verifier disagrees with the corpus | Med | High | A4 is a gate that stops UI work; disagreement is a bug found in September, not at the defence |
| Live traffic contaminates the evidence | Low | **Fatal** | Never written to `results/runs/`; own seed block and arm; quarantine test |
| A credential leaks into an artifact, log or URL | Low | High | Environment/memory only; a test scanning Ticks, artifacts and logs |
| A hosted model is budgeted as free | Med | Med | A5 closes the "absent from PRICING = $0" gap; caps enforced before each call |
| Records sent to a hosted provider without the user realising | Med | Med | The console states the destination per model; free local model offered first |
| Gemini integration untested without a key | Med | Low | Mocked-client tests; a live smoke call when a key is available; stated if never run |
| Refetch arm over-runs or the design breaks | Med | Med | Hard cut 30 Oct; the router's REFETCH ships regardless |
| Budget exhausted | Low | Med | $4.58 left; arm ~$2.20, case study ~$0.05, development ~$0.40; dry-run and caps |
| Template arrives late | Med | Med | Author in Markdown, convert in W12 |
| Laptop sleeps mid-run | Med | Low | `--offset` resume; happened 17 Aug |
| Defence date lands earlier than expected | Med | High | W13–W14 are buffer |

# Cut list (decided — do not reopen)

Real Kafka/Airflow pipeline · leading-indicator/AIRS-drift arm · third task domain /
fifth model · `airs lint` · generic multi-step agent (replaced by the refetch arm) ·
Streamlit rewrite · SaaS hosting · GitHub Actions (replaced by `make ci`) · **from the
Analyst brief:** warehouse connectors that cannot be tested (Snowflake, BigQuery,
Databricks) · open-ended natural language over arbitrary schemas · writes of any kind ·
multi-user, auth, deployment · Mode B's bespoke walkthrough and Mode C (absorbed).
