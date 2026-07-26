# Campaign status

**Updated:** 2026-07-25 · paused mid phase 1

## Where things stand

| | |
|---|---|
| Design | Paired, replication-major, 144 runs at 80 queries |
| Phase 1 | **8 / 36 runs complete** (one full replication = 36 runs) |
| Spent | ~$0.11 of ~$7 OpenAI |
| Results | `results/runs/*.json` — one file per completed run, written on completion |

## Resume

```bash
cd agentic-infra-gap
python -m airsbench.runner.run --main --n-queries 80 --offset 8 --limit 28 --max-cost 1.00
```

Recount first if unsure — the offset is simply the number of completed runs:

```bash
ls results/runs/*.json | wc -l
```

Resumption is exact: `build_grid()` is deterministic (fixed conditions, seeds
derived from condition and replication), so `--offset N` continues precisely
where the previous invocation stopped. Interrupting mid-run loses only that
run's partial spend (~$0.01); nothing already written is affected.

## After phase 1 completes

1. **Go/no-go review.** Check that faults produce measurable degradation and
   that no arm is floored. Phase 1 is a complete balanced replication of all 36
   conditions, so this is a real check, not a spot sample.
2. **Phase 2:** `--offset 36` (108 runs, ~$1.17)
3. **Freshness sweep:** `--freshness-sweep --n-queries 60 --replications 3` (~$0.29)
4. **Cross-model:** local Ollama arm (free), then
   `--cross-model claude-haiku-4-5 --n-queries 100` (~$1.68)
5. Analysis + AIRS calibration → probe → AIST demo rebuild → chapters

## Early signal from the 8 completed runs

Batch/retrieval only so far (grid order), single replication, n=80 — indicative,
not conclusive.

| condition | accuracy | silent failure |
|---|---|---|
| baseline | 0.810 | 19% |
| latency mild | 0.810 | 16% |
| latency severe | 0.797 | 20% |
| freshness mild | 0.772 | 22% |
| freshness severe | 0.772 | 22% |
| schema drift mild | 0.810 | 19% |
| schema drift severe | 0.684 | 32% |

Two things worth noting, both consistent with expectations:

- **Latency shows no accuracy effect** (0.810 → 0.797), exactly as predicted for
  a synchronous agent with no deadline. Analytic latency cannot change what the
  agent reads. This is a finding to frame, not a bug.
- **Schema drift severe is the first clear effect** (−13 points, silent failure
  19% → 32%).

The numbers are internally coherent now — no severe condition outscoring its own
baseline, no below-chance arm — which was the point of the paired-design fix.
Semantic stripping and the streaming arm have not yet been reached.
