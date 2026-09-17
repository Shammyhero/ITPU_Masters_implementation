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

**For the Analyst's remaining stages** (A4 is done — `analysis/verifier_agreement.py`,
`docs/verifier_agreement_findings.md`): `src/airsbench/analyst/{plan,verifier,session}.py`, `src/airsbench/agents/{retrieval,prompts,llm}.py`
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
| `src/airsbench/sources/manifest*.py` | **A2** semantic manifest, the two-state rule, `airs manifest` |
| `src/airsbench/analyst/` | **A3** plans, verifier (four labels), answerers, prompt, session → Tick, `airs analyst` |
| `src/airsbench/analysis/` | one module per result, all $0 |
| `demo/` | console source (Next.js export) → `src/airsbench/web/` via `make web` |
| `results/runs/` | 302 JSON artifacts — **canonical dataset** (invariant 7) |

**Seed blocks:** main <50 000 · freshness_sweep 50–60k · detectability 60–70k · cross_model
70–80k · interaction 80–90k · refetch (planned) 90–100k · **live sessions (reserved, A7)
100–110k** — the demo source already seeds its fault chain from 100 000. Always select runs
with `run_arm(run)`.

## 3. Commands

```bash
make test         # 690 tests, ~26 s
make lint         # ruff src tests
make ci           # clean venv from pyproject + lint + tests (~90 s)
make web          # npm ci + next build → src/airsbench/web/ (refuses while next dev runs)
make dist-check   # wheel → clean install → airs probe/gate/sources + airs serve + console
make figures      # all 10 figures (needs data/ecommerce)
make lock         # re-pin requirements-lock.txt
.venv/bin/airs serve [--records d.jsonl --source u.jsonl] [--sources sources.yaml] [--dev]
.venv/bin/airs sources list | describe <id> | sample <id> [--seed N] [--json] [--sources f]
.venv/bin/airs manifest [--sources f] propose <pair> [--model ollama/<name>] [--out m.yaml] | review m.yaml --source <pair> | show <pair>
.venv/bin/airs analyst ask <pair> [--answerer literal|ollama/<name>] [--questions N] [--seed S]
    [--plan JSON --question TEXT] [--json]     # Ollama here has llama3.1:8b, qwen2.5:14b-instruct
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

**15 Sep (A3):**
- **The corpus's forbidden-prompt-word test matches substrings** (`age`, `old`, `fresh` …), so
  "average", "message", "language", "threshold", "hold" all fail it. Word the Analyst prompt
  around them; `tests/test_analyst_session.py` extends the list with fault vocabulary.
- **Grade against the question's plan, never the agent's.** Agents rewrite filters:
  `llama3.1:8b` wrote `stock >= 1` (equivalent on whole-number stock) and `stock >= 0` (not)
  for `stock > 0`. Form-equality alone is noise; `agent_plan_agrees` re-executes the agent's
  plan over the served records.
- **Ties in `min_by` must go to the first candidate** (strict `<`), or A4 cannot be exact —
  that is what `min()` in `RetrievalAgent.ground_truth` does.
- **An abstained answer is verifiable but carries no attribution** (`attribution: None`);
  counters must skip it rather than count a `None` label.
- **Never read a measure on a record the filter excludes** — the corpus filters in-stock first,
  so a corrupted price on an out-of-stock record must not make the answer uncomputable.
- A local 8 B model answers in ~5–7 s per question on this machine; `qwen2.5:14b` is slower.
- Hosted answerers raise `AnswererError` until A5; a transport failure is an `AnswererError`,
  unparseable output is a parse failure (invariant 6).

**16 Sep (A4):**
- **A run artifact stores no records** — only the AIRS dimensions measured from them. Any
  analysis needing the delivered records must replay the fault chain, and must then prove
  the replay by reproducing that run's logged consistency and semantic scores exactly.
- **Injector seeds are keyed on the parameter shape** (`execute._injector_seed`): flat
  single fault → `config.seed`; nested/compound → per-component streams. The main and
  cross-model arms predate `_component_seed`; the interaction arm writes even solos nested.
  Get this wrong and 88 runs regenerate a different realization (F-E7).
- **`tests/test_interaction_arm.py` builds its conditions the way the arm's grid does** —
  nested for solos too. Built flat, its separability marginals compare different
  realizations and fail by ~0.5–1.5 points.
- **Healthy consistency is 99.88, not 100** — NaN brands never equal themselves (F-B5).
  Do not "fix" it: recomputed scores would stop matching the logged ones.
- `matplotlib` legends built from `label=` while drawing stacked bars only legend the
  first bar's segments — build handles explicitly from every key present.
- The corpus tests skip without `data/ecommerce`; `make test` on a fresh clone will not
  run them. `make figures` does.

**17 Sep (A2):**
- **The semantic score counts four context categories, not described fields.** A manifest
  with one definition scores the same as one with five; coverage is reported separately.
  The brief said otherwise until corrected.
- **Never render a manifest onto a pipeline that renders its own context** (the demo):
  it would put context back on records semantic stripping removed. `renders_context` on
  the delivered source decides; files render, only onto records without context.
- **Severe stripping is probabilistic per record** — `demo-stripped` scores ~17, not 0.
- **A declared `manifest:` file may not exist yet** — that is state *absent*, not a
  declaration error, or `airs manifest propose --out` could never create it.
- **File sources lift the id column out of the payload**; manifest code treats
  `schema.id_field` as present.
- **`sources.manifest` imports `analyst.plan` inside functions** — `analyst` imports
  `sources`, and a module-level import is a cycle.
- `airs sources sample` now states the share of calibrated weight a composite rests on; a
  `100.0 READY` over one measured dimension is a different claim.
- A local 8 B model proposes a manifest in ~8 s and over-fits the entity to the sample
  (`laptop` for a catalog) — the reason nothing counts until reviewed.

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
> `docs/analyst_brief.md`. Confirm the state: `git log --oneline -3` and `make test` (690
> passing). Continue from 02 §1 (A5 model options, then A6).
