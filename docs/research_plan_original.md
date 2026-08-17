> **Archival document.** The research plan as submitted in May 2026, reproduced
> unchanged. It is the origin of the project and is kept for the record — several
> of its commitments were revised once the experiments actually ran.
>
> **Where it has been superseded:**
> - Research questions and hypotheses → [`research_questions_v2.md`](research_questions_v2.md)
> - Methodology as implemented → [`chapter3_methodology.md`](chapter3_methodology.md)
> - The planned "120+ experiments" became **302 runs** across 4 models
> - The demo was rebuilt from Streamlit to React/Next.js
> - Latency was expected to matter; it measured a null on every analysis
>
> Original file: [`research_plan_original.docx`](research_plan_original.docx)

---

Master's Thesis Research Plan

Characterizing the Data Infrastructure Gap for Agentic AI Systems

A Five-Month Empirical Study of Freshness, Latency, Consistency and Semantic Completeness

Shamsiddin Khamidov

M.Sc. Software Engineering — Data Engineering & AI

Course: Methodology of Scientific Research in Computer Sciences & Academic Writing

May 2026


## Executive Summary

Agentic AI systems — software agents that retrieve data, make decisions, and act autonomously — are being deployed at unprecedented scale in 2026. Yet most fail in production. The dominant cause is not the model: it is the data infrastructure feeding the model. Pipelines built for human dashboards cannot satisfy the latency, freshness, consistency, and semantic richness that an autonomous agent demands.

This thesis contributes a formal characterization of that gap. Through 120+ controlled benchmark experiments, it derives empirical thresholds at which agent decision quality degrades, identifies which infrastructure property has the greatest effect on agent accuracy, validates a composite scoring framework called the Agentic Infrastructure Readiness Score (AIRS), and delivers an open-source interactive demonstration tool that visualizes agent behavior under controlled infrastructure conditions.

The contribution is not a comparison of pipeline architectures — that comparison is well documented in existing literature. The contribution is the empirical characterization: the specific values, thresholds, and weightings at which agentic AI systems experience accuracy degradation, together with a measurable framework engineers can use to assess infrastructure readiness prior to deployment.


| Framing of the study The pipeline architectures (batch and streaming) function as the experimental vehicle in this study, not as its subject. The subject is the behavior of agentic AI systems under varying infrastructure conditions: at what thresholds accuracy degrades, which conditions produce the largest effect, and whether degradation can be predicted before it manifests in agent output. |
|---|


## Chapter 1 — The Problem We Are Studying


### 1.1 Context and motivation

Recent industry forecasts (Gartner, 2025) indicate that approximately 40% of enterprise applications will embed AI agents by mid-2026, while parallel studies (MIT Project NANDA, 2025) report that a substantial proportion of generative AI deployments fail to produce measurable returns. Multiple industry analyses converge on a common root cause: limitations in the supporting data infrastructure rather than in the AI model itself (Precisely, 2026; World Economic Forum, 2025).

The mismatch is structural. Data pipelines developed over the past two decades have been optimized for human analytical consumption — periodic batch ingestion, scheduled transformation, and dashboard delivery (Kleppmann, 2017). The implicit consumer contract assumes that occasional latency, missing context, or inconsistency can be compensated by human interpretation or by deferring a decision.

Agentic AI systems operate under a different contract. They are autonomous decision-makers that consume data, reason over it, and act without human intermediation. They cannot defer decisions, request clarification, or interpret missing context. When the data they consume is stale, inconsistent, missing semantic context, or delayed, an agent typically produces a confident but incorrect output (Sculley et al., 2015; Amershi et al., 2019). This failure pattern is observable in deployed systems but is, in the present author's review of the literature, not yet the subject of a peer-reviewed framework for formal measurement.


### 1.2 The current state of the literature

A focused review of recent literature identifies three structural reasons for the limited academic treatment of this problem.

- Disciplinary boundary. Machine learning research has historically focused on model architectures and training procedures; data engineering research has focused on system performance under analytical workloads (Zaharia et al., 2016; Sculley et al., 2015). The interface between agentic AI consumption patterns and data infrastructure design sits between these two research communities and has received limited dedicated treatment.
- Recency of production agentic deployments. Widespread production use of agentic AI is a 2024–2026 development. Empirical evidence of its failure modes is therefore recent, and the formalization process in peer-reviewed venues is still in progress.
- Tool maturity in isolation. Individual components such as LangChain (Chase, 2022), Apache Kafka (Kreps et al., 2011), Apache Airflow, and vector databases are mature in their respective domains. Their interaction under sustained agentic workloads has, to the present author's knowledge, not been systematically benchmarked in peer-reviewed literature.

### 1.3 The research gap, stated formally


| Research gap addressed by this thesis Based on the present author's review of the literature, the data infrastructure requirements of agentic AI systems have not yet been the subject of a peer-reviewed measurement framework. Engineers deploying such systems therefore rely primarily on vendor guidance, industry white papers, and post-deployment failure analysis. This study contributes a measurement framework with empirical thresholds and a predictive readiness score derived from controlled experimentation. |
|---|


## Chapter 2 — Why This Research Matters


### 2.1 Anticipated outcomes

Successful completion of this research enables three outcomes that are difficult to achieve with current tools and literature.

First, engineers planning to deploy agentic AI systems can compute a measurable score — the AIRS — that estimates whether their current infrastructure is suited to the workload. At present, this estimate is typically made on the basis of intuition, vendor recommendation, or post-deployment incident analysis. The thesis contributes a quantitative alternative.

Second, infrastructure investment decisions can be supported by empirical evidence. When data teams must allocate effort across freshness, consistency, latency, or semantic enrichment, this study provides ranked, statistically supported guidance on the relative effect of each property on agent decision quality.

Third, the study contributes a reproducible benchmark — datasets, fault conditions, and scoring methodology — that subsequent researchers can use to compare findings across studies. Reproducible benchmarks are a recognized prerequisite for the maturation of empirical fields (Sculley et al., 2015).


### 2.2 Who benefits


