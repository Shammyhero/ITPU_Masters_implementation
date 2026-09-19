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

# Seed blocks. Each arm draws its seeds from its own range, so a completed run
# can be attributed to the arm that produced it from the artifact alone. This
# matters because arms overlap in condition: the detectability arm and the main
# factorial both contain streaming/freshness/severe runs, and an analysis that
# selected on condition rather than provenance would silently pool them.
#
# Keep these in step with the seed expressions in the builders below; the
# correspondence is asserted in tests/test_seed_blocks.py.
MAIN_SEED_RANGE = (0, 50_000)
SWEEP_SEED_RANGE = (50_000, 60_000)
DETECTABILITY_SEED_RANGE = (60_000, 70_000)
CROSS_MODEL_SEED_RANGE = (70_000, 80_000)
INTERACTION_SEED_RANGE = (80_000, 90_000)
# Reserved, and registered here so a stray artifact from either is ATTRIBUTED
# rather than "unknown": the refetch arm (W6) and the Analyst's live sessions.
# Live traffic never enters results/runs/ at all (analyst/sessions.py), but if a
# Tick is ever copied in by hand, every analysis selects by arm and none accepts
# `live`. → tests/test_live_quarantine.py
REFETCH_SEED_RANGE = (90_000, 100_000)
LIVE_SEED_RANGE = (100_000, 110_000)

SEED_BLOCKS = {
    "main": MAIN_SEED_RANGE,
    "freshness_sweep": SWEEP_SEED_RANGE,
    "detectability": DETECTABILITY_SEED_RANGE,
    "cross_model": CROSS_MODEL_SEED_RANGE,
    "interaction": INTERACTION_SEED_RANGE,
    "refetch": REFETCH_SEED_RANGE,
    "live": LIVE_SEED_RANGE,
}

# ---- fault composition -----------------------------------------------------
#
# The main factorial degrades exactly one dimension per run. AIRS's composite is
# a weighted SUM over dimensions, and `probe`/`gate` apply it to pipelines where
# several dimensions are degraded at once — so the composite's additivity is an
# untested extrapolation. The interaction arm tests it by running fault PAIRS.
#
# COMPOSITION ORDER IS LOAD-BEARING, and only one order is valid.
#
# SchemaDriftInjector renames payload keys (`price` -> `price_v2`).
# SemanticStrippingInjector opaquifies them (`price` -> `f3`) through a STATEFUL
# map keyed on the name it is given. Run drift first and stripping sees
# `price_v2`, so the same semantic field acquires different opaque tokens
# depending on whether drift happened to hit that record — a token instability
# neither fault produces alone, invisible to every AIRS dimension. Applying
# stripping first keeps the map keyed on true field names and yields exactly
# each fault's solo marginal degradation on both dimensions.
# → tests/test_interaction_arm.py::test_composition_preserves_solo_marginals
COMPOSITION_ORDER = ("freshness", "latency", "semantic_stripping", "schema_drift")

# The pairs under test. The two that dominate retrieval and classification
# respectively, their cross, and one control.
INTERACTION_PAIRS = (
    ("freshness", "schema_drift"),
    ("freshness", "semantic_stripping"),
    ("semantic_stripping", "schema_drift"),
    # Method control, not a scientific one: latency has no measurable effect on
    # any outcome, so a correctly specified interaction test must report no
    # interaction here. It validates the test, not the science — see
    # docs/interaction_findings.md on why this control is weaker than it looks.
    ("latency", "schema_drift"),
)


def compose_faults(*names: str) -> str:
    """Canonical label for a compound fault, e.g. 'semantic_stripping+schema_drift'.

    Canonical ordering makes the label commutative: compose_faults(a, b) and
    compose_faults(b, a) are the same string, so a condition cannot be recorded
    under two names.
    """
    unknown = [n for n in names if n not in FAULT_TYPES]
    if unknown:
        raise ValueError(f"unknown fault type(s): {unknown}")
    if len(set(names)) != len(names):
        raise ValueError(f"a fault cannot compose with itself: {names}")
    return "+".join(sorted(set(names), key=COMPOSITION_ORDER.index))


