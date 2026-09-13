# Chapter 3 — Methodology

**Draft 1.** Written against the implementation as it stands; every mechanism
described here exists in the repository and is covered by the test suite
(its test suite is verified against a clean install by `make ci`). Section numbers are provisional.

---

## 3.1 Research design and rationale

This study uses a **controlled factorial experiment** in which the independent
variables are properties of a data pipeline and the dependent variables are
properties of an autonomous agent's decisions.

The design rests on a single methodological commitment, from which everything
else follows:

> **The agent is the measurement instrument, not the object of study.**

The language model, its prompt, the task, the datasets, the hardware and the
scoring procedure are held constant across every experimental condition. The
only quantities that vary are the infrastructure conditions under which data
reaches the agent. Any difference in the agent's output is therefore
attributable to the infrastructure rather than to the agent — which is what
licenses a causal reading of the results.

This distinguishes the study from the two closest pieces of prior work in a way
that matters for interpretation. Advani (2026) characterises silent failure in
LLM agents across 9,876 recorded trajectories but is **purely observational**:
conditions are never manipulated, so no causal claim about *why* agents fail
silently is available. Gupta (2026) manipulates conditions but predominantly at
the system level — timeouts, rate limits, partial responses — holding the
*content* of the data constant. This study manipulates the content and quality
of the data itself, which is the axis neither covers.

The design is quasi-experimental in one respect worth stating plainly: the
underlying data are historical (a product catalog derived from recorded search
judgments; flight records from a public archive), so the "world" the agent
reasons about is simulated rather than live. §3.11 addresses the validity
consequences.

---

## 3.2 Operational definitions

The framework rests on four measurable properties of data infrastructure. Each
is defined **operationally** — computable from runtime measurements by code,
with no subjective judgment — and each is implemented as a pure function in
`airsbench.airs.calculator`.

| Dimension | Operational definition | Implementation |
|---|---|---|
| **Freshness** | Age of a record at the moment the agent reads it: `read_timestamp − event_timestamp`, in seconds. Scored 100 while mean age ≤ 1.0 s, decaying proportionally beyond. | `freshness_score()` |
| **Latency** | End-to-end delivery time from record production to agent consumption, in milliseconds. Scored 100 while ≤ 500 ms, decaying proportionally beyond. | `latency_score()` |
| **Consistency** | Proportion of fields whose key *and* value agree between the source record and the record the agent received. | `payload_consistency()` |
| **Semantic completeness** | Proportion of required context categories — entity type, units, field descriptions, relationship links — present and non-empty at read time. | `semantic_completeness()` |

These four are not proposed as novel dimensions. They are a subset of the data
quality dimensions established by Wang & Strong (1996), selected for their
relevance to an autonomous consumer and re-expressed as executable
measurements. The contribution is the operationalisation and the measurement of
their consequences, not the taxonomy.

### 3.2.1 The composite score

The **Agentic Infrastructure Readiness Score (AIRS)** combines the four
dimension scores into a single 0–100 value by weighted sum. The weights are
**not assumed**: they are estimated by logistic regression on the benchmark
data (§3.9), and until that calibration is performed the implementation uses
equal weights explicitly marked as placeholders.

AIRS is computed **entirely from pipeline telemetry**. It requires no agent, no
task, no ground-truth labels and no model inference. This is the property that
makes it usable before an agent is deployed, and it is the functional
distinction from Gupta's (2026) reliability surface, which is measured *from*
agent executions and therefore presupposes the agent already exists.

### 3.2.2 Dimension independence

For the ranking in RQ2 and the regression in RQ4 to be interpretable, the four
dimensions must be able to move independently: a fault targeting one dimension
must not depress another, or the regression predictors become collinear and
their coefficients cannot be attributed separately.

This required an explicit design decision. Removing the semantic layer includes
replacing self-documenting field names with opaque tokens (§3.3.4), which would
otherwise register as field-level disagreement and depress the *consistency*
score as well. The injector therefore records its name-mapping in the record's
metadata, and the consistency measure reverses that mapping before comparing.
Field-name opacity is thereby attributed to the semantic dimension alone.

