# Handoff 1/3 — Current state and results

**Refreshed:** 14 Sep 2026 · **Last pushed commit:** `b691124` (Analyst adopted) · A1
(sources) committed next
**Repo:** `~/Documents/Masters_thesis_implementation/agentic-infra-gap` · public at
`github.com/Shammyhero/ITPU_Masters_implementation`
**Read next:** `02_plan_and_next_steps.md`, then `03_operating_guide.md`.

Keep these three files current: update them in the same step, and the same commit,
as any change they describe (author's standing instruction, 14 Sep).

---

## 1. The project in one paragraph

Master's thesis (Shamsiddin Khamidov, IT Park University, M.Sc. Software
Engineering). **"Detectability Determines Danger — How Data Infrastructure Faults
Cause Silent Failure in Agentic AI Systems."** A benchmark injects four data faults
(freshness, latency, schema drift, semantic stripping) into records served to an
LLM agent (retrieval over an e-commerce catalog; classification of flight delays),
measures *silent failure* (committed, parseable, wrong), and builds **AIRS** — a
pipeline readiness score computable from telemetry without running an agent. The
product is an installable tool (`pip install .` after `make web`; `airs serve`,
`airs probe`, `airs gate`, `airs sources`), now being extended into **the Analyst**:
live, gated question answering over declared data sources, with every wrong answer
attributed to the pipeline or the model (`docs/analyst_brief.md`).

## 2. Health right now

| | |
|---|---|
| Tests | **567 passing**, lint clean (`make test`, `make lint`) |
| Clean install | `make ci` — fresh venv from `pyproject.toml`, full suite |
| Wheel | `make dist-check` — builds the wheel, installs it non-editable, runs the installed `airs` (probe, gate, sources) and `airs serve` (API + console). Needs `make web` first |
| Pinned env | `requirements-lock.txt` (103 pkgs, Python 3.13 arm64; PyYAML already pinned), `make lock` |
| Figures | `make figures` builds all 9, deterministic |
| Runs on disk | 302 run artifacts in `results/runs/` (committed), 24 270 decisions |
| Spend | $5.15 total — OpenAI ~$4.58 left, Anthropic ~$1.27 left. Nothing spent since |
| CI | **None, deliberately.** `make ci` + `make dist-check` replace it |

## 3. Timeline and where we are

| Milestone | Date | State |
|---|---|---|
| W1 survival fixes · W2 fragility, power, figures | 14–25 Sep (dated) | **done** |
| F-C7 small-cluster correction | 13 Sep | **done** |
| W3 product core — CLI, API, console, packaging | 28 Sep–2 Oct (dated) | **done 14 Sep** |
| **The Analyst adopted** — `docs/analyst_brief.md`, `docs/plan.md` Part 1b | 14 Sep | **done** |
| **A1 sources** | 14–18 Sep | **done 14 Sep** |
| A3 verifier · A4 Fig 4.10 agreement | by Fri 25 Sep · **Fri 2 Oct** | next |
| **M1 — internship ends, the Analyst running** | **Fri 16 Oct (hard)** | |
| Implementation freeze | Fri 6 Nov | |
| Thesis writing | 9 Nov – 4 Dec | |
| **M2 — submission** | ~Fri 4 Dec · defence December, TBC | |

Capacity: 20 h/week. ~159 h of work scheduled into ~160 h to the freeze (02 §1).

## 4. The six research questions — answered

| RQ | Answer | Findings doc |
|---|---|---|
| RQ1 | Degradation monotone in data age; threshold 5.05 s. Retrieval = *exposure* × *conditional rate*. | `freshness_sweep_findings.md`, Fig 4.1 |
| RQ2 | Rank on **residual** impairment (retrieval): drift −0.173 > stripping −0.128 > freshness −0.003 ≈ latency 0. | `flip_partition_findings.md`; Fig 4.2 |
| RQ3 | Silent failure driven by drift + stripping (retrieval), freshness (classification); abstention by stripping only. Every published significant coefficient survives the F-C7 calibration. | `statistical_analysis_findings.md`, `power_findings.md` |
| RQ4 | AIRS ranks held-out pipelines ρ −0.748 / −0.882. **Agent confidence AUC 0.501 on retrieval**; AIRS 0.580, DeLong p<0.0001. | `airs_calibration_findings.md`; Figs 4.3, 4.4 |
| RQ5 | Ranking transfers across 4 models, **inverts across tasks**. | `cross_model_findings.md` |
| RQ6 | Two faults **never compound — they saturate**. | `interaction_findings.md`; Fig 4.6 |

RQs v2 §9 declares three further analyses under the Analyst: verifier agreement (Fig
4.10), the two-condition refetch arm (Fig 4.9), the live-source case study (Fig 4.11).

## 5. Other results that carry the thesis

- **Gate economics** (Fig 4.5): ~75% of silent failure is present on a fault-free
  pipeline (14.2% vs 19.6%); worthwhile gates forfeit **7–21 correct answers per silent
  failure genuinely prevented** (attribution true cost; the raw sweep rate is lower —
  consistency ≥ 90 on retrieval is 2.26 raw vs 7.0 true).
- **Detectability null**: giving the agent each record's age does not make it cautious.
- **AIRS curve sensitivity** (Fig 4.7), **query fragility** (Fig 4.8).
- **Power + F-C7** (Fig 3.1): ICC ≤ 0.003; cell tests now CR2 + Bell–McCaffrey (α
  0.045–0.058); cell MDEs 10–12 pp, pooled 6 pp; decision-model p-values calibrated.
- **Silent-failure definition**: one, threshold-free (invariant 8).

## 6. What exists as a product

| Piece | What |
|---|---|
| `airs` command | `serve`, `probe`, `gate`, `sources` (`src/airsbench/cli.py`) |
| Input contract | JSONL, `payload` required; timestamps epoch seconds or ISO-8601 **with zone**; ms refused; duplicate upstream ids refused; `opaque_map` accepted (consistency reverses stripped names) |
| API (`server/`) | `/api/meta`, `/api/samples`, `/api/score`, `/api/gate`, `/api/replay` (180 baked runs); 422 `{error: {input, line, message}}` |
| Security | 127.0.0.1; Host allowlist; CORS only with `--dev`; 64 MB cap; no outbound requests; files and sources only through CLI flags / `sources.yaml` |
| Console (`demo/`) | `/` Mode A "Check my pipeline"; `/evidence/` the four-act argument; no scoring in TypeScript |
| **Sources (`sources/`, A1)** | protocol `name / describe / sample / fetch(as_of)`; **`demo`** — seeded ESCI slice (200 queries, 1,129 products, 11,341 updates, 0.21 MB) served through the runner's own functions, four built-in pairs; **`files`** (JSONL, CSV, Parquet via `[parquet]`); **`inline`**; `sources.yaml` (PyYAML) refusing unknown keys, duplicate ids and inline credentials; `airs sources list/describe/sample`; `airs serve --sources` |
| Packaging | `make web` → `src/airsbench/web/`; `server/bake.py` bakes `samples.json`, `replay_corpus.json`, `sources/data/esci_slice.json.gz` (all drift-tested) |

## 7. Commits (newest first)

| Commit | What |
|---|---|
| *(next)* | A1 — sources |
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
- Latency runs analytically. Agent is one LLM call until the refetch arm.
- Synthetic faults; one model for most arms; n = 3–4 replications; AIRS constants underived.
- **Product:** no task-profile switch in the console yet (A9); `aist.json` panels partly
  hand-typed (W5 note); a **files source has no history**, so its consistency also absorbs
  staleness — the output says so; console verified in the browser against `next dev`, and
  from the wheel by content checks only.
