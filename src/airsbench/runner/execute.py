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
from .config import COMPOSITION_ORDER, RunConfig, fault_components
from .scoring import RunMetrics, failure_modes, score_binary, score_retrieval

# Batch pipelines serve data assembled at the last scheduled load, so the
# archetype carries inherent staleness even with no fault injected.
#
# This constant was 10.0 s and had to be lowered. At 10 s it exactly equalled
# DEP_DELAY_KNOWLEDGE_HORIZON_S, so every flight in every batch classification
# run was presented as departing precisely on time: the dominant predictive
# feature was zeroed, the arm scored BELOW chance (0.438 on a balanced task),
# and fault severity made no difference because the floor had been reached.
# Batch retrieval was likewise depressed to a ~0.79 ceiling by a 21% answer-flip
# rate before any fault was injected.
#
# At 3 s the batch arm remains meaningfully stale (~8% answer-flip on
# retrieval; ~70% of the delay signal retained on classification) and still
# degrades further when a freshness fault stacks on top, without flooring
# either task. Stated as a limitation: a real 10-minute DAG implies ~300 s and
# would fare far worse than this study's batch arm.
BATCH_INHERENT_STALENESS_S = 3.0
STREAMING_INHERENT_STALENESS_S = 0.05
N_CANDIDATES = 6

# Where attach_record_age parks the age, and the field name the agent sees.
# Kept in meta rather than payload so the AIRS payload dimensions cannot see it.
RECORD_AGE_META_KEY = "record_age_seconds"


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


def attach_record_age(record: Record, now: float) -> None:
    """Deliver the record's own age alongside it — the detectability treatment.

    The manipulated variable of the detectability arm (docs/detectability_arm.md).
    Under a freshness fault the served values are well-formed and the world has
    simply moved on, so nothing in the record marks it as wrong; the agent is
    asked to notice something it was never told. This attaches what a pipeline
    that shipped freshness metadata would have shipped.

    Three properties this must hold to:

    - **Truthful.** The age is measured from the post-chain record, so it is the
      real age of the values the loader served (see ``build_event_ts``). An
      overstated age would confound detectability with being lied to.
    - **Applied after the fault chain**, never inside it. The metadata is not a
      fault; it is what the pipeline chose to deliver about one.
    - **Not part of the payload.** It goes in ``meta``, so AIRS consistency and
      semantic completeness — which read ``payload`` and ``context`` — are
      untouched, and the metadata cannot masquerade as a data field
      (invariant 5).

    The prompt is not changed and never mentions age or staleness. The metadata
    is offered; whether the agent uses it is the measurement.
    """
    record.meta[RECORD_AGE_META_KEY] = round(record.age_seconds(at=now), 2)


def build_fault_chain(config: RunConfig) -> FaultChain:
    """Injectors for this run's condition.

    Freshness is handled by the loader (values must genuinely be old), so the
    injector here only stamps the timestamps AIRS reads.

    Latency runs in analytic mode: the injected delay is recorded for the AIRS
    latency dimension but not slept. Sleeping cannot change what the agent
    reads, so it cannot change accuracy — it would only add wall-clock time
    (hours, at severe severity across the retrieval arm). Reported in the
    methodology as a measurement choice, not a modelling one.
    """
    components = fault_components(config.fault_type)
    injectors = [
        _build_injector(name, _injector_seed(config, name, len(components)),
                        _params_for(config, name, len(components)))
        for name in components
    ]
    return FaultChain(injectors)


def _nested(config: RunConfig, name: str, n_components: int) -> bool:
    """Is this condition written in the compound (per-fault) shape?

    One detection for both the parameters and the seed, so the two can never
    disagree about which shape a condition is in.
    """
    return n_components > 1 or isinstance(config.injector_params.get(name), dict)


def _injector_seed(config: RunConfig, name: str, n_components: int) -> int:
    """The RNG seed for one injector: `config.seed`, unless the run is compound.

    Per-component streams exist to keep two injectors in one run off the same
    draws (see `_component_seed`); a single injector cannot correlate with
    anything, so a flat single-fault condition is seeded with `config.seed`
    itself. That is also what the corpus did: the main factorial and the
    cross-model arm (26 Jul – 31 Jul) predate `_component_seed`, which arrived
    with the interaction arm. Deriving a component seed for them made their
    recorded fault realizations irreproducible from their own configs — the
    realization is the treatment, so that broke the artifact claim that any run
    replays in isolation, while leaving every published number untouched
    (artifacts are canonical, invariant 7).

    Keyed on the parameter shape rather than on a date or an arm: the
    interaction arm writes even its solo conditions in the nested shape, so the
    shape separates the two seed regimes exactly. All 124 drift/stripping runs
    on disk regenerate their logged consistency and semantic scores under this
    rule. → `tests/test_fault_realization.py`, REVIEW F-E7.
    """
    if not _nested(config, name, n_components):
        return config.seed
    return _component_seed(config.seed, name)


