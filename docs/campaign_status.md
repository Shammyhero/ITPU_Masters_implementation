# Campaign status & session handoff

**Updated:** 2026-08-01 · **ALL EXPERIMENTAL ARMS COMPLETE — 248 runs**

This is the operational entry point for any session. Read `CLAUDE.md` first for
the invariants that must not be broken, then this file for what to do next.

---

## State

| | |
|---|---|
| Design | Paired, replication-major, 144 runs @ 80 queries |
| Phase 1 | ✅ **complete — GO** (36/36, all four checks passed) |
| Phase 2 | ✅ **complete** — 78/78, zero failures |
| Runs on disk | **144** main · **14** detectability · **36** sweep · **54** cross-model (3 models) |
| Spent | **$1.91** of ~$7 OpenAI · **$2.73** of ~$4 Anthropic |
| Tests | 322 passing · lint clean |
| AIRS fix | freshness double-count corrected in code; 16 old runs recomputed in the analysis layer |
| Analysis | **RQ1 ✅ · RQ2 ✅ · RQ3 ✅ · RQ4 ✅ · RQ5 ✅ — all five answered** |
| Tooling | `airs probe` (score) · `airs gate` (enforce) · `gate.replay` (price a policy) |

### For a session starting cold — read this box first

**Every experiment is finished and every RQ is answered.** 248 runs, $4.64 of
~$11, 322 tests green. Nothing is mid-flight; nothing needs resuming. What
remains is **build and write**, not measure.

The five findings, in one place:

| RQ | Answer | Where |
|---|---|---|
| RQ1 | Degradation **is** monotone in data age; threshold 5.05 s on both tasks. But retrieval decomposes into *exposure* (rises 2.3%→19.2%) × *conditional rate* (flat at ceiling from 0.55 s). | `freshness_sweep_findings.md` |
| RQ2 | Rank on **residual** impairment, not raw accuracy: schema drift −0.173 > semantic stripping −0.128 > freshness −0.003 ≈ latency 0. | `flip_partition_findings.md` |
| RQ3 | Silent failure is driven by schema drift + semantic stripping (retrieval) and freshness (classification). Abstention is driven by semantic stripping **and nothing else** (OR 51.9). | `statistical_analysis_findings.md` |
| RQ4 | AIRS ranks held-out pipelines at ρ ≈ −0.8 and **beats agent confidence exactly where confidence is at chance** (retrieval, AUC 0.501). Calibrate per task, against total error. | `airs_calibration_findings.md` |
| RQ5 | The ranking transfers **across models** (mean τ +0.762; two hosted models identical at τ +1.000) but **inverts across tasks**. | `cross_model_findings.md` |

**The recommendation, now measured rather than asserted** (`gate_findings.md`):
enforcement works, but ~75% of silent failure is agent-intrinsic and untouchable
by any data gate, and every worthwhile policy forfeits **7–21 correct answers per
silent failure genuinely prevented**. The staleness budget the study originally
recommended is the *wrong* gate for retrieval — gate on consistency there, on
freshness for classification. Latency is un-gateable on both, a fifth
independent route to that null.

**The thesis's central claim, established three independent ways:** freshness
does not impair the agent — it moves the answer key. Flip-partition residual
−0.003 at both severities; decision-level OR 1.00 (p = 0.998) on answerable
retrieval; replicates as a null on all four models (0.88–1.33).

**H3, restated by the data:** an agent abstains only when the corruption is
legible *inside the delivered record*. Semantic stripping → 64% abstention on
Haiku classification. Freshness → 5%. Delivering the record's age changed
nothing (detectability arm, null). So legibility needs the datum **and** a
standard to judge it against.

**Six methodological traps this campaign hit and fixed** — each would have
produced a confident wrong number, and each is now pinned by test:

1. Freshness was double-counted (AIRS 9.95 where 19.80 was right) — fixed in
   `build_event_ts`, 16 old runs corrected in the analysis layer.
2. Raw accuracy under freshness is the answer-flip rate measured with an LLM —
   fixed by the flip partition.
3. Kendall's τ on 4 faults **cannot** reach p<0.05 (floor 0.083) — the report
   prints the floor so "n.s." is not misread as "does not generalise".
4. McNemar needs ≥6 one-directional discordant pairs; the detectability arm had
   2 — the null is reported as underpowered, not as evidence.
