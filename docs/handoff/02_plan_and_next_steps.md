# Handoff 2 of 2 — What to do next, and how to work here

Part A's sections are numbered 1–5 and Part B's B1–B6, so "02 §1" (the next step)
and "02 B4" (the traps) are unambiguous — and neither collides with the plan's
stage names, which are also A1–A9.

**Part A** is the next step and the decisions behind it. **Part B** (below) is
the operating guide: the files worth scanning, the code map, the commands, the
traps this project has actually hit, and the conventions the author expects.

Authoritative plan: **`docs/plan.md`** (Part 1b = the Analyst). Product brief as adopted:
**`docs/analyst_brief.md`** — its header (decisions + 18 corrections) overrides the body.
Adversarial audit: **`REVIEW.md`** (Phase 3 is design history). This file is the condensed
"what to do next" view. Update it whenever the plan moves.

---

## 1. Immediate next step: the freeze week, then the thesis — every experiment is done

**Everything the plan scheduled before the freeze is built and run** (23 Sep): A1–A9, the
refetch arm (Fig 4.9), A10's live sources, and the A11 live case study (Fig 4.11). All 12
figures regenerate from the repository (`make figures`). In one line each:

- **Refetch arm** (`refetch_findings.md`): offered a re-read, gpt-4o-mini asked 0 times in
  1,800 questions — kill question 3 answered; a gate's re-read matches a healthy pipeline
  and, on the corpus, turns a staleness gate from a trade into a gain (`gate_findings.md` §7).
- **Live case study** (`live_case_study_findings.md`): on Vélib' (Paris), a 15-minute cache
  doubles silent failure against a 5-minute one for both models, through exposure (11.0%
  vs 5.7%); **AIRS as calibrated does not rank the failures** (AUC 0.557 [0.435, 0.675])
  while the records' age does (0.690) — F-B1 on real data: a score's timescale must be the
  source's. The recording is committed (`results/livecase/`).

**Next, the freeze week (2–6 Nov, 14 h, all $0):** positioning against ISO/IEC 25012, data
contracts and agent benchmarks (F-A1, 4 h) · a full-text read of the four load-bearing
papers (F-A2, 8 h) · Zenodo DOI + `CITATION.cff` (F-E5, 2 h — needs the author's Zenodo
account). **Then the thesis** (Part 2 of the plan, from 9 Nov), with the M1 presentation on
Fri 16 Oct before it.

