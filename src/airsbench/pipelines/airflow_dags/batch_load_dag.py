"""Batch pipeline DAG: scheduled dataset loading into Postgres.

Represents the batch archetype (research plan §6.2): a parameterizable
DAG that loads the next slice of the prepared dataset into Postgres on a
configurable schedule (default: every 10 minutes). Freshness at the
consumer end = read_time − record event_time, which grows between runs —
exactly the staleness profile batch pipelines exhibit in production.

This file runs INSIDE the Airflow container (mounted via
docker-compose.yml); it is not imported by the airsbench package.
"""

from __future__ import annotations

from datetime import datetime

from airflow.decorators import dag, task


@dag(
    dag_id="airs_batch_load",
    schedule="*/10 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["airs-bench"],
    params={"dataset": "airline_ontime", "batch_size": 500},
)
def airs_batch_load():
    @task
    def load_next_batch(**context) -> int:
        """Load the next slice of the dataset into Postgres.

        Week 3 wires the real loader; the heartbeat below verifies the
        DAG schedules and connects correctly in the Week 1 environment.
        """
        import logging

        params = context["params"]
        logging.info(
            "batch_load heartbeat: dataset=%s batch_size=%s",
            params["dataset"],
            params["batch_size"],
        )
        return 0

    load_next_batch()


airs_batch_load()