def _params_for(config: RunConfig, name: str, n_components: int) -> dict[str, Any]:
    """Injector kwargs, from a flat dict (single fault) or a nested one (compound).

    A compound condition needs per-fault parameters, so `injector_params` is
    keyed by fault name there. Single-fault runs keep the flat shape every
    artifact already on disk uses — `{"delay_seconds": 5.0}`.

    The shape is DETECTED, not inferred from the component count. Deciding by
    count meant a solo condition written in the nested shape was passed straight
    through to the injector, which raised `unexpected keyword argument
    'freshness'` — loudly, and only because the interaction arm happens to write
    its solos that way. A quieter version of the same mistake would have run a
    component at its injector default instead of the declared severity.
    """
    params = config.injector_params
    if not _nested(config, name, n_components):
        return dict(params)
    entry = params.get(name)
    if entry is None:
        raise ValueError(
            f"compound fault {config.fault_type!r} has no injector_params entry "
            f"for {name!r}; a missing entry would silently run that component at "
            f"its injector default rather than at the declared severity"
        )
    return dict(entry)


def _component_seed(seed: int, name: str) -> int:
    """A distinct, deterministic RNG stream per injector within a COMPOUND run.

    Only reached for conditions written in the nested shape (see
    `_injector_seed`); a flat single-fault run uses `config.seed` directly.

    Handing both injectors `config.seed` would give them identical random draws,
    so schema drift and semantic stripping would hit a correlated subset of
    records instead of independent ones. The compound condition would then not
    be "both faults" but "both faults, on the same records" — a different
    treatment, and one that would bias the additivity test.
    """
    return seed + 1_000_003 * (COMPOSITION_ORDER.index(name) + 1)


def _build_injector(name: str, seed: int, params: dict[str, Any]):
    if name == "freshness":
        return FreshnessInjector(seed=seed, **params)
    if name == "latency":
        return LatencyInjector(seed=seed, sleep=False, **params)
    if name == "schema_drift":
        return SchemaDriftInjector(seed=seed, **params)
    if name == "semantic_stripping":
        return SemanticStrippingInjector(seed=seed, **params)
    raise ValueError(f"no injector for fault type {name!r}")


def inherent_staleness_s(config: RunConfig) -> float:
    """Staleness contributed by the pipeline archetype alone, before any fault."""
    return (
        BATCH_INHERENT_STALENESS_S
        if config.pipeline == "batch"
        else STREAMING_INHERENT_STALENESS_S
    )


def value_staleness_s(config: RunConfig) -> float:
    """Total staleness of the VALUES the agent is served."""
    components = fault_components(config.fault_type)
    if "freshness" not in components:
        return inherent_staleness_s(config)
    params = _params_for(config, "freshness", len(components))
    return inherent_staleness_s(config) + float(params.get("delay_seconds", 0.0))


def build_event_ts(config: RunConfig, now: float) -> float:
    """Event timestamp to stamp on a record before the fault chain runs.

    Only the INHERENT staleness is stamped here. FreshnessInjector shifts
    event_timestamp back by the injected delay when it runs, so the record's
    age after the chain is inherent + injected = value_staleness_s — the true
    age of the values the loader served.

    This split is load-bearing. Stamping the full staleness here *and* letting
    the injector shift again double-counts the fault: a severe (5 s) freshness
    run recorded a mean age of 10.05 s against 5.05 s-stale values, so the AIRS
    freshness dimension read roughly half its true score. Nothing the agent saw
    was affected (records carry no timestamp by default), so behavioural results
    from before the fix stand; AIRS freshness from before it does not.
    → tests/test_freshness_accounting.py
    """
    return now - inherent_staleness_s(config)


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

    # Paired design: query sample and query times come from sample_seed,
    # which is identical across conditions within a replication.
    rng = random.Random(config.sample_seed)
    machine = CatalogTimeMachine.load(data_dir)
    context = load_semantic_context(data_dir)
    queries = pd.read_parquet(data_dir / "queries.parquet").to_dict("records")

    chain = build_fault_chain(config)
    agent = RetrievalAgent(client)
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
        event_ts = build_event_ts(config, now)
        served = [
            build_product_record(served_state[pid], context, event_ts=event_ts)
            for pid in ids
        ]
        for record in served:
            record.read_timestamp = now
        baseline_records = [r.clone() for r in served]

        # Apply the fault chain exactly once; the agent and the AIRS
        # measurement must see the identical realization.
        faulted = [chain.apply(r) for r in served]
        if config.emit_record_age:
            for record in faulted:
                attach_record_age(record, now)
        decision = agent.decide(query["query"], faulted, truth)

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
    # Paired design: identical flight sample across conditions within a
    # replication (see RunConfig.sample_seed).
    sampled = flights.sample(
        n=min(config.n_queries, len(flights)), random_state=config.sample_seed
    ).to_dict("records")

    chain = build_fault_chain(config)
    agent = ClassificationAgent(client)
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
        record = build_flight_record(served, context, event_ts=build_event_ts(config, now))
        record.read_timestamp = now
        baseline_record = record.clone()

        # Apply the fault chain exactly once (see run_retrieval).
        faulted = chain.apply(record)
        if config.emit_record_age:
            attach_record_age(faulted, now)
        decision = agent.decide(faulted, label)

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