Independence is asserted by `tests/test_dimension_independence.py`, which
verifies for each fault type that it moves its own dimension and leaves the
other three intact. Residual collinearity is additionally reported as a
variance-inflation-factor table alongside the calibration results.

---

## 3.3 The fault injector

The fault injector is the principal software artifact developed for this study
and the mechanism by which the independent variables are manipulated. It is
implemented as a standalone Python package (`agentic_faults`) that operates as
transparent middleware between the pipeline and the agent runtime: records pass
through the injector before reaching the agent, and the injector applies
transformations parameterised by the experimental configuration.

The package depends only on the standard library, so it is installable wherever
the score is computed, and it is released independently of the benchmark.

### 3.3.1 Architecture

Each injector implements a two-method interface — `configure(**params)` and
`apply(record)` — and injectors compose through a chain-of-responsibility so
that any subset can be applied together for mixed-fault conditions. `apply()`
never mutates its input; it returns a faulted copy, which allows a baseline and
a faulted version of the same record to coexist within a single run and makes
the consistency comparison in §3.2 possible.

Every injector takes a random seed. All stochastic decisions are therefore
reproducible, and any single experimental run can be reproduced in isolation
without re-running the campaign.

The unit of manipulation is the `Record`: a payload (the raw field values), a
context block (the semantic layer), an event timestamp, a read timestamp, and a
metadata block used for instrument bookkeeping and never shown to the agent.

### 3.3.2 Why a purpose-built injector

Existing chaos-engineering tools — Chaos Mesh, Gremlin, Toxiproxy — operate at
the network and process levels. They can drop packets, delay connections and
kill processes, but they cannot remove a unit annotation from a field or
replace a field name with an opaque token. The record-level semantic
manipulation this study requires has no existing implementation, which is why
the injector is a contribution in its own right rather than a configuration of
existing tooling.

### 3.3.3 The four injectors

**FreshnessInjector** (`delay_seconds`, `distribution`). Shifts a record's
event timestamp backward so that its measured age at read time is its natural
age plus the injected delay. Supports constant delay and Poisson-distributed
delay (exponentially distributed gaps with the configured mean), the latter
modelling sporadic rather than uniform staleness. Simulates a pipeline that
updates infrequently or has a slow change-data-capture tail.

**LatencyInjector** (`spike_ms`, `spike_probability`). Introduces delay between
record production and delivery. In wall-clock mode the delay is real; in
analytic mode it is recorded without blocking, for use in tests and dry runs.
Probabilistic mode models sporadic congestion rather than constant delay.
Simulates backpressure, slow brokers and network congestion.

**SchemaDriftInjector** (`drift_probability`, `drift_types`). Alters fields
according to three drift types: *rename* (a key changes, e.g. `price` →
`price_v2`), *retype* (a numeric value becomes its string form, or a
numeric-looking string becomes a number), and *value_shift* (numeric values are
rescaled by a unit-change factor such as minutes-to-seconds, or categorical
values are relabelled through a stable substitution table modelling an upstream
code-table migration). Simulates upstream schema changes propagating without
coordination.

**SemanticStrippingInjector** (`strip_rate`, `strip_targets`,
`opaque_field_names`). Removes context categories from records at the
configured rate.

### 3.3.4 Field-name opacity

Removing the context block alone proved insufficient to remove meaning. In
initial instrument validation, stripping every context category from flight
records produced *no* accuracy degradation: field names such as `DepDelay`,
`Distance` and `Origin` are self-documenting, and the language model read the
meaning directly off the keys.

The research plan's own motivating example of missing semantics is the record
`{"id": 47291, "val": 23, "src": "A"}` — that is, a record with *opaque* keys.
The injector was therefore extended so that when the `descriptions` category is
stripped, the record's payload keys are replaced with stable opaque tokens.

This is distinct from schema drift's *rename*: drift renames a field to another
plausible name, leaving the meaning recoverable, whereas stripping replaces it
with a meaningless token, destroying it. The distinction is asserted in the
test suite. The behaviour can be disabled to measure context-block removal in
isolation.

### 3.3.5 Verification

