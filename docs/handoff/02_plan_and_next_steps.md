# Handoff 2/3 — Plan and next steps

Authoritative week-by-week plan: **`docs/plan.md`**. Adversarial audit and product
spec: **`REVIEW.md`** (Phase 3 = product, Phase 4 = plan). This file is the
condensed "what to do next" view.

---

## 1. Immediate next step: W3 — the product (starts now, ~20 h/week × 3 weeks)

W1 and W2 are done. **W3–W5 build the product and end at M1, Fri 16 Oct.**

### The product decision (confirmed by the author — do not re-litigate)

> Not a defence prop. **A real tool a data engineer uses on their own pipeline**;
> the defence is just one place it is shown. Offline replay is a feature, not the
> point.

- **Distribution:** `pip install airs-bench` → `airs serve` → opens `localhost:8000`.
- **Stack:** **FastAPI backend** serving the **static-exported Next.js** frontend
  (existing `demo/`, 833 LOC, builds). One process, one command. Streamlit rejected.
- **Why a backend:** scoring logic must never be reimplemented in TypeScript
  (`test_controller_and_replay_agree` exists because two implementations drift).
- **Why offline:** `probe` and `gate` are pure arithmetic — no model, no key, no
  network. Customer data never leaves the laptop. That is a product feature.
