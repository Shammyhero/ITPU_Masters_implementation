# Campaign status & session handoff

**Updated:** 2026-07-27 · phase 1 in progress

This is the operational entry point. Read `CLAUDE.md` for the invariants that
must not be broken, then this file for what to do next.

---

## Where things stand

| | |
|---|---|
| Design | Paired, replication-major, 144 runs @ 80 queries |
| **Phase 1** | **~25 / 36 runs** (one full balanced replication of all 36 conditions) |
| Spent | ~$0.29 of ~$7 OpenAI · $0 of ~$4 Anthropic |
| Results | `results/runs/*.json` — one file per run, written on completion |
| Tests | 70 passing |

**Resume / continue phase 1** (offset = number of completed runs):

```bash
ls results/runs/*.json | wc -l          # → N
python -m airsbench.runner.run --main --n-queries 80 --offset N --limit $((36-N)) --max-cost 1.00
```

Resumption is exact: `build_grid()` is deterministic and each run writes its
JSON on completion. Interrupting mid-run loses only that run's partial spend.

---

## Immediate next step

When phase 1 reaches 36 runs:

```bash
python -m airsbench.analysis.phase1_check
```

Four automated checks — coverage, floors, coherence, effects — ending in an
explicit **GO** or **NO-GO**. This checkpoint has already returned NO-GO twice
and caught two design defects that would have made the campaign
uninterpretable (see `results/discarded/README.md`). Do not skip it.

---

## Roadmap after GO

| # | Step | Command / note | Cost |
|---|---|---|---|
| 1 | Phase 2 — remaining 108 runs | `--main --n-queries 80 --offset 36 --max-cost 2.00` | ~$1.17 |
| 2 | Freshness sweep (RQ1 monotonicity) | `--freshness-sweep --n-queries 60 --replications 3` | ~$0.29 |
| 3 | Cross-model: open weights | local via Ollama | $0 |
| 4 | Cross-model: different provider | `--cross-model claude-haiku-4-5 --n-queries 100` | ~$1.68 |
| 5 | Statistical analysis | notebook: RQ1–RQ5 per `research_questions_v2.md` §5 | $0 |
| 6 | AIRS calibration | logistic regression → weights; validate on held-out 20%; **compare against agent-confidence baseline** (data already logged) | $0 |
| 7 | `airs probe` | standalone: score an arbitrary pipeline. The artifact that makes "pre-deployment" concrete — a stated success criterion | $0 |
| 8 | AIST demo rebuild | around **detectability**: fresh vs stale side-by-side, same agent, same question, higher confidence on the wrong answer; AIRS red before accuracy moves | $0 |
| 9 | `airs lint` *(stretch)* | static semantic-completeness scoring for schemas/data contracts — reuses `semantic_completeness()`; first thing to cut if time is short | $0 |
| 10 | Release + chapters | HuggingFace + Zenodo DOI; Results, Discussion, Conclusion | $0 |

**Writing runs in parallel throughout.** Chapter 3 is drafted
(`docs/chapter3_methodology.md`). Chapters 1 and 2 follow from
`literature_review.md` §7 and `research_questions_v2.md` §8. The project's own
risk register rates late writing High/High — it is the likeliest failure mode.

---

## Findings so far (phase 1, partial, n=80/run, one replication)

Indicative only — Wilson 95% half-width at n=80 is ±0.10, so single-run
differences under ~10 points mean nothing on their own. The primary analysis
pools to the decision level (~11,500 observations).

| streaming / retrieval | accuracy | silent failure | abstention |
|---|---|---|---|
| baseline | 0.861 | 13% | 0% |
| freshness mild | 0.810 | 18% | ~1% |
| freshness severe | 0.785 | 20% | ~1% |
| latency mild | 0.861 | 13% | 0% |
| latency severe | 0.873 | 11% | 0% |

| batch / retrieval | accuracy | silent failure |
|---|---|---|
| baseline | 0.810 | 19% |
| schema drift severe | 0.684 | 32% |

Three things worth carrying forward:

1. **Freshness degrades monotonically; latency does not move.** Both are
   "infrastructure problems," but only one corrupts what the agent knows.
2. **Freshness drives silent failure with zero abstention** — the agent never
   signals that anything is wrong, which is H3's prediction for an invisible
   fault.
3. **Streaming baseline (0.861) > batch baseline (0.810)** — the architecture
   contrast, in the expected direction, now that batch is no longer floored.

Semantic stripping under streaming — the sharpest test of H3 — is in the runs
not yet complete.

---

## Context for a fresh session

Everything needed to continue is in the repo:

- `CLAUDE.md` — invariants, budget discipline, known traps, layout
- `docs/research_questions_v2.md` — RQs, hypotheses, stats plan, declared parameters
- `docs/chapter3_methodology.md` — methodology as implemented
- `docs/literature_review.md` — verified sources, defensible gap statement
- `docs/related_work_positioning.md` — differentiation vs the four nearest papers, plus rehearsed defence Q&A
- `results/discarded/README.md` — the defects the checkpoint caught, and why those runs are invalid
- `git log` — commit messages record the reasoning behind each design change

The two things a new session is most likely to get wrong: **spending money
without a dry-run first**, and **breaking the paired design** by deriving query
sampling from the condition seed. Both are covered in `CLAUDE.md`.
