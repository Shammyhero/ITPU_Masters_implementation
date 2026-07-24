"""Execute one benchmark run end-to-end: config in, one result row out.

Pipeline of a run (research plan §4.2):
  load data -> configure fault condition -> deliver records to the agent
  -> agent decides -> score against ground truth -> compute AIRS -> record

The ground truth is always the TRUE state of the world at query time,
never the state the agent was served. That asymmetry is the experiment.
"""

from __future__ import annotations

import json
import random
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_faults import (
    FaultChain,
    FreshnessInjector,
    LatencyInjector,
    Record,
    SchemaDriftInjector,
    SemanticStrippingInjector,
)

from ..agents import ClassificationAgent, LLMClient, RetrievalAgent
from ..airs import (
    AIRSCalculator,
    freshness_score,
    latency_score,
    mean_semantic_completeness,
    payload_consistency,
    semantic_score,
)
from ..pipelines.loader import (
    CatalogTimeMachine,
    build_flight_record,
    build_product_record,
    load_semantic_context,
    stale_dep_delay,
)
from .config import RunConfig
from .scoring import RunMetrics, failure_modes, score_binary, score_retrieval

# Batch pipelines serve data assembled at the last scheduled load, so the
# archetype carries inherent staleness even with no fault injected. A real
# 10-minute DAG interval implies ~300 s mean age, which on a high-velocity
# catalog floors batch accuracy in every condition — a floor effect that
# would mask how the other three faults affect the batch arm. Runs
# therefore model a compressed cycle of one catalog update interval
# (~10 s). Stated as a limitation: real batch deployments fare worse on
# freshness than this study's batch arm.
BATCH_INHERENT_STALENESS_S = 10.0
STREAMING_INHERENT_STALENESS_S = 0.05
N_CANDIDATES = 6


@dataclass
class RunResult:
    run_id: str
    config: dict[str, Any]
    started_at: str
    finished_at: str
    metrics: dict[str, Any]
    airs: dict[str, float]
    usage: dict[str, Any]
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def save(self, out_dir: str | Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.run_id}.json"
        path.write_text(json.dumps(asdict(self), indent=2, default=str))
        return path


def build_fault_chain(config: RunConfig) -> FaultChain:
    """Injectors for this run's condition. Freshness is handled by the
    loader (values must genuinely be old), so the injector here only
    stamps the timestamps AIRS reads."""
    injectors = []
    params = config.injector_params
    if config.fault_type == "freshness":
        injectors.append(FreshnessInjector(seed=config.seed, **params))
    elif config.fault_type == "latency":
        injectors.append(LatencyInjector(seed=config.seed, sleep=True, **params))
    elif config.fault_type == "schema_drift":
        injectors.append(SchemaDriftInjector(seed=config.seed, **params))
    elif config.fault_type == "semantic_stripping":
        injectors.append(SemanticStrippingInjector(seed=config.seed, **params))
    return FaultChain(injectors)


def value_staleness_s(config: RunConfig) -> float:
    """Total staleness of the VALUES the agent is served."""
    inherent = (
        BATCH_INHERENT_STALENESS_S
        if config.pipeline == "batch"
        else STREAMING_INHERENT_STALENESS_S
    )
    injected = (
        float(config.injector_params.get("delay_seconds", 0.0))
        if config.fault_type == "freshness"
        else 0.0
    )
    return inherent + injected


def _airs_components(
    baseline: list[Record], delivered: list[Record], mean_age_s: float
) -> dict[str, float]:
    mean_latency = statistics.fmean(
        [r.meta.get("injected_latency_ms", 0) for r in delivered] or [0.0]
    )
    consistency = statistics.fmean(
        [payload_consistency(b, d) for b, d in zip(baseline, delivered)] or [1.0]
    )
    return {
        "freshness": freshness_score(max(mean_age_s, 1e-6)),
        "latency": latency_score(max(mean_latency, 1.0)),
        "consistency": 100.0 * consistency,
        "semantic": semantic_score(mean_semantic_completeness(delivered)),
    }


