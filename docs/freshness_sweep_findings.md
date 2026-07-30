# Freshness sweep — results (RQ1)

**Run:** 2026-07-28 · 36 runs · 2 160 agent calls · **$0.290**

```bash
python -m airsbench.analysis.freshness_sweep
```

Six staleness levels (0.5–12 s), streaming, both tasks, 3 replications. Answers
RQ1: **is degradation monotone in data age, and where is the threshold?**

## Verdict

**Yes, monotone — on both tasks, by every test applied.** But the two tasks are
monotone in different quantities, and the retrieval result only holds once
silent failure is decomposed.

| task | outcome tested | Spearman ρ | isotonic cost | changepoint | threshold |
|---|---|---|---|---|---|
| retrieval | exposure | **+0.863** (p<0.0001) | +0.0% | 3.05→5.05 s | **5.05 s** |
| retrieval | unconditional silent failure | **+0.613** (p=0.007) | +0.4% | 5.05→8.05 s | **8.05 s** |
| classification | accuracy | **−0.939** (p<0.0001) | +0.0% | 5.05→8.05 s | **5.05 s** |

An isotonic (monotone-constrained) fit costs essentially no extra error against
the unconstrained per-level means in all three cases. Shisher & Sun's
non-monotone regime is not observed here — but see §4 for what that does and
does not license.

---

## 1. Retrieval — the decomposition is the finding

| staleness | raw acc | exposure | unflipped acc | n flipped | silent \| flip | 95% CI | uncond. silent |
|---|---|---|---|---|---|---|---|
| 0.55 s | 0.870 | 2.3% | 0.890 | 4 | 100% | [51%, 100%] | 2.3% |
| 1.55 s | 0.825 | 4.0% | 0.859 | 7 | 100% | [65%, 100%] | 4.0% |
| 3.05 s | 0.836 | 8.5% | 0.901 | 15 | 87% | [62%, 100%] | 7.3% |
| 5.05 s | 0.791 | 13.6% | 0.908 | 24 | 88% | [69%, 100%] | 11.9% |
| 8.05 s | 0.757 | 16.9% | 0.905 | 30 | 97% | [83%, 100%] | 16.4% |
| 12.05 s | 0.723 | 19.2% | 0.881 | 34 | 85% | [70%, 100%] | 16.4% |

Silent failure under staleness factors into two quantities that behave nothing
alike:

```
silent failure  =  EXPOSURE  ×  CONDITIONAL rate
                   (catalog)     (agent)
```

- **Exposure rises monotonically**, 2.3% → 19.2%, ρ = +0.863, isotonic cost 0.0%.
  This is the share of queries staleness makes unanswerable. It is a property of
  **catalog velocity**, not of the agent — an agent-free calculation
  (`check_sensitivity`) predicts it.
- **The conditional rate is saturated.** Every level sits at 85–100%, and every
  interval overlaps every other. There is no headroom for staleness to make it
  worse, and therefore **no conditional threshold to find**.

> **The operational threshold under staleness is set by how fast your data
> changes, not by how stale it is.** The agent's failure mode is already
> maximal at the mildest staleness tested — half a second.

**Unflipped accuracy is flat across the entire sweep** — 0.890, 0.859, 0.901,
0.908, 0.905, 0.881 — from 0.55 s to 12 s. This independently reproduces the
flip partition's central result at six staleness levels spanning a 22× range:
**freshness never impairs the agent's reasoning, at any age tested.**

## 2. Classification — a clean, textbook threshold

| staleness | accuracy | abstained | silent failure | |
|---|---|---|---|---|
| 0.55 s | 0.911 | 0% | 9% | |
| 1.55 s | 0.900 | 0% | 10% | |
| 3.05 s | 0.872 | 0% | 13% | |
| 5.05 s | 0.806 | 0% | 19% | |
| 8.05 s | 0.617 | 0% | 38% | |
| 12.05 s | 0.489 | 0% | 51% | ← feature zeroed by the horizon |

Strongly monotone (ρ = −0.939, isotonic cost 0.0%), with a changepoint between
5 and 8 seconds explaining 89% of the variance and the 10-point band crossed at
5.05 s. This is the RQ1 result in its most quotable form.

**Abstention is 0% at every level, including where accuracy falls to 0.489.**
The agent's answer quality collapses and it never once signals a problem. That
is the thesis's phenomenon, traced across a severity gradient.

**The 12.05 s level is excluded from the tests.** `DepDelay` is modelled as
accruing over a 10 s knowledge horizon, so past 10 s the feature is clamped to
exactly 0.0 for every flight: the arm measures an *absent* feature, not a stale
one. This is the same horizon collision recorded in `CLAUDE.md` from the batch
arm, reappearing at the top of the sweep. Reported, not tested — the analysis
excludes it explicitly rather than fitting through it.

## 3. A trap this arm nearly walked into

The first version of this analysis tested monotonicity on the **conditional**
rate and reported:

> ρ = −0.545, p = 0.019 — *"the response is NOT monotone in age."*

That was wrong, and significantly so. The conditional rate's denominator is the
flip count, which is small at low staleness **by construction**: n = 4 at the
mildest level. A rate of "100%" from four observations has a 95% interval of
[51%, 100%]. The apparent decline was the denominator, against a 100% ceiling —
not the agent.

Reporting it would have produced a false headline (*"freshness degradation is
non-monotone"*) that contradicted the study's own flip-partition result, from a
statistic that was working correctly on a series that could not bear it.

The analysis now refuses to issue a monotonicity verdict on a conditional rate
whose smallest level falls below n = 10, and reports Wilson intervals and the
ceiling instead. `tests/test_freshness_sweep.py` pins this, including a
reproduction of the false-significance failure mode.

## 4. Limitations

- **Monotonicity is established over 0.5–12 s on this catalog.** Shisher & Sun's
  non-monotone regime arises from feedback and control dynamics absent here; not
  observing it in a single-shot QA task is unsurprising and is *not* evidence
  against them. The claim is bounded to the regime tested.
- **The classification curve is bounded by its own modelling assumption.** The
  linear-accrual-over-a-horizon model produces the observed shape almost by
  construction; the finding is that the agent never abstains along it, not the
  shape.
- **Three replications per level.** Adequate for the level-pooled tests (n≈180
  decisions each) but thin for run-level variance.
- **The 10-point band is a declared convention**, not a discovered quantity. The
  full curve is reported so a reader can apply a different band.

## 5. Consequences

- **RQ1 is answered**, and the threshold is reportable: 5.05 s on both tasks by
  the band criterion, with changepoints at 3–5 s (exposure) and 5–8 s (accuracy).
- **The practitioner statement sharpens.** "Keep data fresher than 5 seconds" is
  the wrong lesson; the right one is *measure your answer-flip rate, because the
  threshold is a function of your update velocity, not a universal constant.*
  The sweep gives the method for finding it, and `check_sensitivity` computes it
  with no model calls.
- **`research_questions_v2.md` §5 should record the outcome change**: RQ1's
  monotonicity test is run on exposure and unconditional silent failure, not on
  accuracy, for the reason the flip partition established.
