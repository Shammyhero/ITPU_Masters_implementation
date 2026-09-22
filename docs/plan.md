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
| **The Analyst A1–A9** | 14 Sep → 23 Oct | 103 | ~$0.40 (development calls; estimate) | |
| Adapters A10 · live case study A11 | 19 Oct → 6 Nov | 14 | ~$0.05 | |
| Refetch arm, two conditions | 19 → 30 Oct | 28 | ~$2.20 | |
| M1 presentation | 16 Oct | 2 | $0 | |
| Positioning, papers, DOI | 2 → 6 Nov | 14 | $0 | |
| Thesis document | W9–W12 | 80 | $0 | |
| Defence | W13–W14 | 20 | $0 | |
| **Total** | | **~324** | **~$2.65** | |

**The honest arithmetic.** From Mon 14 Sep to the freeze on Fri 6 Nov is eight weeks,
~160 h. The work scheduled into that window is **161 h — no buffer** (159 h, plus A4's
fault-realization check added on 15 Sep). The author chose
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
| **4.10** | **Verifier agreement — the live verifier reproduces the corpus** | `verifier_agreement.py` | **built 16 Sep** |
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
same renderer — **it was never built, so A8 had nothing to delete**, recorded 21 Sep);
Mode C (absorbed). **What it keeps:** every W3 property — no scoring rule
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

> **Progress 14 Sep — A1 built.** `src/airsbench/sources/`: the four-member protocol;
> the `demo` source — a seeded 200-query ESCI slice (1,129 products, 11,341 updates,
> 0.21 MB, byte-stable bake, drift- and replay-tested against `data/ecommerce`) served
> through the runner's own catalog replay, record builder, staleness accounting and
> fault chain, with four built-in pairs (`demo-healthy`, `demo-stale`, `demo-drift`,
> `demo-stripped`); `files` (JSONL, CSV, and Parquet through the new `[parquet]` extra)
> and `inline` sources; `sources.yaml` read with PyYAML, now a core dependency (author
> decision), refusing unknown keys, duplicate ids and inline credentials; a new
> `airs sources list | describe | sample`; `airs serve --sources` validates at startup.
> Demo questions use simulated time per question (author decision), so upstream is read
> exactly as of the answer and the t0/t1 gap is zero. **Two findings, both fixed and
> tested:** consistency must be scored against upstream *as of when the delivered values
> were true*, the corpus's reference (brief correction 15), so `fetch` takes `as_of`;
> and the probe dropped semantic stripping's `opaque_map`, which now travels through
> `to_probe_entry` and `probe`. The demo source reproduces `runner.execute`'s AIRS
> exactly for every condition tested. 567 tests. Deferred by design: the environment-
> variable credential mechanism (first needed by A10), `--records/--source` as a
> `cli` source pair and the API routes (A7), the console (A8).

### A2 · The semantic manifest · 8 h

`manifest.yaml` schema (field roles: id, measure, label, updated_at; unit; definition;
`checkable_questions`); loading a committed manifest with no model call; a review/approve
flow; **inference** — one costed model call proposing roles from `describe()`, each
field approved by the user. The two-state semantic rule: **no reviewed manifest →
semantic UNMEASURED**; a reviewed manifest renders context into the records and the
probe's existing rule scores it (fields left undescribed lower completeness; no context
at all = 0). Tests pin both states against the probe's own tests.
*Cut gate:* committed manifests only, inference dropped.