| Audience | What they get |
|---|---|
| Data engineers | A measurable score (AIRS) and an open tool to test their own pipelines before deploying agents on top. |
| AI researchers | An empirical foundation for studying agentic AI failure modes rooted in infrastructure, not models. |
| Engineering leaders | Quantitative evidence supporting architecture decisions and infrastructure budget allocation. |
| Future students | A reproducible benchmark and open dataset to build follow-up work on. |
| Standards bodies | Empirical thresholds that can inform future data quality standards for AI systems. |

Table 2.1 — Audiences and the concrete value the research delivers to each.


### 2.3 Scope boundaries

Clear delineation of scope is essential to maintaining rigor under the constraints of a master's thesis timeline. The following boundaries are deliberate:

- The study does not claim that streaming pipelines are superior to batch pipelines in general. Such comparisons are widely documented in industry and academic literature. Pipeline architecture functions as a controlled experimental variable, not as the primary research question.
- The study does not propose improvements to AI model architectures. The agent model is held constant across all experimental conditions; observed differences in performance are attributable to infrastructure conditions, not to model capability.
- The study covers two representative agentic task families: retrieval and classification. Long-running multi-step orchestration and multi-agent coordination are acknowledged as relevant but lie outside the scope of this thesis and are noted for future work.
- The demonstration tool is a research artifact. It is engineered for reproducibility and pedagogical clarity, not for production deployment.

## Chapter 3 — What We Are Actually Studying


### 3.1 The four dimensions of agentic infrastructure (AIRS)

The framework rests on four measurable properties of data infrastructure. Each is operationally defined — meaning each can be computed from runtime measurements without subjective judgment.


| Dimension | Operational definition | Why agents need it |
|---|---|---|
| Freshness | Maximum age, in milliseconds, of any data record at the moment the agent reads it. Computed as (read_timestamp − record_event_timestamp). | Stale data leads to decisions based on a world that no longer exists. |
| Latency | End-to-end pipeline time, in milliseconds, from data event to agent consumption. | Slow data means agents miss the window in which their decision is useful. |
| Consistency | Percentage of records that match across pipeline stages (source vs. sink) within a synchronization window. | Inconsistency causes agents to reason on contradictory facts and produce unstable behavior. |
| Semantic completeness | Percentage of required context fields (entity type, units, field definitions, relationships) present and non-null at read time. | Without meaning, agents either hallucinate interpretations or fail silently. |

Table 3.1 — The four AIRS dimensions, defined operationally so they can be measured by code, not judgment.


### 3.2 The semantic layer — the underappreciated dimension

Of the four dimensions, semantic completeness is the one most often overlooked by engineering teams and the least studied in academic literature. It deserves explicit treatment because this thesis argues — and intends to demonstrate empirically — that it is one of the most damaging infrastructure failures for agentic AI systems.


#### What it is

A semantic layer is the tier of a data system that adds meaning to raw data: entity definitions, field semantics, units of measurement, valid value ranges, and relationships between entities. In traditional analytics, a human reading a dashboard supplies this meaning from context ("oh, the column 'delay_min' is delay in minutes"). An autonomous agent has no such context. It receives bytes, and must decide what they mean.


#### Why it matters specifically for agents

When a row arrives as {"id": 47291, "val": 23, "src": "A"}, a dashboard user knows from the title of the dashboard and the column header that this is flight delay in minutes for American Airlines flight 47291. An LLM-based agent does not have a dashboard title. It either guesses (often wrongly), refuses to act, or fabricates an interpretation. All three failure modes are common in production agentic systems and all three are invisible until the agent's output is audited.


#### How it is known in literature

The concept appears under several names: semantic layer (Cube, dbt, AtScale), data contracts (Jones, 2023), knowledge graphs (Hogan et al., 2021), and semantic data products in the data mesh literature (Dehghani, 2022). All address the same underlying problem: separating meaning from bytes. This thesis treats them as variations of a single dimension — semantic completeness — and measures the impact of its absence on agent decision quality.


| Anticipated contribution of measuring semantic completeness The working hypothesis is that semantic completeness has a comparable or larger effect on agent accuracy than freshness or latency at equivalent severity levels. If the experimental data supports this hypothesis, the finding offers an empirical counterweight to the prevailing emphasis on real-time pipeline design. If the data does not support it, the measurement itself remains a contribution to the literature. |
|---|


### 3.3 The five research questions

Restated from the proposal, the five concrete questions the experimental campaign addresses:

RQ1 — Threshold identification

For each of the four fault types, at what severity does agent accuracy drop by more than 10% relative to baseline? Output: four empirically derived threshold values with 95% confidence intervals.

RQ2 — Relative impact of infrastructure properties

Among freshness, latency, consistency, and semantic completeness, which property produces the largest accuracy degradation at equivalent severity? Output: a ranked ordering with effect sizes.

RQ3 — Task-dependent resilience

Do retrieval-based and classification-based agentic tasks exhibit the same degradation thresholds, or do they differ in resilience to specific fault types? Output: task-specific thresholds with statistical comparison.

RQ4 — Predictive validity of AIRS

Given the four measured dimensions, can a composite score reliably predict agent decision failure with a useful warning interval? Output: a calibrated AIRS formula with reported precision, recall, and warning-time distribution.

RQ5 — Boundary conditions of streaming architectures

Under which experimental conditions does the streaming pipeline lose its accuracy advantage over batch with strong validation? Output: empirical boundary conditions with effect sizes.


## Chapter 4 — How We Will Study It


### 4.1 The measurement principle

The agent is not the subject of study. The agent is the measurement instrument. Like a thermometer, it produces a reading — in this case, an accuracy score — that reflects the condition of what it is measuring. What is being measured is the data infrastructure underneath.

This framing is essential because it makes the experiment rigorous. The agent code, model, prompt, and dataset are held constant across all runs. The only variables that change are the infrastructure conditions. Any difference in the agent's output is therefore caused by the infrastructure — not by the agent.


### 4.2 The experimental loop, step by step

Every benchmark run follows the same six steps.

Step 1 — Load data into the pipeline.

