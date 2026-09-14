# Handoff 1/3 — Current state and results

**Refreshed:** 14 Sep 2026 · **Last commit:** `05d0ce3` (pushed) — W3 step 6
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
product is an installable tool: `pip install .` (from a clone, after `make web`),
then `airs serve` for a local web console, or `airs probe` / `airs gate` on the
command line.

## 2. Health right now

| | |
|---|---|
| Tests | **501 passing**, lint clean (`make test`, `make lint`) |
| Clean install | `make ci` — fresh venv from `pyproject.toml`, full suite (last run: W3 step 3) |
| Wheel | `make dist-check` — builds the wheel, installs it non-editable, runs the installed `airs` and `airs serve` (API + console). Passes. Needs `make web` first |
| Pinned env | `requirements-lock.txt` (103 pkgs, Python 3.13 arm64), `make lock` |
| Figures | `make figures` builds all 9, deterministic. Fig 3.1 regenerated for F-C7 |
| Runs on disk | 302 run artifacts in `results/runs/` (committed), 24 270 decisions |
| Spend | $5.15 total — OpenAI $2.42 of ~$7 (**~$4.58 left**), Anthropic $2.73 of ~$4 (**~$1.27 left**). Nothing spent since |
| CI | **None, deliberately.** `make ci` + `make dist-check` replace it |
| Working tree | Clean at `05d0ce3` apart from uncommitted doc edits in progress |

## 3. Timeline and where we are

| Milestone | Date | State |
|---|---|---|
| W1 survival fixes | 14–18 Sep | **done** |
| W2 fragility, power, figures | 21–25 Sep | **done** |
| F-C7 small-cluster correction | (not in plan) | **done 13 Sep** |
| W3 product backend + Mode A | 28 Sep–2 Oct | **done 14 Sep — ~2 weeks ahead** |
| **Plan revision: the Analyst** | 14 Sep | **adopted** — `docs/analyst_brief.md`, `docs/plan.md` Part 1b; next: stage A1 (02 §1) |
| **M1 — internship ends, the Analyst running** | **Fri 16 Oct (hard)** | |
| Implementation freeze | Fri 6 Nov | |
| Thesis writing | 9 Nov – 4 Dec | |
| **M2 — submission** | ~Fri 4 Dec · defence December, TBC | |

Capacity: 20 h/week. Plan: `docs/plan.md` (W3 progress note has the detail).

## 4. The six research questions — answered

| RQ | Answer | Findings doc |
|---|---|---|
| RQ1 | Degradation monotone in data age; threshold 5.05 s. Retrieval = *exposure* (rises 2.3→19.2%) × *conditional rate* (flat ~85–100%). | `freshness_sweep_findings.md`, Fig 4.1 |
| RQ2 | Rank on **residual** impairment (retrieval): drift −0.173 > stripping −0.128 > freshness −0.003 ≈ latency 0. Raw and residual agree on order; the partition changes magnitude. | `flip_partition_findings.md` §2, §6; Fig 4.2 |
| RQ3 | Silent failure driven by drift + stripping (retrieval), freshness (classification). Abstention driven by stripping only. **Every published significant coefficient survives the F-C7 p-value calibration.** | `statistical_analysis_findings.md`, `power_findings.md` |
| RQ4 | AIRS ranks held-out pipelines ρ −0.748 (retrieval) / −0.882 (classification). **Agent confidence AUC 0.501 on retrieval**; AIRS 0.580, DeLong p<0.0001. Confidence wins on classification (0.608 vs 0.557). | `airs_calibration_findings.md`; Figs 4.3, 4.4 |
| RQ5 | Ranking transfers across 4 models, **inverts across tasks**. | `cross_model_findings.md` |
| RQ6 | Two faults **never compound — they saturate**. 5 of 8 pairs sub-additive. | `interaction_findings.md`; Fig 4.6 |

## 5. Other results that carry the thesis

- **Gate economics** (`gate_findings.md`, Fig 4.5): ~75% of silent failure is present
  on a fault-free pipeline (14.2% vs 19.6%); every worthwhile gate forfeits **7–21
  correct answers per silent failure prevented** (attribution "true cost"; the raw
  sweep rate is lower — consistency ≥ 90 on retrieval is 2.26 raw vs 7.0 true).
