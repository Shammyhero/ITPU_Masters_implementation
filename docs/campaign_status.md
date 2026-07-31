# Campaign status & session handoff

**Updated:** 2026-07-31 · **all five paid/free arms COMPLETE — 230 runs**

This is the operational entry point for any session. Read `CLAUDE.md` first for
the invariants that must not be broken, then this file for what to do next.

---

## State

| | |
|---|---|
| Design | Paired, replication-major, 144 runs @ 80 queries |
| Phase 1 | ✅ **complete — GO** (36/36, all four checks passed) |
| Phase 2 | ✅ **complete** — 78/78, zero failures |
| Runs on disk | **144** main · **14** detectability · **36** sweep · **36** local cross-model |
| Spent | **$1.91** of ~$7 OpenAI · $0 of ~$4 Anthropic |
| Tests | 235 passing · lint clean |
| AIRS fix | freshness double-count corrected in code; 16 old runs recomputed in the analysis layer |
| Analysis | RQ1 ✅ · RQ2 ✅ · RQ3 ✅ · RQ5 (retrieval) ✅ · flip partition ✅ · detectability ✅ |

Resumption is exact: `build_grid()` is deterministic and every run writes its
JSON on completion. Interrupting mid-run loses only that run (~$0.01).

```bash
python -m airsbench.analysis.campaign_state
```

Prints per-arm progress and the exact resume command. **Do not count files for
the offset** — `--offset` indexes into `build_grid()`, but the results directory
now also holds the detectability arm (and later the sweep and cross-model
subset), so counting over-reports it and silently skips runs. `campaign_state`
matches artifacts to grid entries by seed instead, and refuses to emit a resume
command if completed runs are not a contiguous prefix.

---

## Why phase 2 was paused — resolved, and phase 2 has since completed

A question mid-campaign — *"why should the agent doubt the price?"* — exposed
that the rendered record carried **no timestamp, no age, nothing about when the
value was true**. The agent was never given anything by which staleness could be
detected, so the phase-1 reading blamed the agent for missing what the pipeline
never delivered.

Both follow-ups ran before the remaining 78 runs, which was the point of pausing
— framing is cheaper to fix before the data than after:

- The **flip partition** showed freshness does not impair the agent at all — it
  only moves the answer key. The finding is the 90% silent-failure rate on the
  queries it makes unanswerable.
- The **detectability arm** delivered the record's age and **nothing changed**.
  The reframing holds, but its obvious remedy does not: the pipeline delivering
  nothing to notice is the problem, and delivering the number alone is not the
  fix. Ship the age *and* the staleness budget, and enforce the budget outside
  the model.

Net effect on the conditions: **none.** Phase 2 ran the design unchanged; what
changed is how its results are read.

---

## Next steps, in order

| # | Step | Cost | Why this order |
|---|---|---|---|
| ~~1~~ | ~~**Flip-partition analysis**~~ | $0 | ✅ **done** — `docs/flip_partition_findings.md`. Changed how freshness *and* RQ2 must be reported. |
| ~~2~~ | ~~**Detectability arm**~~ | $0.153 | ✅ **done — null branch.** Metadata alone changes nothing. `docs/detectability_findings.md`. |
| ~~3~~ | ~~**Finish phase 2**~~ | $0.768 | ✅ **done — 144/144, zero failures.** All conclusions held and tightened at 4 replications. |
| ~~4~~ | ~~Freshness sweep~~ | $0.290 | ✅ **done — monotone on both tasks.** Threshold 5.05 s. `docs/freshness_sweep_findings.md`. |
| ~~5~~ | ~~Cross-model: local open weights~~ | $0 | ✅ **done — ranking transfers (mean τ +0.778).** Both models FLOOR on classification; retrieval only. `docs/cross_model_findings.md`. |
| **6** | Cross-model: `--cross-model claude-haiku-4-5 --n-queries 100` | ~$1.68 | **← next, and now the strongest remaining use of budget.** Both local models floored on classification, so cross-model generalisation there is untested and needs a capable model. $5.09 of the OpenAI+Anthropic budget remains. |
| ~~7~~ | ~~Statistical analysis~~ | $0 | ✅ **done — RQ2 + RQ3 answered.** Freshness on answerable retrieval: **OR 1.00, p = 0.998**. `docs/statistical_analysis_findings.md`. |
| **8** | AIRS calibration | $0 | **← next (free).** Target **flip-conditioned** silent failure; benchmark against agent self-confidence (already logged) |
| 9 | `airs probe` | $0 | Standalone pipeline scorer — makes "pre-deployment" concrete |
| 10 | AIST demo rebuild | $0 | Around detectability: same stale record with/without its age, side by side |
| 11 | `airs lint` *(stretch)* | $0 | Static semantic-completeness for schemas; first to cut if time is short |
| 12 | Release + chapters | $0 | HuggingFace, Zenodo DOI, Results/Discussion/Conclusion |

### Note on local models, for anyone re-running them

Ollama is installed and both models are pulled. Local throughput is **~4 s per
retrieval call**, not the ~1 s a naive benchmark suggests — a benchmark that
reuses one prompt hits llama.cpp's prompt cache, and real queries never do.
Budget ~90 min per 8B model at 1800 calls, ~2.5 h at 14B. Use `caffeinate -i -w
<pid>` and keep the lid open; closing it sleeps an Apple Silicon Mac regardless.

