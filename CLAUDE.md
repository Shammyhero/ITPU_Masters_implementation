# CLAUDE.md

Master's thesis implementation: **Detectability Determines Danger — How Data
Infrastructure Faults Cause Silent Failure in Agentic AI Systems**
(Shamsiddin Khamidov, IT Park University, 2026).

This is a **scientific instrument**, not an application. Code correctness is
necessary but not sufficient — a change can pass every test and still invalidate
the experiment. Read §"Invariants" before touching `runner/` or `agentic_faults/`.

## Commands

```bash
make test            # pytest (must stay green — CI runs it on every commit)
make lint            # ruff
make grid            # inspect the factorial, no execution, no cost
make up / make down  # Kafka (KRaft) + Airflow + Postgres + Prometheus
make demo            # AIST Streamlit app

# Campaign — ALWAYS --dry-run first to see the cost estimate
python -m airsbench.runner.run --main --n-queries 80 --limit 36 --dry-run
python -m airsbench.runner.run --main --n-queries 80 --limit 36 --max-cost 1.00
python -m airsbench.runner.run --main --n-queries 80 --offset 36 --max-cost 2.00
python -m airsbench.runner.run --freshness-sweep --n-queries 60 --replications 3
python -m airsbench.runner.run --cross-model claude-haiku-4-5 --n-queries 100
python -m airsbench.dataprep.check_sensitivity --n 400   # free, no API calls
```

## Budget — real money, and tight

Roughly **$7 OpenAI / $4 Anthropic** for the whole study. Every paid command
takes `--max-cost`; the guard refuses to start above it and aborts mid-run if
spend exceeds it. **Never launch a paid run without a dry-run first.**

Approximate costs: phase 1 (36 runs × 80q) $0.39 · phase 2 (108 runs) $1.17 ·
freshness sweep $0.29 · Haiku cross-model arm $1.68.

`AVG_INPUT_TOKENS` in `runner/run.py` is calibrated against measured usage. If
prompts change materially, re-derive it from `results/runs/*.json` usage fields —
do not estimate from the templates (the original estimate ran 35% high and
blocked affordable runs).

## Invariants

Violating any of these silently corrupts results while leaving tests green and
output plausible. Each is pinned by tests; if a test here fails, the science is
wrong, not the test.

1. **The agent is the instrument, not the subject.** Model, prompt, temperature,
   dataset, scoring and hardware are held constant. Only infrastructure
   conditions vary. The prompt must never mention faults or hint that data may
   be degraded.

2. **Paired design.** Query/flight sampling derives from `RunConfig.sample_seed`
   — a function of `(task, replication)` **only**. Every condition within a
   replication must see identical inputs at identical simulated timestamps.
   `config.seed` drives the *injectors* (the fault realization is the treatment
   and should vary). → `tests/test_paired_design.py`

3. **Fault chain applied exactly once**, in the runner. Agents consume
   already-faulted records. Applying it in both places advances the injector RNG
   twice, so AIRS would score a *different* random realization than the agent
   received.

4. **Ground truth is the true world state at query time**, never what the agent
   was served. This asymmetry is the experiment. The retrieval loader replays
   the update stream to serve genuinely historical *values* — marking a record
   stale while serving current values would test metadata handling, not
   staleness.

5. **AIRS dimensions must move independently.** A fault targeting one dimension
   must not depress another, or RQ2's ranking and RQ4's regression become
   collinear. Semantic stripping records its name-opacity map so the consistency
   measure can reverse it. → `tests/test_dimension_independence.py`

6. **Unparseable agent output is a failure, not an error.** Never retry it —
   refusing or emitting garbage under degraded data is the phenomenon being
   measured. Only transport errors (network, rate limit) are retried.

7. **Postgres `benchmark_runs` is the canonical dataset.** Prometheus is for the
   live demo only and must never be a results source.

## Known traps

- **`BATCH_INHERENT_STALENESS_S` must stay well below
  `DEP_DELAY_KNOWLEDGE_HORIZON_S`.** At 10 s vs 10 s the batch arm zeroed the
  dominant classification feature and scored below chance.
- **Latency runs in analytic mode (`sleep=False`).** Sleeping cannot change what
  the agent reads, so it cannot change accuracy — it only added ~4 h of
  wall-clock. Expect the latency arm to show ≈no accuracy effect; that is a
  finding, not a bug.
- **Semantic stripping must opaquify field names.** Removing the context block
  alone leaves self-documenting keys (`DepDelay`, `price`) the model reads
  straight off. Without opacity the fault measurably does nothing.
- **Catalog velocity is load-bearing.** Staleness levels under test must be
  comparable to the mean inter-update interval, or freshness faults are a no-op.
  Re-run `check_sensitivity` (free) after changing stream parameters.
- **macOS Docker bind-mounts of single files go stale** when an edit changes the
  inode. Apply `schema.sql` by piping from the host, not via the mount.
- **Backgrounded Python buffers stdout.** Use `python -u`, or read progress from
  `results/runs/*.json` rather than the log.

## Citation hygiene

Every citation must be verified against its publisher or arXiv record before it
enters the thesis. The superseded clinical-topic coursework contains at least
one fabricated reference; **treat that entire list as contaminated.** Industry
sources (blogs, vendor posts) belong in Chapter 1 motivation, clearly labelled
grey literature — never in the peer-reviewed literature review.

## Layout

```
src/agentic_faults/      four record-level injectors + verification (stdlib only)
src/airsbench/airs/      AIRS operational definitions + calculator
src/airsbench/agents/    LLM client, prompts, retrieval + classification agents
src/airsbench/pipelines/ Kafka wrappers, Airflow DAG, catalog time machine
src/airsbench/runner/    grid, staged execution, scoring, benchmark_runs schema
src/airsbench/dataprep/  dataset prep (ESCI, BTS) + free sensitivity check
docs/                    literature review, related-work positioning, RQs v2,
                         Chapter 3 methodology
results/discarded/       runs from superseded designs — evidence, not data
```

## Start here

`docs/campaign_status.md` — current campaign state, the exact resume
command, the remaining roadmap with costs, and findings so far. It is the
operational entry point for any new session.

## Docs to read before changing the design

- `docs/research_questions_v2.md` — current RQs, hypotheses, stats plan,
  declared experimental parameters. **Supersedes the original proposal's RQs.**
- `docs/chapter3_methodology.md` — methodology as implemented
- `docs/literature_review.md` — the gap claim as it can actually be defended
- `docs/related_work_positioning.md` — differentiation vs the four nearest papers
