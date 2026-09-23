# CLAUDE.md

Master's thesis implementation: **An Experimental Study of the Effect of Selected
Data Infrastructure Faults on Silent Failures in Agentic AI Systems**
(Shamsiddin Khamidov, IT Park University, 2026; title adopted 22 Sep on the
supervisor's advice — see `docs/research_questions_v2.md` §1).

This is a **scientific instrument**, not an application. Code correctness is
necessary but not sufficient — a change can pass every test and still invalidate
the experiment. Read §"Invariants" before touching `runner/` or `agentic_faults/`.

## Commands

```bash
make test            # pytest (must stay green)
make ci              # clean-venv install from pyproject + lint + tests
make lock            # re-pin requirements-lock.txt from the results environment
make figures         # regenerate the Chapter 4 figures into docs/figures/
make lint            # ruff
make grid            # inspect the factorial, no execution, no cost
make up / make down  # original Kafka+Airflow+Postgres+Prometheus stack — infra_unused/, used by no result
make demo            # Next.js dev server for the console on :3000 (pair with `airs serve --dev`)
make web             # build the console into src/airsbench/web/ — required before a wheel
make dist-check      # build the wheel, install it clean, run the installed airs + airs serve
airs serve           # local web console + API on 127.0.0.1:8000 (probe/gate/replay, no model)
airs serve --sources sources.yaml   # adds /api/sources, /api/session, /api/ask (SSE) over declared sources
airs sources list | describe <id> | sample <id>   # declared sources; demo pairs always available
airs manifest propose <src> | review <file> --source <src> | show <src>   # what fields mean; semantic UNMEASURED until reviewed
airs analyst ask demo-stale [--answerer ollama/llama3.1:8b]   # verified, attributed answers ($0)
airs analyst ask demo-stale --answerer openai/gpt-4o-mini --max-cost 0.01 [--estimate]   # hosted: capped before each call
airs analyst ask demo-drift --policy p.json [--refetch gate|agent|off]   # router: admit / re-read / refuse ($0 to refuse)

# Campaign — ALWAYS --dry-run first to see the cost estimate
python -m airsbench.runner.run --main --n-queries 80 --limit 36 --dry-run
python -m airsbench.runner.run --main --n-queries 80 --limit 36 --max-cost 1.00
python -m airsbench.runner.run --main --n-queries 80 --offset 36 --max-cost 2.00
python -m airsbench.runner.run --freshness-sweep --n-queries 60 --replications 3
python -m airsbench.runner.run --cross-model claude-haiku-4-5 --n-queries 100
python -m airsbench.runner.run --refetch-arm --dry-run                # exact token count, $0
python -m airsbench.runner.run --refetch-arm --max-cost 2.00 [--offset N --limit M]
python -m airsbench.analysis.refetch --figure docs/figures/fig4_9_refetch.png   # $0
python -m airsbench.gate.replay --refetch          # the third verdict: refuse vs re-read, $0
python -m airsbench.livecase.record --minutes 180   # A11: record a live GBFS feed + real caches, $0
python -m airsbench.livecase.run --dry-run          # A11: questions over the recording (then --max-cost)
python -m airsbench.analysis.livecase --figure docs/figures/fig4_11_livecase.png   # $0
python -m airsbench.dataprep.check_sensitivity --n 400   # free, no API calls
```

## Budget — real money, and tight

Roughly **$7 OpenAI / $4 Anthropic** for the whole study. Every paid command
takes `--max-cost`; the guard refuses to start above it and aborts mid-run if
spend exceeds it. **Never launch a paid run without a dry-run first.**

Approximate costs: phase 1 (36 runs × 80q) $0.39 · phase 2 (108 runs) $1.17 ·
freshness sweep $0.29 · Haiku cross-model arm $1.68 · refetch arm **$0.85 actual**
(dry-run $0.96 expected, $1.85 worst case; `--max-cost` is checked against the worst case) ·
live case study **$0.19 actual** (dry-run $0.24).

The Analyst's hosted answers are capped per session and per day in the request
path (`analyst/budget.py`, `~/.airs/spend.json`), and a hosted model with no
declared price is **refused, never budgeted as free** — local models are free by
construction, which is why they carry no price.

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
   and should vary). A **flat single-fault** condition is seeded with
   `config.seed` itself; only the **nested/compound** shape splits into
   per-component streams (`execute._injector_seed`). Deriving a component seed
   for a solo made 88 runs unable to regenerate their own realization — the
   defect A4 found (REVIEW F-E7). → `tests/test_paired_design.py`,
   `tests/test_fault_realization.py`

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