Each injector ships with a verification routine asserting that the injected
condition equals the configured condition within tolerance. A configured 3-second
freshness delay must produce records whose measured injected age is
3 s ± 200 ms; a configured latency spike must produce a wall-clock delay within
tolerance of its setting; severity settings must produce field-alteration and
context-removal rates matching their configured probabilities within binomial
margins.

These routines are part of the test suite, which `make ci` runs against a
clean installation of the package. Their outputs are
reported in an appendix, so the claim that the manipulation was applied as
specified is evidenced rather than asserted.

---

## 3.4 Datasets and industry scenarios

Two agentic task families are studied, each instantiated in an industry context
chosen so that infrastructure faults are *behaviourally observable* rather than
merely present.

### 3.4.1 E-commerce retrieval

**Source.** The Amazon *Shopping Queries* (ESCI) dataset, filtered to
US-English records: 20,000 products with titles, brands and colours, and 1,500
customer queries with human relevance judgments. Product-relevance lists are
de-duplicated and restricted to exact-match judgments.

**Synthesised dynamics.** ESCI provides real products, queries and relevance
labels but is static. The study therefore generates the commercial dynamics —
price, stock level, and a timestamped update stream of 200,000 price and stock
mutations. Replaying the stream to any timestamp yields the catalog state at
that moment, which is what makes a *stale* view of the catalog differ from the
current one.

Two generator decisions are load-bearing and are declared as domain properties
rather than tuning parameters:

1. **Catalog velocity.** Updates are emitted at 2,000 per second across 20,000
   products, so a given product changes roughly every 10 seconds. The staleness
   levels under test (1.5 s and 5 s) must be comparable to this interval; if
   products changed once per hour, a 5-second-stale record would be identical
   to a fresh one and the freshness fault could not degrade anything by
   construction. The rate models a high-velocity dynamic-pricing catalog.
2. **Price clustering.** Products relevant to the same query are priced within a
   common band (±25% of a per-query base), reflecting that search results for
   one query are substitutes. Globally random pricing would make the cheapest
   candidate obvious and unshakeable, so no realistic price movement could flip
   the correct answer.

Both parameters, and the fact that velocity was raised once during instrument
calibration, are reported (see `research_questions_v2.md` §7).

### 3.4.2 Aviation classification

**Source.** U.S. Bureau of Transportation Statistics *On-Time Performance*
records for January–March 2024 (public domain): 30,000 flights, class-balanced
at 15,000 delayed and 15,000 on-time, across 15 carriers and 321 airports, with
no missing values in the retained fields. Features are scheduled departure and
arrival times, carrier, origin, destination, distance, day of week, month and
departure delay. The label is `ArrDel15` — arrival 15 or more minutes late.

**Staleness model.** Flights have no natural update stream, so staleness is
modelled on the one feature that genuinely accrues information as departure
approaches: the departure delay. A feature store lagging by *n* seconds is
modelled as knowing a proportionally smaller share of the final delay, decaying
linearly to zero over a ten-second knowledge horizon. This is a documented
modelling assumption and is listed among the study's limitations.

### 3.4.3 Why these scenarios

The supervisory guidance to ground the study in industry contexts is met by
instantiating the two task families in two verticals rather than by adding
verticals as an experimental factor — which would multiply the campaign without
addressing any research question. The choice is also methodologically
load-bearing: a static web-QA corpus, the original plan's retrieval dataset,
does not change over time, so a freshness fault applied to it would produce no
measurable effect and RQ1 would have no threshold to find for that fault.

---

## 3.5 Agent instrumentation

### 3.5.1 The two agents

**Retrieval agent.** Receives a customer query and a set of up to six candidate
catalog records, and must identify the cheapest product currently in stock and
report its price. The task depends on values that change (price, stock) and on
knowing which field means what — so both staleness and semantic loss are
capable of producing an objectively wrong answer.

**Classification agent.** Receives a single flight record and predicts whether
the flight will arrive 15 or more minutes late.

Both return a structured verdict, a confidence in [0, 1], and an abstention
flag.

### 3.5.2 Abstention

Both agents may **decline to answer**. This is the instrument change that makes
RQ3 measurable: an agent that is forced to commit cannot demonstrate the
difference between failing silently and correctly recognising that it lacks the
information to judge. The abstention option is offered symmetrically in both
tasks and phrased neutrally, without hinting that the data may be degraded.

