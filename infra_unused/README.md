# infra_unused — the infrastructure the original plan specified, and no result uses

**Quarantined 2026-09-13.** Nothing in this directory is imported, executed or
read by any experiment, analysis, test, figure or number in the thesis.

## What is here

| File | What it was for |
|---|---|
| `docker-compose.yml` | Kafka (KRaft) + Airflow + Postgres + Prometheus, as specified in the May 2026 research plan (`docs/research_plan_original.md` §4) |
| `docker/postgres/01_airflow_db.sql` | Airflow's metadata database |
| `docker/prometheus/prometheus.yml` | Live-demo observability scrape config |
| `streaming.py` | Kafka producer/consumer wrappers for the streaming archetype |
| `airflow_dags/batch_load_dag.py` | Scheduled load DAG for the batch archetype |

## Why none of it is used

The experiments simulate the two pipeline archetypes by their **inherent-staleness
signature** rather than by running them:

```python
# src/airsbench/runner/execute.py
BATCH_INHERENT_STALENESS_S     = 3.0
STREAMING_INHERENT_STALENESS_S = 0.05
```

That is the whole difference between "batch" and "streaming" in every result.
It is a deliberate simplification, and it is defensible for one reason: the
flip-partition analysis (`docs/flip_partition_findings.md`) shows that the only
property of a pipeline that reaches the agent's decision is how stale the values
are. A real broker between the loader and the agent would add timing noise
without adding any variable the agent can respond to.

It is still a simplification, and it must be described as one. The thesis says
"simulated pipeline archetypes", not "Kafka and Airflow pipelines".

## Why these files were kept rather than deleted

They are an honest record of what was planned and what was decided against, and
a reviewer comparing the research plan to the implementation should be able to
see both. Deleting them would make the plan look unimplemented; leaving them in
the working tree made the implementation look like something it is not.

## What stayed in the package

- **`src/airsbench/runner/schema.sql`** stays put. Nothing writes to Postgres,
  but its `fault_type` CHECK constraint is what bars compound fault labels from
  the canonical dataset, and `tests/test_interaction_arm.py` pins it.
- **`src/airsbench/pipelines/loader.py`** stays. It is the catalog time machine
  that serves genuinely historical values, and every experiment depends on it.
- The **`pipelines`** extra in `pyproject.toml` (confluent-kafka, psycopg2,
  prometheus-client) serves only this directory.

## Running it anyway

From the repository root:

```bash
docker compose -f infra_unused/docker-compose.yml up -d
docker compose -f infra_unused/docker-compose.yml down
```

Compose resolves relative paths from this directory, which is why the schema
mount reads `../src/airsbench/runner/schema.sql`. The stack starts; nothing in
the study will talk to it.
