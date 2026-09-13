"""The web console's API: the `airs` command's numbers and refusals, over HTTP.

Two properties carry the weight here:

- **No second implementation.** /api/score must equal `probe.score` and /api/gate
  must equal the controller, exactly — the TypeScript port these routes replace
  had already drifted from the probe before anyone noticed.
- **A local tool holding customer records behaves like one.** Loopback host names
  only, no cross-origin access outside dev mode, bounded request bodies, and a
  scoring core that never loads the web stack.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from airsbench.gate import Controller, Policy
from airsbench.probe import DEFAULT_WEIGHTS, load_weights, parse_records, score
from airsbench.server import create_app
from airsbench.server.api import SAMPLES
from airsbench.server.bake import build

ROOT = Path(__file__).parents[1]
PROBE = ROOT / "examples" / "probe"
POLICY = json.loads((ROOT / "examples" / "gate" / "retrieval.json").read_text())


def _text(name: str) -> str:
    return (PROBE / f"{name}.jsonl").read_text(encoding="utf-8")


def _strict(response):
    """Parse a response the way a browser would — NaN and Infinity are not JSON."""
    def refuse(token):
        raise AssertionError(f"{token} in an API response")
    return json.loads(response.text, parse_constant=refuse)


def _client(tmp_path, **options) -> TestClient:
    options.setdefault("web_dir", tmp_path / "no-web")
    return TestClient(create_app(**options), base_url="http://127.0.0.1")


@pytest.fixture
def client(tmp_path):
    return _client(tmp_path)


# ---- the same numbers as the command ----------------------------------------

@pytest.mark.parametrize("with_source", [True, False])
@pytest.mark.parametrize("name", ["healthy", "degraded"])
def test_score_is_exactly_what_the_probe_computes(client, name, with_source):
    body = {"task": "retrieval", "delivered": _text(name),
            "source": _text("source") if with_source else None}
    response = client.post("/api/score", json=body)
    assert response.status_code == 200

    expected = score(parse_records(_text(name), "delivered"),
                     parse_records(_text("source"), "source", unique_ids=True)
                     if with_source else None,
                     "retrieval")
    assert _strict(response) == json.loads(json.dumps(expected))


def test_an_empty_upstream_box_leaves_consistency_unmeasured_not_perfect(client):
    result = client.post("/api/score", json={"delivered": _text("degraded"),
                                             "source": "  \n"}).json()
    assert result["dimensions"]["consistency"]["score"] is None
    assert "consistency" in result["unmeasured"]


def test_gate_is_exactly_what_the_controller_decides(client):
    body = {"task": "retrieval", "delivered": _text("degraded"),
            "source": _text("source"), "policy": POLICY}
    result = _strict(client.post("/api/gate", json=body))

    weights, _ = load_weights(DEFAULT_WEIGHTS, "retrieval")
    verdict = Controller(Policy.from_dict(POLICY), weights).evaluate(
        parse_records(_text("degraded"), "delivered"),
        parse_records(_text("source"), "source", unique_ids=True))
    expected = json.loads(json.dumps(verdict.to_dict()))

    assert result["admitted"] is False
    assert {key: result[key] for key in expected} == expected
    assert result["policy_description"] == Policy.from_dict(POLICY).describe()


def test_an_unmeasured_rule_comes_back_null_and_refused(client):
    result = _strict(client.post("/api/gate", json={"delivered": _text("degraded"),
                                                    "policy": POLICY}))
    assert result["admitted"] is False
    observed = {v["rule"]: v["observed"] for v in result["violations"]}
    assert observed["min_dimension.consistency"] is None


def test_shadow_mode_admits_and_still_reports(client):
    result = client.post("/api/gate", json={"delivered": _text("degraded"),
                                            "source": _text("source"),
                                            "policy": POLICY, "shadow": True}).json()
    assert result["admitted"] and result["shadowed"] and result["violations"]


# ---- the same refusals, as 422s ----------------------------------------------

DUPLICATE_SOURCE = ('{"id": "A", "payload": {}}\n'
                    '{"id": "B", "payload": {}}\n'
                    '{"id": "A", "payload": {}}')


@pytest.mark.parametrize("body, input_name, line, fragment", [
    ({"delivered": '{"payload": {}}\n{"payload": "x"}'}, "delivered", 2,
     "'payload' must be an object"),
    ({"delivered": '{"payload": {}, "event_timestamp": 10, "read_timestamp": 5}'},
     "delivered", None, "clock skew"),
    ({"delivered": _text("healthy"), "source": DUPLICATE_SOURCE}, "source", None,
     "appears on lines 1 and 3"),
    ({"delivered": _text("healthy"), "task": "summarisation"}, "task", None, "invert"),
    ({"delivered": "  "}, "delivered", None, "no records given"),
    ({"source": _text("source")}, "delivered", None, "Field required"),
    ({"delivered": _text("healthy"), "sourc": "typo"}, "sourc", None,
     "Extra inputs are not permitted"),
    ({"delivered": 42}, "delivered", None, "valid string"),
])
def test_bad_input_is_a_422_naming_the_input_and_line(client, body, input_name, line, fragment):
    response = client.post("/api/score", json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["input"], error["line"]) == (input_name, line)
    assert fragment in error["message"]


def test_a_body_that_is_not_json_gets_the_same_error_shape(client):
    response = client.post("/api/score", content="{not json",
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert set(response.json()["error"]) == {"input", "line", "message"}


@pytest.mark.parametrize("policy, fragment", [
    ({"min_airs": "80"}, "must be a number"),
    ({"max_age_seconds": 5}, "unknown policy field"),
])
def test_a_bad_policy_is_a_422_on_the_policy(client, policy, fragment):
    response = client.post("/api/gate", json={"delivered": _text("healthy"), "policy": policy})
    assert response.status_code == 422
    assert response.json()["error"]["input"] == "policy"
    assert fragment in response.json()["error"]["message"]


def test_an_unknown_api_route_is_a_json_404(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "no API route GET /api/nope"


# ---- what the console is given -----------------------------------------------

def test_meta_serves_the_shipped_calibration(client):
    meta = client.get("/api/meta").json()
    shipped = json.loads(DEFAULT_WEIGHTS.read_text())
    assert meta["profiles"] == shipped["profiles"]
    assert meta["validation"] == shipped["validation"]
    assert [band["label"] for band in meta["bands"]] == ["READY", "WATCH", "AT RISK"]
    assert meta["frontend_built"] is False
    assert meta["preloaded"] is False


def test_samples_are_the_shipped_examples_byte_for_byte(client):
    served = client.get("/api/samples").json()
    by_id = {sample["id"]: sample for sample in served["samples"]}
    assert by_id["healthy"]["delivered"] == _text("healthy")
    assert by_id["degraded"]["source"] == _text("source")
    assert {p["id"]: p["policy"] for p in served["policies"]}["retrieval"] == POLICY
    assert served["preloaded"] is None


def test_the_committed_samples_are_a_fresh_bake():
    """server/data/samples.json is generated. If this fails, run
    `python -m airsbench.server.bake` — never edit the file by hand."""
    assert json.loads(SAMPLES.read_text(encoding="utf-8")) == build()


def test_preloaded_records_are_offered_exactly_as_written(tmp_path):
    from airsbench.server.__main__ import preload

    records = tmp_path / "delivered.jsonl"
    records.write_text('{"id": "A", "payload": {"p": 1}, '
                       '"event_timestamp": "2026-09-13T10:00:00Z", '
                       '"read_timestamp": "2026-09-13T10:00:02Z"}\n')
    client = _client(tmp_path, preloaded=preload(records, None, "retrieval"))

    assert client.get("/api/meta").json()["preloaded"] is True
    offered = client.get("/api/samples").json()["preloaded"]
    assert offered["delivered"] == records.read_text()  # ISO stays ISO
    assert client.post("/api/score", json={"delivered": offered["delivered"]}).status_code == 200


def test_the_console_is_served_when_built_and_explained_when_not(tmp_path, client):
    page = client.get("/")
    assert page.status_code == 200 and "make web" in page.text

    web = tmp_path / "web"
    (web / "evidence").mkdir(parents=True)
    (web / "index.html").write_text("<h1>console</h1>")
    (web / "evidence" / "index.html").write_text("<h1>evidence</h1>")
    built = _client(tmp_path, web_dir=web)
    assert "console" in built.get("/").text
    assert "evidence" in built.get("/evidence/").text
    assert built.get("/api/meta").json()["frontend_built"] is True


# ---- a local tool holding customer records ----------------------------------

def test_a_request_addressed_to_another_host_is_refused(client):
    """DNS rebinding: a page on evil.example re-pointed at 127.0.0.1 still sends
    its own name in the Host header."""
    assert client.get("/api/meta", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/meta", headers={"Host": "localhost:8000"}).status_code == 200


@pytest.mark.parametrize("dev", [False, True])
def test_cross_origin_access_exists_only_in_dev_mode_and_only_for_the_dev_server(tmp_path, dev):
    client = _client(tmp_path, dev=dev)

    def allowed(origin):
        response = client.options("/api/score", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST"})
        return response.headers.get("access-control-allow-origin") == origin

    assert allowed("http://localhost:3000") is dev
    assert allowed("http://evil.example") is False


def test_an_oversized_request_is_refused_before_it_is_read(tmp_path):
    client = _client(tmp_path, max_body_bytes=1000)
    response = client.post("/api/score", json={"delivered": "x" * 5000})
    assert response.status_code == 413
    assert "the limit is 1 KB" in response.json()["error"]["message"]


def test_the_scoring_core_and_the_cli_never_import_the_web_stack():
    """A pipeline step running `airs gate` must not load a web framework. Run in
    a fresh interpreter: this test process has already imported FastAPI."""
    code = ("import sys, agentic_faults, airsbench.probe, airsbench.gate, airsbench.cli\n"
            "print(','.join(m for m in ('fastapi', 'starlette', 'uvicorn', 'pydantic')"
            " if m in sys.modules))")
    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True,
                            text=True, check=True).stdout.strip()
    assert loaded == ""


# ---- `airs serve` refuses before it listens ------------------------------------

def test_serve_refuses_a_source_without_records(capsys):
    from airsbench.server.__main__ import main

    assert main(["--source", str(PROBE / "source.jsonl"), "--no-browser"]) == 2
    assert "--source needs --records" in capsys.readouterr().err


def test_serve_validates_the_records_before_it_listens(tmp_path, capsys):
    from airsbench.server.__main__ import main

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"payload": {}, "event_timestamp": "2026-09-13T10:00:00"}\n')
    assert main(["--records", str(bad), "--no-browser"]) == 2
    assert "has no timezone" in capsys.readouterr().err


def test_serve_names_the_flag_when_the_port_is_taken(monkeypatch, capsys):
    import uvicorn

    from airsbench.server.__main__ import main

    monkeypatch.setattr(uvicorn.Server, "run", lambda self: pytest.fail("the server started"))
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        assert main(["--port", str(held.getsockname()[1]), "--no-browser"]) == 2
    assert "pass --port" in capsys.readouterr().err