### 3.5.3 Held-constant variables

The prompt is a control variable. It is byte-identical across every
experimental condition, never mentions faults, and never suggests the data may
be stale or incomplete. Only the rendered records differ between conditions —
which is precisely the mechanism by which a fault reaches the agent: the values
remain, and whatever context survived injection is rendered alongside them.

The model is held constant within each arm. Temperature is fixed at 0 for
classification and 0.2 for retrieval, seeds are recorded in each run
configuration, and the dataset, scoring procedure and hardware are constant
throughout.

### 3.5.4 Failure handling

When the model returns output that cannot be parsed, the decision is recorded
as an **agent failure**, not as an infrastructure error to be retried. Refusing,
hallucinating or emitting malformed output under degraded data are exactly the
production failure modes this study measures; retrying them would erase the
measurement. Only transport-level errors — network failures and rate limits —
are retried.

---

## 3.6 Ground truth and the asymmetry principle

Ground truth is **always the true state of the world at query time**, never the
state the agent was served. This asymmetry is the experiment.

For retrieval, the correct answer is computed by replaying the update stream to
the query timestamp and identifying the cheapest in-stock product among the
candidates *as of that moment*. The agent, under a freshness fault, is served
the catalog as of `query_time − staleness`. When a price moved or a product
sold out in that window, the agent's answer is wrong even though it reasoned
correctly over the records it was given — which is the failure mode the thesis
is about.

This required a design decision worth stating explicitly. Marking a record as
stale while serving current values would test whether the agent notices
staleness *metadata*; serving genuinely historical values tests whether
staleness changes what the agent *knows*. The latter is the phenomenon of
interest, so the loader serves historical state and the injector independently
stamps the timestamps from which the freshness dimension is computed.

The consequence is a measurable ceiling on freshness-induced degradation,
computable offline with no model calls: at the declared catalog velocity, a
severe freshness fault changes the correct answer for 14.7% of queries. No
agent, however poor, can lose more than that to staleness alone — which bounds
the effect and guards against over-attributing degradation to freshness.

**Freshness is accounted once.** The loader serves values as of
`query_time − staleness`, and the record's stamped age must equal that same
staleness or the AIRS freshness dimension would describe a condition the agent
was never in. The pipeline archetype's inherent staleness is stamped when the
record is built; the injector supplies the injected component when it runs.
Stamping the total in both places double-counts the fault — a defect that
reached the completed phase-1 runs, where severe freshness recorded an age of
10.05 s against values that were 5.05 s stale (§3.11). The two components are
now separated in `build_event_ts` and the identity is pinned by test.

---

## 3.7 Experimental design

### 3.7.1 Main factorial

| Factor | Levels |
|---|---|
| Pipeline archetype *(simulated)* | Batch · Streaming |
| Fault type | None (baseline) · Freshness · Latency · Consistency (schema drift) · Semantic completeness |
| Severity | Mild · Severe |
| Agentic task | Retrieval · Classification |

**The two pipeline archetypes are simulated, not run.** Each is represented by
its inherent-staleness signature — 3.0 s for batch, 0.05 s for streaming
(`runner/execute.py`) — applied by the loader, which serves values as they stood
that long before query time. No message broker or scheduler sits between the
loader and the agent. This is deliberate: the flip-partition analysis (§3.8.1)
shows that staleness of the served values is the only pipeline property that
reaches the agent's decision, and a live broker would add timing noise without
adding any variable the agent can respond to. The Kafka and Airflow environment
specified in the original research plan was built and is retained, unused, in
`infra_unused/`; no result depends on it. Validity consequences are discussed in
§3.11.

Severity presets: freshness 1.5 s / 5.0 s; latency 500 ms / 3000 ms; schema
drift 5% / 25% of fields; semantic stripping 30% / 80% of context.

The full factorial is 2 pipelines × 2 tasks × (1 baseline + 4 faults ×
2 severities) = 36 conditions, each replicated four times, for **144 runs**.
Every run carries a deterministic seed derived from its condition index, so any
run is independently reproducible.

