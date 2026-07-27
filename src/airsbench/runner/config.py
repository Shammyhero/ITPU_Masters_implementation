"""Experiment configuration: the single source of truth for the factorial.

Design (research plan Table 4.2): 2 pipelines x 4 fault types x 2
severities x 2 tasks x ~4 replications, plus baseline (no-fault) runs.
Severity presets are the exact values from research plan §4.2.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

PIPELINES = ("batch", "streaming")
FAULT_TYPES = ("freshness", "latency", "schema_drift", "semantic_stripping")
SEVERITIES = ("mild", "severe")
TASKS = ("retrieval", "classification")

TASK_DATASETS = {
    "retrieval": "ecommerce_esci",       # e-commerce product QA (industry scenario)
    "classification": "airline_ontime",  # aviation delay prediction (industry scenario)
}

SEVERITY_PARAMS: dict[str, dict[str, dict[str, Any]]] = {
    "freshness": {
        "mild": {"delay_seconds": 1.5},
        "severe": {"delay_seconds": 5.0},
    },
    "latency": {
        "mild": {"spike_ms": 500},
        "severe": {"spike_ms": 3000},
    },
    "schema_drift": {
        "mild": {"drift_probability": 0.05},
        "severe": {"drift_probability": 0.25},
    },
    "semantic_stripping": {
        "mild": {"strip_rate": 0.30},
        "severe": {"strip_rate": 0.80},
    },
}

# Freshness sweep for the monotonicity test (docs/related_work_positioning.md
# §4). Shisher & Sun (MobiHoc 2022) prove that prediction error need not be
# monotonic in data age; the main factorial's two severities cannot
# distinguish monotonic from non-monotonic response, because two points
# always look monotonic. These levels span sub-threshold to well past the
# batch arm's inherent staleness.
FRESHNESS_SWEEP_SECONDS = (0.5, 1.5, 3.0, 5.0, 8.0, 12.0)

DEFAULT_MODEL = "gpt-4o-mini"
# Methodological commitment (research plan §6.3): temperature fixed per
# task family, seeds documented, model constant across all conditions.
TASK_TEMPERATURE = {"retrieval": 0.2, "classification": 0.0}
DEFAULT_N_QUERIES = 150


@dataclass
class RunConfig:
    """Configuration of a single benchmark run -> one row in benchmark_runs."""

    pipeline: str
    fault_type: str  # one of FAULT_TYPES or "none" (baseline)
    severity: str    # "mild" | "severe" | "none"
    task: str
    replication: int
    injector_params: dict[str, Any] = field(default_factory=dict)
    dataset: str = ""
    model: str = DEFAULT_MODEL
    temperature: float | None = None
    n_queries: int = DEFAULT_N_QUERIES
    seed: int = 0
    sample_seed: int = 0
    # Detectability arm only: deliver each record's own age alongside it.
    # False everywhere in the main factorial, so that grid is unaffected.
    emit_record_age: bool = False
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.dataset:
            self.dataset = TASK_DATASETS[self.task]
        if self.temperature is None:
            self.temperature = TASK_TEMPERATURE[self.task]
        # PAIRED DESIGN. The sampling seed depends only on (task, replication),
        # never on the experimental condition, so every condition within a
        # replication is evaluated on the IDENTICAL queries at identical
        # simulated timestamps. The fault is then the only difference between
        # conditions, which is what makes the comparison paired.
        #
        # `seed` (condition-specific) continues to drive the fault injectors —
        # the fault realization is the treatment and should vary by condition.
        #
        # Phase-1 evidence for why this matters: with per-condition sampling,
        # query-sample variance alone produced a severe-latency run scoring 22
        # points ABOVE its baseline, which is impossible since analytic latency
        # cannot change what the agent reads.
        if not self.sample_seed:
            self.sample_seed = 10_000 * (TASKS.index(self.task) + 1) + self.replication

    def label(self) -> str:
        age = "+age" if self.emit_record_age else ""
        return (
            f"{self.pipeline}/{self.task}/{self.fault_type}"
            f"/{self.severity}{age}/rep{self.replication}"
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_grid(replications: int = 4, include_baseline: bool = True) -> list[RunConfig]:
    """Full factorial grid. Seeds are derived deterministically from the
    condition index so any single run can be reproduced in isolation."""
    grid: list[RunConfig] = []
    conditions: list[tuple[str, str, str, str, dict[str, Any]]] = []

    for pipeline in PIPELINES:
        for task in TASKS:
            if include_baseline:
                conditions.append((pipeline, task, "none", "none", {}))
            for fault in FAULT_TYPES:
                for severity in SEVERITIES:
                    conditions.append(
                        (pipeline, task, fault, severity, SEVERITY_PARAMS[fault][severity])
                    )

    # Replication-major order: replication is the OUTER loop, so the first
    # len(conditions) runs are one complete balanced replication of the whole
    # design. A campaign stopped or staged partway therefore yields a balanced
    # design at lower replication rather than a subset of conditions at full
    # replication — which is what makes phase 1 a usable go/no-go checkpoint
    # (methodology §3.7.1). Seeds are derived from (condition, replication),
    # so they are unaffected by execution order.
    for rep in range(1, replications + 1):
        for cond_idx, (pipeline, task, fault, severity, params) in enumerate(conditions):
            grid.append(
                RunConfig(
                    pipeline=pipeline,
                    task=task,
                    fault_type=fault,
                    severity=severity,
                    replication=rep,
                    injector_params=dict(params),
                    seed=1000 * cond_idx + rep,
                )
            )
    return grid


def build_freshness_sweep(
    replications: int = 3,
    pipeline: str = "streaming",
    tasks: tuple[str, ...] = TASKS,
    model: str = DEFAULT_MODEL,
) -> list[RunConfig]:
    """Freshness at many severities, for testing monotonicity (RQ1).

    Streaming only by default: the batch arm carries ~10 s of inherent
    staleness, which would confound the low end of the sweep.
    """
    grid: list[RunConfig] = []
    for task_idx, task in enumerate(tasks):
        for level_idx, delay in enumerate(FRESHNESS_SWEEP_SECONDS):
            for rep in range(1, replications + 1):
                grid.append(
                    RunConfig(
                        pipeline=pipeline,
                        task=task,
                        fault_type="freshness",
                        severity=f"sweep_{delay:g}s",
                        replication=rep,
                        injector_params={"delay_seconds": delay},
                        model=model,
                        seed=50000 + 1000 * task_idx + 100 * level_idx + rep,
                    )
                )
    return grid


def build_detectability_arm(
    replications: int = 3,
    severity: str = "severe",
    model: str = DEFAULT_MODEL,
) -> list[RunConfig]:
    """Hold the fault constant; vary only whether it is detectable.

    Design and rationale: docs/detectability_arm.md. The main factorial compares
    detectability *across* fault types, which confounds the kind of corruption
    with whether it is legible. This arm holds staleness fixed and varies one
    thing — whether the record carries its own age — which makes detectability a
    manipulated variable rather than an observed correlate.

    14 runs:
      12  freshness/{severity} x {age absent, age present} x 2 tasks x 3 reps
       2  baseline WITH age, one per task

    The baselines carry the metadata deliberately. Baselines *without* it are
    already established by the main factorial's 36 retrieval + 30 classification
    runs, so the open question is the over-caution branch: shown an age of
    ~0.05 s on fresh data, does the agent start abstaining anyway? Without that
    cell a rise in abstention under B could not be attributed to staleness
    rather than to the mere presence of a metadata field.

    Streaming only: batch's inherent 3 s staleness would blur the contrast, and
    the flip-partition analysis shows the batch baseline is already flipping
    7.1% of answers before any fault is injected.

    Paired throughout. Within a replication the A and B members of a pair share
    `sample_seed` (identical queries at identical simulated times, via
    RunConfig.__post_init__) and `seed` (identical fault realization), so the
    delivered records are byte-identical apart from the age field.
    """
    grid: list[RunConfig] = []

    for task_idx, task in enumerate(TASKS):
        for rep in range(1, replications + 1):
            # One seed per (task, rep) pair, shared by both metadata arms:
            # the fault realization is held constant so it cannot be confounded
            # with the treatment.
            seed = 60_000 + 1_000 * task_idx + rep
            for emit_age in (False, True):
                grid.append(
                    RunConfig(
                        pipeline="streaming",
                        task=task,
                        fault_type="freshness",
                        severity=severity,
                        replication=rep,
                        injector_params=dict(SEVERITY_PARAMS["freshness"][severity]),
                        model=model,
                        seed=seed,
                        emit_record_age=emit_age,
                    )
                )

    for task_idx, task in enumerate(TASKS):
        grid.append(
            RunConfig(
                pipeline="streaming",
                task=task,
                fault_type="none",
                severity="none",
                replication=1,
                model=model,
                seed=69_000 + task_idx,
                emit_record_age=True,
            )
        )
    return grid


def build_cross_model_subset(
    model: str, replications: int = 2, severity: str = "severe"
) -> list[RunConfig]:
    """A reduced factorial on a second model, for generalization.

    Answers the reviewer question the comparison papers invite (they use
    2-8 models; this study's primary arm uses one): does the RANKING of
    infrastructure properties hold across model classes? Only the ranking
    is claimed to generalize, not the absolute thresholds.
    """
    grid: list[RunConfig] = []

    # One baseline per task on this model, so degradation is measured
    # against this model's own ceiling, not the primary model's.
    for task_idx, task in enumerate(TASKS):
        grid.append(
            RunConfig(
                pipeline="streaming",
                task=task,
                fault_type="none",
                severity="none",
                replication=1,
                model=model,
                seed=79000 + task_idx,
            )
        )

    conditions = [(t, f) for t in TASKS for f in FAULT_TYPES]
    for cond_idx, (task, fault) in enumerate(conditions):
        for rep in range(1, replications + 1):
            grid.append(
                RunConfig(
                    pipeline="streaming",
                    task=task,
                    fault_type=fault,
                    severity=severity,
                    replication=rep,
                    injector_params=dict(SEVERITY_PARAMS[fault][severity]),
                    model=model,
                    seed=70000 + 100 * cond_idx + rep,
                )
            )
    return grid
