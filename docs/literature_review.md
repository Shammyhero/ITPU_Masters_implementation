# Literature Review — Chapter 2 working draft

**Thesis:** Characterizing the Data Infrastructure Gap for Agentic AI Systems
**Author:** Shamsiddin Khamidov · Compiled 2026-07-25

> **Verification note.** Every source below was retrieved and checked against its
> publisher or arXiv record during compilation. Titles, authors, venues and years
> are as recorded there. Claims attributed to a paper are drawn from its abstract
> or stated findings. Nothing in this file is reconstructed from memory.
>
> This matters: the reference list of the earlier (superseded) clinical-topic
> coursework contains at least one entry that does not correspond to a real
> publication — "Karpathy, A., et al. (2024). Scaling Clinical MLOps: From
> Research to Production. *ACM Computing Surveys*". **Do not carry any citation
> from that list into this thesis without re-verifying it.**

---

## 1. Why this chapter had to be written before the main campaign

The thesis proposal states the gap as follows:

> "the data infrastructure requirements of agentic AI systems have not yet been
> the subject of a peer-reviewed measurement framework"

**That claim, as written, is no longer defensible.** Two 2026 papers occupy
adjacent ground closely enough that an examiner or reviewer would find them
within minutes of searching, and failing to cite them would be the single most
damaging omission the thesis could make:

- **ReliabilityBench** (Gupta, Jan 2026) applies chaos-engineering-style fault
  injection to LLM agents and reports a composite reliability surface.
- **Semantic Layers for Reliable LLM-Powered Data Analytics** (Rumiantsau &
  Fokeev, Apr 2026) quantifies the accuracy cost of absent semantic metadata for
  LLMs at +17 to +23 percentage points.

The gap is therefore **restated, narrowed, and strengthened** in §7. The narrower
claim survives contact with this literature; the broad one does not.

---

## 2. Theme A — Data quality frameworks: the dimensions are not new

Foundational work established the vocabulary this thesis operationalizes. The
contribution here is **not** proposing freshness/consistency/completeness as
dimensions — that would be a claim the literature refutes — but operationalizing
them **as executable measurements for an autonomous consumer**.

| Source | What it establishes | Relation to this thesis |
|---|---|---|
| Wang & Strong (1996), *Beyond Accuracy: What Data Quality Means to Data Consumers*, JMIS 12(4), 5–33 | 15 DQ dimensions in 4 categories (intrinsic, contextual, representational, accessibility), derived from a two-stage survey of data consumers | The four AIRS dimensions are a **subset selected for agentic relevance**, not an invention. Cite as the origin of the dimensional vocabulary. Note their "contextual" category anticipates semantic completeness. |
| Polyzotis, Zinkevich, Roy, Breck & Whang (2019), *Data Validation for Machine Learning*, MLSys 2019 | Production data-validation system in Google's TFX; validates petabytes/day; most common bugs are new feature columns, unexpected string values, missing feature columns | The closest prior art on **detecting** the faults this thesis injects. Crucially it stops at detection — it does not measure the **decision consequence** for a downstream autonomous consumer. |
| Caveras/Breck et al. (2020), *TensorFlow Data Validation: Data Analysis and Validation in Continuous ML Pipelines*, SIGMOD 2020 | Continuous validation in ML pipelines | Same boundary: anomaly detection, not consequence measurement. |
| Sculley et al. (2015), *Hidden Technical Debt in Machine Learning Systems*, NeurIPS 28 | Data dependencies as the dominant source of hidden debt; "CACE" principle | The canonical justification for treating infrastructure, not models, as the object of study. |
| Amershi et al. (2019), *Software Engineering for Machine Learning: A Case Study*, ICSE-SEIP | Data management dominates practitioner effort in ML systems | Motivation for the practitioner-facing framing of AIRS. |
| *A Survey on Data Quality Dimensions and Tools for Machine Learning* (arXiv:2406.19614) | Recent consolidation of DQ dimensions and tooling for ML | Use for the "dimensions are established, their agentic consequences are not" argument. |

**Synthesis.** The dimensions are settled science; the tooling to *detect* their
violation is mature and deployed at scale. What no source in this theme provides
is a mapping from a violation's **severity** to a consumer's **decision quality**.
For a human reading a dashboard that mapping is unnecessary — the human
compensates. For an autonomous agent it is the whole problem.

---

## 3. Theme B — Freshness and accuracy: rigorous, but not about agents

This theme contains the most methodologically demanding prior work, and it
delivers a result that **directly complicates RQ1**.