- No SaaS (would mean handling other people's production data).

### Three modes

| Mode | What | Needs |
|---|---|---|
| **A — "Check my pipeline"** *(the product)* | User drops JSONL sample (delivered + optional upstream). Shows per-dimension scores with evidence strings, weight-coverage warning (unmeasured ≠ 100), task profile switch (retrieval-like / classification-like — weights invert), **recommended gate policy**, **predicted exchange rate** with the ~75% agent-intrinsic caveat, **weakest dimension shown beside composite** (RQ6/fragility: harm tracks the worst fault), printable one-page report. Plus "generate a sample from Kafka / Postgres / Parquet" snippets. | no LLM, offline |
| **B — "Why should I trust this?"** *(the evidence / defence)* | Walkthrough over the 302 runs: break the pipeline → accuracy drops → **confidence stays high; user guesses which answers are wrong and fails (AUC 0.501)** → gate on → failures caught → exchange-rate bill → staleness policy on retrieval catches almost nothing. **Trace view:** upstream / delivered / answered three-column diff + "answer-key moved vs agent impaired" label. | pre-baked data, offline |
| **C — "Watch it live"** *(optional)* | Real gpt-4o-mini calls on a live-degrading stream, spend-capped (~$0.06 / 15 min). Only if ahead of schedule. | API key |

**Single data contract** for all modes (UI never branches):
```
Tick { t, config{fault,severity,pipeline,task},
       airs{freshness,latency,consistency,semantic,total,covered},
       record{id, upstream{}, delivered{}, corrupted_fields[]},
       decision{answer, truth, correct, abstained, confidence, flipped},
       gate{admitted, violations[], reason},
       running{n, correct, silent, prevented, forfeited, exchange_rate} }
```
Mode A emits one Tick per batch with `decision` null; B replays a pre-baked array;
C streams over WebSocket.

### Build order and hours (from `docs/plan.md`)

| Week | Dates | Work | h |
|---|---|---|---|
| **W3** | 28 Sep–2 Oct *(can start now)* | FastAPI backend: `/score`, `/policy`, `/replay`, static serving (8) · `airs serve` entry point + clean-venv pip install verified (4) · Mode A input: drop/paste JSONL, validation errors that name the fix (4) · Mode A scoring view (4) | 20 |
| **W4** | 5–9 Oct | Task-profile switch (3) · recommended policy from calibration + attribution (6) · predicted exchange rate (5) · report export (6) | 20 |
| **W5** | 12–16 Oct | Mode B walkthrough (10) · trace view (6) · packaging + offline verification (2) · **supervisor presentation** (2) | 20 |

**Checkpoint Fri 9 Oct:** a stranger can score their own JSONL end to end and print a
report — else cut Mode B to a static explainer.

### Before writing W3 code, the new session should read
`src/airsbench/probe.py`, `src/airsbench/gate/` (policy, controller, replay,
`__main__`), `examples/probe/`, `examples/gate/`, `demo/` (structure, `src/data/aist.json`,
`export_demo_data.py`), `src/airsbench/airs/calibrated_weights.json`, `pyproject.toml`
(extras), and `REVIEW.md` Phase 3.

---

## 2. After M1

| Week | Dates | Work |
|---|---|---|
| **W6–W7** | 19–30 Oct | **Refetch arm** (reshaped multi-step arm): give the agent a `refetch(record_id)` tool. Does *acting* on suspicion succeed where *being told* the age failed? Gives the gate a third verdict (refuse / refetch / admit) — each with its own exchange rate. New seed block 90 000–100 000, dry-run first, ~36 runs, ~$1.50, Fig 4.9. **HARD CUT Fri 30 Oct** — if runs not executed, drop the arm. |
| **W8** | 2–6 Nov | Integrate refetch into product; Mode C only if ahead · **positioning vs ISO/IEC 25012, data contracts, AgentBench/tau-bench/WebArena** (zero mentions today, REVIEW F-A1, 4 h) · **full-text read of 4 load-bearing papers** (Shisher & Sun 2022; Gupta 2026 ReliabilityBench; Rumiantsau & Fokeev 2026; Advani 2026 — REVIEW F-A2, 8 h) · Zenodo DOI + `CITATION.cff` |
| — | **Fri 6 Nov** | **Implementation freeze.** |

## 3. Thesis writing (W9–W12, 9 Nov–4 Dec, 80 h, together)

Order: **Ch3 → Ch4 → Ch2 → Ch1 + Ch5** (Introduction last so it promises what was
delivered). Write in Markdown, convert to the institutional template at the end
(template arriving soon; register: casual professional).

| Ch | h | Sources |
|---|---|---|
| 3 Methodology | 12 | `docs/chapter3_methodology.md` (drafted, corrected in W1–W2) + add probe, gate, interaction, sensitivity, fragility, power, refetch |
| 4 Results | 20 | 10 findings docs + Figs 4.1–4.9 + Fig 3.1, all already built |
| 2 Literature | 16 | `literature_review.md`, `related_work_positioning.md` + W8 positioning |
| 1 Introduction | 10 | `research_plan_original.md` Ch1–2 |
| 5 Discussion | 12 | restated recommendation, threats to validity (REVIEW Phase 1G) |
| Front/back, template, refs | 10 | citation hygiene rule in `CLAUDE.md` |

**Checkpoint Fri 27 Nov:** Ch 2–4 drafted, else shorten Ch5. W13–W14 = defence prep
(slides, cold demo rehearsal on venue machine, the 12 kill questions in REVIEW Phase 2).

## 4. Open findings to carry (from `REVIEW.md`)

| ID | Status | What |
|---|---|---|
| **F-C7** | **OPEN** | Cluster-robust test anti-conservative for cell comparisons (α ≈ 0.12). Fix: wild cluster bootstrap or CR2 errors, ~3 h, $0. Three cell p-values in (0.01, 0.05) must not be called significant until then. *Not in plan — ask the author where it goes.* |
| F-A1 | W8 | ISO 25012 / data contracts / agent benchmarks positioning |
| F-A2 | W8 | Read the 4 load-bearing papers in full |
| F-B1 | limitation | AIRS constants underived — state in Ch3/Ch5; sensitivity doc already quantifies |
| F-C4 | polish | No multiple-comparison correction across 8 interaction contrasts |
| F-E5 | W8 | Zenodo DOI |
| Kill Q3 | W6–W7 | "Is one API call agentic?" → refetch arm |
| Fragility predictability | idea | Is fragility predictable from question features? Would give a per-question readiness signal for the product. Not scheduled. |

## 5. Cut list (decided — do not reopen)

Real Kafka/Airflow pipeline · leading-indicator/AIRS-drift arm · third task domain /
fifth model · `airs lint` · generic multi-step agent (replaced by refetch arm) ·
Streamlit rewrite · SaaS hosting · GitHub Actions (replaced by `make ci`).
