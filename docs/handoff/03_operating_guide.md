# Handoff 3/3 — Operating guide: files to scan, rules, traps, working style

---

## 1. Files to scan, in order

**Minimum to be productive:**
1. `CLAUDE.md` — **8 invariants**, budget rules, known traps, commands, layout.
2. `docs/handoff/01_state_and_results.md`, `02_plan_and_next_steps.md` (this set)
3. `docs/plan.md` — week-by-week plan; the W3 section's progress note is the most
   detailed record of the product as built
4. `REVIEW.md` — findings F-*, kill questions (Phase 2), product spec (Phase 3)
5. `README.md` — public landing page

**For product work:** `src/airsbench/cli.py` · `src/airsbench/probe.py` (validator,
`measure`, `score`) · `src/airsbench/gate/{policy,controller,replay}.py` ·
`src/airsbench/server/{app,api,schemas,bake,__main__}.py` · `demo/src/` (`app/page.tsx`,
`app/evidence/page.tsx`, `components/{CheckPipeline,RecordsInput,ScoreView}.tsx`,
`lib/api.ts`) · `tests/test_{server,replay_api,cli,probe,gate}.py` · `tests/dist_smoke.py`

**For the Analyst (adopted 14 Sep):** `docs/analyst_brief.md` (header first — it overrides
the body), `docs/plan.md` Part 1b, `src/airsbench/agents/{retrieval,prompts,llm}.py`
(`llm.py` treats any model absent from `PRICING` as free — A5 must close that for hosted models)
(`RetrievalAgent.ground_truth` seeds the verifier), `src/airsbench/pipelines/loader.py`,
`src/airsbench/analysis/flip_partition.py` (`Replayer`, `QueryOutcome.flipped`),
`docs/flip_partition_findings.md`, `src/airsbench/runner/config.py` (seed blocks, `run_arm`).

**For analysis / writing:** `docs/*_findings.md` · `docs/chapter3_methodology.md` ·
`docs/research_questions_v2.md` · `docs/literature_review.md` · `docs/related_work_positioning.md`

**Stale — do not trust for current state:** `docs/campaign_status.md` (operational log;
roadmap superseded by `docs/plan.md`) · `infra_unused/` (quarantined).

## 2. Code map (what actually runs)

| Path | Role |
|---|---|
| `src/agentic_faults/` | 4 injectors + verification. Core instrument, stdlib only |
| `src/airsbench/runner/` | grid (`config.py`: seed blocks), `execute.py`, `scoring.py` (**`is_silent_failure`**), `run.py` CLI with spend guard |
| `src/airsbench/agents/` | LLM client (OpenAI / Anthropic / Ollama), prompts, retrieval + classification agents — one `.invoke()` per decision |
| `src/airsbench/pipelines/loader.py` | catalog time machine — only live part of `pipelines/` |
| `src/airsbench/probe.py`, `gate/` | scoring and admission control — stdlib only at import time |
| `src/airsbench/server/` | `airs serve`: FastAPI API, the only FastAPI importer; `data/` baked + drift-tested |
| `src/airsbench/cli.py` | the `airs` entry point |
| `src/airsbench/analysis/` | one module per result, all $0: … `power` (CR2), `pvalue_calibration`, `figures`, `export_demo_data` |
| `demo/` | console source (Next.js static export); built into `src/airsbench/web/` by `make web` |
| `results/runs/` | 302 JSON artifacts — **canonical dataset** (invariant 7) |

**Seed blocks:** main <50 000 · freshness_sweep 50–60k · detectability 60–70k ·
cross_model 70–80k · interaction 80–90k · **refetch (planned) 90–100k**. Always
select runs with `run_arm(run)`, never by condition.

## 3. Commands

```bash
make test         # 501 tests, ~21 s
make lint         # ruff src tests
make ci           # clean venv from pyproject + lint + tests (~90 s)
make web          # npm ci + next build, copied into src/airsbench/web/ (~15 s; refuses while next dev runs)
make dist-check   # wheel → clean non-editable install → installed airs + airs serve + console (needs make web)
make figures      # all 9 figures, deterministic
make lock         # re-pin requirements-lock.txt
.venv/bin/airs serve [--records d.jsonl --source u.jsonl --task retrieval] [--dev] [--port N]
.venv/bin/python -m airsbench.server.bake       # regenerate server/data/*.json (never hand-edit)
npm --prefix demo run data                      # regenerate demo/src/data/aist.json (needs data/ecommerce)
python -m airsbench.runner.run --<arm> --dry-run   # ALWAYS before any paid run; then --max-cost
```

