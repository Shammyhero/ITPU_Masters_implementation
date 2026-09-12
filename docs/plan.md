# Week-by-week plan — internship implementation and thesis document

**Author:** Shamsiddin Khamidov · **Written:** 2026-09-12 · **Supersedes** the
roadmap in `campaign_status.md`.

**Capacity:** 20 h/week, 14 weeks, **~260 h total.**
**Evidence base for this plan:** `REVIEW.md` (adversarial audit, 2026-09-12).

## Two hard milestones

| | Date | What must be true |
|---|---|---|
| **M1** | **Fri 16 Oct 2026** | Internship ends. `airs serve` runs on the supervisor's screen. All experimental results collected. Every Chapter 4 figure exists. |
| **M2** | **Fri 04 Dec 2026** | Thesis document submitted. |

Implementation **freezes Fri 06 Nov**. November is writing. December is defence.

## Three rules that govern every week below

1. **Every analysis emits its Chapter 4 figure the day it is written.** A
   finding without its figure is not done. This is why Chapter 4 costs 20 h in
   November instead of 50 h.
2. **No paid run without `--dry-run` first.** $4.58 OpenAI / $1.27 Anthropic
   remain. One arm is funded; there is no budget for a second attempt.
3. **Write in Markdown, convert to the template at the end.** Do not author
   inside the institutional template — it will arrive late and reformatting
   costs days.

## Budget summary

| Stage | Weeks | Hours | API cost |
|---|---|---|---|
| Survival fixes | W1 | 20 | $0 |
| Evidence, figures & power | W2 | 21 | $0 |
| The product | W3–W5 | 60 | $0 |
| Refetch arm | W6–W7 | 40 | ~$1.50 |
| Integration & freeze | W8 | 20 | ~$0.20 |
| Thesis document | W9–W12 | 80 | $0 |
| Defence | W13–W14 | 20 | $0 |
| **Total** | | **261** | **~$1.70** |

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

Nothing else starts until this lands. These remove two of the three defence
questions currently unanswerable (`REVIEW.md` Phase 2, Q1 and Q2).

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

**Gate — Fri 18 Sep:** all eight done. If not, W2 does not start; finish these
first. They are survival, not enhancement.

## W2 · Mon 21 – Fri 25 Sep · Evidence, figures & power · 21 h · $0

| Task | h | Output |
|---|---|---|
| **Query-level fragility** — module + tests + write-up. Different faults fail the *same* queries (2.0–4.4× chance overlap); 30–48% of fault-induced silent failures were already silent at baseline | 10 | `analysis/fragility.py`, `docs/fragility_findings.md` + **Fig. 4.8** |
| Remaining Chapter 4 figures — 4.6 and 4.7 were built in W1 | 6 | **Figs. 4.1–4.5** |
| **Simulation-based power analysis** (REVIEW F-C6) — clustering-adjusted minimum detectable effect per RQ, from the intraclass correlation observed in the existing runs. RQs v2 §6 requires it before the results chapter; added 2026-09-13 using W1's slack | 5 | `analysis/power.py`, Ch. 3 table, RQs v2 §6 rewritten |

**The Chapter 4 figure set, complete by Fri 25 Sep:**

| Fig | Content | Source |
|---|---|---|
| 4.1 | Freshness sweep — exposure × conditional rate | `freshness_sweep.py` |
| 4.2 | Flip partition — raw vs residual impairment by fault | `flip_partition.py` |
| 4.3 | AIRS vs silent-failure rate, run level, held-out ρ | `airs_calibration.py` |
| 4.4 | **ROC: AIRS vs agent confidence (AUC 0.501)** — the headline slide | `airs_calibration.py` |
| 4.5 | Gate coverage vs residual trade-off curve | `gate/replay.py` |
| 4.6 | Interaction — observed vs additive prediction | W1 |
| 4.7 | AIRS curve sensitivity tornado | W1 |
| 4.8 | Query fragility — overlap vs chance | W2 |
| 4.9 | *(reserved for the refetch arm, W7)* | W7 |

**Gate — Fri 25 Sep:** every figure above exists and regenerates with
`make figures`, and the power analysis reports a minimum detectable effect per RQ. **If missed, cut the refetch arm now** — not in October.