5. A NaN from an incomparable pair poisoned a mean and produced a confident
   "does NOT generalise" from data saying the opposite.
6. A fault that drives **refusal** lowers silent failure while destroying
   accuracy (Haiku: acc 0.29, abstention 64%, OR 0.80) — ranking on silent
   failure alone would call the worst fault the safest.

**Cost estimation gotcha:** `TOKEN_PROFILES` in `runner/run.py` is per model
family. A single global output-token figure under-estimated the Haiku arm by
1.8× and tripped the spend guard mid-run. Re-derive from `results/runs/*.json`
after any prompt change.

---

Resumption is exact: `build_grid()` is deterministic and every run writes its
JSON on completion. Interrupting mid-run loses only that run (~$0.01).

```bash
python -m airsbench.analysis.campaign_state
```

Prints per-arm progress and the exact resume command. **Do not count files for
the offset** — `--offset` indexes into `build_grid()`, but the results directory
now also holds the detectability arm (and later the sweep and cross-model
subset), so counting over-reports it and silently skips runs. `campaign_state`
matches artifacts to grid entries by seed instead, and refuses to emit a resume
command if completed runs are not a contiguous prefix.

---

## Why phase 2 was paused — resolved, and phase 2 has since completed

A question mid-campaign — *"why should the agent doubt the price?"* — exposed
that the rendered record carried **no timestamp, no age, nothing about when the
value was true**. The agent was never given anything by which staleness could be
detected, so the phase-1 reading blamed the agent for missing what the pipeline
never delivered.

Both follow-ups ran before the remaining 78 runs, which was the point of pausing
— framing is cheaper to fix before the data than after:

- The **flip partition** showed freshness does not impair the agent at all — it
  only moves the answer key. The finding is the 90% silent-failure rate on the
  queries it makes unanswerable.
- The **detectability arm** delivered the record's age and **nothing changed**.
  The reframing holds, but its obvious remedy does not: the pipeline delivering
  nothing to notice is the problem, and delivering the number alone is not the
  fix. Ship the age *and* the staleness budget, and enforce the budget outside
  the model.

Net effect on the conditions: **none.** Phase 2 ran the design unchanged; what
changed is how its results are read.

---

## Next steps, in order

| # | Step | Cost | Why this order |
|---|---|---|---|
| ~~1~~ | ~~**Flip-partition analysis**~~ | $0 | ✅ **done** — `docs/flip_partition_findings.md`. Changed how freshness *and* RQ2 must be reported. |
| ~~2~~ | ~~**Detectability arm**~~ | $0.153 | ✅ **done — null branch.** Metadata alone changes nothing. `docs/detectability_findings.md`. |
| ~~3~~ | ~~**Finish phase 2**~~ | $0.768 | ✅ **done — 144/144, zero failures.** All conclusions held and tightened at 4 replications. |
| ~~4~~ | ~~Freshness sweep~~ | $0.290 | ✅ **done — monotone on both tasks.** Threshold 5.05 s. `docs/freshness_sweep_findings.md`. |
| ~~5~~ | ~~Cross-model: local open weights~~ | $0 | ✅ **done — ranking transfers (mean τ +0.778).** Both models FLOOR on classification; retrieval only. `docs/cross_model_findings.md`. |
| ~~6~~ | ~~Cross-model: Haiku~~ | $2.73 | ✅ **done — 18/18.** Ranking transfers across models but **inverts across tasks**. `docs/cross_model_findings.md`. Cost ran 1.8× the estimate; the spend guard caught it at 12/18 and the estimator is now calibrated per model family. |
| ~~7~~ | ~~Statistical analysis~~ | $0 | ✅ **done — RQ2 + RQ3 answered.** Freshness on answerable retrieval: **OR 1.00, p = 0.998**. `docs/statistical_analysis_findings.md`. |
| ~~8~~ | ~~AIRS calibration~~ | $0 | ✅ **done — RQ4 answered.** Ranks held-out pipelines at ρ ≈ −0.8; **beats agent confidence on retrieval, where confidence is at chance (AUC 0.501)**. `docs/airs_calibration_findings.md`. |
| ~~9~~ | ~~`airs probe`~~ | $0 | ✅ **done — `python -m airsbench.probe`.** Scores a pipeline with no agent, no ground truth, no model calls. Ships the RQ4 weights as a versioned artifact; refuses to score an unmeasured dimension as healthy. Worked example in `examples/probe/`. |
| ~~10~~ | ~~AIST demo — React / Next.js~~ | $0 | ✅ **done.** Four interactive acts, not a dashboard: the reader plays the agent and walks into the silent failure, then judges four faults by eye and finds their instinct matches the agent's abstention rate. `demo/README.md`. |
| ~~10.5~~ | ~~**`airs gate` — admission control**~~ | $0 | ✅ **done — the recommendation, tested.** `python -m airsbench.gate` refuses a batch before the agent is asked; `gate.replay` prices every policy over all 13 554 decisions. **Enforcement works and costs 7–21 correct answers per silent failure genuinely prevented**, and the staleness budget turns out to be the *wrong* gate for retrieval. `docs/gate_findings.md`, `examples/gate/`. |
| **11** | `airs lint` *(stretch)* | $0 | Static semantic-completeness for schemas; **first to cut** — the writing matters more. |
| **12** | **Release + chapters** | $0 | **← the critical path now.** Every RQ has a findings doc to draw from. The risk register rates late writing High/High and it is the only thing left that can still go wrong. |

