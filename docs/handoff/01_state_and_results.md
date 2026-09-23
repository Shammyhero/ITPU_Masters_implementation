# Handoff 1 of 2 — Where the project stands

**Refreshed:** 24 Sep 2026 · **Last pushed commit:** "The freshness target per source"
(24 Sep), on top of `f228454` (A11: the Vélib' recording, 4 paid runs, Fig 4.11 and the
findings). **Every experiment the plan
scheduled is done.** Before it today: `0a5a3a8` (A10, SQLite/DuckDB/HTTP sources),
`74eaec3` (docs), `14190ce` (the refetch arm's results). Earlier
today: the new thesis title (`60cc800`, supervisor's advice, `docs/research_questions_v2.md`
§1) and the arm's build (`5117e50`, `189a18f`, `f3c653d`).
**Repo:** `~/Documents/Masters_thesis_implementation/agentic-infra-gap` · public at
`github.com/Shammyhero/ITPU_Masters_implementation`
**Read next:** `02_plan_and_next_steps.md` — what to do next, the traps, and
the working conventions. These two files replace the three-file set of 14 Sep
(the operating guide is now Part B of file 2).

Keep both files current: update them in the same step, and the same commit, as any
change they describe (author's standing instruction, 14 Sep).

---

## 1. The project in one paragraph

Master's thesis (Shamsiddin Khamidov, IT Park University, M.Sc. Software
Engineering). **"An Experimental Study of the Effect of Selected Data Infrastructure
Faults on Silent Failures in Agentic AI Systems"** (adopted 22 Sep on the supervisor's
advice; it replaces "Detectability Determines Danger…"). A benchmark injects four data faults
(freshness, latency, schema drift, semantic stripping) into records served to an
LLM agent (retrieval over an e-commerce catalog; classification of flight delays),
measures *silent failure* (committed, parseable, wrong), and builds **AIRS** — a
pipeline readiness score computable from telemetry without running an agent. The
product is an installable tool (`pip install .` after `make web`): `airs probe`,
`airs gate`, `airs sources`, `airs manifest`, `airs analyst`, `airs serve`. **The
Analyst** — live, gated question answering over declared sources or pasted records,
with every wrong answer attributed to the pipeline or the model — is **built**
(A1–A9, `docs/analyst_brief.md`). **The last experiment, the refetch arm, is done**
(23 Sep, `refetch_findings.md`), **A10's live sources** (SQLite, DuckDB, HTTP) and **the A11
live case study** on a real public feed (`live_case_study_findings.md`). What remains: the
freeze week (positioning, the four papers, the DOI) and the thesis document.

## 2. Health right now

| | |
|---|---|
| Tests | **977 passing**, lint clean (`make test`, `make lint`) |
| Clean install | `make ci` — fresh venv from `pyproject.toml`, full suite |
| Wheel | `make dist-check` — builds the wheel, installs it non-editable, runs the installed `airs` (probe, gate, sources) and `airs serve` (API + console). Needs `make web` first |
| Pinned env | `requirements-lock.txt` (103 pkgs, Python 3.13 arm64; PyYAML already pinned), `make lock` |
| Figures | `make figures` builds all 12 (Figs 4.9 and 4.11 added 23 Sep), deterministic |
| Runs on disk | 327 run artifacts in `results/runs/` (committed), 27 620 decisions — 302 corpus + 21 refetch + 4 live case study (never pooled); the case study's recording in `results/livecase/` |
| Spend | **$6.20** in artifacts ($5.15 corpus + $0.85 refetch + $0.19 live case study), + $0.0015 A5 live check + $0.0026 refetch pilot — OpenAI **~$3.70** left, Anthropic **~$1.10** left. No paid work is scheduled |
| CI | **None, deliberately.** `make ci` + `make dist-check` replace it |

## 3. Timeline and where we are

