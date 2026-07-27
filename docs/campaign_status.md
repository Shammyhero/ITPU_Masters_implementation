# Campaign status & session handoff

**Updated:** 2026-07-27 · **phase 2 deliberately paused at 66/144**

This is the operational entry point for any session. Read `CLAUDE.md` first for
the invariants that must not be broken, then this file for what to do next.

---

## State

| | |
|---|---|
| Design | Paired, replication-major, 144 runs @ 80 queries |
| Phase 1 | ✅ **complete — GO** (36/36, all four checks passed) |
| Phase 2 | ⏸ **paused at 30/108** by decision, not by failure |
| Runs on disk | **66 / 144** in `results/runs/*.json` |
| Spent | **$0.70** of ~$7 OpenAI · $0 of ~$4 Anthropic |
| Tests | 97 passing · lint clean |
| Open decision | AIRS freshness was double-counted on 12 runs — `detectability_arm.md` §8 |
| Analysis | flip partition ✅ — see `docs/flip_partition_findings.md` |

Resumption is exact: `build_grid()` is deterministic and every run writes its
JSON on completion. Interrupting mid-run loses only that run (~$0.01).

```bash
ls results/runs/*.json | wc -l    # → N, the offset to resume from
```

---

## ⚠️ Read before resuming: why phase 2 is paused

A question mid-campaign — *"why should the agent doubt the price?"* — exposed
that the rendered record carries **no timestamp, no age, nothing about when the
value was true**. The agent was never given anything by which staleness could be
detected.

So the phase-1 reading was wrong in an important way:

- ❌ "The agent failed to notice the data was stale" — blames the agent
- ✅ **"The pipeline delivered nothing to notice"** — blames the infrastructure

The second is an infrastructure finding with an actionable remedy, and it turns
H3 from an interpretation into a testable causal claim. **Read
`docs/detectability_arm.md` before spending anything further.** Framing is far
cheaper to fix before the remaining 78 runs than after.

---

## Next steps, in order

| # | Step | Cost | Why this order |
|---|---|---|---|
| ~~1~~ | ~~**Flip-partition analysis**~~ | $0 | ✅ **done** — `docs/flip_partition_findings.md`. Changed how freshness *and* RQ2 must be reported. |
| 2 | **Detectability arm** — 14 runs, freshness severe ± `_record_age_seconds` | **$0.152** | ✅ implemented + tested + dry-run; **awaiting the decision to spend.** Pre-registered baseline to move: 5% abstention, 89% silent failure. `--detectability --n-queries 80 --max-cost 0.30` |
| 3 | **Finish phase 2** — `--main --n-queries 80 --offset 66 --limit 78 --max-cost 2.00` | ~$0.85 | Gives the ranking and thresholds regardless of how (1) and (2) land. |
| 4 | Freshness sweep — `--freshness-sweep --n-queries 60 --replications 3` | ~$0.29 | RQ1 monotonicity (Shisher & Sun) |
| 5 | Cross-model: local open weights via Ollama | $0 | |
| 6 | Cross-model: `--cross-model claude-haiku-4-5 --n-queries 100` | ~$1.68 | Haiku, not Sonnet 5 — it still accepts `temperature` |
| 7 | Statistical analysis | $0 | Per `research_questions_v2.md` §5 — decision-level mixed-effects logistic, not ANOVA on run means |
| 8 | AIRS calibration | $0 | Target **silent failure**; benchmark against agent self-confidence (already logged) |
| 9 | `airs probe` | $0 | Standalone pipeline scorer — makes "pre-deployment" concrete |
| 10 | AIST demo rebuild | $0 | Around detectability: same stale record with/without its age, side by side |
| 11 | `airs lint` *(stretch)* | $0 | Static semantic-completeness for schemas; first to cut if time is short |
| 12 | Release + chapters | $0 | HuggingFace, Zenodo DOI, Results/Discussion/Conclusion |

**Writing runs throughout.** Chapter 3 is drafted. Chapters 1–2 follow from
`literature_review.md` §7 and `research_questions_v2.md` §8. The project's own
risk register rates late writing High/High — it is the likeliest failure mode.

---

## Phase 1 results (final — 36 runs, all conditions, $0.371)

Verdict: **GO.** No floored arm, no incoherent comparison, 3 of 4 faults degrade
accuracy at severe. Re-runnable any time with
`python -m airsbench.analysis.phase1_check`.

| fault (severe) | accuracy | Δ vs baseline | abstained | silent failure |
|---|---|---|---|---|
| baseline | 0.877 | — | 0% | 12% |
| latency | 0.877 | **0.000** | 0% | 12% |
| freshness | 0.748 | −0.129 | 1% | **25%** |
| schema drift | 0.748 | −0.129 | 1% | **24%** |
| semantic stripping | **0.648** | **−0.230** | **23%** | 17% |

Baselines by arm: streaming/classification 0.938 · batch/classification 0.900 ·
streaming/retrieval 0.861 · batch/retrieval 0.810.

**Four things to carry forward:**

1. **Latency measured exactly 0.000 effect at both severities.** Correct for a
   synchronous agent with no deadline — it waits and reads identical data. A
   finding to frame, not a bug.
2. **Semantic stripping does the most damage *and* is the only fault the agent
   detects** — abstention 0% → 23%. It refuses rather than guessing.
3. **Freshness does less damage but produces more silent failure** (25% vs 17%)
   at ~1% abstention. The agent never signals a problem.
4. **Schema drift was predicted "visible" but behaves invisible** (1% abstention,
   24% silent). A renamed field still looks like a legitimate field. So the
   operative property is not visible/invisible but **whether the corruption is
   legible *as* corruption** — a sharper claim than H3 as originally written.

---

## Resolved: freshness accuracy was near-arithmetic — it is, entirely

**Settled by the flip-partition analysis. Full write-up in
`docs/flip_partition_findings.md`; re-runnable free with
`python -m airsbench.analysis.flip_partition`.**

On queries whose correct answer did *not* move, accuracy is baseline 0.860 vs
freshness/severe **0.868** — zero residual. Freshness costs accuracy exactly and
only where it moved the answer key, and does not impair the agent's reasoning at
all. The 12.9-point drop must never be reported as a result about the agent.

The finding is the other cell. On the 63 queries staleness made unanswerable:

| abstained | silent failure | chose the answer the served data implied | confidence when wrong |
|---|---|---|---|
| **5%** | **89%** | **71%** | **1.00** |

The agent is not making mistakes — it is reasoning correctly over corrupt input
and reporting the result at maximal confidence. Two further consequences:

- **The RQ2 damage ranking changes.** On residual (non-mechanical) impairment:
  schema drift −0.159 > semantic stripping −0.093 > freshness +0.008 ≈ latency 0.
  Semantic stripping is *not* the most damaging fault — most of its raw drop is
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