7. **The JSON run artifacts in `results/runs/` are the canonical dataset.**
   Every published number is derived from them, and they are committed.
   Postgres `benchmark_runs` was the original plan and nothing has ever written
   to it; `runner/schema.sql` survives only because its `fault_type` CHECK is
   the interaction arm's quarantine, pinned by a test. Prometheus was
   live-demo observability and was never a results source.
8. **Silent failure has exactly one definition:** committed (not abstained),
   parseable, and wrong — with **no confidence threshold**.
   `runner/scoring.py::is_silent_failure` is the reference and every analysis
   must agree with it (→ `tests/test_failure_modes.py`). A threshold would define
   the outcome partly by confidence, the signal AIRS is compared against in RQ4.
   Until 2026-09-13 the docs and `failure_modes` used a 0.7 threshold that nine
   analyses never applied; it survives only as the robustness check in
   `analysis/silent_definition.py`.

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
- **Run artifacts store no records.** Anything needing the records an agent was
  actually shown must replay the fault chain from the config and then prove the
  replay reproduced the run's logged consistency and semantic scores exactly
  (`analysis/verifier_agreement.py`). A seeded-RNG test only proves today's code
  is deterministic; it does not prove an artifact can be regenerated.
- **Live traffic is quarantined, and the quarantine is tested.** Analyst sessions
  write to `~/.airs/sessions/`, carry `arm: "live"` and a seed from the registered
  live block, and every analysis loader drops them — including under
  `include_other_arms=True`, which means other *research* arms.
  → `tests/test_live_quarantine.py`
- **Healthy consistency is 99.88, not 100.** Missing brands load as NaN and NaN
  never equals itself, so `payload_consistency` counts them as altered. Under
  0.2 points, identical across conditions; deliberately not fixed (F-B5).

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
src/airsbench/pipelines/ catalog time machine + record builders (loader.py)
src/airsbench/gate/      admission control: Policy, Controller, offline policy replay
src/airsbench/server/    `airs serve`: FastAPI API (the only FastAPI importer) + baked data
src/airsbench/sources/   declared read-only data sources: demo (study slice), files, inline, and live
                         sqlite / duckdb / http (tables.py, read afresh; `history` = readable as of),
                         sources.yaml, the semantic manifest (two-state rule) and `airs manifest`
src/airsbench/analyst/   the Analyst: checkable plans, the verifier (4 labels), answerers, spend caps,
                         the router + two-step loop (loop.py, shared with the refetch arm)
src/airsbench/runner/    grid, staged execution, scoring, benchmark_runs schema
src/airsbench/dataprep/  dataset prep (ESCI, BTS) + free sensitivity check
src/airsbench/livecase/  A11: record a live GBFS feed (recorder + real caches), replay it, run the
                         questions; the recording is committed in results/livecase/ (Licence Ouverte)
demo/                    web console source (Next.js static export); `make web` builds it in
infra_unused/            original Kafka/Airflow/Postgres stack — quarantined, no result depends on it
docs/                    literature review, related-work positioning, RQs v2,
                         Chapter 3 methodology
results/discarded/       runs from superseded designs — evidence, not data
```

## Start here

`docs/handoff/01_state_and_results.md` → `02_plan_and_next_steps.md` (Part A: the
next step; Part B: the operating guide), then `docs/plan.md`. They carry the current state, the
next step, the traps and the working conventions, and are kept current after
every step. (`docs/campaign_status.md` is the old campaign log; its roadmap is
superseded.)

## Docs to read before changing the design

- `docs/analyst_brief.md` — the product being built now (the Analyst). Its header
  records the author's decisions and the corrections; it overrides the body.
- `docs/research_questions_v2.md` — current RQs, hypotheses, stats plan,
  declared experimental parameters. **Supersedes the original proposal's RQs.**
- `docs/chapter3_methodology.md` — methodology as implemented
- `docs/literature_review.md` — the gap claim as it can actually be defended
- `docs/related_work_positioning.md` — differentiation vs the four nearest papers