| Milestone | Date | State |
|---|---|---|
| W1 survival fixes · W2 fragility, power, figures | 14–25 Sep (dated) | **done** |
| F-C7 small-cluster correction | 13 Sep | **done** |
| W3 product core — CLI, API, console, packaging | 28 Sep–2 Oct (dated) | **done 14 Sep** |
| **The Analyst adopted** — `docs/analyst_brief.md`, `docs/plan.md` Part 1b | 14 Sep | **done** |
| **A1 sources** | 14–18 Sep | **done 14 Sep** |
| **A3 verifier** — four labels, `airs analyst ask`, live on `llama3.1:8b` | by Fri 25 Sep | **done 15 Sep** |
| **A4 Fig 4.10** — 6,714 decisions, 0 disagreements; 90/90 realizations | **Fri 2 Oct** | **done 16 Sep** |
| **A2 manifest** — two-state semantic rule, `airs manifest`, fingerprinted review | 21–25 Sep | **done 17 Sep** |
| **A5 model options** — hosted keys, spend caps in the request path | 28 Sep–2 Oct | **done 18 Sep** |
| **A6 router + shared loop** — admit/refetch/refuse, the session meter | 28 Sep–2 Oct | **done 18 Sep** |
| **A7 API + firewalls** — `/api/ask` SSE, live quarantine, no key in a request | 5–9 Oct | **done 20 Sep** |
| **A8 console** — all four steps done 20–21 Sep (conversation, replay feed, paste + question builder, semantic toggle) | 5–16 Oct | **done 21 Sep** |
| **A9** task switch · recommended policy priced on the corpus · meter prior · printable report | 12–23 Oct | **done 21 Sep** |
| **Refetch arm** — the last experiment, Fig 4.9 | 19–30 Oct | **done 23 Sep** — 21 runs, $0.8541; the agent never acts; the third verdict priced on the corpus |
| A10 adapters — sqlite, duckdb, http | 19–23 Oct | **done 23 Sep** — `sources/tables.py` |
| **A11 live case study** (Fig 4.11) | 2–6 Nov | **done 23 Sep** — Vélib' recorded 180 min; $0.19; AIRS's calibration does not transfer, its mechanism does |
| **M1 — internship ends, the Analyst running** | **Fri 16 Oct (hard)** | |
| Implementation freeze | Fri 6 Nov | |
| Thesis writing | 9 Nov – 4 Dec | |
| **M2 — submission** | ~Fri 4 Dec · defence December, TBC | |

Capacity: 20 h/week. ~159 h of work scheduled into ~160 h to the freeze (handoff 2, Part A §1).

## 4. The six research questions — answered

| RQ | Answer | Findings doc |
|---|---|---|
| RQ1 | Degradation monotone in data age; threshold 5.05 s. Retrieval = *exposure* × *conditional rate*. | `freshness_sweep_findings.md`, Fig 4.1 |
| RQ2 | Rank on **residual** impairment (retrieval): drift −0.173 > stripping −0.128 > freshness −0.003 ≈ latency 0. | `flip_partition_findings.md`; Fig 4.2 |
| RQ3 | Silent failure driven by drift + stripping (retrieval), freshness (classification); abstention by stripping only. Every published significant coefficient survives the F-C7 calibration. | `statistical_analysis_findings.md`, `power_findings.md` |
| RQ4 | AIRS ranks held-out pipelines ρ −0.748 / −0.882. **Agent confidence AUC 0.501 on retrieval**; AIRS 0.580, DeLong p<0.0001. | `airs_calibration_findings.md`; Figs 4.3, 4.4 |
| RQ5 | Ranking transfers across 4 models, **inverts across tasks**. | `cross_model_findings.md` |
| RQ6 | Two faults **never compound — they saturate**. | `interaction_findings.md`; Fig 4.6 |

RQs v2 §9 declares three further analyses under the Analyst. **Verifier agreement (Fig
4.10) is done (16 Sep):** the live verifier reproduces all 6,714 logged retrieval
decisions exactly — correctness, silent failure, the flip partition — and regenerates
90/90 fault realizations; agent impairment is a 9.7% floor on a fault-free pipeline,
while drift and stripping put 25.0% / 22.5% of decisions on records damaged in transit
(`verifier_agreement_findings.md`). **The refetch arm (Fig 4.9) is done (23 Sep):**
offered a re-read, gpt-4o-mini asked **0 times in 1,800 questions**, age shown or not,
fresh or stale (≤ 0.66% per cell) — the detectability null extends from metadata to
action, and kill question 3 is answered; a gate's re-read matches the healthy pipeline
(98.0% same correctness) and gains correct answers where refusal forfeits them;
exploratory, the unused tool-offering prompt costs 2.9–4.3 pp accuracy
(`refetch_findings.md`). **The live case study (Fig 4.11) is done (23 Sep):** on Vélib'
(Paris), a 15-minute cache doubles silent failure against a 5-minute one for both models,
through exposure (11.0% vs 5.7%); the verifier attributes 10 of 19 silent failures to the
pipeline; **H-L is null for AIRS as calibrated** (AUC 0.557) while the records' age ranks
the failures (0.690) — F-B1 on real data (`live_case_study_findings.md`).

