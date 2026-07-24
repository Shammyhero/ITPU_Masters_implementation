import pytest

from agentic_faults import Record
from airsbench.pipelines.loader import CatalogTimeMachine, stale_dep_delay
from airsbench.runner.scoring import auc_roc, f1_score, score_binary


def test_f1_matches_sklearn():
    sklearn_metrics = pytest.importorskip("sklearn.metrics")
    labels = [1, 0, 1, 1, 0, 0, 1, 0]
    preds = [1, 0, 0, 1, 1, 0, 1, 0]
    assert f1_score(labels, preds) == pytest.approx(
        sklearn_metrics.f1_score(labels, preds)
    )


def test_auc_matches_sklearn():
    sklearn_metrics = pytest.importorskip("sklearn.metrics")
    labels = [1, 0, 1, 1, 0, 0, 1, 0]
    scores = [0.9, 0.1, 0.4, 0.8, 0.3, 0.2, 0.7, 0.6]
    assert auc_roc(labels, scores) == pytest.approx(
        sklearn_metrics.roc_auc_score(labels, scores)
    )


def test_auc_handles_ties_and_single_class():
    assert auc_roc([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.5)
    assert auc_roc([1, 1, 1], [0.9, 0.8, 0.7]) is None


def test_score_binary_counts_failures():
    metrics = score_binary([1, 0, 1], [1, 0, 0], [0.9, 0.2, 0.4], parse_failures=2)
    assert metrics.accuracy == pytest.approx(2 / 3)
    assert metrics.parse_failures == 2
    assert metrics.n == 3


def test_catalog_time_machine_replays_updates_in_order():
    machine = CatalogTimeMachine(
        base={"P1": {"product_id": "P1", "price": 10.0, "stock": 5, "last_updated": 0.0}},
        updates=[
            {"ts": 1.0, "product_id": "P1", "price": 12.0},
            {"ts": 2.0, "product_id": "P1", "stock": 0},
            {"ts": 3.0, "product_id": "P1", "price": 15.0},
        ],
    )
    assert machine.state_at(0.5)["P1"]["price"] == 10.0   # before any update
    assert machine.state_at(1.5)["P1"]["price"] == 12.0
    assert machine.state_at(2.5)["P1"]["stock"] == 0
    assert machine.state_at(99)["P1"]["price"] == 15.0
    # replay must not mutate the base state
    assert machine.base["P1"]["price"] == 10.0


def test_stale_values_differ_from_current_values():
    """The mechanism RQ1 depends on: staleness changes what the agent sees."""
    machine = CatalogTimeMachine(
        base={"P1": {"product_id": "P1", "price": 10.0, "stock": 5}},
        updates=[{"ts": 5.0, "product_id": "P1", "price": 99.0}],
    )
    current = machine.state_at(6.0)["P1"]["price"]
    stale = machine.state_at(6.0 - 5.0)["P1"]["price"]
    assert current == 99.0 and stale == 10.0


def test_stale_dep_delay_decays_toward_zero():
    assert stale_dep_delay(60.0, 0.0) == 60.0
    assert stale_dep_delay(60.0, 5.0) == 30.0
    assert stale_dep_delay(60.0, 10.0) == 0.0
    assert stale_dep_delay(60.0, 99.0) == 0.0


def test_record_render_drops_stripped_context():
    from airsbench.agents.prompts import render_record

    record = Record(payload={"price": 10}, context={"units": {"price": "USD"}})
    assert "context" in render_record(record)
    record.context = {}
    assert "context" not in render_record(record)