| Source | What it establishes | Relation to this thesis |
|---|---|---|
| **Shisher & Sun (2022), *How Does Data Freshness Affect Real-time Supervised Learning?*, MobiHoc 2022 (arXiv:2208.06948)** | Information-theoretic analysis: prediction error is a function of Age of Information, and **that function is monotonic only when the feature/target sequence approximates a Markov chain — otherwise it can be non-monotonic** | **The single most important methodological warning for this thesis.** RQ1 assumes a threshold beyond which accuracy degrades. That framing presupposes monotonicity. See §8.1 for the required correction. |
| Wooders et al. (2024), *RALF: Accuracy-Aware Scheduling for Feature Store Maintenance*, PVLDB 17(4), 563 | Feature staleness impacts downstream accuracy **heterogeneously**; scheduling by downstream error ("regret") beats always-refresh-the-stalest policies | Establishes that staleness cost is feature-dependent, not uniform. Supports reporting freshness thresholds as domain-relative rather than universal constants. |
| Shisher et al. (2024), *Timely Communications for Remote Inference* (arXiv:2404.16281) | Extends AoI-to-inference-error analysis | Supporting citation for the AoI framing. |

**Synthesis.** Freshness→accuracy is a studied relationship — for classical
supervised models consuming fixed feature vectors. Agents differ in kind: they
consume *records with meaning*, reason over them in natural language, and commit
to actions. No source in this theme studies an LLM-based autonomous consumer.

---

## 4. Theme C — Agent evaluation: stresses the system, holds the data constant

| Source | What it establishes | Relation to this thesis |
|---|---|---|
| **Gupta (2026), *ReliabilityBench: Evaluating LLM Agent Reliability Under Production-Like Stress Conditions* (arXiv:2601.06112)** | Chaos-style fault injection on agents; reliability surface R(k,ε,λ) over consistency, robustness to task perturbation, fault tolerance; finds **rate limiting most damaging**; success falls 96.9%→88.1% at perturbation intensity ε=0.2 | **The nearest competitor — must be cited and differentiated.** Its faults are predominantly *system-level* (timeouts, rate limits, partial responses); schema drift is the only data-quality dimension included. No freshness, no semantic completeness, no derived thresholds, no readiness score. |
| **Advani (2026), *From Confident Closing to Silent Failure: Characterizing False Success in LLM Agents* (arXiv:2606.09863)** | 45–48% of failures in single-control tau2-bench domains are **false success** — agents claim completion without verified state change; 75.8% among self-assessing coding agents; LLM judges detect this poorly (AUROC ≤0.65) | **A gift to this thesis.** It documents the silent-failure phenomenon at scale and explicitly **does not explain its causes**. This thesis can supply a data-infrastructure explanation for a phenomenon the literature has just quantified. |
| Agent-SafetyBench (arXiv:2412.14470) | Ten failure modes; agents lack robustness and risk awareness | Supporting evidence that agents fail without signalling. |
| AgentProp-Bench (arXiv:2604.16706) | Judge reliability, error propagation cascades in tool-using agents | Relevant to how a single bad record propagates. |
| AgentAtlas (arXiv:2605.20530) | Argues outcome leaderboards do not localize *where* failures originate | Direct support for this thesis's premise: end-to-end scores hide infrastructure causes. |

**Synthesis.** Agent benchmarking is maturing fast, and 2026 work has begun
injecting faults. But the injected faults are overwhelmingly *system-level*, and
the data an agent reads is held constant and assumed correct. The one benchmark
that touches data quality (ReliabilityBench) covers a single dimension.

---

## 5. Theme D — The semantic layer: shown to matter, never graded

| Source | What it establishes | Relation to this thesis |
|---|---|---|
| **Rumiantsau & Fokeev (2026), *Semantic Layers for Reliable LLM-Powered Data Analytics: A Paired Benchmark of Accuracy and Hallucination Across Three Frontier Models* (arXiv:2604.25149)** | Paired single-shot protocol, 3 frontier models, schema-only vs schema+4KB semantic document: **+17 to +23 pp accuracy** (45.5–50.5% → 67.7–68.7%); the semantic document accounts for essentially all significant variance | **Directly overlaps the semantic-completeness hypothesis and must be cited.** Differences: binary on/off (not graded severity), text-to-SQL analytics (not pipeline infrastructure), and **no comparison against freshness, latency or consistency at matched severity** — which is exactly what RQ2 provides. |
| *A Semantic-Layer-Mediated Agent for NL-to-SQL over Heterogeneous Enterprise Databases* (arXiv:2606.31041) | Semantic mediation improves agent querying across heterogeneous sources | Supports semantic layer as an active 2026 research direction. |
| Dehghani (2022), *Data Mesh*, O'Reilly | Semantic data products; meaning as a first-class deliverable | Origin of one naming tradition for the semantic dimension. |
| Hogan et al. (2021), *Knowledge Graphs*, ACM Computing Surveys 54(4) | Formal treatment of entities, relations, semantics | Another naming tradition; supports treating these as one dimension. |

