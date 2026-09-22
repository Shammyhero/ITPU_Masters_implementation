# The refetch arm — design

**Status: DESIGN APPROVED 23 Sep 2026** — the author's four choices (§4) and both
decisions the code forced (§7: D1 (a), D2 kept). **Step 1 (the loop) built 23 Sep**
(§5); **step 2 (the batch runner, artifacts, quarantine) built 23 Sep**; nothing spent.
Budget **$0.96 expected, $1.85 worst case**, counted exactly by the dry-run (corrected 23 Sep from the design's ~$1.45 worst case, which assumed a second call costs what a first does — a second turn carries the records twice), against the ~$2.20 the plan holds for this arm. Quarantined by seed
block (90 000–100 000) and by arm name; nothing outside the arm depends on it. If it
is cut on 30 Oct (the plan's hard cut), the router's REFETCH stays in the product
without an experimental claim behind it.

## 1. The question

The detectability arm found that **telling** the agent a record's age changes
nothing: shown `_record_age_seconds`, gpt-4o-mini was no more careful on stale
data than without it (`detectability_findings.md`). That null leaves one obvious
objection standing: the agent had no way to *act* on what it was told. Its only
options were to answer or to abstain.

**Refetch arm.** *Offered a way to act on suspicion — read the records again
before answering — does the agent use it, and does using it save the answers
staleness costs? And what does a gate that re-reads on the agent's behalf cost,
compared with one that refuses?*

This is also the thesis's answer to kill question 3 ("in what sense is this
agentic? it's one API call"): the agent-initiated condition is a genuine
decide → act → decide loop, where the model chooses whether to take the second
step.

## 2. What the code already does, and what it forces

Checked against the code on 23 Sep. Five facts shape everything below.

**2.1 With default rendering, the agent can't tell stale from fresh.**
`render_record` shows a record's age only when the record carries it in `meta`,
and the demo source never sets it. A stale record's values are well-formed and
plausible; the world has just moved on. So an agent offered a re-read with age
hidden is guessing. The one live data point so far — `llama3.1:8b` asked
**0 times in 12** (18 Sep) — was on records with no age shown. It measures
spontaneous asking, not asking under suspicion. Hence the age factor (§4).

**2.2 On the demo source, the gate's re-read is correct by construction.**
`Loop._refetch` reads upstream as of the question's own moment, and no read
latency is modelled. The re-read therefore returns exactly the records the
answer is graded against. A gate-initiated answer is wrong only if the model
itself errs. So "gate refetch reduces silent failure on flipped questions"
(H-R2 as first declared) is guaranteed, and the arm must not present it as a
finding. What the gate condition *measures* is the cost side: re-reads spent,
dollars spent, and correct answers kept, per silent failure prevented.

**2.3 Exposure caps every effect.** A $0 check with the literal answerer
(600 stale demo questions, 23 Sep): **14.7% flipped at 5.05 s** (the corpus
published 13.6% at the same level). At most one question in seven has anything
a re-read could fix. On the other 85%, the best a re-read can do is nothing.

**2.4 Provenance is hard-wired to live.** `session.build_tick` stamps every Tick
`arm: "live"` with the live seed block, and `DemoDelivered` defaults to seed
100 000. Every analysis loader drops `live`, so an arm built on today's loop
would have its own data discarded as live traffic. Both must become parameters.

**2.5 A second re-read request is graded as a silent failure** (a defect, found
23 Sep). The loop allows one re-read (`MAX_REFETCHES = 1`), then asks again with
the same tool-offering prompt. If the model asks again, `parse_answer` returns an
`AgentAnswer` with `refetch_ids` and no value — not abstained, not a parse
failure — and the verifier grades it as a **committed wrong answer**, i.e. a
silent failure under invariant 8. `test_the_agent_is_offered_a_re_read_only_once`
pins the call count but not the grade. The model never asked in the 18 Sep run,
so it has not happened yet; in the arm it would inflate the agent cells' silent
failure. §7 D1 is how to fix it.

## 3. Hypotheses (refining RQs v2 §9, before anything is run)

RQs v2 §9 declared H-R1 and H-R2 on 14 Sep. §2 shows H-R2 as worded is true by
construction, and H-R1 is untestable without the age factor. Refined here, as §9
was refined for the verifier on 15 Sep; RQs v2 §9 gets the same note once this
design is approved.

- **H-R1a (acting on suspicion).** With age shown, the agent asks for a re-read
  more often on stale batches than on healthy ones (paired by question).
- **H-R1b (does acting pay).** With age shown, the agent loses fewer answers on
  **flipped** stale questions than the no-refetch baseline on the same questions.
- **H-R1c (spontaneous asking).** Reported, not tested: the request rate with
  age hidden, on stale and healthy batches. It is the reference for H-R1a — how
  much asking happens with no signal at all.
- **H-R2 (the third verdict's price).** Restated as a cost comparison, because
  the benefit is by construction (§2.2). On stale batches, each verdict has a
  price per silent failure prevented:
  - **refuse:** correct answers forfeited;
  - **gate re-read:** re-reads and dollars spent, plus any correct answers lost
    to model noise;
  - **admit:** nothing spent, nothing prevented.

  H-R2 is that the gate re-read forfeits fewer correct answers per silent failure
  prevented than refusal. On this source that's near-certain, so it is reported
  as the menu, not as a discovery.

**Every outcome is reportable.** If the agent never asks even with age shown,
the detectability null extends from metadata to action — the stronger version
of the finding. If it asks and it helps, an agent with a tool does what an agent
with metadata did not. If it asks indiscriminately (as often on healthy data),
the tool costs money and buys nothing.

## 4. Design (author's choices, 23 Sep: 1a · 2a · 3a · 4a)

**Held constant (invariant 1):** gpt-4o-mini, temperature 0.2 (the retrieval
setting), the demo source (the study's ESCI slice served through the runner's
own functions), the streaming pipeline, the demo question ("the cheapest product
currently in stock", `min_by price where stock > 0`), 6 candidates. The analyst
prompts are a different instrument from the corpus agent's (brief correction 11),
so the arm's rates are compared **within the arm only** — the baseline cell is the
reference, never the corpus.

**Data states:** healthy (0.05 s inherent staleness) and freshness severe
(5.05 s: 5 s injected + 0.05 s inherent) — choice 2a.

**Cells** (choice 1a: age is a factor for the agent-initiated condition):

| Cell | Mode | Prompt | Age shown | Healthy | Stale |
|---|---|---|---|---|---|
| `baseline` | off, age policy in shadow (`warn`) | standard | no | paid | paid |
| `gate` | gate, age policy enforced | standard | no | ≡ baseline | paid |
| `agent_hidden` | agent | tool-offering | no | paid | paid |
| `agent_shown` | agent | tool-offering | yes | paid | paid |
| `refuse` | derived from `baseline` | — | — | $0 | $0 |

- **`gate` on healthy isn't run.** Nothing violates the policy, so it is the
  baseline: same prompt, same records.
- **`refuse` costs nothing to measure.** The baseline runs with the age policy
  in shadow mode, so every baseline decision records whether the gate would
  have refused it. Refusal's price is what the baseline *actually did* on
  exactly those questions (paired). That is better than the loop's
  `would_have`, which asks the literal answerer and so ignores the model's own
  errors.
- **The age policy** is `max_record_age_seconds = 2.0` (the loop tests' strict
  policy). Any threshold between 0.05 s and 5.05 s behaves identically, because
  age is fixed per state. The gate is therefore a **perfect detector** here:
  it re-reads 100% of stale batches and 0% of healthy ones. Stated, because it
  makes the gate cell an upper bound on what a staleness gate can do.
- **Age shown** uses the detectability arm's own mechanism,
  `execute.attach_record_age`: 0.05 s on healthy records, 5.05 s on stale ones.
  Records returned by a re-read carry their true age too (≈0 s).

**Size** (choice 3a): 7 paid cells × 3 replications × 150 questions =
**21 runs, 3,150 questions.** This replaces the plan's "~54 runs", a figure with
no traceable derivation. Expected ≈66 flipped stale questions per cell across the
three replications (14.7% × 450).

**Seeds and pairing (invariant 2):**

- `sample_seed` = the `RunConfig` default for retrieval (10 000 + replication):
  a function of `(task, replication)` only. Question *i* of a replication draws
  its query and simulated moment with seed `sample_seed × 1 000 + i`. Every cell
  and **both states** in a replication see identical queries at identical
  simulated times — the corpus's pairing.
- `config.seed` = 90 000 + 1 000 × state + replication, **shared by every cell
  of a (state, replication)**, as the detectability arm shared it across its
  A/B pair. The freshness injector is constant-delay, so the realization is
  deterministic anyway; sharing the seed makes that explicit rather than lucky.
- One honest wrinkle: a product created in the last 5 s before the question's
  moment exists for the healthy pipeline but not yet for the stale one, so a
  question's candidate set can differ **between states** (never between cells).
  That is staleness doing its job, and the corpus runner behaves the same way.

**Flipped is defined on the records as first delivered.** After a re-read, the
verifier compares against the refreshed records (A6's fix), so a re-read
question's own `flipped` flag reads False. The analysis needs the question's
exposure *before* anyone acted, identical across cells. So every decision also
records `flipped_as_delivered`, computed from the original served state against
the answer key.

## 5. Build (each step proposed before code)

1. **Loop.** *Built 23 Sep* — 818 tests (`tests/test_refetch_loop.py`, 17 new).
   A $0 smoke run on `llama3.1:8b` (12 stale questions per age setting, not
   evidence): 0 re-read requests with age hidden, **0 with age shown**; the
   continued second turn answered cleanly on the real model (3,509 tokens in).
   - Provenance (arm, seed block) and the demo source's seed become parameters.
     The defaults stay live, so the API and the CLI are unchanged.
   - The demo source can attach record age.
   - Fix §2.5 per D1.
   - Tests:
     - invariant 1 on both prompts, including the age-shown render;
     - pairing across cells and across states;
     - the re-read accounting;
     - termination;
     - an action reply is never graded as an answer.
2. **Batch runner** (`python -m airsbench.runner.run --refetch-arm`). *Built 23 Sep*
   with step 3 — `runner/refetch.py`, `config.build_refetch_arm`, 851 tests
   (`test_refetch_arm.py`, `test_refetch_quarantine.py`). As built, the dry-run
   runs the real loop over all 3,150 questions with a counting answerer in place of
   the model (35 s, $0), so the second turn is counted exactly too, not bounded:
   **$0.9649 expected, $1.8482 worst case** (output at 150 tokens a call). Each
   run's worst case must also fit what is left before that run starts. The
   pre-re-read AIRS reading is kept in the Tick (`refetch.airs_before`,
   `dimensions_before`), because after a gate re-read the gate block describes the
   refreshed records.
   - Builds the 21 configs.
   - **`--dry-run` renders every first-call prompt of the grid and counts its
     tokens exactly** with tiktoken. The prices are gpt-4o-mini's declared ones.
     Second calls are bounded as "every agent question re-reads".
   - `--max-cost` is checked against that bound before starting. Each call also
     passes an analyst `Budget` with the same session cap.
   - `--offset`/`--limit` to resume.
   - Arm spend goes in each artifact's `usage` and **not** in
     `~/.airs/spend.json`, which is live accounting.
   - A transport failure stops the run with no artifact (invariant 6).
3. **Artifacts** (choice 4a): one JSON per (cell, state, replication) in
   `results/runs/`, the corpus shape: `config`, `metrics`, `airs`, `usage`,
   `decisions`.
   - `config.seed` sits in the 90k block, so `run_arm` → `refetch`. It also
     carries the cell's mode and age flag.
   - Each decision carries the Tick's verification (`correct`,
     `silent_failure`, `attribution`), `flipped_as_delivered`, the gate block,
     the re-read block (asked, by whom, which ids, a second request), and the
     per-question usage.
   - **Quarantine test:** every corpus analysis entry point excludes `refetch`,
     including `flip_partition` and `phase1_check` under
     `include_other_arms=True` — the arm is a different instrument and must
     never pool.
4. **Dry-run, shown to you.** Nothing paid before your go-ahead. *Done 23 Sep.*
   **Paid pilot 23 Sep, $0.0026** (one stale age-shown agent run, replication 1, 10 questions, written to a scratch directory, not `results/runs/`): billed input **13,906 tokens = the dry-run's count exactly**; output 92 a call against 150 budgeted; seed 91 001 attributed to the arm; the gate recorded the 5.05 s violation and delegated. gpt-4o-mini **asked for a re-read 0 times in 10** with each record showing its age; 7 correct, 2 abstained, 1 silent (agent impairment, confidence 1.0); 0 flipped questions (P ≈ 0.20 at 14.7% exposure — chance). The pilot is a plumbing check, not evidence.
5. **Run** (~1.5–2.5 h wall-clock at gpt-4o-mini's pace; `--offset` if the
   laptop sleeps).
6. **Analysis + Fig 4.9** (`analysis/refetch.py`, `refetch_findings.md`):
   - **A.** Re-read request rate by cell and state (H-R1a, H-R1c).
   - **B.** Outcomes on flipped vs unflipped stale questions — correct, silent,
     abstained — by cell (H-R1b).
   - **C.** The verdict menu: prevented, forfeited, re-reads and $ per silent
     failure prevented (H-R2).

   Then the third verdict priced in `gate/replay.py`.

## 6. Analysis

- **Unit:** the question, paired across cells by (replication, question index).
- **Test:** paired bootstrap as declared in RQs v2 §9 (`interaction.py`'s
  method), resampling questions within replication.
- **Discordant pairs:** request-rate contrasts (H-R1a) and flipped-question
  accuracy contrasts (H-R1b) are McNemar-shaped: only questions where the two
  cells disagree carry information. So the findings state the discordant counts
  beside every interval.
- **Silent failure:** only `runner/scoring.py::is_silent_failure` (invariant 8).
- **Temperature 0.2** means the same question can get different answers in two
  cells by chance. That noise sits inside each cell's agent-impairment rate and
  is paired out of the contrasts. The healthy baseline's error rate is the floor
  it is measured against.

## 7. Decisions the code forced (decided 23 Sep)

**D1 — how the re-read reaches the model** (fixes §2.5). **Decided: (a).**

- **(a) Continue the conversation — chosen.** The follow-up is a second
  turn in the same exchange: the model's own action message, then a user
  message with the records read again (neutral wording: "These records were
  read again: … Answer the question now."), and no further offer. This is what
  tool use means, it terminates by construction, and the model knows which
  records it already asked about. `langchain` takes the role-tuple messages
  `call_json` already uses. The loop is shared, so the API and console get the
  same behaviour.
- **(b) Keep the single re-sent prompt** (today's loop: the same tool-offering
  prompt with the refreshed records swapped in). Grade a second request as
  **not committed** — reported as its own count, never a silent failure. Less
  change, but the model doesn't see that it already re-read, which invites the
  second request in the first place.

Either way, the grading fix lands: a reply that is an action is never graded as
a committed answer.

**D2 — the healthy side of `agent_shown` shows 0.05 s. Decided: kept.** That is what the
detectability arm's age-baseline cell did, so the two arms stay comparable.
Absent and "0.05 s" are different treatments, and only the second tests whether
the agent reads the number.

## 8. Limitations (to carry into Ch3/Ch4)

- One model (gpt-4o-mini), one question type, one source. The claim is about
  this agent on this task.
- Re-reads are free and instant on the demo source. A real re-read has latency,
  load and can fail; the menu prices re-reads in counts, not seconds.
- The gate is a perfect detector here (§4). A real gate sees noisier ages.
- The tool-offering prompt is a separate instrument. Its rates compare with this
  arm's baseline only.
- Exposure (14.7%) is a property of the slice's catalog velocity, as the
  freshness sweep established. A faster-moving catalog would give a re-read
  more to fix.