**Staged execution.** The campaign runs in two phases. Phase 1 comprises the
first ~30 runs and functions as the study's go/no-go checkpoint: if fault
injection does not produce measurable degradation, the design is revised before
further runs are executed. Phase 2 completes the remaining runs. Both phases use
the same grid and the same seeds, so phase 1 is a prefix of the campaign rather
than a separate pilot — avoiding both duplicated expenditure and the
methodological awkwardness of a pilot that differs from the study.

### 3.7.2 Freshness sweep

The main factorial tests freshness at two severities. Two points cannot
distinguish monotonic from non-monotonic response — any two points look
monotonic — and Shisher & Sun (MobiHoc 2022) establish that prediction error
need not be monotonic in data age. A supplementary arm therefore tests freshness
at six severities (0.5, 1.5, 3, 5, 8 and 12 seconds) on the streaming pipeline
across both tasks with three replications: **36 runs**. The sweep spans the two
main-factorial severities so its curve can be tied back to the primary design.
Streaming only, because the batch arm's inherent staleness would confound the
low end of the sweep.

### 3.7.3 Cross-model generalisation

Comparable 2026 studies evaluate between two and eight models; a single-model
study invites the objection that the findings are an artifact of one model's
behaviour. A reduced factorial — all four faults at severe severity across both
tasks, with per-model baselines — is therefore replicated on additional models:
**18 runs** per model.

The primary arm uses a small proprietary model. A second arm uses an open-weight
model executed locally at zero marginal cost. A third uses a model from a
different provider, which additionally varies the training lineage and so
strengthens the generalisation claim beyond a within-provider comparison.

**A constraint worth reporting.** Current-generation models do not accept the
`temperature` parameter; requests specifying a non-default value are rejected.
The commitment to hold sampling parameters constant therefore **cannot be met
identically across model generations**. The cross-model arm runs each model at
its own default sampling, and this is why the study claims that the *ranking*
of infrastructure properties generalises rather than the absolute thresholds.

### 3.7.4 Architecture as a secondary contrast

The batch arm carries **three seconds** of inherent staleness by construction,
because a batch pipeline serves data assembled at its last scheduled load. This
is realistic, but it means every batch condition combines the injected fault
with baseline staleness, confounding the other three faults.

The value was calibrated, not assumed. At ten seconds it exactly equalled the
aviation task's delay-knowledge horizon, so every flight in every batch
classification run was presented as departing precisely on time: the dominant
predictive feature was zeroed, the arm scored *below* chance, and severity could
not move it because the floor had already been reached. At three seconds the
batch arm remains meaningfully stale — it flips the correct answer on 7.1% of
retrieval queries before any fault is injected — and still degrades further when
a freshness fault stacks on top, without flooring either task.

Primary fault effects are therefore reported on the streaming arm. Batch is
presented as an architecture contrast rather than a co-equal half of the design.
A real ten-minute scheduling interval would imply roughly 300 seconds of
staleness, which would floor batch accuracy in every condition and mask all
other effects; the compressed cycle keeps both architectures within measurable
range, and the limitation is stated: real batch deployments fare *worse* on
freshness than this study's batch arm.

That 7.1% is itself a finding rather than a nuisance parameter. A pipeline
nobody would describe as faulty already produces confident wrong answers on a
few percent of traffic, and the agent abstains on none of them.

### 3.7.5 The detectability arm

The main factorial compares detectability *across* fault types, which confounds
two things: the kind of corruption, and whether it is legible as corruption.
Semantic stripping differs from freshness in both respects at once, so a
difference in abstention between them cannot be attributed to legibility alone.

This arm holds the fault constant and varies only legibility. Every condition is
streaming, freshness, severe; the sole manipulation is whether the delivered
record carries a `_record_age_seconds` field:

| Condition | Record delivered | Fault | Detectable |
|---|---|---|---|
| A | `{"data": {…}, "context": {…}}` | 5 s stale | no |
| B | `{"data": {…}, "context": {…}, "_record_age_seconds": 5.05}` | 5 s stale | yes |

