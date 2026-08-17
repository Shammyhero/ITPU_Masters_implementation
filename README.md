# AIRS-Bench — Characterizing the Data Infrastructure Gap for Agentic AI Systems

Master's thesis implementation — Shamsiddin Khamidov, M.Sc. Software Engineering
(Data Engineering & AI), IT Park University, 2026.

**The claim under study:** agentic AI systems fail in production because of the
data infrastructure feeding them, not the model. This repository measures that
claim. The agent is the *measurement instrument*; the infrastructure is the
subject. Model, prompt, temperature, dataset, scoring and hardware are held
constant — only infrastructure conditions vary.

**Status:** all five research questions answered. 302 benchmark runs, 24 270
agent decisions, 4 models, $5.15 of API spend, 350 tests green. One provisional
arm is mid-flight (see [Status](#status) below). Remaining work is the thesis
write-up, not measurement.

---

## What was found

| | Finding |
|---|---|
| **RQ1** | Degradation **is** monotone in data age; threshold at 5.05 s on both tasks. But retrieval decomposes into *exposure* × *conditional rate* — see below. |
| **RQ2** | Rank faults by **residual** impairment, not raw accuracy: schema drift (−0.173) > semantic stripping (−0.128) > freshness (−0.003) ≈ latency (0). |
| **RQ3** | Silent failure is driven by schema drift and semantic stripping on retrieval, freshness on classification. Abstention is driven by semantic stripping **and nothing else** (OR 51.9). |
| **RQ4** | AIRS ranks held-out pipelines at ρ ≈ −0.8 from telemetry alone, and beats the agent's own confidence exactly where that confidence is worthless. |
| **RQ5** | The ranking transfers **across models** but **inverts across tasks**. One pooled weighting would describe neither. |

Three results are worth stating on their own.

**The agent's confidence about its own silent failures is a coin flip.**
AUC 0.501 on the retrieval task. When the agent is about to give a confident
wrong answer, its self-reported confidence carries no information. That is the
strongest single argument for scoring the pipeline instead of asking the model.

**Stale data does not impair the agent — it moves the answer key.** Separating
"the agent reasoned worse" from "the correct answer changed while it read"
leaves a residual impairment of −0.003. Established three independent ways
(flip partition, decision-level OR 1.00 / p = 0.998, and a null on all four
models). This implies that studies reporting "staleness degrades agents by X%"
may be measuring an artifact of the measurement, not an effect on the agent.

**Enforcement works, and costs more than expected.** ~75% of silent failure is
agent-intrinsic — a fault-free pipeline still produces 14.2% confidently wrong
answers against a 19.6% overall rate — so no data gate can reach it. Every
worthwhile policy forfeits **7–21 correct answers per silent failure genuinely
prevented.** A gate is a trade, not a free win.

Full write-ups per question are in [`docs/`](docs/); each is reproducible from
the committed run artifacts at zero cost.

---

## Documents

Start here if you are reviewing the research rather than the code.

| Document | What it carries |
|---|---|
| [`docs/research_plan_original.md`](docs/research_plan_original.md) | **The research plan as submitted (May 2026)** — the origin of the project. Also as [`.docx`](docs/research_plan_original.docx). |
| [`docs/research_questions_v2.md`](docs/research_questions_v2.md) | Current RQs, hypotheses, statistical plan. **Supersedes the plan's RQs.** |
| [`docs/chapter3_methodology.md`](docs/chapter3_methodology.md) | Methodology as actually implemented (Chapter 3 draft) |
| [`docs/literature_review.md`](docs/literature_review.md) | 25+ verified sources; the gap claim as it can be defended |
| [`docs/related_work_positioning.md`](docs/related_work_positioning.md) | Differentiation against the four nearest papers |
| [`docs/campaign_status.md`](docs/campaign_status.md) | **Operational entry point** — current state, costs, what remains |

**Findings, one per research question:**
[flip partition](docs/flip_partition_findings.md) ·
[freshness sweep](docs/freshness_sweep_findings.md) ·
[statistical analysis](docs/statistical_analysis_findings.md) ·
[AIRS calibration](docs/airs_calibration_findings.md) ·
[cross-model](docs/cross_model_findings.md) ·
[detectability](docs/detectability_findings.md) ·
[the gate](docs/gate_findings.md)

---

## The tools this produced

Two are meant to outlive the thesis. Neither makes a model call, needs an API
key, or costs anything.

**`airs probe`** — score a pipeline's readiness *before* deploying an agent on
it. Reads a sample of records as your pipeline delivers them and applies the
weights calibrated in RQ4. A dimension it cannot measure is reported as
`UNMEASURED`, never as 100 — scoring an absent measurement as healthy is the
failure mode that would make the tool dangerous.

```bash
python -m airsbench.probe --records delivered.jsonl --source upstream.jsonl --task retrieval
```

**`airs gate`** — refuse a batch that violates a declared data contract, before
the agent is ever asked. Exit 1 means refused, and the refusal names the rule
and the observed value, because a refusal nobody can act on is just a slower
failure.

```bash
python -m airsbench.gate --records delivered.jsonl --policy examples/gate/retrieval.json
```

Worked examples: [`examples/probe/`](examples/probe/) · [`examples/gate/`](examples/gate/)

---

## Reproducing

```bash
make setup          # venv + dev install
make test           # 350 tests, including injector verification
make lint
make grid           # inspect the factorial — no execution, no cost
```

Every analysis below reads the committed run artifacts in `results/runs/` and
costs **nothing** — no API key required:

```bash
python -m airsbench.analysis.flip_partition
python -m airsbench.analysis.airs_calibration
python -m airsbench.gate.replay --task retrieval --sweep dimension
python -m airsbench.gate.replay --task retrieval --attribution
```

Re-running the experiments themselves does cost money. Every paid command takes
`--max-cost`, and **`--dry-run` first is mandatory** — the guard refuses to
start above the ceiling and aborts mid-run if spend exceeds it.

```bash
python -m airsbench.runner.run --main --n-queries 80 --dry-run
```

Datasets are not committed (ESCI ≈ 100 MB, BTS ≈ 75 MB):

```bash
.venv/bin/pip install -e ".[data]"
make data-ecommerce && make data-airline
```

---

## Layout

```
src/agentic_faults/      four record-level fault injectors + verification (stdlib only)
src/airsbench/airs/      AIRS operational definitions, calculator, calibrated weights
src/airsbench/agents/    LLM client, prompts, retrieval + classification agents
src/airsbench/pipelines/ Kafka wrappers, Airflow DAG, catalog time machine
src/airsbench/gate/      admission control: Policy, Controller, offline policy replay
src/airsbench/runner/    grid, staged execution, scoring, benchmark_runs schema
src/airsbench/analysis/  one module per research question — all free to re-run
src/airsbench/dataprep/  dataset preparation + free sensitivity check
demo/                    AIST demo (Next.js, static export, pre-baked data)
docs/                    research plan, methodology, literature, findings
results/runs/            302 run artifacts — the evidence behind every number
results/discarded/       runs from superseded designs — evidence, not data
```

## Methodological commitments

- **The agent is the instrument, not the subject.** The prompt never mentions
  faults or hints that data may be degraded.
- **Paired design.** Query sampling derives from `(task, replication)` only, so
  every condition within a replication sees identical inputs at identical
  simulated timestamps. The fault realization is the treatment and varies.
- **Ground truth is the true world state at query time**, never what the agent
  was served. That asymmetry is the experiment.
- **Unparseable output is a failure, not an error**, and is never retried —
  refusing or emitting garbage under degraded data is the phenomenon being
  measured.
- **Arms are quarantined by seed block**, so any run is attributable to the arm
  that produced it from the artifact alone.
- Negative results reported in full. All results with 95% intervals and effect
  sizes.

The full set of invariants — the ones whose violation would silently corrupt
results while leaving tests green — is in [`CLAUDE.md`](CLAUDE.md). Each is
pinned by a test.

## Status

Every experimental arm needed for the five research questions is complete and
analysed. One **provisional** arm is mid-flight: a fault-interaction study
testing whether two simultaneous faults compose additively, which matters
because AIRS's composite is a weighted sum fitted on runs where only one
dimension was ever degraded. It is quarantined by seed block and barred from the
canonical dataset; design in [`docs/interaction_arm.md`](docs/interaction_arm.md).
Roughly half its runs are on disk. It is not part of any current claim.

Remaining work is Chapters 1, 2, 4 and 5.

License: [MIT](LICENSE)