def fault_components(fault_type: str) -> tuple[str, ...]:
    """The faults in a (possibly compound) fault_type, in application order.

    'none' yields (). A single fault yields itself. Every caller that switches
    on fault_type must go through this, or a compound condition will silently
    behave as though it carried no fault at all.
    """
    if fault_type in ("none", ""):
        return ()
    parts = fault_type.split("+")
    unknown = [p for p in parts if p not in FAULT_TYPES]
    if unknown:
        raise ValueError(f"unknown fault type(s) in {fault_type!r}: {unknown}")
    return tuple(sorted(parts, key=COMPOSITION_ORDER.index))


def arm_of(seed: int) -> str:
    """Which arm a seed belongs to; 'unknown' if it falls outside every block."""
    for name, (low, high) in SEED_BLOCKS.items():
        if low <= seed < high:
            return name
    return "unknown"


def run_arm(run: dict) -> str:
    """Arm of a loaded run artifact."""
    return arm_of(run["config"].get("seed", 0))


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


def build_interaction_arm(
    replications: int = 3,
    severity: str = "severe",
    model: str = DEFAULT_MODEL,
) -> list[RunConfig]:
    """Do two faults compose additively? Design in docs/interaction_arm.md.

    Every AIRS composite in this study is a weighted sum, fitted on runs where
    exactly one dimension was ever degraded, and then applied by `airs probe`
    and `airs gate` to pipelines where several are degraded at once — which is
    the normal production case. Additivity is therefore an untested
    extrapolation, and it fails in the unsafe direction: if faults compound,
    AIRS under-predicts risk precisely on the worst pipelines.

    The measurement side is known to compose exactly. Applying stripping then
    drift yields each fault's solo marginal on both dimensions, unchanged
    (invariant 5 holds under composition). So the independent variable is clean
    by construction, and any departure from additivity in the OUTCOME is
    behavioural rather than an artifact of the injectors.

    SELF-CONTAINED, 9 conditions x 2 tasks x `replications`:

        1  baseline (no fault)
        4  each fault alone
        4  the pairs in INTERACTION_PAIRS

    It carries its own solos rather than borrowing the main factorial's, for two
    reasons. The additivity contrast is then paired on *fault realization* as
    well as on queries — a compound run and its two solo runs share the
    component seed, so the same records are hit. And the arm drops as a unit:
    nothing outside `interaction` depends on it, and nothing in it depends on
    anything outside.

    Streaming only. Batch's inherent 3 s staleness would add a fifth degraded
    dimension to every cell and confound the freshness pairs.

    QUARANTINE: `schema.sql` constrains `fault_type` to the four atomic faults,
    so these runs cannot enter Postgres — the canonical dataset (invariant 7) —
    without a deliberate migration. That is intentional while the arm is
    provisional.
    """
    conditions: list[tuple[str, dict[str, Any]]] = [("none", {})]
    for fault in FAULT_TYPES:
        conditions.append((fault, {fault: SEVERITY_PARAMS[fault][severity]}))
    for pair in INTERACTION_PAIRS:
        conditions.append((
            compose_faults(*pair),
            {f: SEVERITY_PARAMS[f][severity] for f in pair},
        ))

    grid: list[RunConfig] = []
    for task_idx, task in enumerate(TASKS):
        for rep in range(1, replications + 1):
            for cond_idx, (fault, params) in enumerate(conditions):
                grid.append(
                    RunConfig(
                        pipeline="streaming",
                        task=task,
                        fault_type=fault,
                        severity="none" if fault == "none" else severity,
                        replication=rep,
                        injector_params=params,
                        model=model,
                        # Seeds are a function of (task, rep) ONLY, not of the
                        # condition. Every condition in a replication therefore
                        # gets the same injector seed, so a pair and its two
                        # solos corrupt the same records — which is what makes
                        # the additivity contrast paired rather than merely
                        # matched. `_component_seed` in execute.py then splits
                        # this into a distinct stream per injector.
                        seed=80_000 + 1_000 * task_idx + rep,
                    )
                )
    return grid