14 runs: 12 = 2 metadata levels × 2 tasks × 3 replications, plus one baseline
per task *with* the metadata. The baselines carry it deliberately — baselines
without it are already established by the main factorial, so the open question
is over-caution: shown an age of 0.05 s on fresh data, does the agent begin
abstaining anyway? Without that cell, a rise in abstention under B could not be
attributed to staleness rather than to the mere presence of a metadata field.

Three constraints make the manipulation clean. The age is **truthful** — it is
measured from the delivered record, so it equals the true staleness of the
values served, and condition B is not confounded with being lied to. It is
attached **after** the fault chain and stored outside the payload, so it cannot
move the AIRS consistency or semantic dimensions. And the **prompt is
unchanged**: it never mentions age, staleness or freshness in either condition.
Instructing the agent to distrust old records would measure instruction-following
rather than whether an agent can use infrastructure metadata unprompted. The
metadata is offered; its use is the agent's decision, and that decision is the
measurement.

Because A and B share `sample_seed` *and* injector seed, the two arms see
identical queries at identical simulated times under an identical fault
realisation. The comparison is therefore paired at the level of the individual
decision, and is tested with McNemar's exact test on the discordant pairs
(§3.9).

---

## 3.8 Measurement

Each run produces exactly one row in the results table, alongside a JSON
artifact containing every individual decision.

**Independent (recorded):** pipeline, fault type, severity, task, replication,
injector parameters, dataset, model, temperature, seed, query count.

**Dependent (measured):** accuracy, F1, AUC-ROC, abstention rate, silent-failure
rate, parse failures, latency percentiles, the four AIRS dimension scores and
the composite.

**Per-decision (recorded):** the input, the agent's output, ground truth,
correctness, reported confidence, abstention flag and parse status.

**Silent failure** is defined as a decision that was *committed* (not
abstained), *parseable*, and *wrong* — with no confidence threshold. A parse
failure is counted as a failure and never retried, but it is not a *silent*
failure, because unusable output is visible. No confidence threshold is applied,
for two reasons. A threshold would define the outcome partly by the agent's own
confidence, which is the signal RQ4 compares AIRS against. And a threshold's
placement is arbitrary with respect to how a model reports confidence: the
primary model reports between 0.8 and 0.9 on most classification silent
failures, so a 0.9 threshold would remove most of them while a 0.7 threshold
removes none. The rate under every threshold from 0.5 to 0.9 is reported in
`docs/silent_definition_findings.md`.

The canonical dataset is the set of structured JSON run artifacts in
`results/runs/`, committed to the repository; every reported number is derived
from them. A PostgreSQL results schema was designed for the original plan and is
retained, but nothing writes to it. Prometheus instrumentation was built for live
demonstration only and is never a source of results.

---

### 3.8.1 The flip partition

Raw accuracy under a freshness fault is near-arithmetic and must not be reported
as a result about the agent. Staleness mechanically changes the correct answer
on a measurable share of queries (§3.6), and an agent reasoning perfectly over
what it was served must be wrong on exactly those. Reporting "freshness lowers
accuracy" would therefore be measuring the answer-flip rate with an expensive
language model.

Every retrieval decision is accordingly partitioned by whether staleness moved
the correct answer for that query:

- **Answer did not flip.** Accuracy should equal baseline. Any shortfall is the
  *residual* — degradation not explained by the answer key having moved, and the
  only part attributable to the agent being impaired.
- **Answer did flip.** The agent cannot be right. The measurement is whether it
  abstains or commits confidently. This is where silent failure lives, and it is
  the reportable finding.

The partition is reconstructed exactly rather than estimated. Query sampling and
query timestamps derive from `sample_seed` alone (§3.7.1), so replaying that
seed regenerates the identical queries at the identical simulated times; flip
status is then joined to the decisions already recorded. The reconstruction is
validated against every logged ground truth before use and raises on any
disagreement, so drift between the analysis and the runner surfaces as a failure
rather than as quietly wrong numbers. It requires no re-execution and no model
calls.

The partition applies to retrieval only. The aviation label is a property of the
flight rather than of the catalog, so staleness there attenuates a feature
rather than moving the correct answer, and there is no flip to condition on.

