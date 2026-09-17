# AIRS-Bench — Characterizing the Data Infrastructure Gap for Agentic AI Systems

Master's thesis implementation — Shamsiddin Khamidov, M.Sc. Software Engineering
(Data Engineering & AI), IT Park University, 2026.

**The claim under study:** agentic AI systems fail in production because of the
data infrastructure feeding them, not the model. This repository measures that
claim. The agent is the *measurement instrument*; the infrastructure is the
subject. Model, prompt, temperature, dataset, scoring and hardware are held
constant — only infrastructure conditions vary.

**Status:** six research questions answered. 302 benchmark runs, 24 270 agent
decisions, 4 models, $5.15 of API spend, 664 tests green. Current work follows
the week-by-week plan in [`docs/plan.md`](docs/plan.md).

---

## What was found

| | Finding |
|---|---|
| **RQ1** | Degradation **is** monotone in data age; threshold at 5.05 s on both tasks. But retrieval decomposes into *exposure* × *conditional rate* — see below. |
| **RQ2** | Rank faults by **residual** impairment, not raw accuracy: schema drift (−0.173) > semantic stripping (−0.128) > freshness (−0.003) ≈ latency (0). |
| **RQ3** | Silent failure is driven by schema drift and semantic stripping on retrieval, freshness on classification. Abstention is driven by semantic stripping **and nothing else** (OR 51.9). |
| **RQ4** | AIRS ranks held-out pipelines at ρ ≈ −0.8 from telemetry alone, and beats the agent's own confidence exactly where that confidence is worthless. |
| **RQ5** | The ranking transfers **across models** but **inverts across tasks**. One pooled weighting would describe neither. |
| **RQ6** | Two faults together **never compound — they saturate.** 5 of 8 pairs are sub-additive, none super-additive, so AIRS's linear composite errs in the safe direction on multi-fault pipelines. |

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
| [`docs/plan.md`](docs/plan.md) | **Current state** — the week-by-week plan, with progress notes |

**Findings, one per research question:**
[flip partition](docs/flip_partition_findings.md) ·
[freshness sweep](docs/freshness_sweep_findings.md) ·
[statistical analysis](docs/statistical_analysis_findings.md) ·
[AIRS calibration](docs/airs_calibration_findings.md) ·
[cross-model](docs/cross_model_findings.md) ·
[detectability](docs/detectability_findings.md) ·
[the gate](docs/gate_findings.md) ·
[fault interaction](docs/interaction_findings.md) ·
[AIRS curve sensitivity](docs/sensitivity_findings.md) ·
[silent-failure definition](docs/silent_definition_findings.md) ·
[query fragility](docs/fragility_findings.md) ·
[power under clustering](docs/power_findings.md) ·
[verifier agreement](docs/verifier_agreement_findings.md)

---

## The tools this produced

Meant to outlive the thesis. None of them makes a model call, needs an API key,
costs anything, or sends records off the machine. All three are one command,
`airs`, from one install — `pip install .` from this repository for now; it is
not yet on PyPI. From a clone, run `make web` first to build the web console
into the package (Node is needed for that, once).

**`airs serve`** — a local web console. Paste or drop a sample of records as
your pipeline delivers them, and see each dimension's score beside its evidence
and its calibrated weight, and how much of that weight the composite actually
rests on. It listens on 127.0.0.1 only; the API behind it is at `/api/docs`.

```bash
airs serve                                             # opens http://127.0.0.1:8000
airs serve --records delivered.jsonl --source upstream.jsonl
```

**`airs probe`** — score a pipeline's readiness *before* deploying an agent on
it. Reads a sample of records as your pipeline delivers them and applies the
weights calibrated in RQ4. A dimension it cannot measure is reported as
`UNMEASURED`, never as 100 — scoring an absent measurement as healthy is the
failure mode that would make the tool dangerous.

```bash
airs probe --records delivered.jsonl --source upstream.jsonl --task retrieval
```