## W3 · Mon 28 Sep – Fri 02 Oct · Product: backend + Mode A core · 20 h · $0

| Task | h |
|---|---|
| FastAPI backend: `/score`, `/policy`, `/replay`; serve the static Next.js build | 8 |
| `airs serve` console entry point; `pip install` path verified in a clean venv | 4 |
| **Mode A input** — drop/paste JSONL, directory pointer, validation errors that name the fix | 4 |
| **Mode A scoring view** — per-dimension bars, evidence strings, weight-coverage warning | 4 |

## W4 · Mon 05 – Fri 09 Oct · Product: Mode A complete · 20 h · $0

| Task | h |
|---|---|
| Task-profile switch (retrieval-like / classification-like) with the inversion stated explicitly | 3 |
| **Recommended policy** generated from the calibration + attribution table | 6 |
| **Predicted exchange rate**, with the ~75%-agent-intrinsic caveat shown, not buried | 5 |
| **Report export** — printable one-page AIRS Readiness Report | 6 |

**Gate — Fri 09 Oct:** a stranger can score their own JSONL end to end and print
a report. **If missed, cut Mode B to a static explainer** and ship the product
without the walkthrough.

## W5 · Mon 12 – Fri 16 Oct · Product: Mode B + M1 · 20 h · $0

| Task | h |
|---|---|
| **Mode B walkthrough** — the six-step sequence over the 302 committed runs | 10 |
| **Trace view** — upstream / delivered / answered three-column diff with flip classification | 6 |
| Packaging: bundled demo data, offline verification, README | 2 |
| **Supervisor presentation** — rehearse, present | 2 |

### ► MILESTONE 1 — Fri 16 Oct 2026
Internship ends. `airs serve` runs. All results collected. Figures 4.1–4.8 exist.

## W6 · Mon 19 – Fri 23 Oct · Refetch arm: build · 20 h · $0

The multi-step arm, reshaped. Gives the agent a `refetch(record_id)` tool:
*metadata did not make it cautious — does the ability to act on suspicion?*
Answers "is this agentic?", revives the detectability null, and gives the gate a
third verdict.

| Task | h |
|---|---|
| Arm design doc — hypothesis, conditions, seed block (90 000–100 000), quarantine | 4 |
| `refetch` tool + two-step agent loop | 8 |
| Tests: tool-call accounting, loop termination, paired design preserved | 4 |
| Dry-run, cost estimate, grid inspection | 4 |

## W7 · Mon 26 – Fri 30 Oct · Refetch arm: run + gate action · 20 h · ~$1.50

| Task | h |
|---|---|
| Execute ~36 runs (monitored; `--offset` resume if the laptop sleeps) | 4 |
| Analysis + **Fig. 4.9** | 6 |
| **Third gate verdict** — refuse / refetch / admit, each with its own exchange rate | 6 |
| `docs/refetch_findings.md` | 4 |

**► HARD CUT — Fri 30 Oct:** if the runs are not executed, **cut the arm
entirely** and carry the hours into W8. It must not touch November.

## W8 · Mon 02 – Fri 06 Nov · Integration & freeze · 20 h · ~$0.20

| Task | h |
|---|---|
| Integrate refetch results into the product; Mode C live stream *only if ahead* | 6 |
| **Positioning gap** — ISO/IEC 25012, data contracts, agent-benchmark precedent (currently zero mentions anywhere) | 4 |
| **Full-text read of the four load-bearing papers** — Shisher & Sun, Gupta, Rumiantsau & Fokeev, Advani | 8 |
| Zenodo DOI + `CITATION.cff`; final repo tidy | 2 |

### ► IMPLEMENTATION FREEZE — Fri 06 Nov 2026
No new features after this date, regardless of state.

---

# Part 2 — Thesis document (W9–W12, Mon 09 Nov – Fri 04 Dec, 80 h)

Written together. Markdown first, template conversion last.

## Chapter-to-source map

