# The detectability arm — manipulating detectability directly

**Status:** designed, not yet implemented. Paused phase 2 at 66/144 to think this
through before spending further.

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