**`airs gate`** — refuse a batch that violates a declared data contract, before
the agent is ever asked. Exit 1 means refused, and the refusal names the rule
and the observed value, because a refusal nobody can act on is just a slower
failure.

```bash
airs gate --records delivered.jsonl --policy examples/gate/retrieval.json
```

**`airs sources`** — the data sources the Analyst will answer from: a bundled demo
slice of the study's own catalog, served exactly the way the benchmark served it
(`demo-healthy`, `demo-stale`, `demo-drift`, `demo-stripped`), plus your own files
declared in a `sources.yaml` (JSONL, CSV, and Parquet with `airs-bench[parquet]`).
Sources are declared, never requested over HTTP, read-only, and credentials never
go in the file.

```bash
airs sources sample demo-stale --seed 7
airs sources --sources sources.yaml list
```

**`airs analyst`** — ask a question of a source and find out whether the answer was
right, and if not, whose fault it was. The answer is re-computed against the system of
record as of the moment it was given, and every wrong one gets a label:
*answer key moved* (the pipeline served values that have since changed), *corrupted in
transit* (fields the answer needs changed on the way), *agent impairment* (the records
arrived intact and the model still got it wrong), or *both*. Answers come from a local
model in your Ollama, or from `literal` — the question executed over the delivered
records at face value. Hosted models arrive with spend caps.

```bash
airs analyst ask demo-stale --questions 5
airs analyst ask demo-drift --answerer ollama/llama3.1:8b
```

`airs probe` and `python -m airsbench.probe` are the same program with the same
exit codes. Timestamps may be epoch seconds or ISO-8601 with a timezone.
Worked examples: [`examples/probe/`](examples/probe/) · [`examples/gate/`](examples/gate/)

---

## Reproducing

```bash
make setup          # venv + dev install
make test           # full test suite, including injector verification
make lint
make grid           # inspect the factorial — no execution, no cost
make ci             # clean-venv install from pyproject.toml + lint + tests
make figures        # regenerate the Chapter 4 figures into docs/figures/
make web            # build the web console into the package (needs Node)
make dist-check     # build the wheel, install it clean, run the installed tools
```

To reproduce with **the exact package versions that produced the published
results**, install from the lockfile instead (Python 3.13):

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
.venv/bin/pip install -e . --no-deps
```

`requirements-lock.txt` is verified by installing it into a clean environment
and running the full suite; `make lock` regenerates it.

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
src/airsbench/pipelines/ catalog time machine + record builders (loader.py)
src/airsbench/gate/      admission control: Policy, Controller, offline policy replay
src/airsbench/server/    `airs serve`: the local API, and the data baked for it
src/airsbench/sources/   declared, read-only data sources: the bundled demo slice, files, inline
src/airsbench/analyst/   the Analyst: checkable question plans, the verifier, answerers
src/airsbench/runner/    grid, staged execution, scoring, benchmark_runs schema
src/airsbench/analysis/  one module per research question — all free to re-run
src/airsbench/dataprep/  dataset preparation + free sensitivity check
demo/                    the web console's source (Next.js, static export, pre-baked evidence)
docs/                    research plan, methodology, literature, findings
infra_unused/            original Kafka/Airflow/Postgres stack — quarantined, used by no result
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

All six research questions are answered and every arm is complete. The
fault-interaction arm (RQ6) finished on 2026-09-10: faults saturate rather than
compound — see [`docs/interaction_findings.md`](docs/interaction_findings.md).

The AIRS scoring curves have been tested for sensitivity to their undocumented
constants: the rankings largely survive, the magnitudes do not —
[`docs/sensitivity_findings.md`](docs/sensitivity_findings.md).

Remaining work, week by week, is in [`docs/plan.md`](docs/plan.md). Next is
**the Analyst** ([`docs/analyst_brief.md`](docs/analyst_brief.md)): live,
gated question answering over your own declared data sources, where every
answer is re-checked against the system of record and each wrong one is
attributed to the pipeline or the model — by mid-October, then the thesis
document.

License: [MIT](LICENSE)