- **Detectability null**: giving the agent each record's age does not make it more cautious.
- **AIRS curve sensitivity** (Fig 4.7): consistency dominance and latency's 0% weight
  survive all 7 parameterisations; freshness weight does not have one value.
- **Query fragility** (Fig 4.8): silent failure concentrates 11.8× / 16.4× beyond a
  permutation null; re-asking gives Jaccard 0.91 / 1.00.
- **Power under clustering + F-C7** (`power_findings.md`, Fig 3.1): ICC ≤ 0.003. The
  original cluster-robust test was anti-conservative (α 0.11–0.12 per cell). Cell and
  pooled comparisons now use **CR2 + Bell–McCaffrey df** (α 0.045–0.058); three cell
  results lost significance; cell MDEs are **10–12 pp**, pooled 6 pp. Decision-model
  coefficients have α 0.06–0.10 and are reported with simulation-calibrated p-values
  (`analysis/pvalue_calibration.py`).
- **Silent-failure definition**: one, threshold-free (invariant 8).

## 6. What exists as a product (W3)

| Piece | What |
|---|---|
| `airs` command | `airs serve`, `airs probe`, `airs gate` (`src/airsbench/cli.py`); exit codes identical to `python -m` |
| Input contract | JSONL, `payload` required; timestamps epoch seconds or ISO-8601 **with zone**; ms values refused; duplicate upstream ids refused; every refusal is a `ProbeError` naming line and fix |
| API (`src/airsbench/server/`) | `GET /api/meta`, `GET /api/samples`, `POST /api/score` (= `probe.score()`), `POST /api/gate` (= `Controller`), `POST /api/replay` (= `gate.replay` over `server/data/replay_corpus.json`, 180 runs). One error shape: 422 `{error: {input, line, message}}` |
| Security | binds 127.0.0.1; Host-header allowlist (DNS rebinding); CORS only with `--dev`; 64 MB body cap; no outbound requests; local files only via `airs serve --records/--source` |
| Console (`demo/`) | `/` = Mode A "Check my pipeline" (paste/drop, samples, score view with unmeasured-weight warning); `/evidence/` = the four-act argument. **No scoring in TypeScript** (`ProbeLive.tsx` deleted) |
| Packaging | `make web` builds the console into `src/airsbench/web/` (gitignored, package data); `server/bake.py` bakes `samples.json` + `replay_corpus.json` (drift-tested) |

## 7. Commits since the previous handoff (newest first)

| Commit | What |
|---|---|
| `05d0ce3` | W3 step 6 — console in the wheel, `aist.json` committed (302 runs), `make web`, dist-check serves the console |
| `0d87c71` | W3 step 5 — Mode A in the browser; TS scorer deleted; a11y + light-theme contrast fixes |
| `137de5d` | W3 step 4 — `/api/replay`; `Outcome.to_dict`; replay via `is_silent_failure` (outputs byte-identical) |
| `d232271` | W3 step 3 — `airs serve`, FastAPI core deps, `.gitignore` `data/` anchored |
| `803fb35` | W3 step 2 — input hardening, ISO timestamps, `probe.score()`, no NaN in JSON |
| `0bcbb62` | W3 step 1 — `airs` CLI, package data (weights were missing from the wheel), `make dist-check` |
| `4c50ca6` | F-C7 — CR2 + Bell–McCaffrey; decision-model p-value calibration |
| `4648406` | the previous handoff |

## 8. Honest limitations already recorded (do not rediscover)

- Pipeline "batch vs streaming" is **simulated** as inherent staleness — no Kafka/Airflow runs.
- Latency runs analytically (`sleep=False`).
- Agent is **one LLM call** — the "is this agentic?" gap (refetch arm / Analyst, see 02).
- Synthetic faults; one model for most arms; n = 3–4 replications.
- AIRS target constants remain underived (state in Ch3/Ch5; sensitivity doc quantifies).
- **Product gaps:** no task-profile switch in the console yet (retrieval unless
  preloaded with `--task`); `aist.json` still has hand-typed panels (W5); the Kafka /
  Postgres / Parquet sample snippets are unscheduled; the console was verified in the
  browser against `next dev`, and from the wheel by content checks only.
