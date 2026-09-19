# Handoff 2/3 — Plan and next steps

Authoritative plan: **`docs/plan.md`** (Part 1b = the Analyst). Product brief as adopted:
**`docs/analyst_brief.md`** — its header (decisions + 18 corrections) overrides the body.
Adversarial audit: **`REVIEW.md`** (Phase 3 is design history). This file is the condensed
"what to do next" view. Update it whenever the plan moves.

---

## 1. Immediate next step: A8 — the console, and the M1 deliverable

**A1–A7 are done.** The whole answering path exists and is exercised over real HTTP:
`airs serve --sources` offers declared sources, opens a session under a policy and a
spend cap, and streams one question as gate → refetch → answer → verified Tick, with the
meter accumulating and every Tick quarantined in `~/.airs/sessions/`.

**A8 (18 h, 5–16 Oct) is now the only thing between here and M1.** It is the interface
your supervisor sees on 16 October, and it consumes A7's routes without adding logic:

- **source picker** from `GET /api/sources` (name, whether it can be verified, semantic
  state) and **model picker** from `GET /api/models` (`literal`, local Ollama, providers
  whose key is configured — the page never sends a key);
- **the conversation**: one renderer for the Tick, fed by the SSE stages, so the gate's
  verdict, the answer and *then* the verification appear in that order — the pause is the
  demonstration, so do not batch the events;
- **the meter**: answered / refused / refetched / prevented / forfeited and the live
  exchange rate, from `GET /api/session/{id}`;
- **the semantic toggle** (drop the manifest mid-session; runs the real injector, brief
  correction 3) — first thing to cut if the week runs short;
- Mode B's walkthrough becomes the same renderer fed from `/api/replay`, so delete the
  bespoke six-step UI rather than maintaining two.

Read `docs/analyst_brief.md` §6 and `docs/plan.md` Part 1b A8 before starting. `make demo`
runs the Next.js dev server on :3000 against `airs serve --dev`; `make web` builds it into
the package, and `make dist-check` must stay green because the console ships in the wheel.

| Stage | h | State |
|---|---|---|
| A1 sources | 12 | **done 14 Sep** (`e78ab97`) |
| A3 verifier | 14 | **done 15 Sep** (`f5da23a`) |
| A4 Fig 4.10 | 8 | **done 16 Sep** (`b2589da`) — gate Fri 2 Oct met early |
| A2 manifest | 8 | **done 17 Sep** |
| A5 model options (Ollama / OpenAI · Anthropic · Gemini, caps, "unpriced = free" closed) | 8 | **done 18 Sep** |
| A6 router + shared loop | 12 | **done 18 Sep** |
| A7 API + firewalls (`/api/ask` SSE, live quarantine, credential test) | 8 | **done 20 Sep** |
| **A8 console** | 18 | **next** — 5–16 Oct · the M1 deliverable |
| A9 task switch, recommended policy, meter prior, report | 15 | 12–23 Oct |
| Refetch arm (two conditions, ~$2.20, Fig 4.9) | 28 | 19–30 Oct, hard cut 30 Oct |
| A10 postgres/duckdb/http | 8 | cut first |
| A11 live case study (Fig 4.11) | 6 | cut second |

**Checkpoints:** ~~Fri 2 Oct Fig 4.10 exact~~ **met 16 Sep** · Fri 9 Oct `/api/ask` on the
free model · **Fri 16 Oct M1** · Fri 23 Oct arm dry-run · Fri 30 Oct arm runs ·
**Fri 6 Nov freeze**. 161 h in ~160 h, no buffer; cut order A10 → A11 → A9 report →
A2 inference → A8 toggle.

## 2. Decisions made (do not re-litigate)

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
| F-B1 | limitation | AIRS constants underived |
| F-C4 | polish | no multiple-comparison correction across 8 interaction contrasts |
| Kill Q3 | Oct | refetch arm, agent-initiated condition. **First live evidence (18 Sep):** offered a re-read, `llama3.1:8b` asked 0 times in 12 stale questions |
| Phase 1D | Nov | external validity → A11 case study |
| CR2/BM refs | before Ch3 | verify the citations |

## 5. Cut list (decided — do not reopen)

Real Kafka/Airflow pipeline · leading-indicator arm · third domain / fifth model · `airs lint` ·
generic multi-step agent · Streamlit rewrite · SaaS · GitHub Actions · untestable warehouse
connectors · open-ended NL over arbitrary schemas · writes · multi-user/auth/deployment ·
Mode B's bespoke walkthrough and Mode C (absorbed).
