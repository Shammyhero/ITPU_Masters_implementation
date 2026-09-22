# The refetch arm — results

**Run:** 2026-09-23 · 21 runs · 3,150 questions · 3,150 model calls · **$0.8541**
(+ $0.0026 pilot, not in the corpus) · gpt-4o-mini · design: `refetch_arm.md`

```bash
python -m airsbench.analysis.refetch --figure docs/figures/fig4_9_refetch.png
python -m airsbench.gate.replay --refetch --task retrieval --sweep age   # the third verdict
```

Seven paid cells on the bundled demo source (the study's ESCI slice served through
the runner's own functions), each run 3 times over 150 questions. Every cell and
both states ask the **same 450 questions at the same simulated moments**, so every
contrast below is paired question by question. The questions:

| | healthy (0.05 s) | stale (5.05 s) |
|---|---|---|
| **baseline** — standard prompt, no re-read, age policy in shadow | ✓ | ✓ |
| **gate** — the age policy re-reads a stale batch before the model is asked | = baseline | ✓ |
| **agent, age hidden** — the model may ask for one re-read | ✓ | ✓ |
| **agent, age shown** — the same, each record showing its age | ✓ | ✓ |
| **refuse** — priced at $0 from what the baseline did on the same questions | | ✓ |

## Verdict: the agent never acts. The action works when the gate takes it.

1. **Offered a re-read, gpt-4o-mini asked 0 times in 1,800 questions** — age hidden
   or shown, fresh data or 5 s stale. Each cell rules out a request rate above
   **0.66%** at 95%. The detectability null extends from *being told* to *being
   able to act*: the model neither uses the age it is shown nor the tool it is
   given. H-R1a and H-R1b are null (Holm p = 1.000, zero discordant questions).
2. **The re-read itself works, when a gate triggers it.** On stale data the gate's
   re-read is indistinguishable from the healthy pipeline — same correctness on
   **98.0%** of questions, accuracy +0.2 pp [−1.1, +1.6] — and against admitting
   every stale answer it prevents **43 of 57 silent failures while gaining 35
   correct answers net**. Refusing the same batches prevents all 57 and forfeits
   **374**. On this source that benefit is by construction (§4); the measured part
   is its price.
3. **Exploratory, not declared in advance:** offering the tool, even though it is
   never used, **costs accuracy** — −4.3 pp with age hidden, −2.9 pp with age
   shown, on healthy data where a re-read cannot help (§5).

**Kill question 3 ("in what sense is this agentic?") now has a measured answer.**
The agent-initiated condition is a genuine decide → act → decide loop, and the
agent declines the act every time. The protection the thesis recommends has to
sit outside the model — as a gate — because the model will not reach for it even
when it is offered, and it is not made cautious by the evidence it would need.

---

## 1. Does the agent ask? (H-R1a, H-R1c)

| cell | healthy | stale |
|---|---|---|
| agent, age hidden | 0 / 450 (≤ 0.66%) | 0 / 450 (≤ 0.66%) |
| agent, age shown | 0 / 450 (≤ 0.66%) | 0 / 450 (≤ 0.66%) |

Exact one-sided 95% upper bounds. **H-R1a** (stale − healthy, age shown): +0.0 pp,
0 discordant questions of 450, Holm p = 1.000.

The age-shown agent was offered, on every stale question, a JSON field saying the
record was **5.05 s old**, a system prompt that says it may ask for any record to
be read again, and the neutral instruction to ask "only if reading them again
would change your answer". It answered instead, 450 times out of 450. The 18 Sep
live check on `llama3.1:8b` (0 of 12, age hidden) and the pilot (0 of 10, age
shown) point the same way, but they are not evidence; this is.

The model is not uncertain when it is wrong, either. Mean confidence on silent
failures is **1.00 in every cell** (0.997 in the two stale agent cells). Nothing
in the answer signals that a re-read was worth having.

## 2. Does acting pay? (H-R1b)

It cannot be measured, because no act happened. On the **41 stale questions whose
answer key the staleness moved** (flipped as first delivered, 9.3% of 443
verifiable — see §6 on why not the planned ~58):

| | correct | silent | abstained |
|---|---|---|---|
| healthy baseline (same questions, fresh data) | 32 | 5 | 4 |
| stale baseline | **0** | **36** | 5 |
| gate re-read | **34** | 3 | 4 |
| agent, age hidden | 0 | 38 | 3 |
| agent, age shown | 0 | 37 | 4 |

**H-R1b** (accuracy on flipped, age shown − baseline): +0.0 pp, 0 discordant, Holm
p = 1.000. The one discordant question on silent failure (+2.4 pp [+0.0, +7.3],
p = 0.706) is an abstention that became a silent failure. On a flipped question
the agent that could have re-read is exactly as wrong as the one that could not —
and the gate that re-read on its behalf is right as often as a fresh pipeline.

## 3. The verdict menu (H-R2)

Every verdict on the 443 verifiable stale questions, against admitting them all.
*Genuine* counts only silent failures the healthy baseline did not also commit on
the same question — what the fault caused. **Raw** and **true cost** are correct
answers forfeited per silent failure prevented, and per genuine one.

| verdict | prevented | genuine | introduced | forfeited | gained | raw | true | re-reads | $ |
|---|---|---|---|---|---|---|---|---|---|
| **refuse** | 57 | 40 | 0 | **374** | 0 | **6.56** | **9.35** | 0 | 0.00 |
| **gate re-read** | 43 | 39 | 3 | 7 | **42** | **0.16** | **0.18** | 450 | 0.1189 |
| agent, age hidden | 2 | 0 | 11 | 16 | 2 | 8.00 | — | 0 | 0.1227 |
| agent, age shown | 4 | 2 | 14 | 19 | 2 | 4.75 | 9.50 | 0 | 0.1258 |

- **Refusal** is the corpus's trade in miniature: 6.56 correct answers forfeited per
  silent failure prevented (9.35 per genuine one), within the 7–21 true-cost range
  `gate_findings.md` measured across the corpus.
- **A gate re-read** keeps every question answered, removes 39 of the 40 genuinely
  fault-caused silent failures, and *gains* 42 correct answers against 7 lost to
  temperature noise. It costs **450 re-reads — 10.5 per silent failure prevented**
  — and no extra model spend (one call per question, as the baseline).
- **The agent cells** are not verdicts at all, since the agent never re-read; their
  rows show what the tool-offering prompt does to the same stale questions — it
  introduces more silent failures (11, 14) than it removes (2, 4). That is §5's
  effect, seen on stale data.

H-R2 as refined — a gate re-read forfeits fewer correct answers per silent
failure prevented than refusal — holds by a wide margin, and on this source it
could not have failed (§4). It is reported as the menu, not as a discovery.

## 4. Is a re-read the healthy pipeline? — and the corpus's third verdict

On the demo source a re-read returns exactly the answer key, so the gate's benefit
is built in (`refetch_arm.md` §2.2). What *is* an empirical question is whether
the model answers a re-read batch the way it answers a healthy one. Paired over
443 questions:

| gate re-read on stale − healthy baseline | |
|---|---|
| accuracy | +0.2 pp [−1.1, +1.6], p = 0.853, discordant 5/4 |
| silent failure | −0.9 pp [−2.0, +0.0], p = 0.125, discordant 1/5 |
| same correctness | **98.0%** of questions |

It is. That licenses the assumption `gate/replay.py` now prices the corpus's third
verdict on: a batch refused for staleness alone is re-read, and answers at the
rates of the matched fault-free streaming run of the same task and replication
(same `sample_seed`, same questions). No arm data enters the corpus — the arm is a
different instrument and is never pooled — it only validates the substitution.

On the corpus (180 gpt-4o-mini pipelines, $0), a staleness gate stops being a
trade:

| age policy | task | verdicts | coverage | prevented | correct answers | re-reads / SF |
|---|---|---|---|---|---|---|
| ≤ 0.1 s | retrieval | refuse only | 33% | 927 | **−3,537** | — |
| | | refuse / re-read | **100%** | 446 | **+451** | 10.1 |
| ≤ 5.0 s | retrieval | refuse only | 83% | 247 | −888 | — |
| | | refuse / re-read | **100%** | 122 | **+133** | 9.5 |
| ≤ 0.1 s | classification | refuse only | 33% | 922 | −3,522 | — |
| | | refuse / re-read | **100%** | 390 | **+546** | 11.8 |

A re-read prevents about half the silent failures refusal does — refusal also
removes the model's own errors, and forfeits every correct answer with them — but
it forfeits nothing and keeps every question answered. Drift and stripping
policies are unchanged: a re-read bypasses the pipeline, so they still refuse.
**The classification rows rest on the substitution unvalidated**: the arm tests it
on retrieval only.

## 5. Exploratory: offering an unused tool costs accuracy

Declared on 23 Sep after replication 1 had been seen and before replications 2–3
ran (`refetch_arm.md` §6); never counted toward H-R1. On **healthy** data, where a
re-read cannot help, the two agent cells against the baseline — same questions,
same records, the prompt the only difference:

| tool-offering prompt − standard | accuracy | silent failure | abstained |
|---|---|---|---|
| age hidden | **−4.3 pp** [−6.8, −2.0], p = 0.0004, disc. 5/24 | **+3.4 pp** [+1.4, +5.6], p = 0.002 | +0.9 pp, p = 0.205 |
| age shown | **−2.9 pp** [−5.2, −0.7], p = 0.012, disc. 7/20 | **+2.0 pp** [+0.2, +4.1], p = 0.043 | +0.9 pp, p = 0.308 |

On stale data the same comparison, over the 402 unflipped questions, gives −3.5 pp
(age hidden, disc. 2/16) and −4.2 pp (age shown, disc. 2/19). The loss is almost
entirely converted into silent failure, not abstention, and every extra wrong
answer on healthy data is `agent_impairment` — the records were intact.

A short paragraph offering a capability the model never used was added to the
prompt, and answers got measurably worse. The mechanism is not established here; the model's
plans matched the question slightly less often under the longer prompt (92.0% vs
94.2% on healthy data), which is consistent with dilution of the instructions but
does not prove it. Two consequences are safe to draw:

- **For the product:** an offered capability is not free even when unused. The
  loop offers the re-read only in the declared agent condition; the standard
  prompt, used everywhere else, is untouched (invariant 1).
- **For the arm's own contrasts:** agent-versus-baseline differences on stale data
  mix the tool's effect (zero, since unused) with this prompt effect. H-R1b is
  unaffected — no discordance at all on flipped questions — but anyone comparing
  the agent cells' raw rates with the baseline's must net this out.

## 6. Limitations

- **One model, one question, one source.** gpt-4o-mini, the demo question (the
  cheapest in-stock product), the ESCI slice. Another model may use the tool; the
  claim is about this agent on this task.
- **The tool is a JSON action in the answer schema, not native function calling**
  (A6 decision, uniform across providers). A model trained to call tools through
  its API's tool interface may reach for one there more readily. This is the most
  plausible reason the null might not transfer, and the cheapest to test next.
- **The age is a JSON field (`_record_age_seconds`)** beside each record, as in the
  detectability arm. A different rendering — prose, a warning — would be a
  different treatment, and one closer to hinting at degradation (invariant 1).
- **Re-reads are free and exact on the demo source.** No latency, no failure, no
  load; the menu prices re-reads in counts, not seconds. A real re-read costs
  more, and a real upstream can be stale itself.
- **The gate is a perfect detector here** — age is fixed per state — so the gate
  cell is an upper bound on what a staleness gate can do.
- **Exposure came in low.** 9.3% of the arm's verifiable stale questions were
  flipped, against 12.9% on a broad sample of the same source (the design's first
  figure, 14.7%, counted unverifiable questions — corrected 23 Sep). An unlucky
  but valid draw: every cell shares it, so no contrast is biased, but H-R1b had 41
  flipped questions rather than ~58. With no request ever made, it could not have
  moved either way.
- **The tool-offering prompt is a different instrument** (brief correction 11).
  The arm's rates compare within the arm only, never with the corpus.
- **Temperature 0.2** lets the same question get different answers in two cells;
  the paired design and the discordant counts carry that noise honestly.

## 7. Spend and reproducibility

$0.8541 for the campaign against a $0.9649 expected / $1.8482 worst-case dry-run
(the worst case assumed every agent question re-reads; none did). The dry-run's
input count matched OpenAI's billing exactly on the pilot. All 21 artifacts are in
`results/runs/` (arm `refetch`, seeds 90 001–90 003 healthy and 91 001–91 003 stale), excluded
from every corpus analysis by `NEVER_POOLED`; the questions, records and fault
realization regenerate from the committed slice and the seeds.