| Chapter | h | What it is built from |
|---|---|---|
| **1 Introduction** | 10 | `research_plan_original.md` Ch. 1–2 · needs 2026 framing, the contribution in one sentence, grey literature clearly labelled |
| **2 Literature review** | 16 | `literature_review.md` (strong raw material) + `related_work_positioning.md` · **must add** ISO/IEC 25012, data contracts, agent-benchmark precedent (W8) |
| **3 Methodology** | 12 | `chapter3_methodology.md` (5.3 k words drafted) · **must add** probe, gate, interaction arm, sensitivity analysis, refetch arm, and the honest "archetypes are simulated" framing |
| **4 Results** | 20 | Nine findings docs + Figs. 4.1–4.9 **already built** · assembly and prose, not analysis |
| **5 Discussion & conclusion** | 12 | Restated recommendation, threats to validity (`REVIEW.md` Phase 1G), future work |
| Front/back matter, template, references | 10 | Citation hygiene rule in `CLAUDE.md`: every source verified against publisher or arXiv |

## W9 · Mon 09 – Fri 13 Nov · Ch. 3 + Ch. 4 skeleton · 20 h

Start with Methodology and Results, not the Introduction — they are the most
drafted and the least negotiable, and writing them tells you what Ch. 1 must
promise.

| Task | h |
|---|---|
| **Ch. 3 Methodology** — revise the existing draft for everything built since July | 12 |
| **Ch. 4 skeleton** — section structure, place all nine figures with captions | 8 |

## W10 · Mon 16 – Fri 20 Nov · Ch. 4 Results · 20 h

| Task | h |
|---|---|
| **Ch. 4 §1–3** — RQ1 freshness, RQ2 flip partition, RQ3 decision models | 10 |
| **Ch. 4 §4–6** — RQ4 calibration + sensitivity, RQ5 cross-model, RQ6 interaction + fragility | 10 |

## W11 · Mon 23 – Fri 27 Nov · Ch. 4 close + Ch. 2 · 20 h

| Task | h |
|---|---|
| **Ch. 4 §7** — the gate, its price, and the refetch arm | 6 |
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
| Slides — findings first, method second; the 0.501 ROC is the anchor slide | 8 |
| **Product demo rehearsed cold** on the venue machine; USB static export + Vercel URL + 3-minute recording as independent paths | 6 |
| Kill-question rehearsal — the twelve in `REVIEW.md` Phase 2, out loud | 6 |

---

# Checkpoint summary

| Date | Gate | If missed |
|---|---|---|
| Fri 18 Sep | W1 survival fixes complete | Stop; nothing else starts |
| Fri 25 Sep | Figs. 4.1–4.8 exist, `make figures` works, power analysis done | Cut the refetch arm now |
| Fri 09 Oct | Mode A works on a stranger's JSONL | Mode B becomes a static explainer |
| **Fri 16 Oct** | **M1 — product runs, results collected** | Non-negotiable |
| Fri 30 Oct | Refetch runs executed | **Hard cut the arm** |
| **Fri 06 Nov** | **Implementation freeze** | Freeze regardless of state |
| Fri 27 Nov | Ch. 2, 3, 4 drafted | Shorten Ch. 5 |
| **Fri 04 Dec** | **M2 — submission** | — |

# Risk register

| Risk | P | Impact | Mitigation |
|---|---|---|---|
| **Writing slips past early December** | High | **Fatal** | 80 h budgeted; figures pre-built in Sept; hard freeze 06 Nov; W11 gate drops Ch. 5 depth rather than shipping incomplete |
| Product scope creeps past M1 | High | High | Mode C explicitly optional; Oct 09 gate degrades Mode B |
| Refetch arm over-runs or the design breaks | Med | Med | Hard cut 30 Oct; it sits after M1 so failure costs nothing downstream |
| Sensitivity analysis undermines a headline | Med | Low | Already measured — retrieval and latency survive; freshness magnitude and classification ordering get softened. Found now, not at the defence |
| Template arrives late | Med | Med | Author in Markdown, convert in W12 |
| Budget exhausted | Low | Med | $4.58 left, arm needs ~$1.50, dry-run mandatory |
| Laptop sleeps mid-run | Med | Low | `--offset` resume; happened 17 Aug |
| Defence date lands earlier than expected | Med | High | W13–W14 are buffer; if the date moves to early Dec, defence prep absorbs W12's read-through |
