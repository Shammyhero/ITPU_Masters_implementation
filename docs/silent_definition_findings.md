# Silent-failure definition — does a confidence threshold change the count?

**Run:** 2026-09-13 · 302 runs, 24,270 decisions, every arm and model · **$0**

```bash
python -m airsbench.analysis.silent_definition
python -m airsbench.analysis.silent_definition --markdown
```

Every number and table below is produced by that module; none is copied by hand.

## Why this exists

The thesis carried **two definitions of silent failure under one name.**

- Chapter 3, `research_questions_v2.md` and `runner/scoring.py::failure_modes` —
  which writes the per-run metric into every artifact — defined it as
  *committed, wrong, and reported at confidence ≥ 0.7*.
- The nine analysis modules that produce every reported silent-failure result
  (`gate/replay`, `interaction`, `airs_calibration`, `freshness_sweep`,
  `cross_model`, `detectability`, `decision_models`, `export_demo_data`)
  computed it as *committed, parseable, and wrong*, with **no threshold**.

The methodology also claimed the threshold's sensitivity was *"checked across
0.5/0.6/0.7/0.8/0.9 in the analysis notebook."* **No such check existed** in any
module, test or notebook.

## Decision

**Silent failure is threshold-free everywhere:** committed (not abstained),
parseable, and wrong. `runner/scoring.py::is_silent_failure` is the single
reference, and `tests/test_failure_modes.py` pins that the analyses' inline
formula is exactly that function, over every combination of flags.

Two reasons. A threshold defines the outcome partly by the agent's own
confidence — the signal RQ4 compares AIRS against, which is circular in
principle. And, as the results below show, a threshold's placement is arbitrary
with respect to how each model happens to report confidence.

## Result

Rates under the definition (bold) and under each threshold applied on top. A
threshold can only remove decisions, so every rate is at or below the definition.

| arm | model | task | n | definition | ≥ 0.5 | ≥ 0.6 | ≥ 0.7 | ≥ 0.8 | ≥ 0.9 | silent failures < 0.7 |
|---|---|---|---|---|---|---|---|---|---|---|
| cross_model | claude-haiku-4-5 | classification | 900 | **10.2%** | 10.2% | 10.2% | 10.2% | 0.7% | 0.1% | 0.0% |
| cross_model | claude-haiku-4-5 | retrieval | 881 | **12.5%** | 12.5% | 12.5% | 11.4% | 9.4% | 5.3% | 9.1% |
| cross_model | ollama/llama3.1:8b | classification | 900 | **52.1%** | 52.1% | 49.9% | 49.9% | 49.9% | 46.1% | 4.3% |
| cross_model | ollama/llama3.1:8b | retrieval | 881 | **35.5%** | 35.4% | 35.0% | 35.0% | 34.8% | 34.2% | 1.6% |
| cross_model | ollama/qwen2.5:14b-instruct | classification | 900 | **41.1%** | 41.1% | 41.1% | 41.1% | 41.1% | 32.8% | 0.0% |
| cross_model | ollama/qwen2.5:14b-instruct | retrieval | 881 | **25.2%** | 25.2% | 25.2% | 25.2% | 24.9% | 24.5% | 0.0% |
| detectability | gpt-4o-mini | classification | 560 | **18.9%** | 18.9% | 18.9% | 18.9% | 18.4% | 1.4% | 0.0% |
| detectability | gpt-4o-mini | retrieval | 547 | **19.2%** | 19.2% | 19.2% | 19.2% | 19.2% | 19.2% | 0.0% |
| freshness_sweep | gpt-4o-mini | classification | 1,080 | **23.4%** | 23.4% | 23.4% | 23.4% | 23.4% | 1.4% | 0.0% |
| freshness_sweep | gpt-4o-mini | retrieval | 1,062 | **18.1%** | 18.1% | 18.1% | 18.1% | 18.1% | 18.1% | 0.0% |
| interaction | gpt-4o-mini | classification | 2,160 | **16.4%** | 16.4% | 16.4% | 16.4% | 14.5% | 2.0% | 0.0% |
| interaction | gpt-4o-mini | retrieval | 2,106 | **24.8%** | 24.8% | 24.8% | 24.8% | 24.8% | 24.8% | 0.0% |
| main | gpt-4o-mini | classification | 5,760 | **17.2%** | 17.2% | 17.2% | 17.2% | 16.4% | 1.5% | 0.0% |
| main | gpt-4o-mini | retrieval | 5,652 | **19.8%** | 19.8% | 19.8% | 19.8% | 19.8% | 19.8% | 0.0% |