> **Progress 17 Sep — A2 done.** `sources/manifest.py` (schema, validation, fingerprint,
> the two-state `semantic_layer`, offline `propose`, `refine_with_model`),
> `sources/manifest_cli.py` (`airs manifest propose | review | show`), a bundled reviewed
> `sources/data/demo_manifest.yaml` baked from the slice's own context, `probe.score(...,
> semantic_unmeasured=)`, and the state in every Tick (`source.semantic`) and in `airs
> sources list | sample`. **Author decisions 17 Sep:** the calibrated category rule is
> kept and field coverage reported beside it (brief correction 2 corrected against the
> code — undescribed fields never lowered the score); reviewed = stamp + schema
> fingerprint; inference ships (heuristic + local Ollama, hosted with A5). Nothing was
> cut. The four demo pairs score exactly what they scored in A1, and the bundled manifest
> renders exactly the context the corpus agent read. **Live, $0:** on a CSV of six real
> catalog rows, `llama3.1:8b` proposed units and definitions in 8 s and named the entity
> `laptop` from the sample — plausible and wrong for a catalog, which is why nothing
> counts until reviewed; semantic went UNMEASURED → 75 on approval (no relationships
> declared). **Found and fixed live:** declaring `manifest:` before the file existed made
> `sources.yaml` unloadable, so `propose --out` could never create it; and `airs sources
> sample` printed `100.0 READY` resting on consistency alone without saying so — it now
> states the share of calibrated weight covered. 690 tests.

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

> **Progress 15 Sep — A3 built.** `src/airsbench/analyst/`: `plan.py` (the six checkable
> types, deterministic, ties to the first candidate — `min_by(price, stock > 0)` equals
> `RetrievalAgent.ground_truth` over 2,000 randomised catalogs; records that lack a
> field or hold a non-number the plan needs are *not computable*, with the reason);
> `verifier.py` (three executions — truth, served, delivered — correctness first,
> `is_silent_failure` imported, and **four labels**); `answerers.py` (`literal`, and a
> local Ollama model through the corpus `LLMClient`; hosted refused until A5);
> `prompts.py` (plan-returning, held to the corpus's forbidden-word list plus fault
> vocabulary); `session.py` (one question as a Tick); `airs analyst ask`. **Author
> decisions 15 Sep:** answers are verified against **the question's plan**, never the
> agent's own (which is recorded, not graded); attribution has four labels —
> `answer_key_moved`, `both`, `corrupted_in_transit`, `agent_impairment` — aggregating
> exactly to the published flipped/unflipped split (property-tested). Literal answerer,
> 60 questions per demo pair: healthy 58/58 correct; stale 6 `answer_key_moved`, one
> per flip; drift 44 abstained, 1 `corrupted_in_transit`; stripped 59 abstained.
> **Live, local, $0 — `llama3.1:8b`:** all 6 flipped stale questions answered with the
> served-best at confidence 1.00 → `answer_key_moved`; drift 4 correct and 2
> `corrupted_in_transit` at 1.00. Found and fixed: the model's plan differed in form from
> the question's in 7 of 12 answers — `stock >= 1` (equivalent on whole-number stock) and
> `stock >= 0` (a real widening) — so the Tick also records `agent_plan_agrees`, the
> agent's plan re-executed over the served records. 652 tests.

### A4 · Verifier agreement — Fig 4.10 · 8 h · **non-negotiable, immediately after A3**

> **Scope added 15 Sep (author decision, +2 h):** A4 also regenerates each corpus run's
> exact fault realization — the runner's fault chain replayed in query order with the
> run's seed — so Fig 4.10 validates all four labels, not only the two-way split. The
> regeneration is itself checked: it must reproduce each run's logged consistency and
> semantic scores exactly, which is record-level evidence for invariant 3.

> **Progress 16 Sep — A4 done, gate met 16 days early.**
> `analysis/verifier_agreement.py`, **Fig 4.10**, `docs/verifier_agreement_findings.md`,
> `tests/test_verifier_agreement.py`, `make figures`. Over 90 retrieval runs (main +
> sweep) and **6,714 decisions: zero disagreements** on verifiable, `correct`, silent
> failure, `flipped` and the attribution partition; **90/90 fault realizations
> regenerated** to their logged consistency and semantic scores (float equality); the
> published RQ2 raw accuracies (0.812 / 0.774 / 0.689 / 0.729) and residuals (−0.003 /
> −0.003 / −0.173 / −0.128) recomputed from the verifier's own correctness. **New
> result** (Fig 4.10, right panel): agent impairment is a floor — 9.7% of decisions on a
> fault-free pipeline and 9.7% under latency; freshness only moves the key (1.7% → 15.3%
> across the sweep at flat impairment); drift and stripping put 25.0% and 22.5% of
> decisions on records whose needed fields changed in transit. **Found and fixed on the
> way (REVIEW F-E7):** 88 runs across the main and cross-model arms could not be replayed
> from their own configs — they predate `_component_seed` — so the injector seed is now
> keyed on the parameter shape; nothing published moves. Recorded, not fixed: NaN brands
> cap healthy consistency at 99.88 (**F-B5**). 664 tests.

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

> **Progress 18 Sep — A5 done.** `analyst/budget.py` (session and day ceilings, the day
> total persisted in `~/.airs/spend.json`, checked **before** each request with that
> request's projected cost), `ModelAnswerer` addressing every model as
> `<provider>/<model>` (`ollama`, `openai`, `anthropic`, `gemini`), Gemini routing in
> `llm.py` behind a `[gemini]` extra, `airs analyst ask --max-cost --max-cost-day
> --estimate`, and the Tick recording the provider, the budget state and a note naming
> where the records went. **The A5 trap is closed:** `require_price` refuses a hosted
> model with no price instead of budgeting it at $0; local models stay free by
> construction. **Author decision 17 Sep — declare or refuse:** only prices verified for
> the corpus models ship; anything else is declared in `~/.airs/pricing.yaml`
> (`input_per_mtok` / `output_per_mtok`), so no price here is a guess at a provider's
> list. **Live, paid, $0.0010 total:** 3 questions on `gpt-4o-mini` through the real API
> — 1 correct, 1 `answer_key_moved`, and 1 **`agent_impairment`** where the model picked a
> $9.57 item over an intact $9.50 one; a $0.0004 cap then refused mid-run before the
> second call, exit 3, with the questions already answered reported. Estimated 1,600
> input tokens against 1,101 actual — over-estimating is the safe direction for a cap.
> 711 tests.

### A6 · Router and the shared two-step loop · 12 h · shared with the refetch arm

`src/airsbench/analyst/loop.py`, called by both the API and the batch runner: sample →
`probe.measure` → `Controller.evaluate(policy)` → **ADMIT** (answer) / **REFETCH**
(gate-initiated: `upstream.fetch` → re-score → answer) / **REFUSE** (no model call,
rule + observed value, $0). The same loop offers the agent a `refetch(record_id)` tool
for the arm's agent-initiated condition. Tool-call accounting, loop termination,
invariant 1 (the prompt never mentions faults), and the paired design preserved in batch
mode — tested.

> **Progress 18 Sep — A6 done (the loop; the arm's batch runner stays in W6).**
> `analyst/loop.py`: `route` (admit / refetch / refuse), `Loop.ask` (one question end to
> end), `Meter` (answered, refused, refetched, prevented, forfeited, live exchange rate),
> reusing `gate.Controller` — one policy evaluator, and the Tick's `airs` block **is** the
> gate's measurement. `airs analyst ask --policy --refetch gate|agent|off`. **Author
> decisions 18 Sep:** a re-read is attempted only for rules it legitimately repairs —
> `max_record_age_seconds`, `min_dimension.freshness` — because a re-read *bypasses* the
> pipeline, and bypassing one that is renaming fields hides a contract violation instead
> of fixing it, so drift and stripping refuse · the agent-initiated tool is a JSON action
> in the answer schema, uniform across providers · a separate prompt for that condition
> only, so invariant 1 holds everywhere else. **Live, $0, `llama3.1:8b`, the same 12
> stale questions under both conditions:** gate-initiated re-read 12/12 → 11 correct, 1
> silent failure; agent-initiated **asked for a re-read 0 times out of 12** → 10 correct,
> 2 silent failures. Offered the ability to re-read, the model never took it — an
> extension of the detectability null, and the first evidence for kill question 3 (one
> model, 12 questions, demo source; the arm measures it properly). **Three bugs found by
> running it:** the loop re-read upstream at the *end* of the stream, i.e. later than the
> question's own answer key; agent mode refused every violation before the agent could
> decide, so the condition measured nothing; and a wrong answer after a re-read was
> labelled `corrupted_in_transit` because the verifier still compared against the
> pre-refetch served state. 740 tests.

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

> **Progress 20 Sep — A7 done.** `GET /api/sources`, `POST /api/sources/{id}/test`,
> `GET /api/models`, `POST /api/session`, `POST /api/ask` (**SSE**: gate → refetch →
> answer → tick), `GET /api/session/{id}`; `analyst/sessions.py` (live sessions, one Tick
> per line in `~/.airs/sessions/`). `Loop.stream` is now the real path and `Loop.ask`
> drains it, so the stream's stages are when the work actually happened, not a timer —
> and the CLI, the API and the arm still share one loop. **Author decisions 19 Sep:**
> keys stay in the environment (no secret in a request body; `/api/models` reports only
> whether a provider is configured) · live Ticks persist to `~/.airs/sessions/` · manifest
> endpoints deferred to A8. **Quarantine, asserted not assumed** (`test_live_quarantine.py`):
> `session_path` refuses any destination under `results/runs/`; every Tick carries
> `arm: "live"` and a seed from the registered live block; each analysis loader drops a
> live artifact planted in a corpus; a Tick that looks like it carries a credential is
> refused rather than written. **Three defects the tests and the live run found:** the
> `include_other_arms=True` flag in `flip_partition` and `phase1_check` admitted live
> traffic (now never); a Tick carried `manifest_path` as an absolute path, leaking the
> user's home directory (now the file name); and a hosted model could open a session with
> no key present, failing mid-stream instead of at the door. Verified over real HTTP
> against `airs serve`: refuse emits no answer event, a path as a source id is refused,
> and the meter accumulates. 779 tests.

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

> **Progress 20 Sep — A8 step 1 of 4: the conversation.** `/` is now the conversation
> (`Conversation.tsx` + `TickView.tsx`); the paste-first probe moved to `/check/`, keeping
> `ScoreView` and its own tests. Source, answerer and policy pickers come from
> `/api/sources` and `/api/models`; a question streams gate → refetch → answer → **then**
> the verdict, rendered as each arrives and never batched, with the trace (delivered /
> served / upstream on the fields the question reads, changed fields, lag, AIRS at that
> moment) and the session meter. Confidence is greyed with "AUC 0.501" beside it, so the
> screen cannot read as reassurance. **Author decisions 20 Sep:** pasted records may be
> answered over — the records ARE the request body, so the declared-sources firewall
> holds — and the manifest stays CLI-reviewed for M1, with the console showing the state
> live. Verified in the browser against a running `airs serve`: a re-read then a correct
> answer; a refusal that names the rule and says it cost nothing but forfeited a correct
> answer; and a real **silent failure · the answer key moved** at confidence 1.00. Two
> light-mode contrast defects found and fixed by measuring, not eyeballing (gate badge
> 3.75, verdict title 4.36 → 4.97 / 5.78). `make web` exports both routes and
> `make dist-check` passes; its console assertion now checks what each route serves
> rather than a nav link that appears on every page. Still to come in A8: the meter's
> replay feed, Mode B folded into this renderer, and the semantic toggle. 783 tests.

> **Progress 21 Sep — A8 step 2 of 4: the replay feed.** `/replay/` plays **seven real
> decisions from five main-arm runs** through the same `TickView` the live conversation
> uses — correct, agent impairment on a fault-free pipeline, the answer key moving,
> corruption in transit under drift and under stripping, and a genuine abstention. It
> needs **no server**: `server/replay_bake.py` regenerates each run's records by replaying
> its fault chain, accepts them only when they reproduce that run's logged consistency and
> semantic scores exactly (the A4 rule), and writes `demo/src/data/replay_ticks.json`,
> which the page imports at build time — so the route opens from a file server, like
> `/evidence/`. **Author decisions 21 Sep:** real logged decisions curated to span the
> four outcomes; its own route; one renderer, two feeds. **Found by building it:** stopping
> the bake early checked a fragment of a run's realization against its whole-run AIRS (the
> check caught it); abstention under stripping is rare enough on the streaming pipeline
> (0, 0, 0, 1 across replications) that the feed searches a condition's runs for each
> outcome rather than taking the first; the `Tick` TypeScript type wrongly claimed a gate,
> session and meter are always present, and that the AIRS block always carries the
> calibration stamp — the router's own block never did; and an abstention rendered no
> verdict at all, though declining is the outcome a gate exists to produce. 791 tests,
> `make dist-check` green with the new route.

> **Progress 21 Sep — A8 step 3 of 4: your own records, in the conversation.** Step 3 was
> planned as "delete the bespoke walkthrough"; that UI was only ever *planned*, so the
> step was re-scoped (author decision) to the gap A7's backend had already opened: the
> console could not paste. `/` now offers **paste my own records** beside the declared
> sources — delivered records, optionally the system of record — with a
> **question builder** (`QuestionBuilder.tsx`) that offers the six checkable plan types
> and takes the measure and filter fields from the pasted records themselves, so every
> question a visitor can ask is verifiable by construction and no free text reaches the
> verifier. Verified in the browser: pasted records → a question built from their fields →
> answered `SKU-3` → **silent failure, corrupted in transit**, which is the honest label
> for a source with no history (brief correction 15). **Found by driving it:** `askOne`
> omitted the pasted text from its dependency list, so it sent the empty initial value and
> the server rightly refused `inline` as an undeclared source — a stale closure, not a
> firewall bug; and a pasted sample carries no timestamps, so the default freshness policy
> refused every batch (correct, but a poor first minute) — pasted sessions now start with
> no policy and say what a timestamp-checking policy would need. 791 tests, wheel green.

> **Progress 21 Sep — A8 step 4 of 4: the semantic toggle. A8 is done.** A checkbox in the
> console runs the study's **own** `SemanticStrippingInjector` (severe, `strip_rate` 0.80)
> over the records the session reads: the context block goes and field names become opaque
> tokens. Dropping the manifest alone would move nothing — `price` and `stock` describe
> themselves (the CLAUDE.md trap) — which is exactly why correction 3 required the real
> injector. Measured live on `demo-healthy`, same question and seed: **semantic 100 → 25,
> consistency stays 100** (the opaque map lets the consistency measure reverse the names,
> invariant 5), AIRS 100 → 87.4, and the answer goes from **correct** to **abstained**.
> Every Tick of such a session says the stripping was done *by this console, not by your
> pipeline*, and the UI says whether it moves an answer on your data is an observation,
> not a promise (OR 51.9 is gpt-4o-mini on ESCI). 797 tests, `make dist-check` green.
> **A8 complete: conversation, replay feed, paste + question builder, toggle.**

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

> **Progress 21 Sep — A9 done, all three pieces.** **Task-profile switch:** retrieval-like
> or classification-like weights, switched when asked and stated out loud — the same
> question on `demo-stale` reads 89.6 READY under retrieval and **83.0 WATCH** under
> classification, and the console says the ranking inverts across tasks (RQ5), because it
> cannot know which task a user's pipeline serves and refusing would be a guess dressed as
> a safeguard (author decision). **Recommended policy** (`POST /api/recommend`): every
> policy in the existing sweeps is replayed over the baked corpus — the accounting behind
> `gate_findings.md` — and the cheapest by exchange rate among those that refuse something
> and still answer is offered, one click to the router. For retrieval it lands on
> **consistency ≥ 90 at 2.26 raw**, the published trade; switch to classification and it
> becomes `age ≤ 10 s`, the inversion showing up in the advice itself. What the session has
> measured only *filters* that list (a floor its pipeline never clears is a refusal
> machine, not advice) and never invents a floor. **The meter's prior** shows the predicted
> rate beside the live one with both costs labelled — 2.26 raw against 7.0 attribution true
> cost, and the ~14% fault-free floor stated, so no reader takes the cheaper number for the
> real one. **Printable report:** one page — dimensions and weights, AIRS and its coverage,
> the policy, every outcome including refusals, predicted against observed cost, and the
> provenance (session id, arm `live`, seed block) so a printout cannot be mistaken for
> corpus data. **Found while building:** the outcome dict's own `policy` key (a name) was
> overwriting the structured policy the console applies; and the report counted only
> verified answers, so three refusals rendered as "no verified answers yet" — a refusal is
> the outcome enforcement exists to produce. 801 tests, wheel green.

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

> **Progress 23 Sep — design approved** (`docs/refetch_arm.md`; hypotheses refined in
> RQs v2 §9 before anything runs). **21 runs, not ~54:** 7 paid cells × 3 replications ×
> 150 questions — baseline and agent-initiated (age hidden, age shown) on healthy and
> freshness 5.05 s data, gate-initiated on stale only (on healthy it *is* the baseline);
> refusal priced at $0 from the baseline's shadow-policy verdicts. ~$0.95 expected,
> ~$1.45 worst case. **What the code forced:** the agent sees no record age by default
> (so age is a factor, the detectability arm's own mechanism); a demo re-read returns
> exactly the answer key (so the gate cell is a cost menu, not a finding); a $0 check
> puts exposure at 14.7% of stale questions; provenance is hard-wired to `live`; and a
> **second re-read request was graded as a silent failure** — fixed by continuing the
> conversation (D1 a: the model's request, then the records read again, no further
> offer), with an action reply never graded as an answer.
>
> **Progress 23 Sep — step 1, the loop, built.** provenance a parameter (live stays the default) · record age on the demo source through `execute.attach_record_age` · the re-read continued as a second turn (`reread_messages`, `ModelAnswerer.answer_after_reread`) · an action reply marked unparseable and `unanswered_action`, and `verify` never commits one. 818 tests. A
> $0 smoke run, `llama3.1:8b`, 12 stale questions each: **0 re-read requests with age
> shown**, as with it hidden — a hint the detectability null extends from metadata to
> action on this model, not evidence (the arm runs gpt-4o-mini).
>
> **Progress 23 Sep — steps 2–3, the batch runner, built.** `--refetch-arm` (`runner/refetch.py`,
> `config.build_refetch_arm`: 21 runs, replication-major, `RunConfig.refetch_mode`); artifacts
> in `results/runs/` as arm `refetch`; `NEVER_POOLED = ("live", "refetch")` closes the three
> loaders that admitted every arm (`flip_partition` and `phase1_check` under
> `include_other_arms`, `silent_definition`'s robustness table); `campaign_state` tracks the
> arm. **The dry-run runs the real loop with a $0 counting answerer** over all 3,150
> questions (35 s) and counts every prompt with gpt-4o-mini's tokenizer: **$0.96 expected,
> $1.85 worst case** — *corrected* from the design's ~$1.45, which assumed a second call
> costs what a first does. Caps: the worst case before the campaign, each run's worst case
> before that run, and the analyst `Budget` before every call; the arm's spend never
> touches `~/.airs`. 851 tests. Next: step 4, the dry-run shown to the author.

## Calendar — Mon 14 Sep to the freeze

| Week | Work | h |
|---|---|---|
| **14–18 Sep** | A1 sources (12) · A3 verifier, start (8) | 20 |
| **21–25 Sep** | A3 finish (6) · **A4 Fig 4.10** (8) · A2 manifest (8) | 22 |
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
