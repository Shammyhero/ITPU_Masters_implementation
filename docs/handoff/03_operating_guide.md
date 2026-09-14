# Handoff 3/3 — Operating guide: files to scan, rules, traps, working style

---

## 1. Files to scan, in order

**Minimum to be productive:**
1. `CLAUDE.md` — **8 invariants**, budget rules, known traps, commands, layout.
2. `docs/handoff/01_state_and_results.md`, `02_plan_and_next_steps.md` (this set)
3. `docs/plan.md` — Part 1b is the Analyst; progress notes sit under each stage
4. `docs/analyst_brief.md` — **header first** (decisions + corrections override the body)
5. `REVIEW.md` — findings F-*, kill questions (Phase 2)

**For product work:** `src/airsbench/cli.py` · `probe.py` (validator, `measure`, `score`) ·
`gate/{policy,controller,replay}.py` · `server/{app,api,schemas,bake,__main__}.py` ·
**`sources/{base,demo,files,inline,config,__main__}.py`** · `demo/src/` · tests
`test_{server,replay_api,cli,probe,gate,sources,demo_source}.py` · `tests/dist_smoke.py`

**For the verifier (A3/A4):** `src/airsbench/agents/{retrieval,prompts,llm}.py`
(`RetrievalAgent.ground_truth`; `llm.py` prices any model absent from `PRICING` at $0 — A5
must close that for hosted models) · `src/airsbench/analysis/flip_partition.py` (`Replayer`,
`QueryOutcome.flipped`, `followed served`) · `docs/flip_partition_findings.md` ·
`src/airsbench/runner/{config,execute,scoring}.py` (`run_arm`, `_airs_components`,
`is_silent_failure`)

**Stale — do not trust for current state:** `docs/campaign_status.md` · `infra_unused/`.

## 2. Code map (what actually runs)

| Path | Role |
|---|---|
| `src/agentic_faults/` | 4 injectors + verification. Core instrument, stdlib only |
| `src/airsbench/runner/` | grid (`config.py`: seed blocks, `SEVERITY_PARAMS`), `execute.py`, `scoring.py` (**`is_silent_failure`**), `run.py` with spend guard |
| `src/airsbench/agents/` | LLM client (OpenAI / Anthropic / Ollama), prompts, retrieval + classification agents |
| `src/airsbench/pipelines/loader.py` | catalog time machine, record builders |
| `src/airsbench/probe.py`, `gate/` | scoring and admission control — stdlib only at import |
| `src/airsbench/server/` | `airs serve` FastAPI API (the only FastAPI importer); `data/` baked |
| `src/airsbench/sources/` | **A1** declared read-only sources; `data/esci_slice.json.gz` baked |
| `src/airsbench/analysis/` | one module per result, all $0 |
| `demo/` | console source (Next.js export) → `src/airsbench/web/` via `make web` |
| `results/runs/` | 302 JSON artifacts — **canonical dataset** (invariant 7) |

**Seed blocks:** main <50 000 · freshness_sweep 50–60k · detectability 60–70k · cross_model
70–80k · interaction 80–90k · refetch (planned) 90–100k · **live sessions (reserved, A7)
100–110k** — the demo source already seeds its fault chain from 100 000. Always select runs
with `run_arm(run)`.

## 3. Commands

```bash
make test         # 567 tests, ~22 s
make lint         # ruff src tests
make ci           # clean venv from pyproject + lint + tests (~90 s)
make web          # npm ci + next build → src/airsbench/web/ (refuses while next dev runs)
make dist-check   # wheel → clean install → airs probe/gate/sources + airs serve + console
make figures      # all 9 figures
make lock         # re-pin requirements-lock.txt
.venv/bin/airs serve [--records d.jsonl --source u.jsonl] [--sources sources.yaml] [--dev]
.venv/bin/airs sources list | describe <id> | sample <id> [--seed N] [--json] [--sources f]
.venv/bin/python -m airsbench.server.bake   # regenerate baked data (slice needs data/ecommerce)
npm --prefix demo run data                  # regenerate demo/src/data/aist.json
python -m airsbench.runner.run --<arm> --dry-run   # ALWAYS before any paid run
```