## What it shows

**1. For the primary model, the retired 0.7 threshold changed nothing.**
It moves gpt-4o-mini's silent-failure rate by **0.0 pp in every arm** — main,
freshness sweep, detectability and interaction, on both tasks. No gpt-4o-mini
silent failure was ever committed below 0.7 confidence, so every primary result
in the thesis is identical under either definition. Thresholds of 0.5 and 0.6 are
equally inert.

**2. On the cross-model arm, the difference is small but real.** The largest
shift at 0.7 is **2.2 pp** (ollama/llama3.1:8b, classification: 52.1% → 49.9%). Claude Haiku on
retrieval moves 1.1 pp (12.5% → 11.4%),
because 9.1% of its retrieval silent failures were reported below 0.7.

**3. The threshold was inert at 0.7 — and nowhere near robust across the range
the methodology promised.** At 0.9, gpt-4o-mini's classification silent-failure
rate collapses from **16.4%–23.4% to 1.4%–2.0%** across the four arms, because the model
habitually reports a confidence between 0.8 and 0.9 on classification.
Retrieval barely moves at any threshold — a single decision in one arm (0.02 pp,
at 0.9) — because retrieval answers are reported at or near 1.0. Claude Haiku's
classification rate collapses already at 0.8 (10.2% → 0.7%).

That third result is the strongest argument for the decision. Had the original
threshold been set at 0.8 or 0.9 instead of 0.7 — a choice no document justified
either way — most classification silent failures would have vanished from the
thesis. A count that depends on where a threshold sits relative to a model's
reporting habit is not measuring silent failure; it is measuring the habit.

## What changed

| File | Change |
|---|---|
| `runner/scoring.py` | `is_silent_failure()` added as the reference definition; `failure_modes()` threshold-free by default, with an optional `min_confidence` kept only for this check |
| `tests/test_failure_modes.py` | Three tests that pinned the 0.7 threshold rewritten as tests of the optional parameter; a new test pins that the analyses' inline formula equals the definition |
| `analysis/silent_definition.py` + tests | The sensitivity check the methodology promised |
| `analysis/phase1_check.py` | Recomputes silent failure from decisions rather than reading the recorded metric, which artifacts before 2026-09-13 stored under the old definition |
| `chapter3_methodology.md` | §3.7 definition rewritten; §3.11 discloses the reconciliation |
| `research_questions_v2.md` | Metric table and threshold paragraph revised |
| `CLAUDE.md` | Invariant 8: one definition, enforced |

**Run artifacts are unchanged.** Their recorded `metrics.silent_failure_rate`
still reflects the old definition, consistent with the practice of never
rewriting artifacts (`airs_correction.py`). Every analysis recomputes from the
logged decisions.

## Limitations

- **Confidence is self-reported and model-specific.** The collapse at 0.8–0.9 is
  a property of how these models format confidence, and a different prompt or
  model could move it. That is part of the argument against a threshold, not a
  flaw in this check.
- **One confidence field.** Only the agent's reported confidence is examined;
  token-level log-probabilities were not collected.
- **Cross-model runs are few** (18 per model) and use a reduced design, so the
  cross-model shifts carry wider uncertainty than the primary-model ones.
