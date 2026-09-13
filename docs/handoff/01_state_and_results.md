# Handoff 1/3 — Current state and results

**Written:** ~14 Sep 2026, end of a long session · **Last commit:** `8c52f0a` (pushed)
**Repo:** `~/Documents/Masters_thesis_implementation/agentic-infra-gap` · public at
`github.com/Shammyhero/ITPU_Masters_implementation`
**Read next:** `02_plan_and_next_steps.md`, then `03_operating_guide.md`.

---

## 1. The project in one paragraph

Master's thesis (Shamsiddin Khamidov, IT Park University, M.Sc. Software
Engineering). **"Detectability Determines Danger — How Data Infrastructure Faults
Cause Silent Failure in Agentic AI Systems."** A benchmark injects four data faults
(freshness, latency, schema drift, semantic stripping) into records served to an
LLM agent (retrieval over an e-commerce catalog; classification of flight delays),
measures *silent failure* (committed, parseable, wrong), and builds **AIRS** — a
pipeline readiness score computable from telemetry without running an agent. Two
tools ship: `airs probe` (score a pipeline) and `airs gate` (refuse bad batches).
The internship goal is to turn these into a **real installable product**.

## 2. Health right now

| | |
|---|---|
| Tests | **398 passing**, lint clean (`make test`, `make lint`) |
| Clean-install check | `make ci` — fresh venv from `pyproject.toml`, full suite |
| Pinned env | `requirements-lock.txt` (99 pkgs, Python 3.13 arm64), `make lock` |
| Figures | `make figures` builds all 9, deterministic (byte-identical) |
| Runs on disk | 302 run artifacts in `results/runs/` (committed), 24 270 decisions |
| Spend | $5.15 total — OpenAI $2.42 of ~$7 (**~$4.58 left**), Anthropic $2.73 of ~$4 (**~$1.27 left**) |
| CI | **None, deliberately.** GitHub Actions removed (billing lock, never passed). `make ci` replaces it. |
| Working tree | Clean except these handoff files |

## 3. Timeline and where we are

| Milestone | Date |
|---|---|
| Week 1 (survival fixes) | **done** |
| Week 2 (fragility, power, figures) | **done, ahead of schedule** (plan dates it 21–25 Sep) |
| **M1 — internship ends, product running, results collected** | **Fri 16 Oct 2026 (hard)** |
| Implementation freeze | Fri 6 Nov |
| Thesis writing (together, Markdown first) | 9 Nov – 4 Dec |
| **M2 — submission** | ~Fri 4 Dec · defence December, TBC |

Capacity: 20 h/week. Full week-by-week plan: `docs/plan.md`.

## 4. The six research questions — answered

| RQ | Answer | Findings doc |
|---|---|---|
| RQ1 | Degradation monotone in data age; threshold 5.05 s. Retrieval = *exposure* (rises 2.3→19.2%) × *conditional rate* (flat ~85–100%). | `freshness_sweep_findings.md`, Fig 4.1 |
| RQ2 | Rank on **residual** impairment (retrieval, pooled pipelines): drift −0.173 > stripping −0.128 > freshness −0.003 ≈ latency 0. Raw and residual **agree on order**; the partition changes **magnitude** (freshness −0.075 raw → −0.003). | `flip_partition_findings.md` §2, §6; Fig 4.2 |
| RQ3 | Silent failure driven by drift + stripping (retrieval), freshness (classification). Abstention driven by stripping only. | `statistical_analysis_findings.md` |
| RQ4 | AIRS ranks held-out pipelines ρ −0.748 (retrieval) / −0.882 (classification). **Agent confidence AUC 0.501 on retrieval** (coin flip); AIRS 0.580, DeLong p<0.0001. Confidence wins on classification (0.608 vs 0.557). | `airs_calibration_findings.md`; Figs 4.3, 4.4 |
| RQ5 | Ranking transfers across 4 models, **inverts across tasks**. | `cross_model_findings.md` |
| RQ6 | Two faults **never compound — they saturate**. 5 of 8 pairs sub-additive; AIRS therefore over-predicts multi-fault risk (safe direction). | `interaction_findings.md`; Fig 4.6 |

## 5. Other results that carry the thesis

- **Gate economics** (`gate_findings.md`, Fig 4.5): ~75% of silent failure is present
  on a fault-free pipeline (14.2% vs 19.6%); every worthwhile gate forfeits **7–21
  correct answers per silent failure prevented**; the staleness budget is the wrong
  gate for retrieval.
- **Detectability null** (`detectability_findings.md`): giving the agent each record's
  age does not make it more cautious.
- **AIRS curve sensitivity** (`sensitivity_findings.md`, Fig 4.7): weights rest on
  underived constants (1.0 s, 500 ms, hyperbola). Consistency dominance on retrieval
  and latency's 0% weight survive all 7 parameterisations; freshness weight ranges
  10.7–22.8% (retrieval) / 16.4–44.7% (classification); classification's top
  dimension flips at a 5 s target.
- **Query fragility** (`fragility_findings.md`, Fig 4.8) — *new in W2*: silent failure
  concentrates 11.8× (retrieval) / 16.4× (classification) beyond a within-run
  permutation null; top 10% of questions carry 39–47% of faulted silent failures;
  re-asking identical inputs gives Jaccard 0.91 / 1.00 → fragility is a stable
  property of the question. Mechanism behind RQ6 saturation.
- **Power under clustering** (`power_findings.md`, Fig 3.1) — *new in W2*: ICC ≤ 0.003
  (clustering negligible); MDE ~8–10 pp per cell, ~6 pp pooled; **the study's
  cluster-robust test is anti-conservative** (α ≈ 0.12 single cell, ≈ 0.075 pooled).
- **Silent-failure definition** (`silent_definition_findings.md`): unified to
  threshold-free (invariant 8). A 0.7 threshold is inert for gpt-4o-mini but at 0.9
  would erase most classification silent failures.

## 6. What was built/fixed in the last two weeks (commit history, newest first)

| Commit | What |
|---|---|
| `8c52f0a` | W2: fragility, power, Figs 4.1–4.5 (`analysis/figures.py`), F-C8 correction, Ch3 mixed-effects claims removed |
| `4beb799` | Lockfile + `make lock`; W1 closed; W2 revised to include power analysis |
| `7c90d47` | One silent-failure definition (`is_silent_failure`), `analysis/silent_definition.py`, invariant 8 |
| `24745a7` | Kafka/Airflow/Postgres quarantined to `infra_unused/`; 6 false claims fixed |
| `f80a898` | RQ6 findings + Fig 4.6 |
| `748d643` | AIRS curve sensitivity + Fig 4.7 |
| `feb7d63` | GitHub Actions removed; `make ci`; `langchain-anthropic` was never declared |
| `43af46f`, `47fe9f8` | `REVIEW.md` (adversarial audit) + `docs/plan.md` |

## 7. Honest limitations already recorded (do not rediscover)

- Pipeline "batch vs streaming" is **simulated** as inherent staleness 3.0 s / 0.05 s — no
  Kafka/Airflow runs. Stated in Ch3 §3.7 and `infra_unused/README.md`.
- Latency runs analytically (`sleep=False`); its null shares one cause — never call
  it "independent routes".
- Agent is **one LLM call** — the "is this agentic?" gap; the refetch arm (W6–W7) addresses it.
- Synthetic faults; one model for most arms; n = 3–4 replications.
- AIRS target constants remain underived — a limitation to state, not fix.