**Done 24 Sep: the freshness target per source** — `freshness_target_s` in `sources.yaml`,
`--freshness-target` on `airs probe` / `airs gate`, the API's score and gate. Default
unchanged (1 s). On A11, by a rule declared first (the feed's 60 s cadence), AIRS's AUC
stays 0.558: necessary, not sufficient (`live_case_study_findings.md` §5a).

**Open for the author — none started, none needed for the thesis:**
1. **A native-function-calling refetch arm** — the refetch arm's most plausible limitation.
   Outside the plan; cost known only after a dry-run.
2. **F-C4** — Holm across the 8 interaction contrasts; it could change what
   `interaction_findings.md` calls significant.

Budget: ~$3.70 OpenAI and ~$1.10 Anthropic remain; no paid work is scheduled.

| Stage | h | State |
|---|---|---|
| A1 sources | 12 | **done 14 Sep** (`e78ab97`) |
| A3 verifier | 14 | **done 15 Sep** (`f5da23a`) |
| A4 Fig 4.10 | 8 | **done 16 Sep** (`b2589da`) — gate Fri 2 Oct met early |
| A2 manifest | 8 | **done 17 Sep** |
| A5 model options (Ollama / OpenAI · Anthropic · Gemini, caps, "unpriced = free" closed) | 8 | **done 18 Sep** |
| A6 router + shared loop | 12 | **done 18 Sep** |
| A7 API + firewalls (`/api/ask` SSE, live quarantine, credential test) | 8 | **done 20 Sep** |
| A8 console | 18 | **done 21 Sep** — conversation, replay, paste, toggle |
| A9 task switch, recommended policy, meter prior, report | 15 | **done 21 Sep** |
| **Refetch arm** (Fig 4.9) | 28 | **done 23 Sep** — 21 runs, $0.8541; the agent never acts; `refetch_findings.md` |
| A10 sqlite / duckdb / http (Postgres dropped) | 8 | **done 23 Sep** — `sources/tables.py`, 42 tests |
| A11 live case study (Fig 4.11) | 6 | **done 23 Sep** — Vélib' recorded 180 min, $0.19; `live_case_study_findings.md` |

**Checkpoints:** ~~Fri 2 Oct Fig 4.10 exact~~ **met 16 Sep** · ~~Fri 9 Oct `/api/ask` on the
free model~~ **met 23 Sep** (the real route in-process with `llama3.1:8b`, both admit and
gate-re-read paths; plan checkpoint table) · **Fri 16 Oct M1** · ~~Fri 23 Oct arm dry-run~~ and ~~Fri
30 Oct arm runs~~ **met 23 Sep** · **Fri 6 Nov freeze**. The arm's 28 h were planned for
19–30 Oct and are done, so A10 and A11 have room; cut order unchanged: A10 → A11.

## 2. Decisions made (do not re-litigate)

**24 Sep, the freshness target:** per source, on every entry point · default stays the
calibrated 1 s so nothing published moves · a declared target is shown beside the score ·
age budgets are held against the measured age, never the score · the A11 check used a rule
fixed before computing (the source's own cadence) and no other target was tried.

**23 Sep, A11's results:** one commit with the results · the recording committed
(`results/livecase/`, Licence Ouverte, with attribution) · the consistency reference
corrected after the run by $0 re-grading, both gradings reported, the artifacts keeping
their own labels.

**23 Sep, A10:** DuckDB included (`[duckdb]` extra; the author: "if it's best") ·
Postgres dropped (it needs a running server to test against) · a side may name its own
`type` · only a table name, never SQL · live sources read afresh on every question.
**A11:** gpt-4o-mini + claude-haiku-4-5 at ≈ $0.25 · real-world questions chosen from
the data · the source is Claude's to choose and verify.

**23 Sep, the arm's results:** the 21 artifacts are committed **as is** — pretty-printed
like the corpus, ~180k lines — because invariant 7 makes them the canonical dataset and
Fig 4.9 must regenerate from the repo (compact or uncommitted alternatives offered and
declined) · the analysis, the artifacts, Fig 4.9 and the findings went in **one commit**
once the findings were written · the prompt-effect contrast is reported, labelled
exploratory · the third verdict is priced on the corpus by the matched fault-free run, the
arm only validating it.

**23 Sep, the refetch arm** (`docs/refetch_arm.md`): age shown is a factor for the
agent-initiated condition (1a) · freshness 5.05 s only (2a) · 150 questions per run, 3
replications (3a) · artifacts in `results/runs/` as arm `refetch` (4a) · the re-read
continues the conversation — the model's request, then the records read again, no further
offer (D1 a) · healthy `agent_shown` records show their true 0.05 s age (D2) · gate on
healthy is not run (it is the baseline) · refusal priced from the baseline, not the
literal answerer · "flipped" defined on the records as first delivered.

**22 Sep, the title:** *An Experimental Study of the Effect of Selected Data Infrastructure
Faults on Silent Failures in Agentic AI Systems*, in title case (supervisor's wording). He
asked that the title state the relation between faults and failures; "the effect of … on
…" does, and the design supports it — faults injected with everything else held constant,
conditions paired. It replaces "Detectability Determines Danger…", which made a claim part
of the evidence runs against. Reasons and history: `research_questions_v2.md` §1.

**21 Sep, A9:** the task profile switches when asked and the console states RQ5's
inversion rather than overriding the choice · the recommended policy is the cheapest real
trade from the **corpus sweep**, with the session only filtering out floors its pipeline
could never clear · both exchange rates are always shown together (raw 2.26 vs
attribution true cost 7.0) with the ~14% fault-free floor stated · the report prints
provenance so it cannot be mistaken for corpus data.

**20–21 Sep, A8:** `/` is the conversation and `/check/` keeps the probe · pasted records
may be answered over, with the question assembled from the six checkable plan types and
the fields found in those records · `/replay/` plays real corpus decisions through the
same renderer and needs no server · the semantic toggle runs the **real** injector and
every Tick says the console applied it, not the user's pipeline.

**19–20 Sep, A7:** keys stay in the **environment** — no secret travels in a request body,
and `/api/models` reports only whether a provider is configured · live Ticks persist to
`~/.airs/sessions/`, one per line, never `results/runs/` · the manifest endpoints are
deferred to A8 · `Loop.stream` is the real path (stages when they happen) and `Loop.ask`
drains it, so CLI, API and the arm keep one loop.

**18 Sep, A6:** a re-read is offered only for rules it legitimately repairs (record age,
freshness) — drift and stripping refuse, because a re-read bypasses the pipeline and
would hide the contract violation · the agent-initiated tool is a **JSON action in the
answer schema**, identical across providers · that condition gets its **own prompt**, so
invariant 1 holds unchanged everywhere else and the two are never pooled · the arm's
batch runner stays in W6 (19–30 Oct), which is when the ~$2.20 is spent.

**18 Sep, A5:** prices are **declared or refused** — only prices verified for the corpus
models ship, anything else goes in `~/.airs/pricing.yaml`, and a hosted model with no
price is refused rather than budgeted at $0 · caps are checked **before** the request
(session + day, the day total in `~/.airs/spend.json`) and the call is charged what it
actually used · every model is addressed `<provider>/<model>` · Gemini ships behind a
`[gemini]` extra, routed and tested with a fake until a key exists.

**17 Sep, A2:** the semantic score stays the calibrated **category** rule; field coverage
is reported beside it, never folded in · reviewed = **stamp + schema fingerprint** (a
renamed or retyped column makes it stale → UNMEASURED) · inference ships: offline
heuristic + local Ollama now, hosted with A5 · a manifest renders only onto bare records;
the demo's pipeline renders its own context and its manifest only describes it.

**16 Sep, A4:** injector seeds keyed on the **parameter shape** — flat single fault gets
`config.seed`, nested/compound gets per-component streams — so every run on disk
regenerates its own fault realization (REVIEW **F-E7**; nothing published moves) · the
NaN-brand consistency ceiling of 99.88 is **recorded, not fixed** (**F-B5**), because
changing the measure would break exactly that regeneration check · Fig 4.10 carries both
panels: agreement, and where each condition's wrong answers came from.

**15 Sep, A3:** answers verified against **the question's plan**; the agent's plan recorded
(`plan_matches_question`, `agent_plan_agrees`), never graded · **four labels**
(`answer_key_moved`, `both`, `corrupted_in_transit`, `agent_impairment`) · answerers in A3
are `literal` and local Ollama only.

**14 Sep, A1:** `sources.yaml` in YAML (PyYAML core) · Parquet as `[parquet]` extra · demo
time simulated per question · `airs sources` · consistency scored against upstream as of when
the delivered values were true.

**14 Sep, the Analyst:** adopt with corrections · sources declared locally, credentials from
environment variables · refetch arm = agent-initiated + gate-initiated on one loop · models:
free local Ollama or API key (OpenAI, Anthropic, Gemini), keys in memory only · W4's Mode A
work kept as A9 · timeline does not drop features.

**W3, still standing:** real tool, not a prop · `pip install` → `airs serve` · no scoring rule
implemented twice · fastapi + uvicorn core, `probe`/`gate`/`airs` import no web stack · Tick
`airs` block `{score | null, detail, weight}` + band · ISO-8601 timestamps with zone · no SaaS,
no GitHub Actions.

## 3. Thesis writing (W9–W12, 9 Nov–4 Dec, 80 h, together)

Order **Ch3 → Ch4 → Ch2 → Ch1 + Ch5**; Markdown first. Ch3 adds the Analyst (sources and the
as-of consistency reference, question plans, the verifier's four labels and why the question's
plan is the standard, quarantine, prompt-as-instrument), the F-B5 measurement note, and the
arm's two conditions; Ch4 covers Figs 4.1–4.11 + 3.1, with **Fig 4.10 as the admissibility
argument** for every live claim in Ch5. **Checkpoint Fri 27 Nov:** Ch 2–4 drafted.

## 4. Open findings to carry (from `REVIEW.md`)

| ID | Status | What |
|---|---|---|
| F-C7 | **RESOLVED 13 Sep** | CR2 + Bell–McCaffrey; decision models calibrated |
| F-E7 | **RESOLVED 16 Sep** | injector seed rule; 124 runs regenerate their realizations |
| F-B5 | recorded, won't fix | NaN brands cap healthy consistency at 99.88 → Ch3 note |
| F-A1 · F-A2 · F-E5 | 2–6 Nov | positioning · read the 4 load-bearing papers · Zenodo DOI |
| F-B1 | limitation | AIRS constants underived — **now shown on real data** (A11: the 1 s freshness target floors minute-scale ages; AIRS AUC 0.557 vs the records' age 0.690) |
| F-C4 | polish | no multiple-comparison correction across 8 interaction contrasts |
| Kill Q3 | **ANSWERED 23 Sep** | refetch arm: gpt-4o-mini declined the re-read in 1,800 of 1,800 questions, age shown or not (`refetch_findings.md`); `REVIEW.md` carries the defence answer |
| Phase 1D | **DONE 23 Sep** | external validity → the A11 case study (`live_case_study_findings.md`): the mechanism and the attribution transfer; AIRS's calibration does not |
| CR2/BM refs | before Ch3 | verify the citations |

## 5. Cut list (decided — do not reopen)

Real Kafka/Airflow pipeline · leading-indicator arm · third domain / fifth model · `airs lint` ·
generic multi-step agent · Streamlit rewrite · SaaS · GitHub Actions · untestable warehouse
connectors · open-ended NL over arbitrary schemas · writes · multi-user/auth/deployment ·
Mode B's bespoke walkthrough and Mode C (absorbed).

---

# Part B — Operating guide


---

## B1. Files to scan, in order

**Minimum to be productive:**
1. `CLAUDE.md` — **8 invariants**, budget rules, known traps, commands, layout.
2. `docs/handoff/01_state_and_results.md` and this file (the handoff set)
3. `docs/plan.md` — Part 1b is the Analyst; progress notes sit under each stage
4. `docs/analyst_brief.md` — **header first** (decisions + corrections override the body)
5. `REVIEW.md` — findings F-*, kill questions (Phase 2)

**For product work:** `src/airsbench/cli.py` · `probe.py` (validator, `measure`, `score`) ·
`gate/{policy,controller,replay}.py` · `server/{app,api,schemas,bake,__main__}.py` ·
**`sources/{base,demo,files,inline,config,__main__}.py`** · `demo/src/` · tests
`test_{server,replay_api,cli,probe,gate,sources,demo_source}.py` · `tests/dist_smoke.py`

**For the console (A8, built):** `src/airsbench/server/api.py` (the A7 routes the page
calls: `/api/sources`, `/api/models`, `/api/session`, `/api/ask` SSE, `/api/session/{id}`) ·
`src/airsbench/analyst/{loop,sessions}.py` (`Loop.stream` yields gate → refetch → answer →
tick; the page renders those in order) · `demo/src/` · `docs/analyst_brief.md` §6 · `src/airsbench/analysis/flip_partition.py` (`Replayer`,
`QueryOutcome.flipped`, `followed served`) · `docs/flip_partition_findings.md` ·
`src/airsbench/runner/{config,execute,scoring}.py` (`run_arm`, `_airs_components`,
`is_silent_failure`)

**For the refetch arm (done):** `docs/refetch_arm.md` (design, with the history of every
decision) · `docs/refetch_findings.md` · `src/airsbench/runner/refetch.py` (grid execution,
the exact dry-run) · `src/airsbench/analysis/refetch.py` (alignment, the tests, Fig 4.9) ·
`src/airsbench/gate/replay.py` (`replay_menu`, the third verdict) · tests
`test_refetch_{loop,arm,quarantine,analysis}.py`.

**Stale — do not trust for current state:** `docs/campaign_status.md` · `infra_unused/`.

## B2. Code map (what actually runs)

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

## B3. Commands

```bash
make test         # 977 tests, ~70 s
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
python -m airsbench.runner.run --refetch-arm --dry-run   # 35 s, exact: $0.96 / $1.85 worst
```

## B4. Traps (beyond CLAUDE.md)

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

**24 Sep (the freshness target):**
- **Declare the rule before computing the check.** A target picked to suit a data set
  (≈ 30 min for Vélib') would be tuning on the outcome; the rule was "the source's own
  cadence", written into the findings before the number existed.
- **A target changes scores, not ages.** `max_record_age_seconds` is held against
  `mean_age_seconds`; a test pins that a declared target never moves an age budget.
- `probe.py` imports the default from `airs.calculator`; ruff sorts it after `from .airs
  import (...)`.

**23 Sep (A11, results):**
- **Grade consistency against the publication a copy holds, not the moment it was taken.**
  A recorder that polls slower than the feed usually holds the PREVIOUS publication at a
  copy's moment; by wall clock, half the questions read consistency < 100 and four answers
  `corrupted_in_transit`, though the caches copy the feed exactly.
- **The Vélib' feed stamps one publication up to a second apart on different requests**
  (served by more than one node). Match publications within 2 s.
- **The recorder's target poll (20 s) was not its actual (median 41 s)** — each request
  took ~20 s. It still saw 213 publications, but missed 20 of the 48 the caches copied. Poll
  faster than the feed with margin, and log the achieved rate.
- **A station's `last_reported` is not its data's age** — quiet stations report rarely
  (median 33–38 min vs a cache 2.6 / 7.9 min old).
- **Re-grade logged answers only after proving the machinery reproduces them**: under the
  run's own reference, 200/200 must come back identical.
- **The corpus's freshness correction applied itself to every run on disk**; non-corpus
  arms (`NEVER_POOLED`) now pass it by. `test_airs_correction` walks every artifact — a new
  arm's artifacts will meet it.
- The first exposure numbers (6.3% / 12.2%) used the clock reference; the reported ones
  (5.7% / 11.0%) use the corrected one. Quote only the latter.

**23 Sep (A11, building):**
- **The Vélib' feed answers 403 to Python's default User-Agent.** Send one.
- **A history can need two clocks** — the event (`last_reported`) for freshness, the version
  (`recorded_at`) for as-of. A10 gained `version_field`.
- **A replayed record's read time must be the question's moment**, or every record is hours
  old.
- **The loop's gate never got the semantic two-state rule** (`Controller.evaluate` now takes
  `semantic_unmeasured`): bare sources scored semantic 0 in the loop, API and console since
  A6. The demo sources have reviewed manifests, which is why nothing caught it.
- **AIRS freshness floors on minute-scale ages** (`100 × 1 s / age`): it ranks, but barely
  moves the composite. Report record age beside AIRS.
- An early probe claimed a one-hour clock offset in the feed; measured against UTC there is
  none. Measure against the real clock before naming a fault in someone else's data.

**23 Sep (A10):**
- **An http upstream cannot be read as of a past time**, so a lagging cache's wrong answer
  is labelled `corrupted_in_transit`, not `answer_key_moved` — correct by brief correction
  15, and stated in the Tick, but it is why A11 records the feed into a history table.
- **`describe()` on a live source reads it** — for http, a GET of someone's API. The loop
  asked it for `supports_as_of` up to four times per question; `reads_as_of()` now answers
  from the declaration.
- **`with sqlite3.connect()` scopes a transaction, not the connection** — close it
  (`contextlib.closing`).
- **`airs sources` / `airs analyst` take `--sources` BEFORE the subcommand.**
- A live sample's moment is real time: `airs sources sample` said "simulated time
  1790169717s" until the label split demo from live.
- `api.py` imports `SourceError` twice (module and function); a replace-once edit guard
  trips on it.

**23 Sep (refetch arm, step 6):**
- **An exposure check must drop unverifiable questions before counting flips.** The design's
  pre-check counted "literal answer not correct", which includes questions with no in-stock
  product at answer time — 14.7% instead of 12.9%. Count `served ≠ truth` over verifiable
  questions only, as `runner/refetch.flipped_as_delivered` does.
- **A sample of questions can be unlucky and still be valid.** The arm's 450 questions are
  9.3% exposed against 12.9% on a broad sample (~2.3 SD). Every cell shares them, so no
  contrast is biased; only the power of flipped-only contrasts drops. Report both numbers.
- **`Batch` is baked into the server's replay corpus field by field** (`asdict` in
  `server/bake.py`, `Batch(**row)` in the API). A new field changes baked data. The third
  verdict reads lineage through its own `load_lineage` instead; `Batch`, `Outcome` and
  `replay()` are untouched.
- **A synthetic campaign's first 40 stale questions contain no flipped one** (the first
  fall at indices 40, 43 and 46); a test of "a re-read repairs every flipped question" needs
  ≥ 50, or it has nothing to test. Assert the count is positive.
- A heredoc Python string turns `\n` inside generated f-strings into real line breaks and
  the module stops parsing. Parse the file (`ast.parse`) after any generated edit.
- Two cells can agree on every aggregate by chance (age hidden and shown, stale, replication
  1: 80.5 / 15.4 / 4.0) while differing on 13 of 150 answers. Check question by question
  before suspecting the treatment did not reach the model; the token counts confirm it did.

**23 Sep (refetch arm, steps 2–3):**
- **After a gate re-read the Tick's gate block describes the REFRESHED records**, so the
  question's first reading (the one that refused) was lost. `refetch.airs_before` and
  `dimensions_before` keep it; the arm prices every verdict on it.
- **Three loaders admitted every arm**: `flip_partition` and `phase1_check` under
  `include_other_arms=True`, and `silent_definition`, which would have added a `refetch` row to
  a published robustness table. `NEVER_POOLED` closes all three; the quarantine test runs a
  genuine arm artifact beside real runs through every loader.
- **`campaign_state` keyed runs without the refetch mode**, so three cells sharing a seed read
  as duplicates of one another. The key now includes it.
- **A second turn costs about twice a first** (the records are sent twice). The design's worst
  case assumed equal calls and was ~25% low; count, never assume.
- `--n-queries` no longer defaults to 12 globally: every old mode still gets 12, the arm 150.
- Healthy and stale prompts total the **same** token count (628,828) although 118 of 150
  questions serve different values: price and stock changes rarely change token length. It
  looks like a pairing bug and is not one — checked.
- A test that loops over an object that turns out not to exist passes vacuously
  (`Panel.members`); pin the allow-list itself as well.

**23 Sep (refetch arm, step 1):**
- **A reply that is still a re-read request is not an answer.** It was graded as a
  committed wrong answer — a silent failure the model never claimed — whenever the model
  asked twice, or asked where no re-read was offered. The loop now marks it unparseable
  (`unanswered_action`), and `verify` refuses to commit any answer carrying `refetch_ids`.
- **`build_tick` stamped `arm: "live"` unconditionally.** Every loader drops `live`, so the
  arm's own decisions would have vanished. `Loop(provenance=…)`; live stays the default.
- **Refreshed records need their own age** when a pipeline shows age — ≈0 s, not the
  stale age they replaced (`Loop._refetch`).
- **Early question seeds can have 2 candidates** (`10_001_000`, `…001`); a test about a
  partial re-read needs a full set (`…004`), or its "untouched" half is empty and passes
  vacuously. Assert the size.
- LangChain maps a `("assistant", …)` tuple to `AIMessage`, so `call_json` carries a
  continued exchange unchanged. llama's tokenizer counted 3,509 input tokens for one.
- The forbidden-word lists match substrings: the follow-up says "read again" and "as they
  stand now" — nothing with `age`, `old` or `recent` inside it.

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

## B5. Working conventions the author expects

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

## B6. Suggested first message for a new session

> Read `docs/handoff/01_state_and_results.md`, then `02_plan_and_next_steps.md`
> (Part A is the next step, Part B the operating guide), then `CLAUDE.md`,
> `docs/plan.md` and the header of `docs/analyst_brief.md`. Treat the handoff as a
> starting point, not ground truth: confirm the state with `git log --oneline -3`
> (expect the newest commit named in handoff 1) and `make test` (the count in handoff 1)
> before trusting anything below.
> Then continue from 02 Part A — the refetch arm, which is the last experiment and
> the only paid work left. Work step by step: propose before writing code, surface
> decisions to me as questions instead of guessing, keep every document current in
> the same commit as the change it describes, and commit only when I ask.