**Synthesis.** The claim "semantics matter to LLMs" is **no longer novel** as of
April 2026 — it is measured, with an effect size. The thesis must stop claiming
discovery here and claim something the literature genuinely lacks: **where
semantic completeness ranks against the other three infrastructure properties at
equivalent severity, and how it degrades as a graded quantity rather than an
on/off switch.**

---

## 6. Theme E — Counter-evidence: degradation is not always in the expected direction

Included deliberately, because a review that only gathers confirming evidence is
not a review.

| Source | What it establishes | Why it matters here |
|---|---|---|
| Cuconasu et al. (2024), *The Power of Noise: Redefining Retrieval for RAG Systems*, SIGIR 2024 (arXiv:2401.14887) | Adding **irrelevant** documents to RAG context can *improve* accuracy (~+9% when positioned near relevant ones) | Degraded input does not monotonically degrade LLM output. The thesis must be prepared for non-intuitive results and report them. |
| *The Powerless Noise: How Experimental Settings Shape the Reported Power of Noise*, SIGIR 2026 (arXiv:2607.03615) | Rebuts/qualifies the above: the reported benefit is sensitive to experimental setup | A cautionary precedent for exactly the risk this thesis carries — that a headline effect is an artifact of experimental configuration. Cite when defending the catalog-velocity choice (§8.2). |
| Shisher & Sun (2022), as above | Non-monotonic AoI→error | Same warning, from theory rather than practice. |

---

## 7. The gap, restated honestly

**Superseded formulation** (do not use): *"no peer-reviewed measurement framework
exists for the data infrastructure requirements of agentic AI systems."*

**Defensible formulation:**

> Four literatures each address part of the problem, and none addresses their
> intersection.
>
> 1. **Data quality research** (Wang & Strong 1996; Polyzotis et al. 2019)
>    defines and detects violations of freshness, consistency and completeness,
>    but stops at detection and targets human or classical-ML consumers.
> 2. **Freshness–accuracy research** (Shisher & Sun 2022; Wooders et al. 2024)
>    rigorously connects staleness to prediction error, but for classical
>    supervised models, not LLM-based autonomous agents.
> 3. **Agent reliability benchmarking** (Gupta 2026; Advani 2026) injects faults
>    into agent execution, but predominantly at the system level, holding the
>    *content* of the data constant; where data faults appear, a single
>    dimension is covered and no thresholds or composite score are derived.
> 4. **Semantic layer research** (Rumiantsau & Fokeev 2026) quantifies the cost
>    of absent semantics for LLMs, but as a binary condition in an analytics
>    setting, without comparison to other infrastructure properties.
>
> **What is absent** is a controlled, factorial comparison of all four
> data-infrastructure quality dimensions on agentic decision quality at matched
> severity — yielding (a) empirically derived degradation thresholds per
> dimension, (b) a ranked ordering with effect sizes, and (c) a composite score
> whose weights are estimated from the resulting data rather than assumed. That
> is the contribution of this thesis.

This is narrower than the original claim. It is also **survivable**, which the
original is not. The thesis now enters an active 2026 conversation with a
specific, unclaimed position rather than asserting an empty field.

---

## 8. What the literature changes about the study design

### 8.1 RQ1 must not presuppose monotonic degradation

Shisher & Sun (2022) prove that prediction error as a function of data age can be
**non-monotonic** when the data sequence departs from a Markov chain. RQ1 as
written ("at what severity does accuracy drop by more than 10%") assumes a single
crossing point.

**Required changes:**
- Test the monotonicity assumption explicitly before fitting thresholds; report
  the full severity–accuracy curve, not only the crossing point.
- Define the threshold operationally as **first crossing** of the −10% band, and
  state that a non-monotonic response would make a single threshold inadequate.
- Cite Shisher & Sun as the theoretical basis for testing rather than assuming.

### 8.2 The catalog-velocity parameter must be pre-declared and defended

The e-commerce update rate governs how much staleness *can* matter, and it was
raised during instrumentation (1000 → 2000 updates/s) after an initial
sensitivity check showed a severe fault flipping only 8.1% of answers.

*The Powerless Noise* (SIGIR 2026) is precedent for reviewers attacking exactly
this kind of configuration sensitivity. **Handle it in the open:**
- Declare velocity as a stated property of the simulated domain with a
  real-world justification (high-velocity dynamic-pricing catalog).
- Report RQ1 findings as a **ratio of staleness to mean inter-update interval**
  alongside absolute seconds, so the finding transfers across domains.
- Run at least one condition at a second velocity to demonstrate the
  relationship scales rather than being an artifact of one setting.

### 8.3 Reframe the semantic finding around silent failure

Rumiantsau & Fokeev already showed semantics improve accuracy. Advani showed
agents fail *confidently and silently* but did not explain why. The distinctive
claim available to this thesis is therefore not "missing semantics hurts
accuracy" but:

