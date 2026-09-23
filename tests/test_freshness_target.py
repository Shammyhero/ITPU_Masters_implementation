"""A freshness target per source (the live case study's lesson, 24 Sep).

Freshness scores `100 x target / mean age` beyond the target. The calibrated target
is one second — the study's seconds-scale staleness — and on a source that changes
over minutes every record scores near 0, so freshness stops moving the composite
(`docs/live_case_study_findings.md`). A source may now declare its own target.

What has to hold:

- **The default is unchanged**, so every corpus number, baked file and published
  figure is untouched.
- **A declared target is reported beside the score**, because the weights were
  fitted at the default.
- **It changes how an age is scored, never the age a policy holds a budget
  against** — `max_record_age_seconds` is a rule about seconds, not scores.
- **It reaches every entry point:** `probe`, `gate`, `sources.yaml` (so the loop,
  the API session and `airs analyst ask`), and the API's score and gate.
"""

from __future__ import annotations

import json
import math
import time

import pytest

from airsbench.gate.controller import Controller
from airsbench.gate.policy import Policy
from airsbench.probe import ProbeError, freshness_target, measure, score


def batch(age_s: float, n: int = 3) -> list[dict]:
    now = time.time()
    return [{"id": f"r{i}", "payload": {"x": i}, "event_timestamp": now - age_s,
             "read_timestamp": now} for i in range(n)]


# ---- the probe ----------------------------------------------------------------------------

def test_the_default_is_the_calibrated_one_second():
    freshness = measure(batch(5.0))["freshness"]
    assert freshness["score"] == pytest.approx(20.0)
    assert freshness["target_seconds"] == 1.0 and "declared" not in freshness["detail"]


@pytest.mark.parametrize("age,expected", [(30.0, 100.0), (60.0, 100.0), (120.0, 50.0),
                                          (600.0, 10.0)])
def test_a_declared_target_scores_ages_on_the_sources_own_scale(age, expected):
    freshness = measure(batch(age), freshness_target_s=60)["freshness"]
    assert freshness["score"] == pytest.approx(expected)
    assert freshness["target_seconds"] == 60.0
    assert "declared target of 60s (calibrated at 1s)" in freshness["detail"]


@pytest.mark.parametrize("bad", [0, -5, math.nan, math.inf, True, "60"])
def test_a_target_is_a_positive_number_of_seconds(bad):
    with pytest.raises(ProbeError, match="positive number of seconds"):
        freshness_target(bad)


def test_the_composite_moves_with_the_target_and_says_which_it_used():
    records = batch(120.0)
    default, declared = score(records), score(records, freshness_target_s=60)
    assert declared["freshness_target_s"] == 60.0 and default["freshness_target_s"] == 1.0
    assert declared["dimensions"]["freshness"]["score"] > \
        default["dimensions"]["freshness"]["score"]


def test_the_probe_command_takes_it(tmp_path, capsys):
    from airsbench.probe import main

    path = tmp_path / "d.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in batch(120.0)) + "\n")
    assert main(["--records", str(path), "--json", "--freshness-target", "60"]) in (0, 1)
    out = json.loads(capsys.readouterr().out)
    assert out["freshness_target_s"] == 60.0
    assert out["dimensions"]["freshness"]["score"] == pytest.approx(50.0)


# ---- the gate -------------------------------------------------------------------------------

def test_a_target_never_moves_an_age_budget():
    """Declared or not, a batch 120 s old breaks a 90 s age budget: the rule is
    held against the measured age, not the score."""
    policy = Policy(name="age", max_record_age_seconds=90.0)
    for target in (None, 60, 600):
        verdict = Controller(policy, freshness_target_s=target).evaluate(batch(120.0))
        assert not verdict.admitted
        assert verdict.violations[0].rule == "max_record_age_seconds"
        assert verdict.record_age_seconds == pytest.approx(120.0, abs=1)


def test_a_freshness_floor_is_judged_on_the_declared_scale():
    policy = Policy(name="floor", min_dimension={"freshness": 40.0})
    assert not Controller(policy).evaluate(batch(120.0)).admitted            # 0.8 at 1 s
    assert Controller(policy, freshness_target_s=60).evaluate(batch(120.0)).admitted  # 50


