# Handoff 2/3 — Plan and next steps

Authoritative plan: **`docs/plan.md`** (Part 1b = the Analyst). Product brief as adopted:
**`docs/analyst_brief.md`** — its header (decisions + 15 corrections) overrides the body.
Adversarial audit: **`REVIEW.md`** (Phase 3 is design history). This file is the condensed
"what to do next" view. Update it whenever the plan moves.

---

## 1. Immediate next step: A3 — the verifier (then A4)

**A1 (sources) is done** (14 Sep): `src/airsbench/sources/` with the `demo` source (the
study's own serving recipe over a bundled slice), `files`, `inline`, `sources.yaml`,
`airs sources`. Next, per rule 4 of the plan — **verifier before interface**:

- **A3 (14 h, non-negotiable)** — `src/airsbench/analyst/verifier.py`: answer-plan schema;
  checkable types `min_by`, `max_by`, `count_where`, `sum_where`, `lookup`, `top_k`, executed
  deterministically on the delivered read (t0) and the upstream read of **the same ids**;
  `RetrievalAgent.ground_truth` becomes the `min_by` case. Correctness against upstream first,
  then attribution (`answer_key_moved` / `agent_impairment` / `both`; none for abstained or
  parse-failed); `runner/scoring.py::is_silent_failure` imported. Build on the `demo` source,
  stdout Ticks, no UI. Use `Sample.meta["served_as_of"]` for the consistency reference and
  `Sample.as_of` for the answer key.
- **A4 (6 h, non-negotiable, by Fri 2 Oct)** — the verifier over the main-factorial and
  freshness-sweep **retrieval** runs must reproduce correctness, silent-failure rates and the
  flip-partition split **exactly** → `analysis/verifier_agreement.py`, **Fig 4.10**,
  `docs/verifier_agreement_findings.md`. Any mismatch stops UI work.
- A2 (manifest, two-state semantic rule) follows in the week of 21 Sep.

| Stage | h | State |
|---|---|---|
| A1 sources | 12 | **done 14 Sep** |
| A2 manifest | 8 | 21–25 Sep |
| **A3 verifier** | 14 | **next** (gate Fri 25 Sep: attributed Ticks on `demo`) |
| **A4 Fig 4.10** | 6 | gate **Fri 2 Oct** |
| A5 model options (free Ollama / OpenAI · Anthropic · Gemini key; close "unpriced = free") | 8 | 28 Sep–2 Oct |
| A6 router + shared loop | 12 | 28 Sep–2 Oct |
| A7 API + firewalls (`/api/ask` SSE, live quarantine, credential test) | 8 | 5–9 Oct |
| A8 console | 18 | 5–16 Oct |
| A9 task switch, recommended policy, meter prior, report | 15 | 12–23 Oct |
| Refetch arm (two conditions, ~$2.20, Fig 4.9) | 28 | 19–30 Oct, hard cut 30 Oct |
| A10 postgres/duckdb/http | 8 | cut first |
| A11 live case study (Fig 4.11) | 6 | cut second |

**Checkpoints:** Fri 25 Sep A3 · **Fri 2 Oct Fig 4.10 exact** · Fri 9 Oct `/api/ask` on the
free model · **Fri 16 Oct M1** · Fri 23 Oct arm dry-run · Fri 30 Oct arm runs · **Fri 6 Nov
freeze**. No buffer; cut order A10 → A11 → A9 report → A2 inference → A8 toggle.

## 2. Decisions made (do not re-litigate)

**14 Sep, the Analyst:** adopt with the brief's corrections · sources declared locally,
credentials from environment variables · refetch arm = agent-initiated + gate-initiated
conditions on one loop · models: free local Ollama or API key (OpenAI, Anthropic, Gemini),
keys in memory only · W4's Mode A work kept as A9 · timeline does not drop features.

**14 Sep, A1:** `sources.yaml` in YAML with PyYAML as a core dependency · Parquet as the
optional `[parquet]` extra · demo time is simulated per question (reads exactly as of the
answer) · `airs sources` command added · consistency is scored against upstream as of when
the delivered values were true (brief correction 15).

**W3, still standing:** real tool, not a prop · `pip install` → `airs serve` · no scoring
rule implemented twice · fastapi + uvicorn core, `probe`/`gate`/`airs` import no web stack ·
Tick `airs` block `{score | null, detail, weight}` + band · ISO-8601 timestamps with zone ·
no SaaS, no GitHub Actions.

## 3. Thesis writing (W9–W12, 9 Nov–4 Dec, 80 h, together)

Order **Ch3 → Ch4 → Ch2 → Ch1 + Ch5**; Markdown first. Ch3 adds the Analyst (sources and the
as-of consistency reference, verifier, attribution, quarantine, prompt-as-instrument) and the
arm's two conditions; Ch4 covers Figs 4.1–4.11 + 3.1. **Checkpoint Fri 27 Nov:** Ch 2–4 drafted.

## 4. Open findings to carry (from `REVIEW.md`)

| ID | Status | What |
|---|---|---|
| F-C7 | **RESOLVED 13 Sep** | CR2 + Bell–McCaffrey; decision models calibrated |
| F-A1 · F-A2 · F-E5 | 2–6 Nov | positioning (ISO 25012, data contracts, agent benchmarks) · read the 4 load-bearing papers · Zenodo DOI |
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