**Consequence for the fault ranking.** Faults are ranked on residual
impairment, not on raw accuracy drop, because the raw drop mixes two
non-comparable quantities: how far a fault moves the answer key, and how much it
impairs the agent. Within retrieval the two rankings agree on order — schema
drift, then semantic stripping, then freshness — but disagree sharply on
magnitude: freshness costs 7.5 points of raw accuracy and has a residual
impairment indistinguishable from zero. A different ordering appears only when
the raw drop is pooled across both tasks, where semantic stripping ranks first
because on classification it converts corruption into abstention. Counting a
refusal as equal in cost to a confident wrong answer is precisely the conflation
this thesis argues against, so that pooled ordering is not used.

---

## 3.9 Statistical analysis

The analysis plan is specified in full in `research_questions_v2.md` §5. In
summary: changepoint detection with an explicit monotonicity test for
thresholds (RQ1); two-way ANOVA with effect sizes for the ranking (RQ2);
**decision-level logistic regression with standard errors clustered by run**
for failure modes (RQ3), declared in `research_questions_v2.md` §5 as a
substitution for the originally specified random intercept, because the only
mixed logit available is variational-Bayes and does not report the frequentist
standard errors the plan requires; logistic regression for AIRS weight
calibration with held-out validation
and a comparison against an agent-confidence baseline detector (RQ4); and rank
correlation across tasks and models for generalisation (RQ5).

The detectability arm (§3.7.5) is analysed separately and as a **paired**
design, since A and B differ by one field over identical inputs. Abstention is
compared with **McNemar's exact test** on the discordant decision pairs — the
exact form rather than the chi-square approximation, because the discordant
counts are small. Treating the arms as independent samples would discard the
pairing the design was built to obtain.

Binary outcomes are modelled at the decision level rather than as run-level
proportions, with standard errors clustered by run absorbing within-run
correlation. This uses 11,412 observations rather than 144 aggregates. The
substitution for a random intercept is harmless in practice: the run-level
intraclass correlation is negligible (ICC ≤ 0.003, design effect ≤ 1.25;
`docs/power_findings.md`).

Clustered errors are, however, anti-conservative with few clusters. A simulation
of the study's original test shows that a single-cell comparison — four runs per
group, eight clusters — rejects a true null about 12% of the time rather than 5%,
and a pooled comparison about 7.5%. Cell and pooled comparisons therefore use
CR2 standard errors with Bell–McCaffrey degrees of freedom, chosen on simulated
size before being applied to any observed cell; on the same simulated studies
their type-I error is 4.5–5.8%. At that size the minimum detectable effect is
about 10–12 percentage points for a single cell and 6 points pooled, at 80%
power. The decision-level models keep their cluster-robust logistic fits, but
each condition coefficient rests on eight or sixteen runs per group and its
empirical type-I error reaches 10%, so every p-value is also calibrated against
2,000 studies simulated under that coefficient's null. Every coefficient
reported as significant remains significant after calibration
(`docs/power_findings.md`).

All results are reported with 95% confidence intervals and effect sizes.
Negative results, unsupported hypotheses and unexpected findings are reported in
full.

---

## 3.10 Reproducibility

Every experiment runs as a single Python process with no external services: the
loader, fault injectors, agent and scorer execute in one runtime, and the only
network dependency is the model API. Reproduction therefore requires a Python
environment and the prepared datasets, not a container stack. The Compose
manifest for the originally planned Kafka/Airflow/PostgreSQL/Prometheus
environment is retained in `infra_unused/` and validates, but no experiment
uses it.

The codebase is public under an MIT licence. `make ci` verifies the artifact from
a clean environment: it creates a fresh virtual environment, installs only the
dependencies the package declares, and runs linting and the full test suite,
including the injector verification routines. The check exists because a
developer's own environment masks undeclared dependencies — it found one, the
Anthropic client library, whose absence made the cross-model arm irreproducible
from the package metadata. Every run configuration and result is written as
structured JSON.

On completion, the benchmark dataset — every run's configuration, raw agent
outputs, ground truth, infrastructure metrics and AIRS components — is published
with a citable identifier so that independent researchers can perform
alternative analyses without re-running the campaign.

Total computational cost of the full campaign is under twenty US dollars, which
makes independent replication economically trivial — itself a contribution in a
field where reproduction is often prohibited by cost.