## 5. Other results that carry the thesis

- **Gate economics** (Fig 4.5): ~75% of silent failure is present on a fault-free
  pipeline (14.2% vs 19.6%); worthwhile gates forfeit **7–21 correct answers per silent
  failure genuinely prevented** (attribution true cost; the raw sweep rate is lower —
  consistency ≥ 90 on retrieval is 2.26 raw vs 7.0 true).
- **Detectability null**: giving the agent each record's age does not make it cautious —
  and, since the refetch arm, neither does giving it a way to act (0 re-reads in 1,800).
- **The third verdict** (`gate_findings.md` §7, 23 Sep): a staleness gate that re-reads
  instead of refusing keeps 100% coverage and *gains* correct answers (retrieval, age ≤
  0.1 s: +451 against −3,537 for refusal), at ~10 re-reads per silent failure prevented.
  Priced on the corpus by the matched fault-free run; validated by the arm on retrieval.
- **AIRS curve sensitivity** (Fig 4.7), **query fragility** (Fig 4.8).
- **Power + F-C7** (Fig 3.1): ICC ≤ 0.003; cell tests now CR2 + Bell–McCaffrey (α
  0.045–0.058); cell MDEs 10–12 pp, pooled 6 pp; decision-model p-values calibrated.
- **Silent-failure definition**: one, threshold-free (invariant 8).

## 6. What exists as a product

| Piece | What |
|---|---|
| `airs` command | `serve`, `probe`, `gate`, `sources`, `manifest`, `analyst` (`src/airsbench/cli.py`) |
| Freshness target | per source (24 Sep): `freshness_target_s` in `sources.yaml`, `--freshness-target` on `airs probe`/`airs gate`, the API's score/gate; default the calibrated 1 s; a declared target is shown beside the score; age budgets unaffected |
| Input contract | JSONL, `payload` required; timestamps epoch seconds or ISO-8601 **with zone**; ms refused; duplicate upstream ids refused; `opaque_map` accepted (consistency reverses stripped names) |
| API (`server/`) | `/api/meta`, `/api/samples`, `/api/score`, `/api/gate`, `/api/replay` (180 baked runs); **A7:** `/api/sources`, `/api/sources/{id}/test`, `/api/models`, `/api/session`, `/api/ask` (SSE), `/api/session/{id}`; 422 `{error: {input, line, message}}` |
| Security | 127.0.0.1; Host allowlist; CORS only with `--dev`; 64 MB cap; outbound requests only to an `http` source's declared url and a configured model provider, never to an address a request names; files and sources only through CLI flags / `sources.yaml` |
| Console (`demo/`) | **`/` the conversation, over declared sources or your own pasted records (question builder: six checkable types, fields read from the records; semantic toggle runs the real stripping injector)**; **`/replay/` seven real corpus decisions through the same renderer, no server needed**; **the conversation** (source/answerer/policy pickers, streamed gate → answer → verdict, trace, meter); `/check/` Mode A "Check my pipeline"; `/evidence/` the four-act argument; no scoring in TypeScript |
| **Sources (`sources/`, A1)** | protocol `name / describe / sample / fetch(as_of)`; **`demo`** — seeded ESCI slice (200 queries, 1,129 products, 11,341 updates, 0.21 MB) served through the runner's own functions, four built-in pairs; **`files`** (JSONL, CSV, Parquet via `[parquet]`); **A10:** **`sqlite`**, **`duckdb`** (`[duckdb]`), **`http`** — read afresh each question, `history: true` = readable as of, mixed-type pairs, a table name never SQL; **`inline`**; `sources.yaml` (PyYAML) refusing unknown keys, duplicate ids and inline credentials; `airs sources list/describe/sample`; `airs serve --sources` |
| **Analyst (`analyst/`, A3)** | `plan.py` six checkable types (min_by ≡ `RetrievalAgent.ground_truth`); `verifier.py` truth / served / delivered executions, correctness first, **four labels** `answer_key_moved · both · corrupted_in_transit · agent_impairment`, changed fields as evidence, agent plan recorded (`plan_matches_question`, `agent_plan_agrees`) never graded; `answerers.py` `literal` + local Ollama (hosted refused until A5); `prompts.py` plan-returning, invariant 1; `session.py` one question → Tick; `airs analyst ask`. Nothing written to disk |
| **Manifest (`sources/manifest*.py`, A2)** | `manifest.yaml`: entity, per-field role (id/measure/label/updated_at), unit, definition, relationship, checkable questions; reviewed = stamp + schema fingerprint. States reviewed / unreviewed / stale / absent / invalid → only *reviewed* measures semantic, by the probe's unchanged category rule; field coverage reported beside it. Renders onto bare (files) records only; the demo's bundled `data/demo_manifest.yaml` describes the context its pipeline already renders. `airs manifest propose [--model ollama/…] · review · show`; state in every Tick and in `airs sources` |
| **Live case study (`livecase/`, A11)** | `record.py` (a GBFS feed into a SQLite history + real caching pipelines; `--archive`), `replay.py` (questions at seeded moments of the recording; the consistency reference matched by publication), `questions.py` (three rider questions), `run.py` (exact dry-run, caps); `analysis/livecase.py` (Fig 4.11, H-L, $0 re-grading of logged answers) |
| Packaging | `make web` → `src/airsbench/web/`; `server/bake.py` bakes `samples.json`, `replay_corpus.json`, `sources/data/esci_slice.json.gz` (all drift-tested) |