---

**Writing runs throughout.** Chapter 3 is drafted. Chapters 1–2 follow from
`literature_review.md` §7 and `research_questions_v2.md` §8. The project's own
risk register rates late writing High/High — it is the likeliest failure mode.

---

## Main factorial — final (144 runs, all conditions, $1.470)

Coverage balanced at 36 runs per arm, no floored arm, no coherence violation.
Re-runnable with `python -m airsbench.analysis.phase1_check`.

**Raw accuracy — necessary, but NOT the headline.** Freshness's drop here is
almost entirely mechanical; read this table through §"flip partition" below.

| fault (severe) | accuracy | Δ vs baseline | abstained | silent failure |
|---|---|---|---|---|
| baseline | 0.856 | — | 0% | 14% |
| latency | 0.856 | **+0.000** | 0% | 14% |
| freshness | 0.741 | −0.116 | 1% | **25%** |
| schema drift | 0.744 | −0.112 | 1% | **25%** |
| semantic stripping | **0.639** | **−0.218** | **18%** | 22% |

Baselines by arm: streaming/classification 0.900 · batch/classification 0.850 ·
streaming/retrieval 0.861 · batch/retrieval 0.762.

**Four things to carry forward:**

1. **Latency measured +0.000 effect at both severities.** Correct for a
   synchronous agent with no deadline — it waits and reads identical data. A
   finding to frame, not a bug.
2. **Semantic stripping is the only fault the agent reliably detects** —
   abstention 0% → 18%. It refuses rather than guessing. On *raw* accuracy it
   looks like the most damaging fault, but that is an artifact of counting a
   refusal as equal to a confident wrong answer; see the flip partition.
3. **Freshness produces the most silent failure** (25%) at ~1% abstention. The
   agent never signals a problem — and the arm below shows that handing it the
   record's age does not change this.
4. **Schema drift was predicted "visible" but behaves invisible** (1% abstention,
   25% silent) *and* does the most real damage to reasoning (residual −0.173).
   A renamed field still looks like a legitimate field. So the operative
   property is not visible/invisible but **whether the corruption is legible
   *as* corruption** — a sharper claim than H3 as originally written.

---

## Resolved: freshness accuracy was near-arithmetic — it is, entirely

**Settled by the flip-partition analysis. Full write-up in
`docs/flip_partition_findings.md`; re-runnable free with
`python -m airsbench.analysis.flip_partition`.**

On queries whose correct answer did *not* move, accuracy is baseline 0.888 vs
freshness/severe **0.886** — residual **−0.003 at both severities**, flat where a
real effect would grow with severity. Freshness costs accuracy exactly and only
where it moved the answer key, and does not impair the agent's reasoning at all.
The 11.6-point drop must never be reported as a result about the agent.

The finding is the other cell. On the 140 queries staleness made unanswerable:

| abstained | silent failure | chose the answer the served data implied | confidence when wrong |
|---|---|---|---|
| **4%** | **90%** | **75%** | **1.00** |

The agent is not making mistakes — it is reasoning correctly over corrupt input
and reporting the result at maximal confidence. Two further consequences:

- **The RQ2 damage ranking changes.** On residual (non-mechanical) impairment:
  schema drift −0.173 > semantic stripping −0.128 > freshness −0.003 ≈ latency 0.
  Semantic stripping is *not* the most damaging fault — much of its raw drop is
  abstention, which is the safe behaviour. Schema drift is.
- **The batch baseline is not clean.** With no fault injected, its inherent 3 s
  staleness flips 7.1% of answers and silently fails on **100%** of them.

---

## For a fresh session

Everything needed is in the repo — this file plus:

| File | What it carries |
|---|---|
| `CLAUDE.md` | The seven invariants, budget discipline, known traps, layout |
| `docs/detectability_arm.md` | **The pending design decision** — read before spending |
| `docs/flip_partition_findings.md` | Why freshness accuracy is not a result, and what is |
| `docs/detectability_findings.md` | The detectability arm's null, and why it is the useful answer |
| `docs/freshness_sweep_findings.md` | RQ1 answered: monotone, threshold 5.05 s, and the decomposition it rests on |
| `docs/statistical_analysis_findings.md` | RQ2 + RQ3 answered at decision level; why 'freshness' is two phenomena |
| `docs/cross_model_findings.md` | RQ5: the ranking transfers; both local models floor on classification |
| `docs/research_questions_v2.md` | Current RQs, hypotheses, stats plan, declared parameters. Supersedes the proposal. |
| `docs/chapter3_methodology.md` | Methodology as implemented (Chapter 3 draft) |
| `docs/literature_review.md` | 25+ verified sources; the gap claim as it can actually be defended |
| `docs/related_work_positioning.md` | Differentiation vs the four nearest papers + rehearsed defence Q&A |
| `results/discarded/README.md` | The two defects the checkpoint caught, and why those runs are invalid |
| `git log` | Reasoning behind every design change |

**The three things a new session is most likely to get wrong:**

1. Spending money without a `--dry-run` first.
2. Breaking the paired design by deriving query sampling from the condition seed.
3. Treating the go/no-go checkpoint as a formality — it has already returned
   NO-GO twice and caught two campaign-invalidating defects.

**To resume, say:** *"continue the AIRS thesis — read docs/campaign_status.md"*