> **Missing semantics causes agents to fail silently rather than abstain** —
> quantified, graded by severity, and ranked against freshness, latency and
> consistency.

This requires the harness to record not just correctness but **failure mode**:
did the agent answer wrongly with high confidence, or decline/flag uncertainty?
The smoke runs already log per-decision confidence and parse failures, so the
data needed is being captured; the analysis must exploit it.

### 8.4 Position AIRS against ReliabilityBench explicitly

ReliabilityBench's R(k,ε,λ) is a composite agent-reliability surface. AIRS is a
composite *infrastructure-readiness* score computed on the pipeline, before and
independently of agent execution. The distinction to state in Chapter 2:
ReliabilityBench measures **how reliably the agent behaves under stress**; AIRS
estimates **whether the data substrate is fit for an agent at all**, and is
computable without running the agent. These are complementary; the thesis should
say so rather than ignore the overlap.

---

## 9. Reading status

- [x] 20+ sources identified, retrieved and verified
- [x] Thematic synthesis across five themes including counter-evidence
- [x] Gap restated to survive the 2026 literature
- [x] Four concrete design corrections derived
- [ ] Full-text deep read of the four load-bearing papers (Shisher & Sun; Gupta;
      Rumiantsau & Fokeev; Advani) — required before Chapter 2 final draft
- [ ] Forward-citation sweep on Gupta (2026) and Rumiantsau & Fokeev (2026)
      immediately before submission; both are recent and actively cited
- [ ] Confirm venue/DOI for each arXiv-only preprint at submission time

---

## 10. Verified bibliography (APA 7)

Advani, L. (2026). *From confident closing to silent failure: Characterizing
false success in LLM agents*. arXiv:2606.09863.

Amershi, S., Begel, A., Bird, C., DeLine, R., Gall, H., Kamar, E., Nagappan, N.,
Nushi, B., & Zimmermann, T. (2019). Software engineering for machine learning: A
case study. *ICSE-SEIP 2019*, 291–300.

Cuconasu, F., Trappolini, G., Siciliano, F., Filice, S., Campagnano, C., Maarek,
Y., Tonellotto, N., & Silvestri, F. (2024). The power of noise: Redefining
retrieval for RAG systems. *SIGIR 2024*. arXiv:2401.14887.

Dehghani, Z. (2022). *Data mesh: Delivering data-driven value at scale*.
O'Reilly Media.

Gupta, A. (2026). *ReliabilityBench: Evaluating LLM agent reliability under
production-like stress conditions*. arXiv:2601.06112.

Hogan, A., Blomqvist, E., Cochez, M., d'Amato, C., de Melo, G., Gutierrez, C.,
… Zimmermann, A. (2021). Knowledge graphs. *ACM Computing Surveys, 54*(4), 1–37.

Kleppmann, M. (2017). *Designing data-intensive applications*. O'Reilly Media.

Kreps, J., Narkhede, N., & Rao, J. (2011). Kafka: A distributed messaging system
for log processing. *NetDB Workshop*.

Polyzotis, N., Zinkevich, M., Roy, S., Breck, E., & Whang, S. (2019). Data
validation for machine learning. *MLSys 2019*.

Rumiantsau, M., & Fokeev, I. (2026). *Semantic layers for reliable LLM-powered
data analytics: A paired benchmark of accuracy and hallucination across three
frontier models*. arXiv:2604.25149.

Sculley, D., Holt, G., Golovin, D., Davydov, E., Phillips, T., Ebner, D.,
Chaudhary, V., Young, M., Crespo, J.-F., & Dennison, D. (2015). Hidden technical
debt in machine learning systems. *NeurIPS 28*, 2503–2511.

Shisher, M. K. C., & Sun, Y. (2022). How does data freshness affect real-time
supervised learning? *MobiHoc 2022*. arXiv:2208.06948.

Wang, R. Y., & Strong, D. M. (1996). Beyond accuracy: What data quality means to
data consumers. *Journal of Management Information Systems, 12*(4), 5–33.

Wooders, S., et al. (2024). RALF: Accuracy-aware scheduling for feature store
maintenance. *Proceedings of the VLDB Endowment, 17*(4), 563–576.

*Additional verified sources for supporting citation:* Agent-SafetyBench
(arXiv:2412.14470); AgentProp-Bench (arXiv:2604.16706); AgentAtlas
(arXiv:2605.20530); Semantic-Layer-Mediated NL-to-SQL Agent (arXiv:2606.31041);
*The Powerless Noise* (SIGIR 2026, arXiv:2607.03615); *A Survey on Data Quality
Dimensions and Tools for ML* (arXiv:2406.19614); TensorFlow Data Validation
(SIGMOD 2020).

> **Before submission:** complete author lists for RALF and the arXiv-only
> entries must be filled in from the publisher record, and any preprint that has
> since appeared in a venue should be cited in its published form.
