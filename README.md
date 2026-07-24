# AIRS-Bench — Characterizing the Data Infrastructure Gap for Agentic AI Systems

Master's thesis implementation — Shamsiddin Khamidov, M.Sc. Software
Engineering, IT Park University, 2026.

**The claim under study:** agentic AI systems fail in production because of
the data infrastructure feeding them, not the model. This repo measures
that claim: the agent is the *measurement instrument*; the infrastructure
is the subject.

**The artifacts:**

| Artifact | What it is |
|---|---|
| `agentic_faults` | Record-level fault injector: freshness, latency, schema drift, semantic stripping — the study's technical core |
| Benchmark | ~144-run full factorial: 2 pipelines × 4 faults × 2 severities × 2 tasks × 4 reps (+ baselines) |
| **AIRS** | Agentic Infrastructure Readiness Score (0–100); weights derived from the benchmark by logistic regression, never assumed |
| **AIST** | Streamlit demo: fault sliders → live AIRS radar → agent decisions degrading in real time |

**Industry scenarios:** e-commerce product QA (retrieval — prices/stock
change, so staleness is behaviorally observable) and aviation delay
prediction (classification, BTS On-Time data).

## Quickstart

```bash
make setup          # venv + dev install
make test           # unit tests incl. injector verification mode
make grid           # inspect the full experiment grid (dry run)
make up             # Kafka (KRaft) + Airflow + Postgres + Prometheus
make demo           # AIST v0 (requires: pip install -e ".[demo]")
```

Datasets (not committed; ~sizes: ESCI subset ≈ 100 MB, BTS ≈ 3 × 25 MB):

```bash
.venv/bin/pip install -e ".[data]"
make data-ecommerce
make data-airline
```

## Layout

```
src/agentic_faults/      fault injector package (stdlib-only, releasable standalone)
src/airsbench/airs/      AIRS operational definitions + calculator
src/airsbench/agents/    LangGraph agents (Week 3)
src/airsbench/pipelines/ Kafka wrappers + Airflow DAG
src/airsbench/runner/    experiment grid, runner CLI, benchmark_runs schema
src/airsbench/dataprep/  dataset preparation (ESCI, BTS On-Time)
tests/                   unit + verification tests (CI on every commit)
demo/                    AIST Streamlit app
docker/                  Prometheus + Postgres init
notebooks/               statistical analysis (Week 6)
```

## Methodological commitments

- Model, prompt, dataset, hardware held constant; only infrastructure
  conditions vary. Temperature 0 (classification) / 0.2 (retrieval).
- Every run has a deterministic seed; any single run reproduces in isolation.
- `benchmark_runs` (Postgres) is the canonical dataset; Prometheus is
  demo observability only.
- Injector verification mode asserts injected == configured (±200 ms for
  freshness) and runs in CI.
- All results reported with 95% CIs and effect sizes; negative results
  reported in full.

## Roadmap (4-week compressed schedule)

- [x] W1: scaffold — injectors + tests, compose env, grid, schema, AIST v0
- [ ] W1: datasets prepared; environment verified end-to-end
- [ ] W2: agent harness + scoring; baselines; **pilot (30 runs) → go/no-go**
- [ ] W3: main campaign (~144 runs); statistical analysis; AIRS calibration
- [ ] W4: AIST full demo; open-source release (HuggingFace + Zenodo); thesis chapters

License: MIT

## Experimental arms

Beyond the main factorial, two arms exist because the related-work review
required them (see `docs/related_work_positioning.md`):

```bash
python -m airsbench.runner.run --freshness-sweep --n-queries 150   # RQ1 monotonicity, ~$1
python -m airsbench.runner.run --cross-model <model> --n-queries 150  # generalization, ~$0.50
```

The freshness sweep exists because Shisher & Sun (MobiHoc 2022) show error
need not be monotonic in data age, and two severity levels cannot tell the
difference. The cross-model arm exists because comparable 2026 studies use
2–8 models; the claim that generalizes is the *ranking* of infrastructure
properties, not the absolute thresholds.