def run_retrieval(config: RunConfig, data_dir: Path, client: LLMClient) -> tuple[
    RunMetrics, dict[str, float], list[dict[str, Any]]
]:
    import pandas as pd

    rng = random.Random(config.seed)
    machine = CatalogTimeMachine.load(data_dir)
    context = load_semantic_context(data_dir)
    queries = pd.read_parquet(data_dir / "queries.parquet").to_dict("records")

    chain = build_fault_chain(config)
    agent = RetrievalAgent(client, fault_chain=chain)
    staleness = value_staleness_s(config)

    correct_flags: list[bool] = []
    confidences: list[float] = []
    decisions: list[dict[str, Any]] = []
    baseline_all: list[Record] = []
    delivered_all: list[Record] = []
    ages: list[float] = []

    usable = [q for q in queries if len(q["relevant_product_ids"]) >= 2]
    sampled = rng.sample(usable, min(config.n_queries, len(usable)))

    for query in sampled:
        # Query time: a random point late in the update stream, so there
        # is always history to be stale against.
        t_query = rng.uniform(machine.max_ts * 0.5, machine.max_ts)
        truth_state = machine.state_at(t_query)
        served_state = machine.state_at(max(0.0, t_query - staleness))

        ids = [str(pid) for pid in query["relevant_product_ids"]][:N_CANDIDATES]
        ids = [pid for pid in ids if pid in truth_state]
        if len(ids) < 2:
            continue

        truth = RetrievalAgent.ground_truth([truth_state[pid] for pid in ids])
        if truth is None:
            continue  # nothing in stock: no well-defined answer

        now = time.time()
        served = [
            build_product_record(served_state[pid], context, event_ts=now - staleness)
            for pid in ids
        ]
        for record in served:
            record.read_timestamp = now
        baseline_records = [r.clone() for r in served]

        decision = agent.decide(query["query"], served, truth)
        faulted = [chain.apply(r) for r in baseline_records]

        correct_flags.append(decision.correct)
        confidences.append(decision.confidence)
        baseline_all.extend(baseline_records)
        delivered_all.extend(faulted)
        ages.extend(r.age_seconds(at=now) for r in faulted)
        decisions.append(
            {
                "query": query["query"],
                "chosen": decision.product_id,
                "ground_truth": decision.ground_truth_id,
                "correct": decision.correct,
                "confidence": decision.confidence,
                "parse_failed": decision.parse_failed,
                "abstained": decision.abstained,
            }
        )

    metrics = score_retrieval(correct_flags, confidences, client.usage.parse_failures)
    metrics.abstention_rate, metrics.silent_failure_rate = failure_modes(decisions)
    airs = _airs_components(baseline_all, delivered_all, statistics.fmean(ages or [0.0]))
    return metrics, airs, decisions


def run_classification(config: RunConfig, data_dir: Path, client: LLMClient) -> tuple[
    RunMetrics, dict[str, float], list[dict[str, Any]]
]:
    import pandas as pd

    context = load_semantic_context(data_dir)
    flights = pd.read_parquet(data_dir / "flights.parquet")
    sampled = flights.sample(
        n=min(config.n_queries, len(flights)), random_state=config.seed
    ).to_dict("records")

    chain = build_fault_chain(config)
    agent = ClassificationAgent(client, fault_chain=chain)
    staleness = value_staleness_s(config)

    labels: list[int] = []
    predictions: list[int] = []
    scores: list[float] = []
    decisions: list[dict[str, Any]] = []
    baseline_all: list[Record] = []
    delivered_all: list[Record] = []
    ages: list[float] = []

    for flight in sampled:
        label = int(flight["ArrDel15"])
        served = dict(flight)
        # Stale feature store: the delay signal accrued only partially.
        served["DepDelay"] = stale_dep_delay(float(flight["DepDelay"]), staleness)

        now = time.time()
        record = build_flight_record(served, context, event_ts=now - staleness)
        record.read_timestamp = now
        baseline_record = record.clone()

        decision = agent.decide(record, label)
        faulted = chain.apply(baseline_record)

        labels.append(label)
        predictions.append(decision.predicted if decision.predicted is not None else 0)
        scores.append(decision.score)
        baseline_all.append(baseline_record)
        delivered_all.append(faulted)
        ages.append(faulted.age_seconds(at=now))
        decisions.append(
            {
                "origin": flight["Origin"],
                "dest": flight["Dest"],
                "predicted": decision.predicted,
                "label": label,
                "correct": decision.correct,
                "confidence": decision.confidence,
                "parse_failed": decision.parse_failed,
                "abstained": decision.abstained,
            }
        )

    metrics = score_binary(labels, predictions, scores, client.usage.parse_failures)
    metrics.abstention_rate, metrics.silent_failure_rate = failure_modes(decisions)
    airs = _airs_components(baseline_all, delivered_all, statistics.fmean(ages or [0.0]))
    return metrics, airs, decisions


def execute_run(
    config: RunConfig,
    data_root: Path = Path("data"),
    out_dir: Path = Path("results/runs"),
    calculator: AIRSCalculator | None = None,
) -> RunResult:
    started = datetime.now(timezone.utc)
    client = LLMClient(model=config.model, temperature=config.temperature or 0.0)

    if config.task == "retrieval":
        metrics, airs, decisions = run_retrieval(config, data_root / "ecommerce", client)
    else:
        metrics, airs, decisions = run_classification(config, data_root / "airline", client)

    calculator = calculator or AIRSCalculator()
    airs = dict(airs)
    airs["total"] = calculator.composite(
        {k: v for k, v in airs.items() if k != "total"}
    )

    result = RunResult(
        run_id=config.run_id or str(uuid.uuid4()),
        config=config.to_dict(),
        started_at=started.isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        metrics={
            "accuracy": metrics.accuracy,
            "f1": metrics.f1,
            "auc_roc": metrics.auc_roc,
            "n": metrics.n,
            "parse_failures": metrics.parse_failures,
            "abstention_rate": metrics.abstention_rate,
            "silent_failure_rate": metrics.silent_failure_rate,
            "llm_latency_ms_p50": (
                statistics.median(client.usage.latencies_ms)
                if client.usage.latencies_ms
                else None
            ),
        },
        airs=airs,
        usage={
            "calls": client.usage.calls,
            "input_tokens": client.usage.input_tokens,
            "output_tokens": client.usage.output_tokens,
            "cost_usd": round(client.usage.cost_usd(config.model), 6),
        },
        decisions=decisions,
    )
    result.save(out_dir)
    return result
