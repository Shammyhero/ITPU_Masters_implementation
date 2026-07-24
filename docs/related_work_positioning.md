# Positioning against the four load-bearing papers

**Purpose.** Chapter 2 related-work section, and defense preparation. Each of
these four papers was read in full, not from its abstract. For each: what it
actually did, what it did *not* do, how this thesis differs, and what must change
in our design because of it.

**The honest summary in one line:** three of the four papers are stronger than
this thesis on *model coverage*, and none of them covers *more than one data
quality dimension*. Our differentiation is breadth of dimension and causal
control; our exposure is breadth of model.

---

## 1. ReliabilityBench — Gupta (2026), arXiv:2601.06112

**The nearest competitor. Cite prominently, differentiate explicitly.**

### What it actually did

| Aspect | ReliabilityBench | This thesis (built + planned) |
|---|---|---|
| Scale | 1,280 episodes | 144 runs × 150 queries ≈ 21,600 agent decisions |
| Models | **2** (Gemini 2.0 Flash, GPT-4o) | **1** (GPT-4o-mini) + planned cross-model subset |
| Architectures | **2** (ReAct, Reflexion) | 1 (LangGraph, fixed) |
| Domains | 4 (scheduling, travel, customer support, **e-commerce**) | 2 (e-commerce retrieval, aviation classification) |
| Faults | timeouts, rate limits, partial responses, **schema drift** | freshness, latency, **schema drift**, **semantic stripping** |
| Correctness | action metamorphic relations, end-state equivalence | ground truth at query time from replayed world state |
| Output | reliability surface R(k,ε,λ) | AIRS 0–100 + per-dimension thresholds |
| Headline | 96.9% → 88.1% at ε=0.2; **rate limiting most damaging** | TBD; smoke suggests freshness/semantic dominate |
| When computed | **post-hoc, requires running the agent** | **pre-deployment, computed on the pipeline** |

### Where they beat us

They have twice our model coverage and twice our architecture coverage, and one
more domain. They also anticipated our e-commerce setting. If asked "isn't this
just ReliabilityBench?", the weakest possible answer is to dispute their scale.

### Where we are genuinely different — the three defensible claims

1. **Fault taxonomy.** Their four faults are three system-level (timeouts, rate
   limits, partial responses) plus one data-level (schema drift). Ours are four
   *data-level* faults spanning all four AIRS dimensions. Their finding "rate
   limiting is most damaging" is a claim about **infrastructure availability**;
   ours will be a claim about **infrastructure data quality**. Different axis.
2. **AIRS is computable without the agent.** R(k,ε,λ) is measured *from agent
   executions* — you must already have the agent, the environment, and the
   budget to run it k times. AIRS is computed from pipeline telemetry
   (record age, delivery latency, cross-stage field agreement, context
   completeness) **before an agent is deployed at all**. That is the practical
   difference for an engineer deciding whether to build the agent.
3. **Thresholds, not deltas.** They report success-rate changes at chosen
   intensities. We derive the severity at which degradation crosses a stated
   band, with confidence intervals — a citable reference value.

### What must change in our plan because of it

- **Cite in Chapter 1**, not just Chapter 2. The gap statement must name it.
- **Add a sentence to the AIRS contribution claim**: "unlike agent-execution
  reliability surfaces (Gupta, 2026), AIRS is computable pre-deployment."
- **Model coverage becomes our top methodological risk** (see §5).

---

## 2. Semantic Layers for LLM Analytics — Rumiantsau & Fokeev (2026), arXiv:2604.25149

**Pre-empts the naive version of our semantic hypothesis. Must be cited.**

### What it actually did

- 100 natural-language questions over the Cleaned Contoso **Retail** dataset in
  ClickHouse.
- 3 frontier models: Claude Opus 4.7, Claude Sonnet 4.6, GPT-5.4.
- Paired single-shot protocol, **two conditions only**: schema-only vs schema +
  a 4 KB hand-authored markdown document of measures, conventions and
  disambiguation rules.
- Result: **45.5–50.5% → 67.7–68.7%**, i.e. **+17 to +23 pp**. Models
  statistically indistinguishable within condition (p < 0.01); the semantic
  document accounted for essentially all significant variance.

### What it did NOT do — our four openings