A subset of a public benchmark dataset (MS MARCO for retrieval, Airline On-Time for classification) is loaded into the configured pipeline (Kafka for streaming, Airflow for batch). Each record carries ground-truth labels — the known correct answer for each question or classification.

Step 2 — Configure infrastructure condition.

The fault injector is set to one of four conditions at one of two severity levels: freshness delay (mild = 1.5s / severe = 5s), latency spike (mild = 500ms / severe = 3000ms), schema drift (mild = 5% / severe = 25% of fields corrupted), semantic stripping (mild = 30% / severe = 80% of context fields removed).

Step 3 — Run the agent.

The same LangChain agent (powered by GPT-4o-mini) executes the task. For retrieval: receives a question, queries the pipeline for relevant passages, returns the best answer. For classification: receives flight features, predicts delay/on-time.

Step 4 — Score against ground truth.

The agent's output is compared to the labeled correct answer. AUC-ROC and F1-score are computed. End-to-end latency is recorded. Data quality metrics (the four AIRS dimensions) are computed from pipeline observations.

Step 5 — Record one row.

A single row enters the benchmark dataset: (pipeline, fault_type, severity, task, accuracy, latency, AIRS_components, AIRS_total).

Step 6 — Repeat.

The loop runs 120+ times across the full factorial design (2 pipelines × 4 fault types × 2 severities × 2 tasks × ~8 replications = 128 runs), fully automated, producing the dataset for statistical analysis.


### 4.3 The fault injector — the technical heart

The fault injector is a custom Python module sitting between the pipeline and the agent. It is the controlled variable of the experiment. Its design determines whether the study is rigorous or anecdotal. Each fault type has a precise operational implementation:


| Fault type | How it is injected | What it simulates |
|---|---|---|
| Freshness delay | Each record's timestamp is artificially advanced backward, simulating that the data is older than it appears. The agent reads it as if it were N seconds stale. | A pipeline that updates infrequently or has a slow CDC tail. |
| Latency spike | A controlled delay is added between record production and agent read, simulating network or processing bottleneck. | Backpressure under load, slow brokers, network congestion. |
| Schema drift | A configurable percentage of fields have their type, name, or value distribution altered between baseline and read. | Upstream schema changes that propagate without coordination. |
| Semantic stripping | Context fields (entity type, units, descriptions, relationships) are removed from N% of records, leaving only raw values. | Data delivered without a semantic layer — bytes without meaning. |

Table 4.1 — Each fault type has a precise implementation that mirrors a real-world failure mode.


### 4.4 Variables, controls, and sample size


| Variable type | Variable | Levels |
|---|---|---|
| Independent (controlled) | Pipeline architecture | Batch (Airflow) \| Streaming (Kafka) |
| Independent (controlled) | Fault type | Freshness \| Latency \| Consistency \| Semantic |
| Independent (controlled) | Severity | Mild \| Severe |
| Independent (controlled) | Agent task type | Retrieval \| Classification |
| Dependent (measured) | Agent decision accuracy | F1-score, AUC-ROC |
| Dependent (measured) | End-to-end latency | Milliseconds |
| Dependent (measured) | AIRS score | 0–100 composite |
| Held constant | Model, prompt, dataset, hardware | Single fixed configuration |

Table 4.2 — Variable specification for the benchmark study.

