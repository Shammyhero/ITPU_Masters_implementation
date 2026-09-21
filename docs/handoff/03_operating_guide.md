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

**For the console (A8, next):** `src/airsbench/server/api.py` (the A7 routes the page
calls: `/api/sources`, `/api/models`, `/api/session`, `/api/ask` SSE, `/api/session/{id}`) ·
`src/airsbench/analyst/{loop,sessions}.py` (`Loop.stream` yields gate → refetch → answer →
tick; the page renders those in order) · `demo/src/` · `docs/analyst_brief.md` §6 · `src/airsbench/analysis/flip_partition.py` (`Replayer`,
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
| `src/airsbench/analyst/` | **A3–A7** plans, verifier (four labels), answerers, spend caps (`budget.py`), the router and two-step loop (`loop.py`), live sessions (`sessions.py`) |
| `src/airsbench/analysis/` | one module per result, all $0 |
| `demo/` | console source (Next.js export) → `src/airsbench/web/` via `make web` |
| `results/runs/` | 302 JSON artifacts — **canonical dataset** (invariant 7) |

**Seed blocks:** main <50 000 · freshness_sweep 50–60k · detectability 60–70k · cross_model
70–80k · interaction 80–90k · refetch (reserved) 90–100k · **live sessions 100–110k**. All
seven are registered in `SEED_BLOCKS`, so `run_arm(run)` names a live Tick as `live` rather
than `unknown`. Always select runs with `run_arm(run)`, and never pool `live`.

## 3. Commands

```bash
make test         # 801 tests, ~30 s
make lint         # ruff src tests
make ci           # clean venv from pyproject + lint + tests (~90 s)
make web          # npm ci + next build → src/airsbench/web/ (refuses while next dev runs)
make dist-check   # wheel → clean install → airs probe/gate/sources + airs serve + console
make figures      # all 10 figures (needs data/ecommerce)
make lock         # re-pin requirements-lock.txt
.venv/bin/airs serve [--records d.jsonl --source u.jsonl] [--sources sources.yaml] [--dev]
.venv/bin/airs sources list | describe <id> | sample <id> [--seed N] [--json] [--sources f]
.venv/bin/airs manifest [--sources f] propose <pair> [--model ollama/<name>] [--out m.yaml] | review m.yaml --source <pair> | show <pair>
.venv/bin/airs analyst ask <pair> [--answerer literal|ollama/<n>|openai/<m>|anthropic/<m>|gemini/<m>]
    [--max-cost 0.50] [--max-cost-day 2.00] [--estimate] [--questions N] [--seed S]
    [--policy p.json] [--refetch gate|agent|off]   # the router: admit / refetch / refuse
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

**21 Sep (A9):**
- **`Outcome.to_dict()` carries its own `policy` key — the NAME.** Spreading it after a
  structured policy silently replaced the object the console applies with a string.
- **A report must count refusals.** Counting only verified answers made three refused
  questions render as "no verified answers yet", which reads as a bug and hides the
  outcome enforcement exists to produce.
- **Recommendations come from the corpus sweep, never from the session.** What the
  session measured may only remove policies its pipeline could never clear
  (`_feasible`); inventing a floor from live data would be a heuristic pretending to be
  evidence.
- **Two exchange rates, never blended:** raw (2.26 on retrieval) credits a gate with
  every silent failure in a refused batch; attribution true cost (7.0) credits only the
  excess over a fault-free pipeline. Show both or neither.
- Switching the task profile visibly moves the score (89.6 READY → 83.0 WATCH on the same
  question) and changes the recommendation — that is RQ5's inversion, not a bug.

**21 Sep (A8 step 4):**
- **The semantic toggle must run the injector, not hide the manifest.** Measured:
  stripping takes semantic 100 → 25 and leaves consistency at 100 (the opaque map
  reverses the names — invariant 5). Hiding the manifest alone moves nothing, because
  `price` and `stock` describe themselves.
- **Say who applied a fault.** The console strips; the user's pipeline did not. Every
  Tick of such a session carries that sentence, or a demonstration reads as a
  measurement of someone's own system.
- A stripped session makes the literal answerer abstain (the fields its plan needs are
  gone), which is the honest outcome, not a bug.
- **An edit helper that writes only after every replacement succeeds loses the whole
  file's edits when one anchor is stale** — that is how these two blocks went missing
  once. Check the file after a failed batch.

**21 Sep (A8 step 3):**
- **`useCallback` deps must list every value the request is built from.** `askOne` left
  out the pasted records, sent the stale empty string, and the server refused `inline`
  as an undeclared source — which looked like a firewall bug and was a stale closure.
- **Pasted records carry no timestamps**, so any policy with `max_record_age_seconds`
  refuses every batch ("we did not look" is not "it is fine"). Pasted sessions default
  to no policy and explain what such a policy needs.
- **Mode B's six-step walkthrough was only ever planned** — there was no bespoke UI to
  delete, and `Stress`/`Inversion` on /evidence/ are aggregate arguments, not
  per-decision walkthroughs. Check before scheduling a deletion.
- The demo has **no JS test runner**; frontend logic is covered by typecheck, the
  browser pass, and the Python contract tests. Keep pure helpers small and obvious.

**21 Sep (A8 step 2):**
- **A partial realization cannot be checked against a whole-run AIRS.** The replay bake
  stopped as soon as it had the decisions it wanted, then compared a fragment with the
  run's logged scores — the A4 check caught it. Iterate the whole run, select as you go.
- **Abstention under stripping is rare on the streaming pipeline** (0, 0, 0, 1 across its
  four runs), so a curated feed must search a condition's replications for an outcome
  rather than taking whatever the first run holds.
- **TypeScript infers an imported JSON's type from its CONTENTS**, so `records.served`
  became a union of today's product ids. Cast once, and assert the shape in Python where
  the file is generated (`tests/test_replay_ticks.py`).
- **The Tick shape has two producers.** `probe.score()` carries the calibration stamp and
  held-out validation; `analyst/loop.py`'s own AIRS block does not. The TS type claimed
  they were always present — and that gate, session and meter always are, which a
  replayed Tick disproves.
- `demo/src/data/replay_ticks.json` is generated by `python -m airsbench.server.bake`
  (needs `data/ecommerce`) and committed; a test fails when it differs from a fresh bake.

**20 Sep (A8 step 1):**
- **`next lint` is not configured** in this project (it prompts interactively). Use
  `npx tsc --noEmit` for the frontend, and `make web` to prove the export builds.
- **`make web` refuses while `next dev` runs** — stop the dev server first.
- **Measure contrast, don't eyeball it.** Two light-mode elements were under 4.5:1
  (gate badge 3.75, verdict title 4.36). A tinted pill background is the usual cause;
  the established fix here is to outline the pill and darken the ink.
- **A contrast script must handle `color(srgb r g b / a)`**, which `color-mix` produces.
  Parsing it as `rgb()` silently gives nonsense ratios (it read 0.06 as 6/255).
- **The dev server needs `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000`** and
  `airs serve --dev` for CORS; without it every fetch is same-origin to :3000.
- **`dist_smoke.py` asserted "Check my pipeline" at `/`** — which the nav carries on
  every page, so it would have passed whatever was served. Assert per route.

**20 Sep (A7):**
- **`TestClient` needs `base_url="http://127.0.0.1"`** or the Host allowlist answers
  "Invalid host header" in plain text and every assertion reads as a JSON error.
- **A dataclass default captures the module constant at import**, so monkeypatching
  `SESSIONS_DIR` did nothing and tests wrote into the author's real `~/.airs/sessions`.
  Resolve the directory when writing, not when the class is defined.
- **`include_other_arms=True` meant "all arms" — including live.** Loaders now drop
  `arm == "live"` unconditionally (`flip_partition`, `phase1_check`).
- **Anything that travels into a Tick must not carry a path.** `SemanticLayer.to_dict`
  emitted the manifest's absolute path; a written Tick then contained `/Users/<name>/…`.
- **A hosted model must be checked for its key when the session opens**, not at the
  first question — failing mid-stream is the worst moment to learn the key is missing.
- **`load_dotenv()` restores keys a test deleted**, so a "no key configured" test must
  stub it out as well as calling `monkeypatch.delenv`.
- Substring credential checks are unreliable against real catalogs: a product title
  containing "desk-projector" matches a naive search for `sk-proj`.

**18 Sep (A6):**
- **"Now" on a simulated source is the question's own moment**, not the end of the update
  stream. A re-read without `as_of` reads later than the answer key — the future.
- **Agent mode must ADMIT a repairable violation, not refuse it**, or the model is never
  asked and the arm's condition measures nothing. The gate/agent contrast is *who
  decides*, not *whether the question is asked*.
- **After a re-read, the refreshed records are the delivery.** Keep comparing with the
  pre-refetch served state and every repaired field reads as `corrupted_in_transit`.
- **A re-read bypasses the pipeline**, so it is only offered for staleness rules; drift
  and stripping refuse (`REPAIRABLE`).
- `build_tick` needs a reason when nothing was verified — a gate refusal produces no
  answer at all.
- The corpus forbidden-word list bites here too: "a fresh read" fails it. The
  tool-offering prompt says "read again".

**18 Sep (A5):**
- **A hosted model with no price is refused**, never billed at $0 (`require_price`).
  Ship only verified prices; anything else goes in `~/.airs/pricing.yaml`.
- **Address every model as `<provider>/<model>`.** A bare `gemini-2.5-flash` would route
  to the OpenAI client and try to bill an OpenAI key for it.
- **Caps are checked before the request** with that request's projected cost, and the
  call is charged what it actually used. Exit status 3 is "a cap refused a call".
- The day ledger lives in `~/.airs/spend.json` — never `results/runs/` (invariant 7).
- `langchain-openai` 1.4 / `openai` 2.48 work with the pinned client; one transient 404
  appeared once and did not reproduce — retry before debugging the client.
- Live A5 check cost **$0.0015** in total; the remaining OpenAI budget is ~$4.58.

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
> `docs/analyst_brief.md`. Confirm the state: `git log --oneline -3` and `make test` (801
> passing). Continue from 02 §1 (the refetch arm — the last experiment).
