# The Analyst — implementation brief, as adopted

**Adopted into `docs/plan.md` on 14 Sep 2026** (stages A1–A11). Below the line is the
author's brief, verbatim. This header records the author's decisions on the points it
left open and the corrections made after checking it against the code.
**Where this header and the brief disagree, the header wins.**

## Author decisions (14 Sep 2026)

| Question | Decision |
|---|---|
| How sources reach `airs serve` | **Declared locally** — a `sources.yaml` or CLI flags, credentials from environment variables. The console lists, tests and describes *declared* sources; it never accepts a path, DSN or URL over HTTP. This keeps the W3 security property: any web page can send requests to a server on localhost, so the server must not be a file-reader or connection-opener on request. Paste stays available as an inline source. |
| The W6 refetch arm | **Two conditions, one loop** (`src/airsbench/analyst/loop.py`, used by the API and the batch runner). *Agent-initiated* refetch — the agent is given `refetch(record_id)` and decides — is the treatment that answers kill question 3 ("is this agentic?") and extends the detectability null. *Gate-initiated* refetch — the router's REFETCH verdict — is a second condition that prices the third gate verdict. Seed block 90 000–100 000; ~$2.20; dry-run first. **Done 23 Sep** (`refetch_findings.md`, $0.85): the agent never asked for a re-read (0 of 1,800); a gate's re-read matches the healthy pipeline. |
| Which model answers | **Two options in the console.** *Free:* any model the user already has in a local **Ollama**, discovered from Ollama itself — no key, $0, records stay on the machine. *API key:* **OpenAI, Anthropic or Google Gemini**, the model chosen from that provider's list. The key comes from an environment variable or is entered in the console for the session: held in process memory only, never written to disk, logs, Ticks, artifacts or URLs. The console states plainly that records are sent to that provider. With neither, the console still scores and replays. Gemini is new: `agents/llm.py` routes only OpenAI, Anthropic and Ollama today. |
| W4's Mode A work | **Kept, redesigned into the Analyst**: the task-profile switch, the recommended policy, the predicted exchange rate as the meter's prior (stating raw sweep rate vs attribution "true cost"), and a printable readiness report that includes the session's attribution. The timeline is not a reason to drop any of it. |

## Corrections to the brief (each verified against the code, 14 Sep)

1. **§3.4 — correctness is tested first.** The brief's table labels an answer that
   ignores the delivered records and lands on the true value "agent impairment".
   Correctness is against upstream (invariant 4); attribution applies to wrong,
   committed, parseable answers only:

   ```
   abstained or parse_failed                           → no attribution
   agent == upstream                                   → CORRECT
   agent != upstream, delivered == upstream            → AGENT IMPAIRMENT
   agent != upstream, agent == delivered               → ANSWER KEY MOVED   (pipeline)
   agent != upstream, agent != delivered != upstream   → BOTH
   ```

   This refines, and must aggregate to, the published partition: a query is *flipped*
   when the delivered-best differs from the true-best (`flip_partition.py`,
   `QueryOutcome.flipped`); ANSWER KEY MOVED + BOTH = wrong on flipped queries;
   AGENT IMPAIRMENT = wrong on unflipped queries.

2. **§3.2 — the semantic rule has two states, not one.** The brief says an unapproved
   manifest scoring UNMEASURED is "the same commitment `probe.py` already makes". It is
   not: the probe scores records with no context block **0**, deliberately, and a test
   pins it ("missing context is not a missing measurement — it IS the degradation").
   Implemented rule: **no reviewed manifest → semantic UNMEASURED** (the tool does not
   know what the fields mean); **reviewed manifest → context rendered from it and scored
   by the probe's existing rule**, where records with no context score 0.
   *Corrected 17 Sep, against the code:* the probe's rule counts the four context
   categories (entity, units, descriptions, relationships), not the fields described —
   an earlier version of this line said undescribed fields lower completeness, and they
   do not. The calibrated rule is kept unchanged (author decision); field coverage is
   reported beside the score as an observation. See correction 19.