The full factorial of 2 × 4 × 2 × 2 = 32 distinct conditions is tested, each replicated ~4 times, for ~128 total experimental runs. Power analysis confirms this is sufficient to detect medium effect sizes (Cohen's d = 0.50) with statistical power above 0.80 at α = 0.05. Additional pilot runs in Month 2 may bring the total to ~150.


### 4.5 Statistical analysis plan


| Analysis | Method | Answers |
|---|---|---|
| Threshold detection per fault type | Regression discontinuity + changepoint detection (ruptures library) | RQ1 |
| Which fault causes most damage | Two-way ANOVA with interaction effects; effect size = η² and Cohen's d | RQ2 |
| Pipeline × fault comparison | One-way ANOVA across pipeline types with Tukey HSD post-hoc; non-parametric Kruskal-Wallis if normality fails | RQ3, RQ5 |
| AIRS predictive validation | Logistic regression on (freshness, latency, consistency, semantic) → failure; ROC-AUC, precision-recall, calibration curves | RQ4 |
| All comparisons | 95% confidence intervals on every reported metric; Cohen's d for all pairwise effect sizes | All |

Table 4.3 — Statistical methods mapped to research questions.


## Chapter 5 — The Five-Month Execution Plan

Each month has one primary deliverable. Writing happens continuously, not at the end. Pilot validation in Month 2 is the most important checkpoint — if the experimental setup does not produce measurable degradation under fault injection, the design must be revised before any main runs.


### Month 1 — Foundation and infrastructure

Primary deliverable: a working Docker environment with two pipelines, a fault injector v1, and a 20-paper literature review draft.


#### Week 1–2: Literature and definitions

- Read 20 papers deeply across agentic AI failures, data pipeline benchmarks, semantic data design, MLOps observability.
- Establish, through the literature review, the current state of formal academic treatment of agentic data infrastructure measurement, and articulate the research gap accordingly.
- Write operational definitions for each AIRS dimension — as code, not prose.
- Draft Chapter 1 (Introduction) and skeleton of Chapter 2 (Literature Review).

#### Week 3: Environment setup

- Single docker-compose.yml that spins up: Kafka + Airflow + Postgres + Prometheus + agent runtime.
- Verify the same environment runs on personal laptop AND on a cloud spot instance.
- Set up Git repo with MIT license, CI for tests, and structured experiment logging.

#### Week 4: Fault injector v1

- Python module with four parameterized functions, one per fault type.
- Unit tests for each: assert that injecting a 3s freshness delay produces records whose age, when read, is 3s ± 200ms.
- Validate against three documented real-world failures from literature so injected faults reflect reality.

### Month 2 — Agent setup and pilot validation

Primary deliverable: 30-run pilot study with measurable accuracy degradation, plus updated methodology.


#### Week 1: Agent and tasks

- LangChain agent wrapping GPT-4o-mini, with two task variants: Retrieval QA on MS MARCO, Classification on Airline On-Time.
- Baseline accuracy measured for both tasks with no faults — establishes the ceiling against which degradation is measured.
- Ground-truth scoring pipeline: AUC-ROC and F1 computed automatically from agent output.

#### Week 2: Pilot — 30 runs

- Run baseline + one fault type at one severity for both tasks on both pipelines.
- Check: does agent accuracy actually drop measurably? Are metrics collecting correctly?
- If yes — proceed to main study. If no — redesign before more runs.

#### Week 3–4: Refinement and writing

- Refine fault injector and metrics based on pilot results.
- Complete Chapter 2 (Literature Review) and Chapter 3 (Methodology) drafts — much of Chapter 3 reuses the proposal text.
- Send a draft to supervisor for early feedback.

### Month 3 — Main benchmark and statistical analysis

Primary deliverable: ~128 completed runs, raw results database, and statistical findings for all five research questions.


#### Week 1–2: 128 automated runs

- Run overnight on cloud spot instances; full factorial design.
- Approximate compute budget: $30–50 across the campaign.
- Every run logs: configuration, raw agent output, ground truth, all four AIRS components, end-to-end latency.

#### Week 3: Statistical analysis

- Run all five analyses from Table 4.3 in a Jupyter notebook with reproducible seeds.
- Report all results with 95% confidence intervals and effect sizes.
- Generate publication-quality plots: threshold curves, fault-type ranking, task-by-task degradation profiles.

#### Week 4: Identify headline findings

- Write down the three numbers that go on page 1 of the thesis.
- Example shape: "Agent accuracy drops 31% when freshness exceeds 4.2s", "Semantic stripping is 2.7× more damaging than equivalent freshness delays", "AIRS score < 62 predicts agent failure with 84% precision".

### Month 4 — AIRS calibration and demo tool

Primary deliverable: calibrated AIRS formula validated on held-out data, plus working Streamlit demonstration tool.


#### Week 1: Calibrate the AIRS formula

- Logistic regression on benchmark data: agent_failure = f(freshness, latency, consistency, semantic).
- Derived coefficients become the published AIRS weights — these are not assumed, they are data-derived.
- Validate on a held-out 20% of runs; report precision, recall, AUC, and warning-time distribution.

#### Week 2–3: Build the Streamlit demonstration tool

- Streamlit app (NOT React + FastAPI) to fit timeline — single file, deployable in one command.
- Live sliders for each fault parameter; live radar chart of the four AIRS dimensions.
- Agent decision timeline showing correct vs. incorrect outputs in real time.
- Architecture comparator: same task, batch vs. streaming side by side.

#### Week 4: Polish and open-source release

- README with one-command setup, sample runs, and screenshots.
- Open-source release on GitHub under MIT; publish benchmark dataset to HuggingFace and Zenodo.
- Demo recording as backup video for defense day.

### Month 5 — Writing, revision, defense

Primary deliverable: finished thesis, defense rehearsal, working live demo.


#### Week 1–2: Results and discussion chapters

- Chapter 4 (Results) — present all five findings with figures and statistical tables.
- Chapter 5 (Discussion) — interpret findings, address limitations, propose future work.
- Chapter 6 (Conclusion) — summarize contributions and practical implications.

#### Week 3: Supervisor revision cycle

- Submit full draft 2 weeks before deadline.
- Expect one round of substantive revisions.
- This week is reserved exclusively for revisions — not new work.

#### Week 4: Defense preparation

- Twenty-minute presentation centered on the live demo.
- Demo crash plan: backup video, screenshot fallback, narrated walkthrough.
- Rehearse with peers; prepare for likely Q&A topics.

| Scope adjustments from the original proposal The experimental campaign is reduced from 360 to approximately 128 runs; statistical power remains above 0.80 for medium effect sizes. The task families are reduced from four to two (retrieval and classification), covering common agentic workloads. Pipeline types are reduced from three to two; the batch-versus-streaming contrast captures the principal architectural dimension while micro-batch is retained for future work. The demonstration tool is implemented in Streamlit rather than React + FastAPI, preserving demonstration capability within the available engineering budget. The expert validation panel is treated as optional and is contingent on the availability of suitable participants; if not feasible, it is noted as future work. |
|---|


## Chapter 6 — Technology Stack and Justification

The technical choices in this study are not arbitrary. Each tool selection is made with reference to three criteria: (1) representativeness of the component in current industry practice, so that findings generalize beyond the research setting; (2) openness and reproducibility, so that the experimental setup can be replicated by independent researchers; and (3) compatibility with the five-month timeline. This chapter documents the full technology stack across seven functional layers and provides the rationale for each component.


### 6.1 Stack overview

The complete technology stack is organized into seven layers, each addressing a distinct functional concern in the experimental architecture. The layers are coordinated through Docker Compose to ensure environment parity across local development, cloud execution, and reproducibility by independent researchers.


| Layer | Concern | Selected technology |
|---|---|---|
| 1. Streaming pipeline | Event-driven data delivery to the agent | Apache Kafka 3.x |
| 2. Batch pipeline | Scheduled batch data delivery | Apache Airflow 2.x |
| 3. Storage | Persistent state for benchmark records | PostgreSQL 16 + Parquet on local FS |
| 4. Agent runtime | Multi-step agentic workflow execution | LangChain + LangGraph |
| 5. Language model | Decision-making component within the agent | OpenAI GPT-4o-mini (primary), Llama 3 8B (backup) |
| 6. Fault injection | Controlled introduction of infrastructure failures | Custom Python module (study contribution) |
| 7. Observability | Metric collection and AIRS computation | Prometheus + Great Expectations + custom AIRS calculator |
| 8. Analysis | Statistical processing of benchmark results | Python (SciPy, Pingouin, scikit-learn, ruptures) |
| 9. Demonstration tool | Interactive defense-day presentation | Streamlit + Plotly |
| 10. Environment | Reproducibility across machines | Docker + Docker Compose |

Table 6.1 — Complete technology stack across functional layers.


### 6.2 Data pipeline layer


#### Apache Kafka (streaming pipeline)

Apache Kafka 3.x is selected as the streaming pipeline component because it is the dominant event-streaming platform in production deployments of agentic systems, with broad adoption in retrieval-augmented generation architectures and real-time machine learning serving (Kreps, Narkhede, & Rao, 2011). Its publish-subscribe semantics, durable log storage, and configurable retention windows make it well-suited to representing the streaming archetype in this study.

For the experimental setup, a single-broker Kafka cluster is configured inside Docker with two topics: one carrying baseline (uncorrupted) records and one carrying fault-injected records. Consumer offsets are committed automatically. Latency is measured between record production and consumer commit, providing the end-to-end latency metric used in the AIRS computation.


#### Apache Airflow (batch pipeline)

Apache Airflow 2.x is selected as the batch pipeline component because it is widely adopted for ETL orchestration in enterprise data platforms and remains a common substrate for analytical workloads that have not yet been migrated to streaming architectures. Its directed-acyclic-graph model of scheduled tasks provides a faithful representation of the batch archetype against which the streaming pipeline is compared.

The Airflow deployment in this study runs a parameterizable DAG that loads dataset records into PostgreSQL on a configurable schedule (default: 10-minute intervals). Freshness is measured as the time elapsed between record event time and the agent's read time at the consumer end.


#### Justification for selecting two pipeline types rather than three

The proposal originally specified a third architecture (micro-batch processing via Apache Flink). The revised plan reduces the architectural axis to two pipelines for two reasons: (a) the principal contrast in pipeline design that is relevant to agentic workloads is between scheduled batch and continuous streaming; (b) within the five-month timeline, the additional configuration, validation, and benchmarking effort required for a third pipeline does not yield proportional research value. Micro-batch processing is noted as future work.


### 6.3 Agent runtime layer


#### LangChain and LangGraph

LangChain (Chase, 2022) is the most widely adopted framework for constructing multi-step agentic workflows in 2026, and its companion library LangGraph provides stateful graph-based agent orchestration. The combination is selected because it: (a) supports the construction of both retrieval-based and classification-based agents with a unified interface; (b) provides instrumented tool-calling primitives that facilitate measurement of agent decisions; (c) is open-source under MIT license, supporting reproducibility; and (d) is representative of the framework that practitioners will use when applying the study's findings.

Within the experimental setup, two agent configurations are constructed:

- Retrieval agent. A LangGraph workflow with three nodes: question reception, passage retrieval from the pipeline, and answer composition. The agent calls a retrieval tool that issues a query against the configured pipeline (Kafka or Airflow) and returns the top-ranked passage. The answer is then scored against the MS MARCO ground-truth label.
- Classification agent. A LangGraph workflow that receives flight features from the pipeline, applies feature reasoning, and outputs a binary classification (delayed / on-time). The decision is scored against the Airline On-Time ground truth.

#### Language model: GPT-4o-mini (primary) and Llama 3 8B (backup)

GPT-4o-mini is selected as the primary language model for three reasons: it is the most cost-efficient model in the GPT-4 family at the time of writing (approximately $0.15 per million input tokens, $0.60 per million output tokens), making the experimental campaign feasible within the project budget; it offers latency characteristics representative of production agentic deployments; and it is widely used by practitioners, supporting external validity.

Llama 3 8B is configured as a local backup model accessed through Ollama. It serves three purposes: continuity of experimentation in the event of API rate limits or outages; verification that observed findings are not artifacts of a single proprietary model; and supplementary runs at zero marginal cost on local hardware. A subset of approximately 20% of total runs is reserved for cross-model verification with Llama 3.


#### Constancy of the model across conditions

A critical methodological commitment is that the language model is held constant across all benchmark runs. Variations in agent output are therefore attributable to infrastructure conditions, not to model variation. Model temperature is fixed at 0 for classification tasks and 0.2 for retrieval, with random seeds documented in the run configuration to support reproducibility.


### 6.4 Fault injector — the technical core of the study

The fault injector is the principal piece of software developed during this study and warrants extended treatment. It is implemented as a standalone Python package that operates as a transparent middleware between the pipeline layer and the agent runtime. Records flow through the injector before reaching the agent, and the injector applies controlled transformations parameterized by the experimental configuration.


#### Architecture

The fault injector is implemented as a chain-of-responsibility pattern in which four independent injectors can be composed in any combination. Each injector is a Python class implementing a common interface with two methods: configure(parameters) and apply(record). The injector module is packaged as agentic_faults and installed as a dependency of both pipelines.


| Injector module | Parameters | Implementation approach |
|---|---|---|
| FreshnessInjector | delay_seconds (float), distribution (constant / poisson) | Overrides the record's effective read timestamp; the injector holds a configurable number of records in an internal buffer and releases them after the specified delay. Includes a verification mode that asserts injected age equals configured age within ±200ms. |
| LatencyInjector | spike_ms (int), spike_probability (float) | Introduces network-equivalent delay between record production and consumer delivery using asyncio.sleep(). Optional probabilistic mode simulates sporadic congestion rather than constant delay. |
| SchemaDriftInjector | drift_probability (float), drift_types (list) | Selectively renames, retypes, or alters field values according to a configurable distribution. Drift types include rename (field key changed), retype (string becomes int), and value_shift (categorical relabeling). |
| SemanticStrippingInjector | strip_rate (float), strip_targets (list) | Removes selected context fields from records: entity type, unit annotations, field descriptions, and relationship links. Default strip_targets covers all four context categories at the configured rate. |

Table 6.2 — Fault injector implementation specification.


#### Validation against documented failure modes

Each injector is validated against three documented real-world failure cases drawn from industry incident reports and literature. For example, the FreshnessInjector is calibrated to reproduce the staleness characteristics described in the Precisely (2026) data integrity report; the SchemaDriftInjector is validated against the schema-evolution failure patterns documented by Sculley et al. (2015). Validation results are reported in the thesis methodology chapter and included as a reviewer-facing appendix.


#### Why a custom implementation

Existing chaos-engineering tools (Chaos Mesh, Gremlin, Toxiproxy) operate primarily at the network and process levels. They do not provide the record-level semantic manipulation required to study semantic completeness and schema-drift effects on agentic AI workloads. A purpose-built injector is therefore necessary. The injector is released as open-source software (MIT license) and constitutes one of the secondary contributions of the thesis.


### 6.5 Observability and AIRS computation layer


#### Prometheus for pipeline metrics

Prometheus is selected for runtime metric collection because it is the de facto standard observability tool in modern data platforms, exposes a well-documented query language (PromQL), and integrates natively with the Python ecosystem through prometheus_client. Custom counters and histograms are instrumented at every stage of the pipeline (record production, fault injection, agent read, agent decision) to provide the raw measurements required for AIRS computation.


#### Great Expectations for data quality assertions

Great Expectations is used to define and validate the four AIRS dimensions in a declarative, reproducible form. Each dimension is expressed as an expectation suite: freshness expectations check record age distributions, consistency expectations verify cross-source field agreement, and completeness expectations enforce required field presence. Expectation results feed directly into the AIRS calculator.


#### Custom AIRS calculator

The AIRS calculator is a Python module that ingests Prometheus metrics and Great Expectations results, computes the four dimension scores, and combines them into a composite 0–100 score. The composition formula uses weights derived from the logistic regression analysis in Month 4 — the weights are not assumed but estimated from experimental data. The calculator is released as part of the open-source AIST distribution and is the primary applied artifact of the thesis.


### 6.6 Statistical analysis stack

All statistical analyses are performed in Python within a Jupyter notebook environment, supporting both interactive exploration during analysis and reproducible execution for the final report. The following libraries are used:


| Library | Purpose | Used for |
|---|---|---|
| SciPy | Foundational statistical functions | ANOVA, t-tests, normality tests (Shapiro-Wilk) |
| Pingouin | Higher-level statistical tests with effect sizes | Two-way ANOVA with η², post-hoc Tukey HSD |
| scikit-learn | Machine learning and model validation | Logistic regression for AIRS calibration; ROC-AUC, precision-recall curves |
| ruptures | Changepoint detection (Tibshirani et al., 2012) | Identifying threshold values for RQ1 across continuous fault parameters |
| pandas | Data manipulation and aggregation | Benchmark result preparation and exploratory analysis |
| NumPy | Numerical computation | All numeric operations underlying the above |
| Matplotlib + Seaborn | Publication-quality plots | Threshold curves, fault-type degradation profiles, AIRS calibration curves |

Table 6.3 — Statistical analysis libraries and their roles.


### 6.7 Demonstration tool stack


#### Streamlit

Streamlit is selected for the AIST demonstration tool because it offers an efficient path from experimental Python code to an interactive web interface. The framework's reactive execution model maps naturally to the live-update pattern required by the demonstration: parameter changes trigger reruns of relevant components without manual state management. Streamlit's wide adoption in scientific demonstration contexts also reduces friction for follow-up researchers.


#### Plotly for interactive charts

Plotly is used for the live radar chart of AIRS dimensions and for the agent decision timeline. Its support for interactive hover, zoom, and animated updates exceeds what Matplotlib provides for live demonstration contexts. Plotly figures are constructed dynamically from the Prometheus metrics stream and refresh every two seconds during demonstration.


#### Why not React + FastAPI

The original proposal specified a React frontend with a FastAPI backend. Within the five-month constraint, this introduces substantial additional engineering effort — state management, API design, frontend build tooling, deployment configuration — without commensurate research value. Streamlit provides the same interactive demonstration capabilities through a single Python file deployable via Docker Compose. The engineering effort saved is allocated to the experimental campaign, statistical analysis, and writing. A migration to React + FastAPI is a viable post-thesis activity if the demonstration is to be developed into a polished portfolio artifact or distributed product.


### 6.8 Environment and reproducibility layer


#### Docker and Docker Compose

All components are containerized and orchestrated through a single docker-compose.yml manifest. This design choice ensures three properties: (a) environmental parity between local development on the researcher's laptop and remote execution on cloud spot instances; (b) elimination of "works on my machine" failures that would impede reproducibility by independent researchers; (c) one-command setup for both the experimental campaign and the demonstration tool. The compose file defines services for Kafka, Airflow, PostgreSQL, Prometheus, the agent runtime, the fault injector, and the Streamlit application.


#### Version control and continuous integration

The full codebase is maintained in a public Git repository under the MIT license. Each commit is automatically validated through GitHub Actions: unit tests on the fault injector, integration tests that verify the full pipeline executes end-to-end on a sample dataset, and Docker build verification. Experimental run configurations and results are stored as structured JSON and committed to a separate data branch for full provenance.


#### Open dataset release

The complete benchmark dataset (all 128+ run outputs, including raw agent responses, ground-truth labels, infrastructure metrics, and AIRS components) is released on HuggingFace Datasets and archived on Zenodo with a citable DOI. This release enables follow-up researchers to perform alternative analyses on the same underlying data without rerunning the experimental campaign.


### 6.9 Public datasets used in the study


| Dataset | Source | Used for | License |
|---|---|---|---|
| MS MARCO v2 (subset) | HuggingFace Datasets | Retrieval QA agentic task; ground-truth passage labels for accuracy scoring | Microsoft Research License (research use) |
| Airline On-Time Performance | U.S. Bureau of Transportation Statistics | Classification agentic task; binary delay/on-time labels | Public domain |
| Optional: BEIR Benchmark Suite | HuggingFace Datasets | Cross-domain retrieval verification (subset, contingent on schedule) | Apache 2.0 / dataset-specific |

Table 6.4 — Public datasets used in the experimental campaign.


### 6.10 Summary of technology choices

Three principles govern the technology selection in this study: representativeness of current industry practice (Kafka, Airflow, LangChain, GPT-4o-mini), openness for reproducibility (all components are open-source or use research-licensed datasets), and feasibility within a five-month timeline (Streamlit rather than React + FastAPI; two pipelines rather than three; cloud spot instances for the benchmark campaign). The complete stack is reproducible by an independent researcher through a single docker-compose up command after cloning the public repository.


## Chapter 7 — The Demonstration Tool


### 7.1 Role of the demonstration in the thesis

The thesis concludes with an interactive demonstration in addition to a written report. The rationale is methodological: the central empirical claims of the research describe how agentic AI behavior varies as a function of infrastructure conditions. A live, interactive demonstration enables the defense panel to observe these claims under direct manipulation of the experimental variables.

The Agentic Infrastructure Stress Tester (AIST) is the artifact through which this demonstration is conducted. It serves three roles: an interactive experimental instrument, a pedagogical tool that makes findings reproducible by independent observers, and an open-source contribution that practitioners can deploy on their own pipelines.


### 7.2 What the demonstration shows on screen

The interface is a single Streamlit page divided into four regions, each chosen to align directly with a research question.


| Region | What it does | Which RQ it serves |
|---|---|---|
| Fault control panel | Sliders for each of the four fault parameters: freshness delay (0–10s), latency spike (0–5000ms), schema drift (0–50%), semantic stripping (0–100%). Severity level can be set per fault type independently. | RQ1, RQ2 |
| Live AIRS radar | Four-axis radar chart updating every two seconds. Each axis shows the current value of one AIRS dimension. The composite AIRS score is displayed prominently as a single number with color-coded threshold zones (green > 80, amber 60–80, red < 60). | RQ4 |
| Agent decision timeline | Scrolling event log showing each agent decision with its input, output, ground truth, and correctness indicator. Incorrect decisions are flagged in red with the AIRS score at the moment of failure. | RQ1, RQ4 |
| Architecture comparator | Side-by-side panels: identical task running on batch pipeline and streaming pipeline simultaneously, with their accuracy curves overlaid. The viewer can see the architectural difference in real time, including the conditions where streaming loses its advantage. | RQ3, RQ5 |

Table 7.1 — Demonstration regions mapped to research questions.


### 7.3 Demonstration narrative aligned to research questions

The demonstration is structured as a sequence of acts, each aligned to one or more research questions. The structure ensures that the panel encounters the experimental evidence in the same order as the thesis presents it.

Act 1 — Baseline establishment

All fault parameters are set to zero. The agent operates at baseline accuracy with an AIRS score above 95. This establishes the reference condition against which subsequent degradation is compared.

Act 2 — Freshness threshold (RQ1)

The freshness delay parameter is gradually increased. Accuracy remains stable until the empirically derived threshold is reached, after which a measurable decline occurs. The threshold value is annotated on the display with the corresponding confidence interval reported in the thesis.

Act 3 — Comparison with semantic completeness (RQ2)

Freshness is reset to baseline and the semantic stripping parameter is increased. Accuracy degradation occurs at a comparatively lower severity level, providing visual support for the working hypothesis on the relative effect of semantic completeness.

Act 4 — Task-dependent behavior (RQ3)

The agent task is toggled between retrieval and classification with identical fault conditions. The two accuracy curves differ, supporting the finding that task type influences resilience to specific fault types.

Act 5 — AIRS as a leading indicator (RQ4)

A mixed-fault scenario is initiated. The AIRS score decreases below the calibrated threshold of approximately 62 several seconds before observable accuracy degradation. The warning interval is visible on the timeline and represents the principal applied contribution of the score.

Act 6 — Boundary conditions of streaming (RQ5)

Using the side-by-side comparator, schema drift is increased on both pipelines. The accuracy advantage initially held by streaming is reduced and, beyond a threshold, reversed in favor of batch with strong validation. The streaming advantage is shown to be conditional rather than universal.


| Pedagogical role of the demonstration An interactive demonstration in which observable infrastructure manipulations produce measurable agent accuracy degradation — accompanied by an AIRS score that signals failure ahead of accuracy collapse — provides the defense panel with direct empirical grounding for the thesis's central claims. The demonstration serves simultaneously as a research instrument, a pedagogical tool, and a reusable artifact. |
|---|


### 7.4 Implementation choice: Streamlit

The original proposal specified a React + FastAPI architecture for the demonstration tool. Within the constraints of a five-month timeline, Streamlit provides a more efficient implementation path. It supports the required interactivity — sliders, live charts, scrolling event logs, side-by-side comparisons — with substantially less engineering effort, and is widely used in scientific demonstration contexts. The reduction in implementation effort allocates additional time to the experimental campaign, statistical analysis, and writing.

A subsequent migration of the demonstration to a polished React frontend, intended for broader dissemination or follow-up publication, can be undertaken after thesis submission but is not on the critical path of this study.


## Chapter 8 — Contributions, Risks, and Limitations


### 8.1 Contributions ranked by anticipated value


| Rank | Contribution | Why it matters |
|---|---|---|
| 1 | Empirical thresholds — specific values at which agent accuracy degrades for each fault type | Quantitative thresholds of this form have not, to the present author's knowledge, been reported in peer-reviewed literature. They provide citable, defensible reference points for both practitioners and follow-up research. Highest research value. |
| 2 | AIRS formula with data-derived weights | A single, measurable, predictive metric that engineers can compute on their own systems. This is the principal applied contribution and the artifact most likely to see practitioner adoption. |
| 3 | Empirical finding on semantic completeness (working hypothesis) | If the data supports the hypothesis that semantic completeness has a comparable or larger effect than freshness, the finding contributes an empirical counterweight to the prevailing emphasis on real-time pipeline design. |
| 4 | Open-source fault injector and reproducible benchmark dataset | Supports reproducibility and provides a foundation for subsequent comparative studies. |
| 5 | AIST demonstration tool | A defense-day artifact and pedagogical instrument. Lower direct research weight but significant value for dissemination and follow-up engagement. |
| 6 | Formal taxonomy of the four AIRS dimensions | The dimensions themselves are understood implicitly by practitioners; the contribution lies in their formal, operational definition and inclusion in a measurable framework. |

Table 8.1 — Contributions ranked by anticipated research value.


### 8.2 Risk register


| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Pilot study does not produce measurable accuracy degradation | Medium | High | Multiple fault types provide redundancy; the Month 2 pilot is designed specifically to surface this risk before main runs; methodology will be revised on the basis of pilot evidence rather than after sunk cost. |
| Fault injector produces conditions that diverge from real-world failure modes | Medium | High | Each fault implementation is validated against three documented real-world failure cases drawn from the literature; case studies are reported in Chapter 4 of the thesis. |
| Benchmark execution exceeds planned time (e.g. API rate limits) | Medium | Medium | Cloud spot instances; parallelization across multiple API keys where licensing permits; a reduced campaign of ~80 runs still yields acceptable statistical power. |
| Streamlit demonstration insufficient for defense impact | Low | Medium | The principal visual evidence — accuracy curves and live AIRS readouts — is well supported by Streamlit. If specific components require richer interactivity, a D3.js component can be embedded within the Streamlit application. |
| Writing accumulates toward the end of the timeline | High | High | Chapter drafts begin in Month 1. A full draft is submitted to the supervisor at the end of Month 4 rather than Month 5. Writing is treated as a continuous activity throughout the project. |
| AIRS predictive precision below 80% | Medium | Low | The thesis reports observed values regardless of whether they meet the hypothesized threshold. Calibration analysis and confidence intervals are reported in all cases; lower precision values can still constitute a valid contribution when reported with rigor. |
| Empirical findings on semantic completeness diverge from the working hypothesis | Medium | Low | The contribution of the study is the measurement, not the confirmation of the hypothesis. Any rigorous result advances the literature. |

Table 8.2 — Risk register with mitigations.


### 8.3 Limitations

Explicit acknowledgement of limitations is essential to scholarly transparency. The following are addressed in the thesis discussion chapter:

- Single model. Experiments use GPT-4o-mini throughout. Generalization to larger models, smaller open models, or non-GPT architectures is acknowledged as future work.
- Two task families. Retrieval and classification represent two common agentic workloads but do not exhaust the space. Long-running multi-step orchestration is outside the scope of this study.
- Synthetic fault injection. Faults are introduced synthetically rather than observed in production. The synthetic conditions are calibrated against documented field failures; a follow-up field study with naturally occurring failures is recommended for future work.
- Single hardware environment. All runs execute in Docker on equivalent cloud instances. Generalization to different hardware classes is acknowledged but not investigated.
- Public benchmark datasets. Datasets reflect their original collection contexts. Generalization to proprietary enterprise data is a function of practitioner evaluation, which the open-source AIRS tool is designed to facilitate.

## Chapter 9 — Resources, Ethics, and AI Tool Use


### 9.1 Budget


| Resource | Description | Cost |
|---|---|---|
| Cloud compute | Spot instances for ~128 benchmark runs across Months 2–3 | $30–60 |
| LLM API | GPT-4o-mini, est. 500K–800K tokens across pilot + main | $15–25 |
| Software | All tools open-source (Kafka, Airflow, LangChain, Streamlit, Prometheus, Great Expectations) | $0 |
| Datasets | All public (MS MARCO, Airline On-Time) | $0 |
| Hardware | Personal laptop for development; cloud for benchmark execution | $0 |
| TOTAL | Realistic upper bound | Under $90 |

Table 9.1 — Total project budget.


### 9.2 Ethics

No human subjects are involved. All datasets are public, anonymized or synthetic, and released under permissive licenses. No personally identifiable information is processed at any stage of the study. No ethics board approval is required.

All experimental results — including negative results, failed hypotheses, and unexpected findings — will be reported in full. The complete codebase, raw experimental data, and analysis scripts will be published openly on GitHub and Zenodo to ensure full reproducibility by independent researchers.


### 9.3 AI tool use — full disclosure

This research transparently discloses the use of AI assistants in alignment with academic integrity standards.


| Tool | Permitted use | Prohibited use |
|---|---|---|
| ChatGPT / Claude | Structural organization, language refinement, brainstorming research direction, academic tone editing. | Generating research results, fabricating data, drafting analysis sections, writing conclusions without author verification. |
| GitHub Copilot | Boilerplate code generation (Kafka consumer templates, Streamlit layouts, test scaffolding). | Generating the AIRS algorithm logic or fault injector core; all such code is hand-written and tested. |
| Grammarly | Grammar and spelling correction; readability improvement. | Paraphrasing to disguise sourcing; meaning-altering rewrites. |
| GPT-4o-mini | Used as the agent under test — research subject, not writing aid. | N/A — this is experimental instrumentation. |

Table 9.2 — AI tool use declaration.

Every AI-assisted passage of text has been manually rewritten in the author's voice. Every factual claim has been cross-referenced against primary sources. The author takes full responsibility for the content, methodology, and conclusions of this thesis.


## Chapter 10 — Summary


### 10.1 The thesis in one paragraph

Agentic AI systems are increasingly observed to underperform in production. A growing body of industry analysis attributes this to limitations in supporting data infrastructure rather than to model capability. This thesis contributes a formal characterization of those infrastructure limitations. Through approximately 128 controlled experiments, it derives empirical thresholds at which agent accuracy degrades, identifies the relative effect of four infrastructure properties on agent decision quality, validates a composite predictive score (AIRS), and delivers an open-source demonstration tool that makes the findings reproducible. The principal contribution is the empirical characterization and the predictive framework; the architectural comparison serves as the experimental vehicle, not the research question.


### 10.2 Principal takeaway


| Anticipated takeaway for the reader Agent decision quality is a measurable function of infrastructure properties. The relative weighting of those properties is, on the working hypothesis of this study, not always aligned with prevailing industry emphasis. The AIRS score provides a single quantitative input that supports an actionable engineering decision. |
|---|


### 10.3 Indicators of project success

- A successful thesis defense in which the live demonstration produces visible, measurable agent accuracy degradation under controlled fault conditions, with AIRS providing an early indication of failure.
- An open-source release whose documentation enables an independent engineer to compute AIRS on their own pipeline within approximately one hour.
- Three numeric findings of sufficient precision and rigor to be referenced by subsequent academic work and applied by practitioners.
- Submission of the completed thesis within the five-month timeline, with supervisor endorsement and a viable path toward publication at a venue such as IEEE ICDE, ACM SIGMOD, or the VLDB demonstrations track.
— End of Research Plan —