| They did not | We do |
|---|---|
| Grade semantic completeness — it is **binary** (doc present/absent) | Mild (30%) and severe (80%) stripping, plus continuous 0–100% in the AIST demo |
| Compare semantics against **any other** infrastructure property | Rank semantics against freshness, latency and consistency **at matched severity** (RQ2) |
| Measure **abstention or refusal** | `abstention_rate` and `silent_failure_rate` per run |
| Study a **pipeline** — it is prompt-context composition | Faults injected in transit between pipeline and agent |

### The uncomfortable truth to state plainly

"Semantic context improves LLM accuracy" is **settled as of April 2026**, with an
effect size. Our thesis must not present that as a discovery. The defensible
formulation:

> Rumiantsau & Fokeev (2026) establish that supplying semantic context improves
> LLM analytical accuracy by 17–23 pp in a binary comparison on frontier models.
> This thesis asks the next questions: how the effect scales with *degree* of
> semantic loss, how it ranks against other infrastructure degradations at
> equivalent severity, and — critically — whether semantic loss causes agents to
> **fail silently or to abstain**.

### Convergent-validation opportunity

Their effect is +17–23 pp. Our smoke runs show roughly −25 to −33 pp under severe
stripping. Same order of magnitude, opposite direction, different models and
task. **If the main campaign lands in that band, report it as convergent
validation** — independent replication of an effect size on a different model
class, task family and delivery mechanism. That is a genuine strengthening move,
and it costs nothing to make.

---

## 3. False Success in LLM Agents — Advani (2026), arXiv:2606.09863

**The paper that defines our best contribution by leaving a question open.**

### What it actually did

- **9,876 trajectories** from **8 model families** on tau2-bench; **1,879
  trajectories** from 4 model families on AppWorld.
- False success = agent asserts completion while environment state shows
  otherwise.
- Prevalence: **45–48%** of failures in single-control tau2-bench domains,
  **3%** in the dual-control telecom domain (where an independent user simulator
  can verify state), **75.8%** in AppWorld self-assessing trajectories.
- Detection: LLM judges are poor (AUROC ≤0.65, and 0.54 on AppWorld);
  lightweight TF-IDF detectors reach **0.83–0.95** at 3,300× lower latency.

### The decisive limitation — and our opening

> **The study is purely observational.** It analyses existing trajectories. It
> never manipulates data quality or environment conditions, and the authors do
> not characterise the root behavioural causes of agent overconfidence.

Observation cannot establish causation. **We inject conditions and observe the
failure mode**, which can. That is the cleanest differentiation available to this
thesis, and it is a difference in *evidence class*, not merely in scope.

### What our smoke data already suggests (n=12, indicative only)

| Condition | Abstained | Silent failure |
|---|---|---|
| Retrieval + severe freshness | 0% | **42%** |
| Retrieval + severe semantic stripping | 0% | 33% |
| Classification + severe semantic stripping | **50%** | **0%** |

The mechanism is legible: **opaque field names are visible to the agent, so it
can decline; stale values are invisible, so it cannot.** A stale price is
perfectly well-formed. This yields the sharpest claim in the project:

> **Detectability, not magnitude, determines danger.** The infrastructure fault
> that produces the most silent failure is not the one that degrades accuracy
> most, but the one that leaves no trace in the data the agent can see.

### A competitive baseline we should now run (cheap, high value)

Advani establishes two detection baselines. AIRS is a *third*, operating earlier:

| Approach | Signal | When available |
|---|---|---|
| LLM judge (Advani) | agent's own output text | after the decision |
| TF-IDF detector (Advani) | surface linguistic patterns | after the decision |
| Agent self-confidence | reported confidence | at the decision |
| **AIRS (this thesis)** | **pipeline telemetry** | **before the decision** |

**Add to RQ4:** compare AIRS's precision/recall for predicting silent failure
against agent self-reported confidence as a baseline, on our own data. Both are
already logged, so this costs **zero additional API calls**. If AIRS beats
confidence, the applied contribution is demonstrated against a real alternative
rather than asserted in a vacuum.

---

## 4. Data Freshness and Real-time Learning — Shisher & Sun (2022), MobiHoc, arXiv:2208.06948

**Not a competitor — a methodological constraint we must satisfy.**

### What it establishes

- Prediction error is a function of Age of Information, and that function is
  **monotonic only if the feature/target sequence approximates a Markov chain**.
  Where the sequence is far from Markovian, the relationship **can be
  non-monotonic**.
- Classical supervised learning only. **No language models.** The agentic case
  is untouched — which is our room to work.