## 7. Commits (newest first)

| Commit | What |
|---|---|
| (24 Sep) | The freshness target per source |
| `f228454` | A11: the live case study — recording, runs, Fig 4.11, findings |
| `0a5a3a8` | A10: live sources — SQLite, DuckDB and HTTP |
| `74eaec3` | Docs: the `/api/ask` local-model checkpoint met, README commands, file guide |
| `14190ce` | Refetch arm: results — 21 runs, analysis, Fig 4.9, findings, the third verdict |
| `f3c653d` | Refetch arm: the pilot ($0.0026; dry-run counted it exactly) |
| `189a18f` | Refetch arm steps 2–3 — batch runner, artifacts, quarantine |
| `5117e50` | Refetch arm step 1 — the design, and the loop it runs on |
| `60cc800` | The thesis title (supervisor's advice) |
| `75fa839` | Handoff: three files into two |
| `53ea7ad` | A9 — task profile, recommended policy, readiness report |
| `eb03731` | A8 step 4 — the semantic toggle (A8 complete) |
| `2b137ab` | A8 step 3 — paste and the question builder |
| `ce1fcb1` | A8 step 2 — the replay feed |
| `0d0d89c` | A8 step 1 — the conversation console |
| `fffc5cc` | A7 — the Analyst API and its firewalls |
| `7d2cf0c` | A6 — the router and the shared loop |
| `f2c2b1f` | A5 — model options and spend caps |
| `477a8a5` | A2 — the semantic manifest |
| `b2589da` | A4 — verifier agreement, Fig 4.10, seed-rule fix (F-E7) |
| `f5da23a` | A3 — the verifier |
| `e78ab97` | A1 — sources |
| `b691124` | The Analyst adopted; handoff notes refreshed |
| `05d0ce3` | W3 step 6 — console in the wheel, `aist.json` committed |
| `0d87c71` | W3 step 5 — Mode A in the browser; TS scorer deleted |
| `137de5d` | W3 step 4 — `/api/replay` |
| `d232271` | W3 step 3 — `airs serve`, `.gitignore` `data/` anchored |
| `803fb35` | W3 step 2 — input hardening, `probe.score()` |
| `0bcbb62` | W3 step 1 — `airs` CLI, package data, `make dist-check` |
| `4c50ca6` | F-C7 — CR2 + Bell–McCaffrey; p-value calibration |

## 8. Honest limitations already recorded (do not rediscover)

- Pipeline archetypes are **simulated** staleness signatures — no Kafka/Airflow runs.
- Latency runs analytically. The agent is one LLM call everywhere except the refetch
  arm's agent condition, where it may take a second step and never does.
- Synthetic faults; one model for most arms; n = 3–4 replications; AIRS constants underived.
- **Product:** no task-profile switch in the console yet (A9); `aist.json` panels partly
  hand-typed (W5 note); a **files source has no history**, so its consistency also absorbs
  staleness — the output says so; console verified in the browser against `next dev`, and
  from the wheel by content checks only.