## 4. Traps (beyond CLAUDE.md)

**Earlier sessions:** Python `hash()` is per-process · macOS: no `timeout`, BSD tools,
`$pipestatus` · `latency_score` saturates at 100 · semantic stripping runs before schema drift
· cluster-robust GLM with one run per condition degenerates · state the population of every
table (F-C8) · laptop sleep hangs paid runs (`--offset`) · `next build` during `next dev`
corrupts `.next` · figures print recomputed vs published values.

**13–14 Sep (W3):**
- **zsh does not word-split `$var`** — use arrays: `files=(a b); git add "${files[@]}"`.
- **Never run `git add` in parallel with file writes** — the index can capture either version.
- **`.gitignore` `data/` was unanchored** and hid `server/data/` and `demo/src/data/`; now `/data/`.
- **A built wheel ≠ an editable install** — non-`.py` files need package-data; only
  `make dist-check` catches omissions; the package-data test uses `Path.glob` semantics.
- Python's `json` accepts NaN/Infinity; Starlette will not emit them — emit `null`.
- `pgrep -f "next dev"` in a recipe matches its own shell — use `"[n]ext dev"`.
- **The Browser pane cannot launch `airs serve`** here (macOS blocks the python.org
  interpreter reading `~/Documents`); start the API from a terminal for connected checks.
- Browser tool quirks: `find` matches `title`; tools can set `open` on `<details>`;
  `read_page` interactive lists only the viewport.
- Starlette 1.6 warns to use `httpx2` (unresolved).

**14 Sep (A1):**
- **Consistency's reference is upstream *as of when the delivered values were true*, not
  now.** The corpus compared with pre-fault records (state at t − staleness). Comparing with
  current upstream makes freshness depress consistency (invariant 5). Demo: `served_as_of`;
  files cannot, and say so (brief correction 15).
- **`probe` entries must carry `opaque_map`** or semantic stripping depresses consistency;
  `sources.to_probe_entry` keeps it.
- **Never read a record's id back out of its payload** — faults rename and opaquify keys.
  Sources stamp `meta["record_id"]`.
- **`agentic_faults.Record` defaults `event_timestamp` to `time.time()`** — a source must never
  rely on that default; missing timestamps are flagged (`event_timestamp_absent`) so freshness
  stays UNMEASURED.
- PyYAML's `safe_load` silently keeps the last of two duplicate keys — `sources/config.py` uses a
  loader that refuses them.
- `gzip.compress(..., mtime=0)` or every bake rewrites the slice with a new timestamp.
- The slice bake needs `data/ecommerce`; without it `bake` keeps the committed slice.

## 5. Working conventions the author expects

- **Step by step.** Propose before code; surface decisions via questions; wait for approval.
- **Verify, don't assume.** Read the code before claiming; every number in a doc comes from code.
- **Keep every document current after each step** — plan progress notes, these handoff files,
  README, CLAUDE.md, the brief's header, findings docs — in the same commit.
- **Honest register.** Corrections recorded as F-* findings or "Corrected in …" notes.
- **Every analysis emits its figure/table when written.**
- **Commits:** only when asked; explicit paths; staging guard —
  `files=(…); git add "${files[@]}"; [ "$(git diff --cached --name-only | sort)" = "$(printf '%s\n' "${files[@]}" | sort)" ]` —
  then a long explanatory message ending with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`;
  push to `main`.
- **Budget:** dry-run before any paid run; `--max-cost` always; quote costs.
- **Author preferences:** a real product, not a presentation; heavy engineering; honest weak
  points surfaced; casual professional writing register.

## 6. Suggested first message for a new session

> Read `docs/handoff/01_state_and_results.md`, `02_plan_and_next_steps.md`,
> `03_operating_guide.md`, then `CLAUDE.md`, `docs/plan.md` and the header of
> `docs/analyst_brief.md`. Confirm the state: `git log --oneline -3` and `make test` (567
> passing). Continue from 02 §1 (A3, the verifier).