### AIST demo — built, and what it argues

`demo/` is a Next.js static export (`npm --prefix demo run dev`). Data is baked
from the artifacts by `airsbench.analysis.export_demo_data`; the page makes no
model calls and needs no key. Full description in `demo/README.md`.

It is structured as an argument, not a dashboard — four acts the reader plays:

1. **You be the agent.** A real query and the real records the agent was
   served, reconstructed exactly. The reader picks the cheapest in-stock
   product, picks what the agent picked, and both are wrong. Nothing in the
   record could have told either of them.
2. **Could you have known?** The same record under four faults. The reader's eye
   and the agent's abstention rate produce the same ordering (1%, 0%, 1%, 18%).
3. **So ask the agent how sure it is.** The reader guesses, then meets 0.501.
4. **Probe your own pipeline.** Live, in-browser, with the UNMEASURED guard.

Then an appendix — severity dial, cross-model table — for readers who want the
underlying data.

**Trap when working on it:** never run `next build` while `next dev` is up. They
share `.next/` and the dev server 500s with
`__webpack_modules__[moduleId] is not a function`. Stop dev, `rm -rf .next`.

### Note on local models, for anyone re-running them

Ollama is installed and both models are pulled. Local throughput is **~4 s per
retrieval call**, not the ~1 s a naive benchmark suggests — a benchmark that
reuses one prompt hits llama.cpp's prompt cache, and real queries never do.
Budget ~90 min per 8B model at 1800 calls, ~2.5 h at 14B. Use `caffeinate -i -w
<pid>` and keep the lid open; closing it sleeps an Apple Silicon Mac regardless.

---

**Writing runs throughout.** Chapter 3 is drafted. Chapters 1–2 follow from
`literature_review.md` §7 and `research_questions_v2.md` §8. The project's own
risk register rates late writing High/High — it is the likeliest failure mode.

---

## Main factorial — final (144 runs, all conditions, $1.470)

Coverage balanced at 36 runs per arm, no floored arm, no coherence violation.
Re-runnable with `python -m airsbench.analysis.phase1_check`.

**Raw accuracy — necessary, but NOT the headline.** Freshness's drop here is
almost entirely mechanical; read this table through §"flip partition" below.

| fault (severe) | accuracy | Δ vs baseline | abstained | silent failure |
|---|---|---|---|---|
| baseline | 0.856 | — | 0% | 14% |
| latency | 0.856 | **+0.000** | 0% | 14% |
| freshness | 0.741 | −0.116 | 1% | **25%** |
| schema drift | 0.744 | −0.112 | 1% | **25%** |
| semantic stripping | **0.639** | **−0.218** | **18%** | 22% |

Baselines by arm: streaming/classification 0.900 · batch/classification 0.850 ·
streaming/retrieval 0.861 · batch/retrieval 0.762.

**Four things to carry forward:**

1. **Latency measured +0.000 effect at both severities.** Correct for a
   synchronous agent with no deadline — it waits and reads identical data. A
   finding to frame, not a bug.