### Direct consequences for RQ1

1. **Do not assume a single crossing point.** Report the full severity–accuracy
   curve for each fault; treat the threshold as the *first* crossing of the
   −10% band and say so explicitly.
2. **Test the assumption rather than inherit it.** Run the freshness arm at more
   than two severities so monotonicity is checkable rather than presumed. Our
   current design has exactly two (1.5 s, 5 s), which **cannot distinguish
   monotonic from non-monotonic behaviour** — two points always look monotonic.
   → **Design change required:** add intermediate freshness severities.
3. **A non-monotonic result is a finding, not a failure.** If agent accuracy
   under staleness is non-monotonic, that extends Shisher & Sun's theoretical
   result to LLM agents empirically — a stronger contribution than a clean
   threshold.

### Why our setting may well be non-Markovian

Our retrieval ground truth is "cheapest in-stock product," which depends on the
*relative ordering* of several independently-updating products. That is a
maximum over a set of random walks — not obviously Markovian in the required
sense. **There is a real chance of observing non-monotonic degradation**, and the
design must be able to detect it rather than average it away.

---

## 5. Consolidated: where we stand, honestly

### Our three defensible contributions after this review

1. **Only study covering all four data-quality dimensions on agents at matched
   severity** — ReliabilityBench has one, Rumiantsau has one, Shisher & Sun has
   one (and no agents).
2. **Only causal evidence on what produces silent failure** — Advani quantifies
   the phenomenon observationally; we manipulate conditions.
3. **Only pre-deployment readiness score** — everything else requires running
   the agent first.

### Our single biggest exposure: model coverage

| Study | Models |
|---|---|
| Advani (2026) | 8 model families |
| Rumiantsau & Fokeev (2026) | 3 frontier models |
| Gupta (2026) | 2 models |
| **This thesis, as planned** | **1** |

Compounding it: GPT-4o-mini is a 2024-era small model, while the comparison
papers use 2026 frontier models. The obvious reviewer question — *"do frontier
models handle degraded data better, making your thresholds obsolete?"* — has no
answer in the current design.

**Recommended change (cost-justified):** the full campaign costs ≈ $4, so the
budget can absorb triangulation.

| Arm | Model | Runs | Est. cost |
|---|---|---|---|
| Primary | GPT-4o-mini | 144 (full factorial) | ~$4 |
| Open-model replication | local via Ollama | ~30 subset | $0 |
| Frontier check | one current frontier model | ~30 subset | ~$10–15 |

Total stays well under the $90 budget and converts the biggest objection into a
sentence: *"the ranking of infrastructure properties is stable across a small
proprietary model, an open model, and a frontier model."* Note the frontier-model
choice should be made at run time from what is current, not fixed now.

### Design changes this review requires

- [ ] Add intermediate freshness severities (≥4 levels) so monotonicity is
      testable — **required by §4, currently impossible with 2 levels**
- [ ] Add cross-model arms: open model (free) + frontier subset (~$10–15)
- [ ] Add agent self-confidence as the competing baseline in RQ4 — **zero cost,
      data already logged**
- [ ] Reframe the semantic claim around silent failure vs abstention, and cite
      Rumiantsau & Fokeev as prior art on the accuracy effect itself
- [ ] State the AIRS/ReliabilityBench distinction (pre-deployment vs post-hoc)
      in both Chapter 1 and Chapter 2
- [ ] Report our semantic effect size against their +17–23 pp as convergent
      validation

### Questions to rehearse for the defense

1. *"How is this different from ReliabilityBench?"* → Their faults are
   availability-level and post-hoc; ours are data-quality-level and
   pre-deployment. Different axis, complementary result.
2. *"Rumiantsau already showed semantics matter."* → Correct, and cited. They
   showed *that* it matters, binary, on one property. We show *how much relative
   to other properties, at what severity, and with what failure mode.*
3. *"Only one model?"* → Three arms: primary, open, frontier subset; the ranking
   is what we claim generalises, not the absolute thresholds.
4. *"Your thresholds depend on your simulated catalog velocity."* → Yes, and
   reported as a ratio to the update interval for that reason; one condition is
   replicated at a second velocity to show it scales.
5. *"Isn't opaquifying field names just guaranteeing failure?"* → It is the
   research plan's own definition of missing semantics, and the empirical result
   is *not* the accuracy drop but that agents **abstain** when meaning is
   visibly absent and **fail silently** when data is merely stale.
