# Handoff 3/3 — Operating guide: files to scan, rules, traps, working style

---

## 1. Files to scan, in order

**Minimum to be productive (read these first):**
1. `CLAUDE.md` — **8 invariants**, budget rules, known traps, layout. Non-negotiable.
2. `docs/handoff/01_state_and_results.md`, `02_plan_and_next_steps.md` (this set)
3. `docs/plan.md` — week-by-week plan with progress notes (W1, W2 marked done)
4. `REVIEW.md` — adversarial audit: findings F-*, kill questions, **Phase 3 product spec**
5. `README.md` — public landing page

**For W3 product work:** `src/airsbench/probe.py` · `src/airsbench/gate/{policy,controller,replay,__main__}.py` ·
`src/airsbench/airs/{calculator.py,calibrated_weights.json}` · `examples/probe/`, `examples/gate/` ·
`demo/` (Next.js; `src/components/*.tsx`, `src/data/aist.json`) · `src/airsbench/analysis/export_demo_data.py` ·
`pyproject.toml` (extras: `ci`, `data`, `analysis`, `agents`, `pipelines`, `dev`)

**For analysis / writing:** the 10 findings docs in `docs/*_findings.md` ·
`docs/chapter3_methodology.md` · `docs/research_questions_v2.md` (supersedes the original RQs) ·
`docs/literature_review.md` · `docs/related_work_positioning.md` · `docs/research_plan_original.md` (archival)

**Stale — do not trust for current state:** `docs/campaign_status.md` (operational log;
its roadmap is superseded by `docs/plan.md`) · `infra_unused/` (quarantined, used by no result).

## 2. Code map (what actually runs)

| Path | Role |
|---|---|
| `src/agentic_faults/` | 4 injectors + verification. Core instrument. |
| `src/airsbench/runner/` | grid (`config.py`: seed blocks, `compose_faults`), `execute.py`, `scoring.py` (**`is_silent_failure` = the definition**), `run.py` CLI with spend guard |
| `src/airsbench/agents/` | LLM client (OpenAI / Anthropic / Ollama routing), prompts, retrieval + classification agents — **one `.invoke()` per decision** |
| `src/airsbench/pipelines/loader.py` | catalog time machine — only live part of `pipelines/` |
| `src/airsbench/probe.py`, `gate/` | the two shipped tools |
| `src/airsbench/analysis/` | one module per result, all $0, re-run from `results/runs/`: `flip_partition`, `freshness_sweep`, `decision_models`, `airs_calibration`, `cross_model`, `detectability`, `interaction`, `curve_sensitivity`, `silent_definition`, `fragility`, `power`, `figures`, `airs_correction`, `phase1_check`, `export_demo_data` |
| `results/runs/` | 302 JSON artifacts — **canonical dataset** (invariant 7) |
| `docs/figures/` | Figs 3.1, 4.1–4.8 (`make figures`) |

**Seed blocks (arm provenance):** main <50 000 · freshness_sweep 50–60k · detectability
60–70k · cross_model 70–80k · interaction 80–90k · **refetch (planned) 90–100k**.
Always select runs with `run_arm(run)`, never by condition.

## 3. Commands

```bash
make test        # 398 tests, ~20 s
make lint        # ruff src tests
make ci          # clean venv from pyproject + lint + tests (~85 s) — run before releases
make lock        # re-pin requirements-lock.txt
make figures     # all 9 figures, deterministic (~9 s)
python -m airsbench.runner.run --<arm> --n-queries 80 --dry-run        # ALWAYS first
python -m airsbench.runner.run --<arm> --n-queries 80 --max-cost 0.80  # then paid
```

## 4. Traps discovered in this session (beyond CLAUDE.md)

- **Python `hash()` is randomised per process** — never use it for seeds (made a test flaky).
- **zsh expands unquoted globs** — quote `--include='*.py'` in grep.
- **macOS:** no `timeout`; BSD `cat -et` not `cat -A`; `stat -f %m`; `$pipestatus` not `$PIPESTATUS`.
- **`latency_score` saturates at 100 at/below target** — never invert AIRS scores to
  recover physical values; read them from the run config (`value_staleness_s`, `spike_ms`).
- **Composition order is load-bearing:** semantic stripping must run before schema drift
  (stateful opaque map). Pinned by test.
- **Cluster-robust GLM with one run per condition degenerates** (p = 0.000 everywhere) —
  use the closed-form paired bootstrap in `interaction.py`.
- **Mixed populations in tables:** phase-1 numbers pool both tasks; residuals are
  retrieval-only. Always state the population (F-C8 came from this).
- **Laptop sleep hangs paid runs** on a dead socket (60 s timeout doesn't fire) — kill and
  resume with `--offset N`.
- **`next build` while `next dev` runs corrupts `.next`.**
- Figures must print recomputed values beside published ones (`_check` in `figures.py`) —
  this caught F-C8.
- "Byte-identical output" can mean "not regenerated" — check mtimes before claiming determinism.
- `research_questions_v2.md` once cited an "analysis notebook" that never existed; treat any
  "checked in X" claim as unverified until the code is found.

## 5. Working conventions the author expects

- **Step by step, not one shot.** Surface decisions; the author answers via questions.
- **Verify, don't assume.** Read the code before claiming; every number in a doc must come
  from code output (generators, not hand-copying).
- **Honest register.** Corrections are recorded in `REVIEW.md` findings (F-*) with status;
  findings docs carry "Corrected in W*" notes rather than silent edits.
- **Every analysis emits its figure/table when written**, so Chapter 4 is assembly.
- **Commits:** explicit `git add <paths>` (never `-A` blindly), check nothing unintended is
  staged, long explanatory message ending with
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. **Commit/push only when asked**
  (the author has approved pushing each completed step so far).
- **Public repo:** keep secrets local (`.env` gitignored, history verified clean).
- **Budget discipline:** dry-run before any paid run; `--max-cost` always; quote costs and
  confirm if a plan's cost changes.
- **Writing register (November):** casual professional; Markdown first; template later.
- **Author preferences learned:** wants a real product, not a presentation; values
  "heavy engineering"; doesn't want GitHub Actions; wants honest weak points surfaced.

## 6. Suggested first message for the new session

> Read `docs/handoff/01_state_and_results.md`, `02_plan_and_next_steps.md`,
> `03_operating_guide.md`, then `CLAUDE.md`, `docs/plan.md` and `REVIEW.md` Phase 3.
> We are starting **W3: the product** — FastAPI backend, `airs serve`, Mode A input
> and scoring view. First read `probe.py`, `gate/`, and `demo/`, then propose the
> backend API and repo layout before writing code. Also ask me where F-C7
> (small-cluster correction, ~3 h) should go.
