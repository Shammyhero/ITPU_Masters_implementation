# The detectability arm — manipulating detectability directly

**Status:** ✅ **implemented, tested, dry-run at $0.152. Not yet executed.**

```bash
python -m airsbench.runner.run --detectability --n-queries 80 --dry-run --max-cost 0.50
python -m airsbench.runner.run --detectability --n-queries 80 --max-cost 0.30
```

`build_detectability_arm()` in `runner/config.py`; the treatment itself is
`attach_record_age()` in `runner/execute.py`; 15 tests in
`tests/test_detectability_arm.py` pin "varies detectability and nothing else".

**Pre-registered baseline to move**, from the flip-partition analysis: on
queries staleness made unanswerable, condition A gives **5% abstention, 89%
silent failure, mean confidence 1.00 when wrong.**

**Origin.** Saman asked: *"why should the agent doubt the price — how would it
know the data is old?"* The answer is that it could not. The rendered record
carries no timestamp, no age, nothing about when the value was true. Expecting
abstention under a freshness fault was expecting the agent to detect something
it was never told.

That reframes the study's central claim, and it turns out to strengthen it.

---

## 1. What the phase-1 result actually shows

The original wording of H3 implicitly blamed the agent:

> ❌ "The agent fails to notice that the data is stale."

The accurate wording blames the pipeline:

> ✅ **"The pipeline delivers nothing the agent could notice."**

The distinction matters because the second is an infrastructure finding with an
actionable remedy, while the first is a vague claim about model capability.

| Fault | Where the corruption lives | Agent abstains? |
|---|---|---|
| Semantic stripping | **Inside the record** — `price` becomes `f4` | **23%** |
| Schema drift | Inside the record, but plausibly (`price` → `price_v2`) | 1% |
| Freshness | **Outside the record** — the value is well-formed; the *world* moved | 1% |
| Latency | Outside the record; no corruption at all | 0% |

Detectability is therefore not a property of agent intelligence. It is a
property of **what the pipeline chose to deliver alongside the data.**

---

## 2. Why this is a better experiment than what we have

The main factorial compares detectability *across* fault types, which confounds
two things: the kind of corruption, and whether it is legible. Semantic
stripping differs from freshness in both respects at once.

The detectability arm **holds the fault constant and varies only legibility**:

| Condition | Record delivered | Fault present? | Detectable? |
|---|---|---|---|
| A (current) | `{"price": 12.99}` | yes — 5 s stale | **no** |
| B (new) | `{"price": 12.99, "_record_age_seconds": 5.0}` | yes — same 5 s stale | **yes** |

Identical staleness. Identical wrong answer available. The *only* difference is
whether the record carries its own age. This isolates detectability as a
manipulated variable rather than an observed correlate — which is what turns H3
from an interpretation into a tested causal claim.

---

## 3. Predictions, and why every outcome is publishable

| Outcome in condition B | Interpretation |
|---|---|
| Abstention rises, silent failure falls | **Silent failure from staleness is a pipeline design defect, not a model limitation.** Shipping freshness metadata largely fixes it. Direct, actionable engineering recommendation. |
| No change | **Agents ignore freshness metadata even when given it.** Metadata alone is insufficient; the guard must be enforced outside the model. Arguably the more important result, and a warning to anyone about to "just add a timestamp". |
| Abstention rises *too much* — agent refuses on fresh data too | Metadata induces over-caution; there is a calibration problem in how age is presented. Suggests a follow-up on framing. |

There is no null result here. Every branch says something an engineer can act on.

---

## 4. Design