3. **§3.2 — the semantic toggle applies the real injector.** Dropping the manifest alone
   will not move abstention on real data: columns such as `price` and `stock` describe
   themselves, which is the known trap in `CLAUDE.md` ("semantic stripping must
   opaquify field names… without opacity the fault measurably does nothing"). The toggle
   runs `SemanticStrippingInjector` — context removed and names made opaque, with the
   opaque map recorded so consistency can reverse it (invariant 5). Whether abstention
   moves on a user's data is an observation to report; OR 51.9 is gpt-4o-mini on ESCI and
   is not promised.

4. **§3.1 — no upstream loses consistency and the verifier, not freshness.** The probe
   measures freshness from the delivered records' own `event_timestamp` and
   `read_timestamp`, and the brief itself requires identical behaviour to `airs probe`.
   The delivered-to-upstream lag is recorded as an additional observation; it is not the
   freshness dimension the weights were calibrated on.

5. **§3.3 — aggregates are verified over the same ids.** Checkable questions are scoped
   to the records sampled at t0; at t1 the verifier fetches exactly those ids and runs the
   same plan. A "bounded resample" would compare different populations, and the
   attribution would mean nothing (the paired-design argument behind invariant 2).

6. **§7.1 — Fig 4.10 covers the retrieval runs and must agree exactly.** Classification's
   answer (`ArrDel15`) is a property of the flight, not computable from the delivered
   record, so there is nothing to verify there. The verifier recomputes what `Replayer`
   and the runner already computed on the main-factorial and freshness-sweep retrieval
   runs, so agreement must be **exact**, not "within Monte-Carlo error"; any mismatch is
   a bug in the verifier.

7. **§3.5 — the router's REFETCH is not, by itself, the W6 arm.** A gate deciding to
   re-read involves no agent decision and does not answer kill question 3. See the
   decision above: both conditions, one loop.

8. **§8.6 and §11.1 — "no key, offline, $0" requires a local model.** `pip install` does
   not provide one. Acceptance criterion 1 becomes: *with a local Ollama model, no key and
   no network, a visitor selects the bundled source, approves its manifest, asks a
   question, and sees a verified answer with its attribution, at $0; with an API key
   instead, the same flow; with neither, scoring and replay.*

9. **§8.1 — live traffic is never written into `results/runs/`.** Tagging and filtering
   are kept as a second line: live artifacts go to a user directory (`~/.airs/sessions/`),
   carry `arm: "live"` and a reserved seed block (100 000–110 000), and
   `tests/test_live_quarantine.py` asserts every analysis entry point excludes them.

10. **§4 — the Tick keeps the approved `airs` extension**: each dimension
    `{score | null, detail, weight}` plus band, as W3 decided, not bare numbers.

11. **§3.4 — the plan-returning prompt is a different instrument.** Asking the agent for a
    structured answer plan changes what it does. Live silent-failure rates are therefore
    not directly comparable with the corpus's, and Chapter 3 says so. Invariant 1 still
    holds: the prompt never mentions faults or degraded data.

12. **§7.2 — say what is real in the case study.** A public API supplies one read. The
    delivered side has to be a real caching or polling pipeline set up for the study, so
    the data and its update velocity are real and the lag is produced by a real pipeline,
    but the pipeline's design is ours. Report it that way.

13. **Privacy wording.** "Nothing leaves this machine" holds for scoring, replay and the
    free local model. It does not hold for hosted models (records go to the provider) or
    for the Postgres and HTTP adapters (the tool connects wherever the user points it).
    The console states which applies.

14. **§9 — hours and order** are replaced by `docs/plan.md`, stages A1–A11.

15. **§3.1 and §3.4 — consistency is scored against upstream as of when the delivered
    values were true, not against upstream now** (found building A1). The corpus compared
    delivered records with the same records before the fault chain — the catalog as of
    t − staleness (`runner.execute.run_retrieval`) — so consistency measured what the
    pipeline did and freshness measured age (invariant 5). Comparing with upstream at
    answer time would count every value that moved during the staleness window against
    consistency, making it collinear with freshness under the calibrated weights. So
    `Source.fetch` takes `as_of`: **consistency uses upstream as of the delivered values'
    time; the verifier uses upstream at answer time.** A source with no history (a file, a
    table without versions) reports `supports_as_of: false`, and its consistency also
    absorbs staleness — said in the output, not hidden.

16. **§3.4 — answers are verified against the question's plan, not the agent's** (author
    decision, 15 Sep). An agent that misreads "cheapest" as "most expensive" and then
    carries out its own plan correctly would otherwise be graded correct. Questions are
    structured (a plan plus wording); the agent still returns its plan, which is recorded
    twice — `plan_matches_question` (same form) and `agent_plan_agrees` (same answer when
    re-executed over the served records) — and never graded. Seen live: `llama3.1:8b` wrote
    `stock >= 1` (equivalent on whole-number stock) and `stock >= 0` (a real widening) for
    `stock > 0`.

17. **§3.4 — four labels, not three** (author decision, 15 Sep):

    ```
    answer_key_moved      served ≠ truth, the agent gave the served answer
    both                  served ≠ truth, the agent gave something else
    corrupted_in_transit  served = truth, a field the plan reads was missing, renamed,
                          retyped, changed or made opaque in delivery
    agent_impairment      served = truth, the fields it reads arrived intact
    ```

    On the demo source severe drift changed a needed field in 76% of questions and severe
    stripping in 99%; with three labels every wrong answer there would read "agent
    impairment (model)". `corrupted_in_transit` states a fact about the delivery and lists
    the fields; it does not claim the change caused the error. The first two labels sum to
    wrong answers on flipped queries and the last two to wrong answers on unflipped ones,
    so the published partition is recovered exactly.

18. **§7.1 — Fig 4.10 validates all four labels** (author decision, 15 Sep): A4 regenerates
    each corpus run's fault realization and checks it against the run's logged consistency
    and semantic scores before using it.

19. **§3.2 — the manifest, as built** (author decisions, 17 Sep):
    - **The score stays the calibrated category rule.** Which fields lack a definition is
      reported as field coverage beside it, never folded in (see correction 2).
    - **Reviewed means a stamp plus a schema fingerprint** — field names and kinds, with
      integer and float one kind. A renamed or retyped column makes the manifest stale
      and semantic UNMEASURED until it is reviewed again. `reviewed: true` would have
      stayed "reviewed" through exactly the drift a manifest exists to catch.
    - **Five states, two outcomes:** reviewed → measured; unreviewed, stale, absent
      (including a declared file not written yet) and invalid → UNMEASURED with the reason
      and the command that fixes it.
    - **Inference ships:** an offline heuristic (roles from names and types, never units or
      meanings) always, refined by a local Ollama model at $0; hosted models with A5's
      spend caps. Nothing proposed counts until reviewed.
    - **Rendering depends on the source.** A pipeline that renders its own semantic layer
      (the demo, via the runner's record builders) is *described* by its manifest and never
      re-rendered — that would undo semantic stripping. Bare records (files) get the
      reviewed manifest rendered in, only where they carry no context of their own. The
      bundled demo manifest renders exactly the context the corpus agent read (tested).
    - The manifest schema adds `relationship` per field and `entity` at the top, because
      the probe's four categories need both; a manifest without them scores 50–75 and says so.

---

# Implementation brief — the Analyst: live AIRS-gated question answering over a connected source

**For:** a session working in `ITPU_Masters_implementation`.
**Supersedes:** Mode A's "paste your own JSONL" input (REVIEW Phase 3) and Mode C
("watch it live", optional). Both are replaced by what follows.
**Author's framing:** this is a tool a data engineer could point at their own
pipeline. The defence is a place it happens to be shown, not what it is for.

---

## 0. Read before writing any code

In this order:

1. `CLAUDE.md` — all eight invariants. Several of them constrain this work
   directly and are cited by number below.
2. `src/airsbench/probe.py` — `measure`, `score`, `composite`, `DIMENSIONS`,
   `BANDS`, `ProbeError`. **Every number in this feature comes from here.**
3. `src/airsbench/gate/controller.py` and `policy.py` — `Verdict`, `Violation`,
   `Policy`. The verdict shape is already right; do not invent a second one.
4. `src/airsbench/server/api.py` — the existing `/api` routes and the single
   error shape (422, `{"error": {"input", "line", "message"}}`).
5. `src/airsbench/agents/retrieval.py` — `ground_truth()` is the seed of the
   verifier in §3.4. Generalise it; do not replace it.
6. `src/airsbench/pipelines/loader.py` — the catalog time machine. It is the
   existing proof that delivered-vs-true is computable; the adapters are the
   same idea against real systems.
7. `docs/flip_partition_findings.md` — §3.4's attribution logic must agree with
   the published partition. If it disagrees, the code is wrong, not the paper.

**Hard rule, carried from `server/api.py`'s docstring:** no scoring rule is
implemented twice. The TypeScript port already drifted once and was deleted for
it. Everything in this feature calls `probe` and `gate`.

---

## 1. What this replaces, and why

Mode A asked a visitor to produce two JSONL files. Practitioners will not do
this. The input is the reason the tool goes unused, and the paste box is what
makes the product look like a form validator rather than an instrument.

Replace it with **source adapters**: point the tool at where the data already
lives, and it samples both streams itself.

This is not a convenience change. It is what makes the rest possible. Two live
reads of the same source, taken at different points in the pipeline, are
exactly the asymmetry the whole thesis is built on:

| Thesis | Product |
|---|---|
| `--records delivered.jsonl` | what the user's pipeline currently serves |
| `--source upstream.jsonl` | what the system of record says right now |
| ground truth at query time (invariant 4) | the upstream read, taken at answer time |

The contract is unchanged. The adapters only remove the file.

---

## 2. The claim this feature makes

State this in Chapter 3 and on the defence slide, because it is what separates
this from a demo.

The thesis established offline, on two curated datasets:

- the agent's own confidence carries no information about its silent failures
  (AUC 0.501);
- pipeline telemetry alone carries some (0.580, DeLong p = 0.0001);
- accuracy loss under staleness is mostly the answer key moving, not the agent
  degrading (residual −0.003, established three ways).

The Analyst tests whether that machinery **transfers to data the study did not
design around**, at runtime, with a real verifier. That is the external-validity
section REVIEW Phase 1D marks as weak, answered by construction rather than by
argument.

It also converts a static score into a runtime detector. `airs probe` says "this
pipeline is risky before you deploy." The Analyst says "this specific answer,
just now, was wrong, and here is whose fault it was." Nothing in the commercial
space does the second thing, because doing it requires holding a counterfactual
and no product holds one.

**The headline capability, in one line:** live flip-partition attribution on
every answer.

---

## 3. Architecture

Five pieces. Build them in this order; each is independently useful and each has
a cut point.

### 3.1 Source adapters

New package `src/airsbench/sources/`.

```python
class Source(Protocol):
    name: str
    def sample(self, n: int, *, key: str | None = None) -> list[Record]: ...
    def fetch(self, ids: Sequence[str]) -> list[Record]: ...
    def describe(self) -> SourceSchema: ...   # columns, types, row count, a few example values
```

`fetch` exists because the refetch arm (W6) needs it and because §3.4 needs a
targeted upstream re-read rather than a full resample.

Ship these adapters:

| Adapter | Why it is on the list |
|---|---|
| `demo` | bundled ESCI slice + its update stream. A visitor with no database gets the full experience in one click, offline, free. **Build this first** and develop the other four against it. |
| `files` | CSV / Parquet / JSONL, file or directory. Covers the "my pipeline lands in S3" case and preserves the old input path for anyone who wants it. |
| `postgres` | connection string + table or query. The most common system of record. |
| `duckdb` / `sqlite` | a local file, zero setup, good for the README walkthrough. |
| `http` | a JSON endpoint plus a JSONPath to the record array. Covers APIs and anything not on the list. |

Snowflake, BigQuery and Databricks are **not** in scope. Note in the README that
the protocol is four methods and that adding one is an afternoon. Claiming
warehouse support you have not tested is exactly the `infra_unused/` mistake
again, and kill question 2 already punished it once.

A **source pair** is what the tool actually operates on:

```python
@dataclass(frozen=True)
class SourcePair:
    delivered: Source          # what the agent will be fed
    upstream: Source | None    # the system of record; None is legal and consequential
    manifest: Manifest
```

If `upstream` is None, consistency and freshness fall to `UNMEASURED` and the
verifier in §3.4 is disabled. Say so loudly in the UI. This is the same rule as
`airs probe` clearing its upstream box, and it must behave identically.

Connection strings and credentials: read from environment or a local config
file, never from a URL parameter, never logged, never written into a Tick or a
run artifact. Add a test that asserts no Tick field matches a DSN pattern.

### 3.2 The semantic manifest — the ontology, and it is load-bearing

To score `semantic` and `consistency` you have to know which column means what.
TextQL calls this an ontology and stores it as code in a git-backed repo. Do the
same, for a better reason than they have: **here it is an input to a
measurement.**

```yaml
# manifest.yaml
source: ecommerce_catalog
entity: product
fields:
  product_id:  {role: id}
  price:       {role: measure,    unit: USD,   definition: "current listed price, excl. tax"}
  stock:       {role: measure,    definition: "units on hand at the fulfilment centre"}
  updated_at:  {role: updated_at, tz: UTC}
  title:       {role: label}
checkable_questions: [min_by, max_by, count_where, sum_where, lookup, top_k]
```

Two ways to get one, both required:

1. **Inferred.** One `describe()` plus one cheap model call proposes a manifest
   from column names, types and example values. The user reviews and approves
   it field by field. This is Ana's "proposes, you approve," and it is the right
   pattern.
2. **Committed.** `manifest.yaml` lives in the user's repo, is versioned, and is
   loaded without a model call.

**The rule that makes it matter, and the one a professor will ask about:** an
unapproved or absent manifest scores `semantic: UNMEASURED`, never 100. A field
whose role is unknown is not a healthy field. This is the same commitment
`probe.py` already makes and the same reason the README gives for making it.

Nice consequence, and worth demonstrating live: the manifest **is** the thing
`semantic_stripping.py` removes. Toggling the manifest off in the UI is the
semantic stripping fault, applied to the user's own data, with abstention moving
the way RQ3 says it moves (OR 51.9). The user performs your experiment on their
own pipeline in about four seconds.

### 3.3 The dual read

On every question:

1. `t0`: sample from `delivered`. These records are what the agent will see.
   Score them with `probe.measure` exactly as the gate already does.
2. The agent answers from those records and nothing else.
3. `t1`: `upstream.fetch(ids_the_agent_reasoned_over)` plus, for aggregate
   questions, a bounded resample. This is the answer key.

Record `t0`, `t1`, and the observed delivered-to-upstream lag. The lag is a real
freshness measurement on the user's real pipeline, which is a number most teams
do not have and will want.

Two honest constraints to document rather than paper over:

- `t1` happens after `t0`, so some of the divergence is the world moving during
  the answer, not pipeline lag. Report the interval alongside the attribution
  and let a reader judge. Where the source exposes a transaction timestamp, read
  as of `t0` instead and say the interval is zero.
- `fetch` on a heavily loaded production source is a cost the user is paying.
  Make it sampled, bounded and configurable, with the row count shown before
  anything runs.

### 3.4 The verifier — and the live flip partition

This is the centre of the feature. Everything else exists so this can work.

The agent returns, alongside its prose answer, a structured **answer plan**:

```json
{
  "answer": "B07X9 at $24.99",
  "plan": {"type": "min_by", "measure": "price",
           "where": [{"field": "stock", "op": ">", "value": 0}]},
  "value": {"id": "B07X9", "price": 24.99},
  "confidence": 1.0,
  "abstained": false
}
```

Only the question types in `checkable_questions` are accepted. Anything outside
that set is answered with the verifier disabled and labelled as unverified in
the UI. Do not guess at a verification for an open-ended question; an unreliable
silent-failure flag is worse than none, and a professor will find it.

Then execute the plan twice, deterministically, in Python, with no model call:

| | computed over | meaning |
|---|---|---|
| `answer_delivered` | the records the agent was served | what a perfect agent *should* have concluded from what it saw |
| `answer_upstream` | the `t1` read | what is actually true |

Three-way attribution, which is `docs/flip_partition_findings.md` running live:

```
agent == delivered  and  delivered == upstream   →  CORRECT
agent == delivered  and  delivered != upstream   →  ANSWER KEY MOVED     (pipeline)
agent != delivered                               →  AGENT IMPAIRMENT     (model)
agent != delivered  and  delivered != upstream   →  BOTH — report both, do not collapse
```

Silent failure keeps **exactly one definition**, from invariant 8 and
`runner/scoring.py::is_silent_failure`: committed, parseable, and wrong against
the upstream answer, **with no confidence threshold**. Import that function.
Do not re-derive it, and do not add a threshold here because the UI would look
calmer with one.

The UI line, which is the moment worth building the whole thing for:

```
  upstream now            pipeline delivered      agent answered
  price: 24.99            price: 24.99            "B07X9 — $24.99"
  stock: 4                stock: 0   ← 41s stale   truth: B09K
                                                  ✗ SILENT FAILURE
  AIRS at this moment: fresh 19.8 · lat 100 · cons 74.6 · sem 100  → 61.2 (AT RISK)
  Attribution: ANSWER KEY MOVED — your pipeline, not your model.
  Agent's own confidence: 1.00   (AUC 0.501 — it says that when it is right, too)
```

### 3.5 The router — admit / refetch / refuse

Put the gate in the request path, before the model is asked.

```
question → sample delivered → probe.measure → Controller.evaluate(policy)
                                                    │
                    ┌───────────────────────────────┼────────────────────────┐
                 ADMIT                          REFETCH                   REFUSE
             answer normally            upstream.fetch() → re-score      no model call
                                        → answer from refreshed data     rule + observed value
                                        (this is the W6 arm's loop)      $0, cannot hallucinate
```

Three properties to preserve:

- **REFUSE costs nothing and cannot hallucinate.** It is arithmetic. Say this in
  the UI; it is the cheapest credibility in the product.
- **REFETCH is the W6 refetch arm.** Write the two-step loop once, in
  `src/airsbench/analyst/loop.py`, and have both the batch runner and the API
  call it. This is the scheduling argument for the whole feature: the arm is
  already budgeted 14 h and ~$1.50, and building it as a service instead of a
  script gives the product a live agent as a byproduct.
- **The session meter runs against real ground truth**, because §3.4 provides
  it: answered, refused, refetched, correct, silent failures caught, correct
  answers forfeited, and the live exchange rate. The thesis says every policy
  forfeits 7–21 correct answers per silent failure prevented. Watching that
  meter move during a conversation is a better argument than Fig 4.5.

---

## 4. Data contract

Extend the existing `Tick` (REVIEW Phase 3) rather than adding a second shape.
One message, all modes, so the UI never branches.

```
Tick {
  t, mode: "analyst" | "replay" | "probe",
  source  { delivered, upstream|null, manifest_id, manifest_approved: bool },
  config  { fault|null, severity|null, pipeline, task },
  airs    { freshness, latency, consistency, semantic, total|null, covered, band },
  gate    { verdict: "admit"|"refetch"|"refuse", violations[], reason },
  records { ids[], delivered{}, upstream{}, changed_fields[], lag_seconds },
  decision{ answer, plan, value, confidence, abstained, parse_failed,
            answer_delivered, answer_upstream,
            correct, silent_failure,
            attribution: "correct"|"answer_key_moved"|"agent_impairment"|"both"|null },
  refetch { attempted: bool, n_records, verdict_after, airs_after },
  cost    { input_tokens, output_tokens, usd, model },
  running { n, correct, silent, refused, refetched, prevented, forfeited, exchange_rate },
  provenance { arm: "live", seed_block, run_id|null, session_id }
}
```

`mode: "replay"` replays a pre-baked array from `results/runs/`, so **Mode B's
walkthrough is the same component with a different data source.** Delete the
bespoke six-step UI. One renderer, three feeds.

---

## 5. API

Extend `src/airsbench/server/api.py`. Keep it thin by the same rule: no score
computed in that file.

```
POST /api/sources/test      → validate a connection, return describe()
POST /api/sources/manifest  → propose a manifest (one model call, costed)
PUT  /api/sources/manifest  → approve/edit; returns manifest_id
POST /api/session           → open a session; returns session_id, spend cap, policy
POST /api/ask               → one question. Streams Ticks (SSE). The whole feature.
GET  /api/session/{id}      → the running meter
POST /api/replay            → unchanged
```

`/api/ask` streams so the user watches the gate decide, the agent answer, and the
verifier resolve, in that order. The pause between "answered" and "verified" is
dramatically useful and costs nothing to create; it is where the viewer forms an
expectation the verifier then breaks.

Errors keep the existing 422 shape. Connection failures name the adapter and the
thing to fix, never a traceback — same commitment as W3 step 2.

---

## 6. UI

Replace `demo/src/components/RecordsInput.tsx` with a connect flow. Keep
`ScoreView.tsx`. Add:

- **Connect** — pick adapter, test, see `describe()` output, choose the upstream
  pair. A visible "no upstream" path that shows what goes UNMEASURED and what
  stops working.
- **Manifest review** — proposed roles, field by field, approve or edit. Shows
  unapproved fields as UNMEASURED in the score panel behind it, live, so the
  cost of skipping is visible while you skip it.
- **Conversation** — question in, gate verdict badge, streamed answer, then the
  verifier resolving. Confidence shown greyed with `AUC 0.501` beside it
  permanently.
- **Trace panel** — the three-column diff from §3.4, expandable on any answer.
- **Meter** — the running exchange rate, always visible.
- **Semantic toggle** — drop the manifest mid-session, watch abstention move.

Styling follows `demo/src/app/globals.css`. Do not introduce a component
library for this.

---

## 7. How this earns a place in Chapter 4

A feature is not a finding. Do these two analyses or the chapter cannot cite it.

**7.1 Verifier calibration against the corpus.** Replay all 302 committed runs
through the §3.4 verifier and the §3.5 router in offline mode. The verifier must
reproduce the published silent-failure rates and the published flip-partition
split to within Monte-Carlo error. If it does, the live instrument measures the
same construct the thesis measured, and you can say so with a number. If it does
not, the verifier is wrong and you have found that before the defence rather
than during it. Emit this as **Fig 4.10, verifier agreement**. It is cheap,
free, and it is the figure that makes the product admissible as evidence.

**7.2 A live-source case study.** Point the Analyst at one real source that is
not ESCI or BTS. A public API with genuine update velocity is enough; it does
not need to be a bank. Run 50–100 questions. Report AIRS, the observed lag
distribution, the attribution split, and whether AIRS ranked the risky moments
above the safe ones. Even a null is publishable here and it is the only external
validity the thesis will have. Budget ~$0.05.

---

## 8. Invariants and firewalls

1. **Live traffic never touches the evidence.** Reserve a seed block for
   sessions, tag every artifact `arm: "live"`, and make every module in
   `analysis/` filter it explicitly. Add `tests/test_live_quarantine.py`
   asserting that each analysis entry point excludes it. Without this, the first
   question at the defence is whether demo traffic contaminated the results, and
   "I think not" is not an answer.
2. **Invariant 1 holds.** The Analyst's prompt must not mention faults,
   staleness, or that data may be degraded. The router acts on the data; the
   agent is still the instrument. If the prompt hints, §7.1 will silently
   disagree with the corpus and you will not know why.
3. **Invariant 8 holds.** One definition of silent failure, imported, no
   threshold.
4. **Invariant 3 holds in demo mode.** The fault chain is applied once, by the
   source, never again downstream.
5. **Spend cap in the request path, not around it.** Per-session and per-day
   ceilings, enforced before the call, returning a typed refusal. Reuse the
   existing budget guard. `--dry-run` equivalent: `/api/ask?estimate=true`
   returns the projected cost without calling anything.
6. **Free by default.** `ollama/llama3` is the default model for a public
   deployment; hosted models require an explicit key. `llm.py` already prices
   local models at zero.
7. **Credentials never leave the process.** Not in Ticks, artifacts, logs or
   URLs. Test it.

---

## 9. Build order, hours, cut gates

Sized against 20 h/week. This **replaces** the Mode A input work and Mode B's
bespoke walkthrough, and absorbs Mode C, so it is not additive to all of
W3–W5.

| Stage | Work | h | Cut gate |
|---|---|---|---|
| S1 | `sources/` protocol + `demo` adapter + `files` adapter | 10 | — |
| S2 | Manifest: schema, inference call, approve UI, UNMEASURED rule | 8 | If behind: committed manifests only, drop inference |
| S3 | Verifier + `checkable_questions` + live flip attribution | 14 | **Non-negotiable. This is the feature.** |
| S4 | §7.1 verifier calibration vs 302 runs + Fig 4.10 | 6 | **Non-negotiable. Do it immediately after S3, not later.** |
| S5 | Router + two-step loop, shared with the W6 arm | 12 | Shared budget; not new hours |
| S6 | Conversation UI, trace panel, meter, semantic toggle | 14 | If behind: drop the toggle, keep the trace |
| S7 | `postgres` + `duckdb` + `http` adapters | 8 | **Cut first.** `demo` + `files` is a shippable product |
| S8 | §7.2 live case study | 6 | Cut second. Costs the thesis its only external validity |

S3 before S6. If the verifier does not work, the UI is a chat box and you have
spent the autumn on a chat box. Build S3 against the `demo` adapter with no
frontend at all, print Ticks to stdout, and only draw it once the attribution is
reproducing the corpus.

---

## 10. Non-goals

- Warehouse connectors you cannot test.
- Open-ended natural language over arbitrary schemas. The verifier is what makes
  this research; ungoverned questions have no ground truth and turn it back into
  a demo.
- Writes of any kind. Read-only, everywhere, enforced at the adapter.
- Beating TextQL on breadth. The differentiator is one thing: attribution.
- Multi-user, auth, deployment. A local `airs serve` is the product.

---

## 11. Acceptance criteria

1. `pip install .` then `airs serve`, no key, no config: a visitor connects the
   bundled source, approves a manifest, asks a question, and sees a verified
   answer with an attribution. Offline, $0.
2. Point at a real Postgres with a delivered table and an upstream table. Same
   flow, real lag, real attribution.
3. The verifier reproduces the published silent-failure rate and flip-partition
   split across the 302 runs (Fig 4.10).
4. A refused batch names the rule and the observed value, with no model call and
   no cost.
5. `make ci` green. Live quarantine test green. No credential appears in any
   artifact.

**The three defence moments this is built to produce:**

- The agent answers confidently. The verifier resolves. It was wrong, confidence
  1.00, and the panel says *answer key moved — your pipeline, not your model.*
- The examiner asks in what sense this is agentic. You ask a question against a
  degraded source, the gate returns REFETCH, and they watch the loop run.
- Someone asks what enforcement costs. You point at the meter, which has been
  counting forfeited correct answers the whole time, in public, without being
  asked.