2. **Semantic stripping is the only fault the agent reliably detects** —
   abstention 0% → 18%. It refuses rather than guessing. On *raw* accuracy it
   looks like the most damaging fault, but that is an artifact of counting a
   refusal as equal to a confident wrong answer; see the flip partition.
3. **Freshness produces the most silent failure** (25%) at ~1% abstention. The
   agent never signals a problem — and the arm below shows that handing it the
   record's age does not change this.
4. **Schema drift was predicted "visible" but behaves invisible** (1% abstention,
   25% silent) *and* does the most real damage to reasoning (residual −0.173).
   A renamed field still looks like a legitimate field. So the operative
   property is not visible/invisible but **whether the corruption is legible
   *as* corruption** — a sharper claim than H3 as originally written.

---

## Resolved: freshness accuracy was near-arithmetic — it is, entirely

**Settled by the flip-partition analysis. Full write-up in
`docs/flip_partition_findings.md`; re-runnable free with
`python -m airsbench.analysis.flip_partition`.**

On queries whose correct answer did *not* move, accuracy is baseline 0.888 vs
freshness/severe **0.886** — residual **−0.003 at both severities**, flat where a
real effect would grow with severity. Freshness costs accuracy exactly and only
where it moved the answer key, and does not impair the agent's reasoning at all.
The 11.6-point drop must never be reported as a result about the agent.

The finding is the other cell. On the 140 queries staleness made unanswerable:

| abstained | silent failure | chose the answer the served data implied | confidence when wrong |
|---|---|---|---|
| **4%** | **90%** | **75%** | **1.00** |

The agent is not making mistakes — it is reasoning correctly over corrupt input
and reporting the result at maximal confidence. Two further consequences:

- **The RQ2 damage ranking changes.** On residual (non-mechanical) impairment:
  schema drift −0.173 > semantic stripping −0.128 > freshness −0.003 ≈ latency 0.
  Semantic stripping is *not* the most damaging fault — much of its raw drop is
  abstention, which is the safe behaviour. Schema drift is.
- **The batch baseline is not clean.** With no fault injected, its inherent 3 s
  staleness flips 7.1% of answers and silently fails on **100%** of them.

---

## For a fresh session

Everything needed is in the repo — this file plus:

| File | What it carries |
|---|---|
| `CLAUDE.md` | The seven invariants, budget discipline, known traps, layout |
| `docs/detectability_arm.md` | **The pending design decision** — read before spending |
| `docs/flip_partition_findings.md` | Why freshness accuracy is not a result, and what is |
| `docs/detectability_findings.md` | The detectability arm's null, and why it is the useful answer |
| `docs/freshness_sweep_findings.md` | RQ1 answered: monotone, threshold 5.05 s, and the decomposition it rests on |
| `docs/statistical_analysis_findings.md` | RQ2 + RQ3 answered at decision level; why 'freshness' is two phenomena |
| `docs/cross_model_findings.md` | RQ5: ranking transfers across models, inverts across tasks; refusal can mask damage |
| `docs/airs_calibration_findings.md` | RQ4: calibrated weights per task; agent confidence is at chance on retrieval |
| `docs/gate_findings.md` | **The recommendation restated**: most silent failure is not infrastructure's fault, and every worthwhile gate forfeits more correct answers than it saves |
| `examples/gate/README.md` | `airs gate` worked example — admitted, refused, unmeasured, shadow mode |
| `examples/probe/README.md` | `airs probe` worked example — healthy vs degraded pipeline, real catalog data |
| `docs/research_questions_v2.md` | Current RQs, hypotheses, stats plan, declared parameters. Supersedes the proposal. |
| `docs/chapter3_methodology.md` | Methodology as implemented (Chapter 3 draft) |
| `docs/literature_review.md` | 25+ verified sources; the gap claim as it can actually be defended |
| `docs/related_work_positioning.md` | Differentiation vs the four nearest papers + rehearsed defence Q&A |
| `results/discarded/README.md` | The two defects the checkpoint caught, and why those runs are invalid |
| `git log` | Reasoning behind every design change |

**The three things a new session is most likely to get wrong:**

1. Spending money without a `--dry-run` first.
2. Breaking the paired design by deriving query sampling from the condition seed.
3. Treating the go/no-go checkpoint as a formality — it has already returned
   NO-GO twice and caught two campaign-invalidating defects.

**To resume, say:** *"continue the AIRS thesis — read docs/campaign_status.md"*