## 4. Traps (beyond CLAUDE.md)

**Found in earlier sessions:**
- Python `hash()` is randomised per process — never use it for seeds.
- **macOS:** no `timeout`; BSD `cat -et`; `stat -f %m`; `$pipestatus`.
- `latency_score` saturates at 100 at/below target — never invert AIRS scores.
- Composition order is load-bearing: semantic stripping before schema drift.
- Cluster-robust GLM with one run per condition degenerates — interaction uses a paired bootstrap.
- Mixed populations in tables (F-C8) — always state the population.
- Laptop sleep hangs paid runs — kill and resume with `--offset N`.
- **`next build` while `next dev` runs corrupts `demo/.next`** (`make web` now refuses).
- Figures print recomputed vs published values (`_check`) — keep that habit.

**Found 13–14 Sep:**
- **zsh does not word-split `$var`.** `git add $files` passes one path. Use an array:
  `files=(a b); git add "${files[@]}"`.
- **Never run `git add` in parallel with file writes** — the index can capture either version.
  Stage, verify with `git diff --cached --name-only`, then commit (staging guard pattern in 03 §5).
- **The root `.gitignore` `data/` rule was unanchored** and silently ignored
  `src/airsbench/server/data/` and `demo/src/data/`. Now `/data/`. Check `git check-ignore -v`
  when a new file won't stage.
- **A built wheel ≠ an editable install.** Non-`.py` files need `[tool.setuptools.package-data]`;
  only `make dist-check` catches omissions. Its package-data test uses `Path.glob`
  (`**` spans zero dirs, like setuptools) — `fnmatch` does not.
- Python's `json` accepts `NaN`/`Infinity`; Starlette refuses to emit them (500). Unmeasured
  values are `null`; infinite exchange rates are `null`.
- `pgrep -f "next dev"` inside a make recipe matches its own shell — use `"[n]ext dev"`.
- **The Browser pane cannot launch `airs serve`** here: macOS blocks the python.org
  interpreter (the venv's base) from reading `~/Documents`. Node dev servers work. Start
  the API from a terminal (or Bash, with the author's OK) for connected browser checks.
- Browser tool quirks: `find` matched buttons by `title` (a real a11y bug, fixed with
  `aria-label`); `read_page`/`find` can set `open` on `<details>`; `read_page` interactive
  lists only the viewport; textbox names show the placeholder even when a `<label>` is wired.
- Starlette 1.6's test client warns to use `httpx2` instead of `httpx` (unresolved).
- A method comparison (e.g. CR2 vs wild bootstrap) is chosen on **simulated** size before
  looking at real p-values; the screening script is not in the repo.
- "Byte-identical" claims need a before/after capture (the replay refactor kept 8 reports identical).

## 5. Working conventions the author expects

- **Step by step.** Propose before code; surface decisions via questions; wait for approval.
- **Verify, don't assume.** Read the code before claiming; every number in a doc comes from code output.
- **Keep every document current after each step** — plan.md progress, these handoff files,
  README, CLAUDE.md, demo/README, findings docs — in the same commit (instruction of 14 Sep).
- **Honest register.** Corrections recorded in `REVIEW.md` (F-*) and "Corrected in …" notes.
- **Every analysis emits its figure/table when written.**
- **Commits:** only when asked; explicit paths; staging guard —
  `files=(…); git add "${files[@]}"; [ "$(git diff --cached --name-only | sort)" = "$(printf '%s\n' "${files[@]}" | sort)" ]` —
  then a long explanatory message ending with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`;
  push to `main`.
- **Budget:** dry-run before any paid run; `--max-cost` always; quote costs; confirm cost changes.
- **Public repo:** secrets stay local (`.env` gitignored).
- **Author preferences:** a real product, not a presentation; heavy engineering; no GitHub
  Actions; honest weak points surfaced; casual professional writing register.

## 6. Suggested first message for a new session

> Read `docs/handoff/01_state_and_results.md`, `02_plan_and_next_steps.md`,
> `03_operating_guide.md`, then `CLAUDE.md` and `docs/plan.md`. Confirm the state is
> real: `git log --oneline -3` and `make test` (501 passing). Continue from 02 §1.
