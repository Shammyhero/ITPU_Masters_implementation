# Handoff 2/3 — Plan and next steps

Authoritative plan: **`docs/plan.md`** (Part 1b = the Analyst). Product brief as adopted:
**`docs/analyst_brief.md`** — its header (decisions + corrections) overrides the brief
body. Adversarial audit: **`REVIEW.md`** (Phase 3 is now design history). This file is
the condensed "what to do next" view. Update it whenever the plan moves.

---

## 1. Immediate next step: stage A1 — sources

W1, W2, F-C7 and W3 are done (14 Sep, ~2 weeks ahead). The Analyst was adopted on
14 Sep and replaces the old W4–W8. Start with **A1**, then A3 → A4 before any UI:

| Stage | h | Summary |
|---|---|---|
| **A1** | 12 | `src/airsbench/sources/`: `Source` protocol (`sample`, `fetch`, `describe`), `SourcePair`, read-only; `demo` adapter (bundled ESCI slice + update stream, fault chain applied once by the source) built first; `files` adapter; sources **declared** in `sources.yaml` / CLI; paste becomes the `inline` source |
| A2 | 8 | manifest schema, committed manifests, review/approve, costed inference; **two-state semantic rule** |
| **A3** | 14 | verifier + checkable question types + live attribution, stdout Ticks, no UI — **non-negotiable** |
| **A4** | 6 | verifier agreement with the corpus, exact, retrieval only → **Fig 4.10** — **non-negotiable, stops UI work if it fails** |
| A5 | 8 | model options: free local Ollama (discovered) or API key (OpenAI / Anthropic / **Gemini**, new); caps before each call; close the "unpriced = free" gap |
| A6 | 12 | router admit/refetch/refuse + `analyst/loop.py`, shared with the refetch arm |
| A7 | 8 | `/api/sources`, `/api/models`, `/api/session`, **`/api/ask` (SSE Ticks)**; live quarantine + credential tests |
| A8 | 18 | console: source picker, manifest review, model choice, conversation, trace panel, meter, semantic toggle, replay feed |
| A9 | 15 | task switch, recommended policy, meter prior (raw vs true cost), printable report |
| A10 | 8 | postgres, duckdb/sqlite, http adapters — cut first |
| A11 | 6 | live-source case study → Fig 4.11 — cut second |
| Refetch arm | 28 | agent-initiated + gate-initiated conditions, ~54 runs, ~$2.20, Fig 4.9, hard cut 30 Oct |

**Calendar:** A1 + A3 start (14–18 Sep) · A3 + A4 + A2 (21–25 Sep) · A5 + A6 (28 Sep–2 Oct) ·
A7 + A8 (5–9 Oct) · A8 + A9 + M1 presentation (12–16 Oct) · A9 + arm build + A10 (19–23 Oct) ·
arm run + A10 (26–30 Oct) · A11 + positioning + papers + DOI (2–6 Nov). **159 h in ~160 h —
no buffer**, by the author's choice to keep everything; cut order if a checkpoint slips:
A10 → A11 → A9 report → A2 inference → A8 toggle.

**Checkpoints:** Fri 25 Sep A3 prints attributed Ticks · **Fri 2 Oct Fig 4.10 exact** · Fri 9 Oct
`/api/ask` end to end on the free model · **Fri 16 Oct M1** · Fri 23 Oct arm dry-run · Fri 30 Oct
arm runs (hard cut) · **Fri 6 Nov freeze**.

## 2. Decisions made on 14 Sep (do not re-litigate)

- **Adopt the Analyst**, with the 14 corrections in the brief's header (correctness before
  attribution; two-state semantic rule; toggle = real injector; no upstream loses consistency
  and the verifier, not freshness; same ids at t1; Fig 4.10 retrieval-only and exact; router
  REFETCH ≠ the arm; "offline $0" needs a local model; live never in `results/runs/`; keep the
  Tick `airs` extension; the plan prompt is a different instrument; honest case-study framing;
  per-mode privacy wording).
- **Sources declared locally**, credentials from environment variables; the console selects,
  tests and describes declared sources; no path/DSN/URL over HTTP.
- **Refetch arm: two conditions, one loop.**
- **Models: Free (local Ollama, whatever is installed) or API key (OpenAI, Anthropic, Gemini)**;
  keys from environment or entered for the session, memory only.
- **W4's Mode A work kept**, redesigned into A9. Timeline does not drop features; the cut order
  applies only when a checkpoint is missed.

## 3. Product decisions from W3 (still standing)

- Real tool for a data engineer's own pipeline; the defence is one place it is shown.
- `pip install` → `airs serve`; FastAPI serving the static Next.js export; one process.
- **No scoring rule implemented twice.**
- fastapi + uvicorn core; `probe`, `gate`, `airs` import no web stack (pinned).
- Tick `airs` block = `{score | null, detail, weight}` + band, all modes.
- Timestamps epoch seconds or ISO-8601 with zone; duplicate upstream ids refused.
- No SaaS, no GitHub Actions.

## 4. Thesis writing (W9–W12, 9 Nov–4 Dec, 80 h, together)

Order **Ch3 → Ch4 → Ch2 → Ch1 + Ch5**; Markdown first. Ch3 must add the Analyst (verifier,
attribution, quarantine, prompt-as-instrument) and the arm's two conditions; Ch4 covers
Figs 4.1–4.11 + 3.1. RQs v2 §9 declares the three new analyses (verifier agreement, refetch
arm, case study) and their hypotheses. **Checkpoint Fri 27 Nov:** Ch 2–4 drafted.

## 5. Open findings to carry (from `REVIEW.md`)

| ID | Status | What |
|---|---|---|
| F-C7 | **RESOLVED 13 Sep** | CR2 + Bell–McCaffrey; decision models calibrated |
| F-A1 | 2–6 Nov | ISO 25012 / data contracts / agent benchmarks positioning |
| F-A2 | 2–6 Nov | Read the 4 load-bearing papers in full |
| F-B1 | limitation | AIRS constants underived — state in Ch3/Ch5 |
| F-C4 | polish | No multiple-comparison correction across 8 interaction contrasts |
| F-E5 | 2–6 Nov | Zenodo DOI |
| Kill Q3 | Oct | "Is one API call agentic?" → refetch arm, agent-initiated condition |
| Phase 1D | Nov | external validity → live case study (A11) |
| CR2/BM refs | before Ch3 | verify the CR2, Bell–McCaffrey and few-cluster citations |
| Fragility predictability | idea | per-question readiness signal; unscheduled |

## 6. Cut list (decided — do not reopen)

Real Kafka/Airflow pipeline · leading-indicator/AIRS-drift arm · third task domain / fifth
model · `airs lint` · generic multi-step agent · Streamlit rewrite · SaaS hosting · GitHub
Actions · untestable warehouse connectors · open-ended NL over arbitrary schemas · writes of
any kind · multi-user/auth/deployment · Mode B's bespoke walkthrough and Mode C (absorbed).