def test_the_gate_command_takes_it(tmp_path, capsys):
    from airsbench.gate.__main__ import main

    records = tmp_path / "d.jsonl"
    records.write_text("\n".join(json.dumps(r) for r in batch(120.0)) + "\n")
    policy = tmp_path / "p.json"
    policy.write_text(json.dumps({"name": "floor", "min_dimension": {"freshness": 40}}))
    assert main(["--records", str(records), "--policy", str(policy), "--json"]) == 1
    capsys.readouterr()
    assert main(["--records", str(records), "--policy", str(policy), "--json",
                 "--freshness-target", "60"]) == 0


# ---- a declared source ------------------------------------------------------------------------

def declared(tmp_path, extra: str = "    freshness_target_s: 60\n"):
    from airsbench.sources.config import load_sources

    now = time.time()
    rows = [{"id": f"p{i}", "payload": {"price": 10 + i, "stock": 1},
             "event_timestamp": now - 120, "read_timestamp": now} for i in range(3)]
    (tmp_path / "d.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (tmp_path / "sources.yaml").write_text(
        "sources:\n  shop:\n    type: files\n    delivered: ./d.jsonl\n    upstream: ./d.jsonl\n"
        + extra)
    return load_sources(tmp_path / "sources.yaml")


def test_a_source_declares_its_target_and_the_loop_scores_with_it(tmp_path):
    from airsbench.analyst.answerers import LiteralAnswerer
    from airsbench.analyst.loop import Loop
    from airsbench.analyst.session import DEMO_PLAN, Question

    pair = declared(tmp_path)["shop"]
    assert pair.freshness_target_s == 60.0
    tick = Loop(pair=pair, policy=Policy(name="open"), answerer=LiteralAnswerer(),
                mode="off").ask(Question("Cheapest?", DEMO_PLAN, n=3), seed=1)
    assert tick["airs"]["freshness_target_s"] == 60.0
    assert tick["airs"]["dimensions"]["freshness"]["score"] == pytest.approx(50.0, abs=1)


def test_the_demo_sources_keep_the_default():
    from airsbench.sources.config import load_sources

    assert all(p.freshness_target_s is None for p in load_sources().values())


@pytest.mark.parametrize("bad", ["0", "-1", "soon"])
def test_a_bad_declaration_is_named(tmp_path, bad):
    from airsbench.sources import SourceError

    with pytest.raises(SourceError, match="freshness_target_s"):
        declared(tmp_path, f"    freshness_target_s: {bad}\n")


def test_airs_sources_sample_uses_the_declared_target(tmp_path):
    from airsbench.sources.__main__ import sample_report

    report = sample_report(declared(tmp_path)["shop"], 3, None, 1, "retrieval")
    assert report["airs"]["freshness_target_s"] == 60.0


# ---- the API ------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from airsbench.server.app import create_app

    monkeypatch.setattr("airsbench.analyst.sessions.SESSIONS_DIR", tmp_path / "sessions")
    return TestClient(create_app(web_dir=tmp_path / "no-web",
                                 sources=declared(tmp_path)), base_url="http://127.0.0.1")


def jsonl(records):
    return "\n".join(json.dumps(r) for r in records)


def test_the_api_scores_and_gates_with_a_target(client):
    body = {"delivered": jsonl(batch(120.0)), "freshness_target_s": 60}
    scored = client.post("/api/score", json=body).json()
    assert scored["freshness_target_s"] == 60.0
    assert scored["dimensions"]["freshness"]["score"] == pytest.approx(50.0, abs=1)
    gated = client.post("/api/gate", json={**body, "policy": {
        "name": "floor", "min_dimension": {"freshness": 40}}}).json()
    assert gated["admitted"] is True
    assert client.post("/api/score", json={**body, "freshness_target_s": 0}).status_code == 422


def test_the_api_lists_a_sources_target(client):
    listed = {s["id"]: s for s in client.get("/api/sources").json()["sources"]}
    assert listed["shop"]["freshness_target_s"] == 60.0
    assert listed["demo-stale"]["freshness_target_s"] is None
