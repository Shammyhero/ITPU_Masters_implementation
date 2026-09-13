"""/api/replay: the published gate economics, reproducible from an installed wheel.

`docs/gate_findings.md` was produced by `gate.replay` reading `results/runs/`.
The wheel carries those runs reduced to batches (`server/data/replay_corpus.json`)
so the console can price a policy on the same evidence. These tests pin that the
route IS that replay, the corpus IS those runs, and an infinite exchange rate
never reaches JSON as something a browser cannot parse.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from airsbench.gate.replay import SWEEPS, load_batches, replay
from airsbench.probe import DEFAULT_WEIGHTS, load_weights
from airsbench.server import create_app
from airsbench.server.api import REPLAY
from airsbench.server.bake import REPLAY_ARMS, build_replay_corpus

RESULTS = Path("results/runs")
needs_runs = pytest.mark.skipif(not list(RESULTS.glob("*.json")), reason="no run artifacts")
NO_GATE = {"name": "no gate"}


def _strict(response):
    def refuse(token):
        raise AssertionError(f"{token} in an API response")
    return json.loads(response.text, parse_constant=refuse)


def _replay(client, policy, task="retrieval"):
    return client.post("/api/replay", json={"task": task, "policy": policy})


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(web_dir=tmp_path / "no-web"), base_url="http://127.0.0.1")


@pytest.fixture(scope="module")
def batches():
    return load_batches(RESULTS, arms=REPLAY_ARMS)


@needs_runs
def test_the_committed_corpus_is_a_fresh_bake_of_the_run_artifacts():
    """server/data/replay_corpus.json is generated. If this fails, run
    `python -m airsbench.server.bake` — never edit the file by hand."""
    assert json.loads(REPLAY.read_text(encoding="utf-8")) == build_replay_corpus(RESULTS)


@needs_runs
@pytest.mark.parametrize("sweep", sorted(SWEEPS))
@pytest.mark.parametrize("task", ["retrieval", "classification"])
def test_the_route_is_the_replay_over_results_runs(client, batches, task, sweep):
    weights, _ = load_weights(DEFAULT_WEIGHTS, task)
    selected = [b for b in batches if b.task == task]
    for policy in SWEEPS[sweep](task):
        response = _replay(client, policy.to_dict(), task)
        assert response.status_code == 200, response.text
        expected = json.loads(json.dumps(replay(selected, policy, weights).to_dict()))
        assert _strict(response)["outcome"] == expected, policy.name


def test_the_published_gate_headline_is_reproduced_from_the_wheel_data(client):
    """gate_findings.md: on retrieval, 19.6% of answers are silent failures with no
    gate, and 14.2% on fault-free pipelines — most of it no gate can reach."""
    result = _replay(client, NO_GATE).json()
    assert round(100 * result["no_gate"]["baseline_silent_rate"], 1) == 19.6
    assert round(100 * result["fault_free"]["rate"], 1) == 14.2


def test_a_policy_that_prevents_nothing_has_a_null_exchange_rate(client):
    result = _strict(_replay(client, NO_GATE))
    assert result["outcome"]["prevented"] == 0
    assert result["outcome"]["exchange_rate"] is None


def test_a_real_gate_has_a_finite_price_and_a_two_sided_account(client):
    policy = {"name": "consistency", "min_dimension": {"consistency": 90.0}}
    outcome = _replay(client, policy).json()["outcome"]
    assert outcome["prevented"] > 0 and outcome["forfeited"] > 0
    assert outcome["exchange_rate"] == pytest.approx(outcome["forfeited"] / outcome["prevented"])
    assert 0.0 < outcome["coverage"] < 1.0


def test_the_response_says_what_evidence_the_price_comes_from(client):
    corpus = _replay(client, NO_GATE).json()["corpus"]
    assert corpus["arms"] == list(REPLAY_ARMS)
    assert corpus["models"] == ["gpt-4o-mini"]
    assert (corpus["runs"], corpus["decisions"]) == (180, 13_554)
    assert "not a forecast" in corpus["note"]


@pytest.mark.parametrize("body, input_name", [
    ({"task": "summarisation", "policy": {}}, "task"),
    ({"task": "retrieval", "policy": {"min_airs": "80"}}, "policy"),
    ({"task": "retrieval"}, "policy"),
])
def test_bad_replay_input_is_a_422_on_that_input(client, body, input_name):
    response = client.post("/api/replay", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["input"] == input_name
