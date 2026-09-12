"""Kafka streaming pipeline wrappers (thin by design).

Single-broker KRaft cluster (infra_unused/docker-compose.yml), two topics per task:
``<dataset>.baseline`` and ``<dataset>.faulted``. Latency is measured
between produce and consumer handoff — this feeds the AIRS latency
dimension. confluent-kafka is imported lazily so the core package and
tests never require it.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Iterable

from agentic_faults import Record

DEFAULT_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")


def _record_to_wire(record: Record) -> bytes:
    return json.dumps(
        {
            "payload": record.payload,
            "context": record.context,
            "event_timestamp": record.event_timestamp,
        }
    ).encode()


def _record_from_wire(raw: bytes) -> Record:
    data = json.loads(raw.decode())
    record = Record(
        payload=data["payload"],
        context=data.get("context", {}),
        event_timestamp=data["event_timestamp"],
    )
    record.read_timestamp = time.time()
    return record


def produce_records(
    topic: str, records: Iterable[Record], bootstrap: str = DEFAULT_BOOTSTRAP
) -> int:
    from confluent_kafka import Producer  # lazy: pipelines extra only

    producer = Producer({"bootstrap.servers": bootstrap})
    count = 0
    for record in records:
        producer.produce(topic, _record_to_wire(record))
        count += 1
    producer.flush()
    return count


def consume_records(
    topic: str,
    handler: Callable[[Record], Any],
    limit: int,
    bootstrap: str = DEFAULT_BOOTSTRAP,
    group_id: str = "airsbench",
    timeout_s: float = 30.0,
) -> int:
    from confluent_kafka import Consumer  # lazy: pipelines extra only

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([topic])
    seen = 0
    deadline = time.time() + timeout_s
    try:
        while seen < limit and time.time() < deadline:
            msg = consumer.poll(0.5)
            if msg is None or msg.error():
                continue
            handler(_record_from_wire(msg.value()))
            seen += 1
    finally:
        consumer.close()
    return seen