Focused arm, not a new factor across the whole factorial (which would double the
campaign for no benefit — the other three faults do not have an "outside the
record" character to reveal).

| | |
|---|---|
| Fault | freshness only, **severe** (5 s) — plus a baseline for reference |
| Metadata | absent (A) vs present (B) |
| Pipeline | streaming only — batch's inherent staleness would blur the contrast |
| Tasks | retrieval + classification |
| Replications | 3 |
| **Runs** | 2 metadata × 2 tasks × 3 reps + 2 baselines = **14 runs** |
| Cost | ~$0.15 at 80 queries |

**Metadata form.** Add one field to the rendered record, adjacent to the data
and phrased neutrally — no instruction, no hint that old is bad:

```json
{"data": {...}, "context": {...}, "_record_age_seconds": 5.0}
```

**The age must be truthful.** Implementing this surfaced a defect in the
freshness accounting: `execute` stamped `event_ts = now - value_staleness`, and
then `FreshnessInjector` shifted `event_timestamp` back by the injected delay a
*second* time. A severe (5 s) streaming run therefore carried a record age of
10.05 s against values that were only 5.05 s stale.

Left unfixed, condition B would have shown the agent an age twice the real one,
confounding "the record is legible" with "the record overstates its age".
Fixed in `build_event_ts()`: only the pipeline's inherent staleness is stamped
before the chain, and the injector supplies the rest, so age after the chain
equals `value_staleness_s` exactly. Pinned by
`tests/test_freshness_accounting.py`. See §8 for what this means for the runs
already completed.

**What must NOT change:** the system prompt. It must not mention staleness,
freshness, or that age matters. If the prompt tells the agent to distrust old
records, the experiment measures instruction-following rather than whether the
agent can use infrastructure metadata on its own. The metadata is offered; its
use is the agent's decision, and that decision is the measurement.

**Secondary reading.** Compare confidence distributions between A and B on the
subset of queries whose answer flipped. Even without full abstention, a drop in
reported confidence would show the metadata is being partially used.

---

## 5. Consequences for the rest of the thesis

- **RQ3 is restated.** From *"which faults cause silent failure?"* to
  *"is silent failure a property of the fault, or of what the pipeline delivers
  about the fault?"* — a causal question with a manipulation behind it.
- **H3 is restated.** From "visible faults produce abstention" to: **an agent can
  only abstain from a fault the delivered record makes legible; legibility is a
  pipeline design choice, not an agent capability.**
- **Chapter 3** gains this arm; the raw freshness accuracy metric gains an
  explicit caveat (see §6).
- **AIST demo** gains its strongest panel: same stale record, side by side, with
  and without its age. One lies confidently; the other says "I can't be sure."
- **The practitioner recommendation** becomes concrete and quotable: *ship record
  age with the record.*

---

## 6. Related correction: the flip-partition analysis

Independently of this arm, raw accuracy under freshness is close to arithmetic:
at severe staleness ~16% of queries have a different correct answer, and the
observed drop (12.9 points) is slightly *below* that mechanical ceiling. Agents
lose roughly what staleness makes available to lose.

Reporting it as a headline number would be measuring the answer-flip rate with
an expensive language model. The analysis must instead partition queries:

- **Answer did not flip (~84%)** — accuracy here should match baseline. If it
  does not, staleness is doing something beyond changing the right answer.
- **Answer did flip (~16%)** — the agent cannot be right. **Does it abstain or
  commit confidently?** This cell is the actual finding.

Recoverable for free from completed runs: sampling is deterministic, so replaying
each run's `sample_seed` regenerates the exact queries and timestamps, and flip
status can be joined to the logged decisions. No re-running, no API calls.

---

## 8. Open decision: AIRS freshness on the 66 completed runs

The double-count described in §4 means the 12 completed freshness runs recorded
an AIRS freshness dimension computed from twice the injected delay:

| condition | recorded age | true age | recorded AIRS | correct AIRS |
|---|---|---|---|---|
| streaming / freshness / mild | 3.05 s | 1.55 s | 32.79 | **64.52** |
| streaming / freshness / severe | 10.05 s | 5.05 s | 9.95 | **19.80** |
| batch / freshness / mild | 6.00 s | 4.50 s | 16.67 | **22.22** |
| batch / freshness / severe | 13.00 s | 8.00 s | 7.69 | **12.50** |

Both `recorded` columns are read from the run artifacts; both `correct` columns
are `freshness_score(value_staleness_s(config))` under the fixed accounting.

**What is unaffected:** everything behavioural. Records carry no timestamp
unless this arm attaches one, so no agent in any completed run ever saw an age.
Accuracy, abstention, silent failure, confidence, every logged decision, and the
entire flip-partition analysis stand as recorded. Baseline, latency, schema
drift and semantic stripping runs are unaffected outright — with no
`FreshnessInjector` in the chain there was nothing to double-count, and their
recorded freshness of 100.0 is correct.

**What is affected:** the AIRS freshness dimension on 12 runs, and anything
downstream of it — RQ4's regression and the AIRS calibration in step 8.

The corrected value is a deterministic function of the config
(`age = inherent + injected`), so it can be recomputed offline for free. Two
options, to decide before step 7:

1. **Recompute in the analysis layer** — free, keeps run artifacts as immutable
   records of what the instrument actually emitted, and the correction is
   auditable in code. Preferred.
2. **Re-run the 12 freshness runs** — ~$0.13, gives artifacts that are correct
   on their face, but replaces data that is behaviourally valid, and the new
   runs would carry different fault realizations from their pairs.

Option 1 unless there is a reason to prefer pristine artifacts over a
documented correction.

---

## 7. Order of work when resuming

1. **Flip-partition analysis** — free, retroactive, and it determines how the
   freshness result should be reported at all.
2. **Detectability arm** — ~$0.15, 14 runs. Highest scientific value per dollar
   in the whole study.
3. **Finish phase 2** — `--offset 66 --limit 78`, ~$0.85.
4. Freshness sweep, cross-model arms, calibration, probe, demo, chapters.

Phase 2 is deliberately third: the main factorial establishes the ranking and
thresholds, but the detectability arm may change how those results are framed,
and framing is cheaper to get right before the writing than after.
