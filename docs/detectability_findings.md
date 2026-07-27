# Detectability arm — results

**Run:** 2026-07-27 · 14 runs · 1 120 agent calls · **$0.153**

```bash
python -m airsbench.analysis.detectability
```

The fault is held constant — freshness, severe (5 s), streaming — and one thing
varies: whether the delivered record carries `_record_age_seconds`. Design and
rationale in `detectability_arm.md`.

## Verdict: the null branch. Metadata alone changes nothing.

Of the three outcomes pre-registered in `detectability_arm.md` §3, the arm
returned the second:

> **Agents ignore freshness metadata even when given it.** Metadata alone is
> insufficient; the guard must be enforced outside the model. Arguably the more
> important result, and a warning to anyone about to "just add a timestamp".

---

## 1. The headline cell

Queries where staleness moved the correct answer — the agent cannot be right,
so the only question is whether it says so.

| | n | accuracy | abstained | silent failure | confidence when wrong |
|---|---|---|---|---|---|
| **A** age absent | 27 | 7% | 4% | **89%** | **1.00** |
| **B** age delivered | 27 | 4% | 11% | **85%** | **1.00** |

McNemar exact on abstention: 2 discordant pairs, both favouring B, **p = 0.50**.

The point estimate moves in the predicted direction and the confidence interval
swamps it. This cell alone cannot decide anything (§3).

## 2. Overall, both tasks

| task | | n | accuracy | abstained | silent | McNemar |
|---|---|---|---|---|---|---|
| retrieval | A | 234 | 79% | 2% | 20% | b=6, c=3 |
| retrieval | B | 234 | 77% | 3% | 20% | **p = 0.51** |
| classification | A | 240 | 79% | **0%** | 21% | b=0, c=0 |
| classification | B | 240 | 79% | **0%** | 21% | **p = 1.00** |

**Classification is the strong result.** Zero abstentions in 480 decisions
across both arms. The agent is offered the option in the system prompt, is shown
that its record is 5.05 seconds old, and never once declines. By the rule of
three, a true abstention rate above **1.25%** is ruled out. That is not an
underpowered null — it is a flat one.

Confidence when wrong is unmoved (1.00 → 1.00 retrieval, 0.80 → 0.81
classification), so the secondary reading proposed in the design — that partial
use of the metadata might show up as reduced confidence even without abstention
— finds nothing either. The metadata is not being used weakly. It is not being
used.

## 3. What this rules out, and what it does not

Reported explicitly because a null is only worth as much as its power.

- **The flip-conditioned cell is underpowered.** Under McNemar's exact test at
  α = 0.05, at least **6** one-directional discordant pairs are needed for
  significance regardless of how many concordant pairs surround them. The arm
  produced **2**. A small-to-moderate effect there is neither demonstrated nor
  excluded, and the +7 point abstention difference must not be reported as a
  finding.
- **A large effect is excluded.** Had the metadata converted most silent
  failures into abstentions — the outcome the arm was built to detect — it would
  have shown at this n. It did not.
- **Over-caution is excluded.** On baseline data with the age delivered,
  abstention is **0%** on both tasks. The agent is not reacting to the field at
  all, in either direction. The third predicted outcome does not occur.

## 4. Why the null is the interesting answer

An age is **not actionable without a freshness policy.** The agent is told the
record is 5.05 seconds old and never told what age is acceptable. Nothing in the
prompt, the task, or the record establishes that five seconds is unusual for a
product catalog — and deliberately so, since telling it would have measured
instruction-following rather than whether an agent can use infrastructure
metadata unprompted.

There is a second reason built into the design: **within a run every record
carries the same age**, so there is nothing to discriminate against. The agent
cannot notice that *this* record is older than its neighbours, because none of
them differ. It would have to hold an absolute prior about acceptable staleness,
and it has none.

Both point the same way, and it is the thesis's argument rather than a
concession: freshness is a property of the *pipeline*, and the pipeline is where
it has to be enforced. Handing the number to the model and hoping it infers a
policy does not work. This is a sharper practitioner recommendation than the one
the arm was expected to produce:

> Shipping record age is necessary but not sufficient. Ship the age **and the
> staleness budget**, and enforce the budget outside the model — a pipeline that
> emits `_record_age_seconds` and no SLA has documented its defect, not fixed it.

## 5. Consequences

- **H3 stands, restated and now with a manipulation behind it.** An agent can
  only abstain from a fault the delivered record makes legible — and the arm
  shows that legibility is not achieved merely by *including* the relevant
  number. Legibility requires the datum *and* the standard to judge it against.
- **RQ3** gains a causal answer. Silent failure under staleness is not a model
  limitation the pipeline can fix by disclosure alone.
- **The AIST demo panel changes.** The intended contrast — same stale record,
  with and without its age, one lying and one declining — does not exist,
  because both lie. The honest and more interesting panel is three-way: no
  metadata, age alone, and age against a declared budget with enforcement
  outside the model.
- **Follow-up, cheap and well-motivated:** vary the *policy*, not the datum.
  Deliver `_record_age_seconds` alongside a stated freshness budget, or vary age
  across records within a run so relative staleness becomes visible. Either
  isolates "the agent has no standard" from "the agent ignores the field".

## 6. Limitations of this arm

- **n is small in the cell that matters.** 27 flipped queries per arm; the
  design allocated 3 replications on a cell whose size is set by the answer-flip
  rate (~12%), which was not accounted for when the arm was costed. A power
  calculation on the flip-conditioned cell should have preceded it.
- **Field placement and framing were not varied.** `_record_age_seconds` is
  rendered after the record's context block, and named neutrally. Whether a more
  prominent placement or a different name would change the result is untested,
  and is a plausible alternative explanation for the null that this arm cannot
  exclude.
- **One model.** gpt-4o-mini. Whether a stronger model infers a staleness prior
  unprompted is open, and is the single most valuable extension — the
  cross-model arm can answer it cheaply by carrying this condition along.
