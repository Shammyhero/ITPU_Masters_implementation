"""The bundled demo source must serve records exactly the way the study served them.

A demo condition is only worth showing if it IS the corpus condition: the same
catalog replay, the same staleness accounting, faults applied once, and scores
equal to what the runner computed for the same records. If any of these drifts,
the Analyst's verifier-agreement figure (A4) would be measuring the adapter.
"""

from __future__ import annotations

import gzip
import json
import math
import random
import statistics
from pathlib import Path

import pytest

from airsbench.probe import DIMENSIONS, measure
from airsbench.runner.execute import _airs_components, value_staleness_s
from airsbench.sources import to_probe_entry
from airsbench.sources.demo import (
    BUILT_IN,
    SLICE,
    Condition,
    DemoDelivered,
    demo_pair,
    load_slice,
)

DATA = Path("data/ecommerce")
needs_data = pytest.mark.skipif(not (DATA / "updates.jsonl").exists(),
                                reason="data/ecommerce not prepared")
SEED = 100_007


def CLOCK():
    return 1_800_000_000.0


CONDITIONS = {
    **BUILT_IN,
    "latency-severe": Condition("latency", "severe"),
    "sweep-8s": Condition("freshness", "sweep_8s"),
    "batch-healthy": Condition(pipeline="batch"),
}


@pytest.mark.parametrize("name", CONDITIONS)
def test_the_demo_source_scores_exactly_what_the_runner_scored(name):
    """`runner.execute._airs_components` on the records, against the probe fed through
    the adapter: every dimension, every condition, including semantic stripping —
    whose opaque field names must not depress consistency (invariant 5)."""
    pair = demo_pair(name, CONDITIONS[name], seed=SEED, clock=CLOCK)
    for draw in range(3):
        sample = pair.delivered.sample(seed=draw)
        baseline = pair.upstream.fetch(sample.ids, as_of=sample.meta["served_as_of"])
        expected = _airs_components(baseline, sample.records,
                                    statistics.fmean(r.age_seconds() for r in sample.records))
        measured = measure([to_probe_entry(r, i) for r, i in zip(sample.records, sample.ids)],
                           [to_probe_entry(r) for r in baseline])
        for dim in DIMENSIONS:
            assert measured[dim]["score"] == pytest.approx(expected[dim], abs=1e-9), (draw, dim)


@pytest.mark.parametrize("name", CONDITIONS)
def test_delivered_records_are_exactly_as_old_as_the_condition_and_faulted_once(name):
    """A chain applied twice would shift the timestamps twice — the double count that
    once read a 5.05 s record as 10.05 s (tests/test_freshness_accounting.py)."""
    condition = CONDITIONS[name]
    delivered = DemoDelivered(name, condition, seed=SEED, clock=CLOCK)
    staleness = value_staleness_s(condition.run_config(SEED))
    assert delivered.staleness_seconds == pytest.approx(staleness)
    for record in delivered.sample(seed=3).records:
        assert record.age_seconds() == pytest.approx(staleness)


@pytest.mark.parametrize("name", ["demo-healthy", "demo-stale", "sweep-8s"])
def test_delivered_values_are_the_catalog_as_of_t_minus_staleness(name):
    pair = demo_pair(name, CONDITIONS[name], seed=SEED, clock=CLOCK)
    sample = pair.delivered.sample(seed=5)
    assert sample.meta["served_as_of"] == pytest.approx(
        sample.as_of - pair.delivered.staleness_seconds)
    served = load_slice().machine.state_at(sample.meta["served_as_of"])
    for pid, record in zip(sample.ids, sample.records):
        assert (record.payload["price"], record.payload["stock"]) == \
            (served[pid]["price"], served[pid]["stock"])


def test_upstream_as_of_the_question_is_the_answer_key():
    pair = demo_pair("demo-stale", BUILT_IN["demo-stale"], seed=SEED, clock=CLOCK)
    sample = pair.delivered.sample(seed=9)
    truth = pair.upstream.fetch(sample.ids, as_of=sample.as_of)
    state = load_slice().machine.state_at(sample.as_of)
    assert [r.meta["record_id"] for r in truth] == sample.ids
    assert [(r.payload["price"], r.payload["stock"]) for r in truth] == \
        [(state[i]["price"], state[i]["stock"]) for i in sample.ids]


def test_semantic_stripping_records_its_opaque_map_and_the_entry_keeps_it():
    pair = demo_pair("demo-stripped", BUILT_IN["demo-stripped"], seed=SEED, clock=CLOCK)
    sample = pair.delivered.sample(seed=1)
    opaque = [r for r in sample.records if r.meta.get("opaque_map")]
    assert opaque, "severe stripping at seed 1 opaquified no record"
    entry = to_probe_entry(opaque[0])
    assert entry["opaque_map"] == opaque[0].meta["opaque_map"]
    assert entry["id"] == opaque[0].meta["record_id"]


def test_the_same_seed_serves_the_same_question():
    first = demo_pair("a", BUILT_IN["demo-drift"], seed=SEED, clock=CLOCK).delivered
    second = demo_pair("b", BUILT_IN["demo-drift"], seed=SEED, clock=CLOCK).delivered
    for _ in range(3):
        a, b = first.sample(), second.sample()
        assert (a.key, a.as_of, a.ids) == (b.key, b.as_of, b.ids)
        assert [r.payload for r in a.records] == [r.payload for r in b.records]


def test_a_query_key_selects_that_query():
    delivered = demo_pair("a", BUILT_IN["demo-healthy"], clock=CLOCK).delivered
    key = str(load_slice().usable_queries[0]["query_id"])
    assert delivered.sample(key=key, seed=1).key == key


@pytest.mark.parametrize("kwargs, message", [
    ({"fault": "freshness", "severity": "extreme"}, "severity for freshness"),
    ({"fault": "flooding", "severity": "mild"}, "fault must be none or one of"),
    ({"severity": "mild"}, "healthy condition"),
    ({"pipeline": "kafka"}, "pipeline must be one of"),
])
def test_only_study_conditions_are_accepted(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Condition(**kwargs)


def test_the_slice_is_small_and_every_query_is_answerable_from_it():
    data = load_slice()
    assert SLICE.stat().st_size < 1_000_000
    assert len(data.usable_queries) == len(data.queries) == 200


@needs_data
def test_the_committed_slice_is_a_fresh_bake():
    """sources/data/esci_slice.json.gz is generated. If this fails, run
    `python -m airsbench.server.bake` — never edit the file by hand."""
    from airsbench.server.bake import build_esci_slice

    committed = json.loads(gzip.decompress(SLICE.read_bytes()))
    assert committed == json.loads(json.dumps(build_esci_slice(DATA)))


def _same(slice_value, full_value) -> bool:
    if isinstance(full_value, float) and math.isnan(full_value):
        return slice_value is None
    return slice_value == full_value


@needs_data
def test_the_slice_replays_to_the_full_catalog_state_exactly():
    from airsbench.pipelines.loader import CatalogTimeMachine

    full = CatalogTimeMachine.load(DATA)
    demo = load_slice().machine
    rng = random.Random(1)
    for t in [0.0, full.max_ts] + [rng.uniform(0, full.max_ts) for _ in range(3)]:
        full_state, demo_state = full.state_at(t), demo.state_at(t)
        for pid, row in demo_state.items():
            assert set(row) == set(full_state[pid])
            assert all(_same(row[k], full_state[pid][k]) for k in row), (t, pid)
