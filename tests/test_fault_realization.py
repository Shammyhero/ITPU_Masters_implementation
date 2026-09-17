"""The fault realization is the treatment, so it must replay from the config alone.

A run's recorded delivered records are not stored — only the AIRS dimensions
measured from them are. Regenerating a realization is therefore how the corpus
is audited after the fact (`analysis/verifier_agreement.py`), and the check that
it worked is that the regenerated records reproduce the run's logged consistency
and semantic scores exactly.

That failed for the 88 main-factorial and cross-model drift/stripping runs until
2026-09-16: they were executed before `_component_seed`, which arrived with the
interaction arm, so today's chain seeded their injectors differently from the
runner that produced them (REVIEW F-E7). The rule pinned here — `config.seed`
for a flat single fault, per-component streams only for the nested shape the
interaction arm writes — is what every run on disk was actually run under.
"""

from __future__ import annotations

from agentic_faults import Record, SchemaDriftInjector
from airsbench.runner.config import SEVERITY_PARAMS, RunConfig, compose_faults
from airsbench.runner.execute import _component_seed, build_fault_chain

SEED = 6003


def config(**overrides) -> RunConfig:
    base = dict(task="retrieval", pipeline="batch", fault_type="schema_drift",
                severity="severe", seed=SEED, replication=0,
                injector_params={"drift_probability": 0.25})
    return RunConfig(**{**base, **overrides})


def records() -> list[Record]:
    return [Record(payload={"product_id": f"P{i}", "price": 1.0 + i, "stock": i % 3},
                   context={"units": {"price": "USD"}}) for i in range(60)]


def realize(chain) -> list[dict]:
    return [chain.apply(r).payload for r in records()]


def test_a_flat_single_fault_is_seeded_with_the_run_seed_itself():
    """What the main factorial and cross-model arms were run under."""
    assert realize(build_fault_chain(config())) == \
        realize(SchemaDriftInjector(seed=SEED, drift_probability=0.25))


def test_the_nested_shape_keeps_its_per_component_stream():
    """The interaction arm writes solos nested; those runs replay the other way."""
    nested = config(fault_type="schema_drift",
                    injector_params={"schema_drift": {"drift_probability": 0.25}})
    assert realize(build_fault_chain(nested)) == \
        realize(SchemaDriftInjector(seed=_component_seed(SEED, "schema_drift"),
                                    drift_probability=0.25))
    assert realize(build_fault_chain(nested)) != realize(build_fault_chain(config()))


def test_two_injectors_in_one_run_never_share_a_stream():
    """The reason component seeds exist at all: correlated draws would change
    the compound treatment into 'both faults, on the same records'."""
    compound = config(
        fault_type=compose_faults("schema_drift", "semantic_stripping"),
        injector_params={f: SEVERITY_PARAMS[f]["severe"]
                         for f in ("schema_drift", "semantic_stripping")})
    seeds = {_component_seed(SEED, name) for name in ("schema_drift", "semantic_stripping")}
    assert len(seeds) == 2 and SEED not in seeds
    assert len(build_fault_chain(compound).injectors) == 2


def test_a_realization_replays_identically_from_the_same_config():
    assert realize(build_fault_chain(config())) == realize(build_fault_chain(config()))