---

## 3.11 Threats to validity

**Synthetic fault injection.** Faults are introduced deliberately rather than
observed in production. Each injector is calibrated against documented
real-world failure modes, but the conditions remain synthetic. A field study
using naturally occurring failures is recommended as future work.

**Synthetic catalog dynamics.** The e-commerce price and stock dynamics are
generated rather than observed, and their velocity determines how much staleness
*can* matter. The velocity is declared in advance, justified as a domain
property, reported alongside results, and — critically — RQ1 findings are
expressed both in absolute seconds and as a ratio of staleness to mean
inter-update interval, so the finding transfers to domains with different
velocities. One condition is replicated at a second velocity to demonstrate the
relationship scales.

**Modelled staleness for classification.** The aviation task has no natural
update stream; its staleness model is an assumption about how delay information
accrues, not an observation.

**In-distribution calibration of AIRS.** The AIRS weights and threshold are
estimated from the same distribution of synthetic faults on which they are
validated. Held-out validation guards against overfitting *within* that
distribution but cannot establish performance on naturally occurring faults.
AIRS is therefore presented as a methodology practitioners recalibrate on their
own systems, not as a set of universal coefficients.

**Limited task and model coverage.** Two task families and four models do not
exhaust the space. Long-running multi-step orchestration and multi-agent
coordination are outside scope. The cross-model arm compares primarily
small-to-mid-capability models; whether frontier-scale models resist degraded
data better is left open and is the most valuable single extension.

**Architecture confounding.** As set out in §3.7.4, the batch arm's inherent
staleness confounds the other three faults, which is why primary effects are
reported on the streaming arm.

**Single execution environment.** All runs execute as the same Python process
on one development machine, calling hosted models over their APIs and local
models through Ollama; generalisation to other hardware classes is not
investigated. Hosted-model behaviour may also change on the provider's side
without notice, which no local control can prevent.

**A reconciled construct definition, disclosed.** Until September 2026 the
thesis carried two definitions of silent failure under one name. The
methodology and the per-run metric applied a confidence threshold of 0.7; the
analysis modules that produce every reported silent-failure result applied none.
The methodology also stated that the threshold's sensitivity had been checked
across 0.5–0.9, and no such check existed. The definition is now threshold-free
throughout, the check has been implemented, and the two are held in agreement
by a test. For the primary model the definitions coincide in every arm, so no
primary result changed; on the cross-model arm a 0.7 threshold would lower
silent-failure rates by at most 2.2 percentage points. The check also shows why
no threshold is defensible: raising it from 0.7 to 0.9 would erase most
classification silent failures, because the primary model habitually reports a
confidence between 0.8 and 0.9.

**A corrected instrument defect, disclosed.** The freshness accounting
double-counted the injected delay during phase 1 and the first 30 runs of phase
2 (§3.6): the record's age was stamped with the total staleness before the
injector then subtracted the injected component a second time. Sixteen runs —
the freshness conditions among the first 66 — recorded an AIRS freshness
dimension computed from twice the injected delay.

The scope of the error is bounded and verifiable. Records carry no timestamp
unless the detectability arm attaches one, so no agent in any affected run was
shown an age, and the served values were stale by the intended amount
throughout. Every behavioural measure — accuracy, abstention, silent failure,
confidence, and each logged decision — is therefore unaffected, as is the flip
partition, which derives from the loader's staleness rather than the stamp. The
50 runs without a freshness injector are unaffected outright, which the
artifacts corroborate: they recorded exactly the values the corrected code
produces.

What is affected is the AIRS freshness dimension on those sixteen runs, and
anything downstream of it. The corrected value is a deterministic function of
the run configuration, so it is recomputed in the analysis layer rather than by
re-executing the runs; the run artifacts are retained unmodified as records of
what the instrument actually emitted, and the correction is applied in code
where it is auditable. The identity `stamped age = served staleness` is now
pinned by test in every condition, end to end.

**Public benchmark datasets.** Both datasets reflect their original collection
contexts. Generalisation to proprietary enterprise data is a matter for
practitioner evaluation, which the open-source tooling is designed to enable.
