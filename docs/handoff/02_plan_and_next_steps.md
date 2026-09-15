# Handoff 2/3 — Plan and next steps

Authoritative plan: **`docs/plan.md`** (Part 1b = the Analyst). Product brief as adopted:
**`docs/analyst_brief.md`** — its header (decisions + 18 corrections) overrides the body.
Adversarial audit: **`REVIEW.md`** (Phase 3 is design history). This file is the condensed
"what to do next" view. Update it whenever the plan moves.

---

## 1. Immediate next step: A4 — verifier agreement, Fig 4.10

**A1 (sources) and A3 (the verifier) are done.** `airs analyst ask` verifies answers on
the demo source and attributes each wrong one with four labels; a real local model
(`llama3.1:8b`) reproduced the thesis live — confident, stale-faithful, `answer_key_moved`.

**A4 (8 h, non-negotiable, gate Fri 2 Oct)** — `analysis/verifier_agreement.py`:
1. For every retrieval run of the main factorial and the freshness sweep, rebuild each
   decision's candidates, query time, served state and true state with
   `analysis.flip_partition.Replayer` (already verified decision by decision against the
   logged ground truth), and run `analyst.verify` with the logged `chosen` as the answer
   (`abstained`, `parse_failed` from the log) and `DEMO_PLAN` (min_by price, stock > 0).
2. **Exact checks:** `correct` == logged `correct`; silent failure == `is_silent_failure`;
   `flipped` == `QueryOutcome.flipped`; answer_key_moved + both == wrong on flipped;
   corrupted_in_transit + agent_impairment == wrong on unflipped; the published
   `flip_partition_findings.md` §2 table reproduced.
3. **Fault realizations** (author decision): regenerate each run's delivered records by
   replaying `runner.execute.build_fault_chain(config)` over the candidates **in the
   runner's exact order** (one `chain.apply` per record, queries in plan order, skipped
   queries consuming no chain draws — check `run_retrieval`), then require the run's logged
   `airs` consistency and semantic to be reproduced exactly before trusting the
   corrupted/impairment split. Watch: the runner builds records with `build_product_record`
   from the served state and `build_event_ts`; latency is analytic.
4. Emit **Fig 4.10**, `docs/verifier_agreement_findings.md`, a test, and add the figure to
   `make figures`. Any mismatch is a verifier bug and **stops UI work**.

Then **A2** (manifest, two-state semantic rule) in the week of 21 Sep.

| Stage | h | State |
|---|---|---|
| A1 sources | 12 | **done 14 Sep** (`e78ab97`) |
| A3 verifier | 14 | **done 15 Sep** |
| **A4 Fig 4.10** | 8 | **next** — gate **Fri 2 Oct** |
| A2 manifest | 8 | 21–25 Sep |
| A5 model options (free Ollama / OpenAI · Anthropic · Gemini key; close "unpriced = free") | 8 | 28 Sep–2 Oct |
| A6 router + shared loop | 12 | 28 Sep–2 Oct |
| A7 API + firewalls (`/api/ask` SSE, live quarantine, credential test) | 8 | 5–9 Oct |
| A8 console | 18 | 5–16 Oct |
| A9 task switch, recommended policy, meter prior, report | 15 | 12–23 Oct |
| Refetch arm (two conditions, ~$2.20, Fig 4.9) | 28 | 19–30 Oct, hard cut 30 Oct |
| A10 postgres/duckdb/http | 8 | cut first |
| A11 live case study (Fig 4.11) | 6 | cut second |

**Checkpoints:** **Fri 2 Oct Fig 4.10 exact** · Fri 9 Oct `/api/ask` on the free model ·
**Fri 16 Oct M1** · Fri 23 Oct arm dry-run · Fri 30 Oct arm runs · **Fri 6 Nov freeze**.
161 h in ~160 h, no buffer; cut order A10 → A11 → A9 report → A2 inference → A8 toggle.

## 2. Decisions made (do not re-litigate)

**15 Sep, A3:** answers verified against **the question's plan**; the agent's plan recorded
(`plan_matches_question`, `agent_plan_agrees`), never graded · **four labels**
(`answer_key_moved`, `both`, `corrupted_in_transit`, `agent_impairment`) · A4 includes
regenerating fault realizations (+2 h) · answerers in A3 are `literal` and local Ollama only.

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
plan is the standard, quarantine, prompt-as-instrument) and the arm's two conditions; Ch4 covers
Figs 4.1–4.11 + 3.1. **Checkpoint Fri 27 Nov:** Ch 2–4 drafted.

## 4. Open findings to carry (from `REVIEW.md`)

| ID | Status | What |
|---|---|---|
| F-C7 | **RESOLVED 13 Sep** | CR2 + Bell–McCaffrey; decision models calibrated |
| F-A1 · F-A2 · F-E5 | 2–6 Nov | positioning · read the 4 load-bearing papers · Zenodo DOI |
| F-B1 | limitation | AIRS constants underived |
| F-C4 | polish | no multiple-comparison correction across 8 interaction contrasts |
| Kill Q3 | Oct | refetch arm, agent-initiated condition |
| Phase 1D | Nov | external validity → A11 case study |
| CR2/BM refs | before Ch3 | verify the citations |

## 5. Cut list (decided — do not reopen)

Real Kafka/Airflow pipeline · leading-indicator arm · third domain / fifth model · `airs lint` ·
generic multi-step agent · Streamlit rewrite · SaaS · GitHub Actions · untestable warehouse
connectors · open-ended NL over arbitrary schemas · writes · multi-user/auth/deployment ·
Mode B's bespoke walkthrough and Mode C (absorbed).
