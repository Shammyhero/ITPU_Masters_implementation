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
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.dataset:
            self.dataset = TASK_DATASETS[self.task]
        if self.temperature is None:
            self.temperature = TASK_TEMPERATURE[self.task]

    def label(self) -> str:
        return (
            f"{self.pipeline}/{self.task}/{self.fault_type}"
            f"/{self.severity}/rep{self.replication}"
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

    for cond_idx, (pipeline, task, fault, severity, params) in enumerate(conditions):
        for rep in range(1, replications + 1):
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
