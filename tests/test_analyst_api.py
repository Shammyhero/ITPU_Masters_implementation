"""The Analyst API (plan A7): transport only, and three firewalls.

The routes add HTTP to `analyst/loop.py` and nothing else — no scoring, no
routing logic — so what the console shows is what the CLI and the corpus
measured. What is actually pinned here:

- **Sources are declared, never requested.** A request may name an id the server
  already loaded; a path, DSN or URL in a request must be refused, because any
  page in the browser can post to localhost.
- **`/api/ask` streams the real order** — gate, then answer, then the verified
  Tick — with the verification arriving strictly after the answer.
- **A refusal costs nothing**, over HTTP as at the command line: no model call,
  no spend.
- **No key leaves the process.** `/api/models` says whether a provider is
  configured, never what the key is.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from airsbench.server.app import create_app

DEMO_PLAN = {"type": "min_by", "measure": "price",
             "where": [{"field": "stock", "op": ">", "value": 0}]}
STRICT = {"name": "intact", "min_dimension": {"consistency": 95.0}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A server whose live sessions write to a temporary directory."""
    monkeypatch.setattr("airsbench.analyst.sessions.SESSIONS_DIR", tmp_path / "sessions")
    return TestClient(create_app(web_dir=tmp_path / "no-web"),
                      base_url="http://127.0.0.1")


def open_session(client, **overrides):
    body = {"source": "demo-stale", "answerer": "literal", **overrides}
    response = client.post("/api/session", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def events(client, session_id, **body):
    """The SSE stream of one question, parsed into (stage, payload) pairs."""
    with client.stream("POST", "/api/ask",
                       json={"session_id": session_id, **body}) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())
    out = []
    for block in raw.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


# ---- sources are declared, never requested ----------------------------------

def test_the_bundled_sources_are_listed_with_their_semantic_state(client):
    body = client.get("/api/sources").json()
    ids = {source["id"] for source in body["sources"]}
    assert {"demo-healthy", "demo-stale", "demo-drift", "demo-stripped"} <= ids
    stale = next(s for s in body["sources"] if s["id"] == "demo-stale")
    assert stale["verifiable"] is True and stale["supports_as_of"] is True
    assert stale["semantic"]["state"] == "reviewed"


@pytest.mark.parametrize("named", [
    "/etc/passwd", "postgres://user:pw@host/db", "https://example.com/data.jsonl",
    "../../secrets.jsonl",
])
def test_a_source_that_was_never_declared_is_refused(client, named):
    """The W3 security property: any web page can post to localhost, so the
    server must not open a file or a connection because a request asked it to."""
    response = client.post(f"/api/sources/{named}/test".replace("//", "/"))
    assert response.status_code in (404, 422)
    if response.status_code == 422:
        assert "declared" in response.json()["error"]["message"]

    opened = client.post("/api/session", json={"source": named, "answerer": "literal"})
    assert opened.status_code == 422
    assert opened.json()["error"]["input"] == "source"


def test_testing_a_source_returns_its_schema_and_a_sample(client):
    body = client.post("/api/sources/demo-healthy/test").json()
    assert [field["name"] for field in body["schema"]["fields"]][:2] == ["product_id", "title"]
    assert len(body["sample"]) == 3 and "price" in body["sample"][0]


# ---- models: what can answer, never a key -----------------------------------

def test_models_reports_configured_providers_without_revealing_any_key(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-NEVER-RETURNED-0123456789")
    raw = client.get("/api/models").text
    body = json.loads(raw)
    assert "sk-test" not in raw and "NEVER_RETURNED" not in raw
    openai = next(p for p in body["providers"] if p["provider"] == "openai")
    assert openai == {"provider": "openai", "configured": True, "env": "OPENAI_API_KEY",
                      "note": openai["note"]}
    assert body["literal"]["note"].endswith("$0")


# ---- one question, streamed in the order it happens -------------------------

def test_ask_streams_gate_then_answer_then_the_verified_tick(client):
    session = open_session(client)
    stages = [stage for stage, _ in events(client, session["session_id"])]
    assert stages == ["gate", "answer", "tick"]


def test_the_answer_arrives_before_any_verdict_about_it(client):
    """The pause between answering and verifying is the demonstration."""
    session = open_session(client)
    stream = dict(events(client, session["session_id"]))
    answer_keys = set(stream["answer"]["answer"])
    assert "value" in answer_keys
    assert not {"correct", "silent_failure", "attribution"} & answer_keys
    assert {"correct", "silent_failure", "attribution"} <= set(stream["tick"]["decision"])


def test_a_stale_pipeline_under_an_age_budget_re_reads_before_answering(client):
    session = open_session(client, policy={"name": "fresh", "max_record_age_seconds": 2.0})
    stages = [stage for stage, _ in events(client, session["session_id"])]
    assert stages == ["gate", "refetch", "answer", "tick"]


def test_a_refusal_reaches_no_model_and_costs_nothing(client):
    session = open_session(client, source="demo-drift", policy=STRICT)
    stream = dict(events(client, session["session_id"]))
    assert "answer" not in stream
    assert stream["gate"]["verdict"] == "refuse"
    tick = stream["tick"]
    assert tick["decision"]["refused"] is True and tick["cost"]["usd"] == 0.0
    assert client.get(f"/api/session/{session['session_id']}").json()["meter"]["refused"] == 1


# ---- the session and its meter ----------------------------------------------

def test_a_session_reports_its_caps_policy_and_quarantine(client):
    session = open_session(client, max_cost=0.25)
    assert session["arm"] == "live" and session["seed_block"] == [100000, 110000]
    assert session["budget"]["session_cap_usd"] == 0.25
    assert session["policy_description"].startswith("open")


def test_the_meter_accumulates_across_questions(client):
    session = open_session(client)
    for _ in range(3):
        events(client, session["session_id"])
    meter = client.get(f"/api/session/{session['session_id']}").json()["meter"]
    assert meter["asked"] == 3 and meter["answered"] == 3
    assert meter["correct"] + meter["silent_failures"] <= 3


def test_every_tick_of_a_session_is_written_to_the_users_own_directory(client, tmp_path):
    from airsbench.analyst.sessions import read_session

    session = open_session(client)
    events(client, session["session_id"])
    events(client, session["session_id"])
    ticks = read_session(session["session_id"], tmp_path / "sessions")
    assert len(ticks) == 2
    assert all(tick["provenance"]["arm"] == "live" for tick in ticks)
    assert 100_000 <= ticks[1]["provenance"]["seed"] < 110_000


def test_asking_on_a_session_that_was_never_opened_says_how_to_open_one(client):
    response = client.post("/api/ask", json={"session_id": "0" * 12})
    assert response.status_code == 422
    assert "POST /api/session" in response.json()["error"]["message"]


# ---- refusals keep the one error shape --------------------------------------

@pytest.mark.parametrize("body, field, fragment", [
    ({"source": "demo-stale", "answerer": "openai/gpt-4o-mini"}, "answerer",
     "OPENAI_API_KEY"),
    ({"source": "demo-stale", "answerer": "nonsense"}, "answerer", "not a model"),
    ({"source": "demo-stale", "refetch": "sometimes"}, "refetch", "refetch must be one of"),
    ({"source": "demo-stale", "task": "sentiment"}, "task", "calibrated profile"),
    ({"source": "demo-stale", "policy": {"min_airs": 300}}, "policy", "0-100"),
])
def test_a_session_that_cannot_be_opened_names_the_input_and_the_fix(
        client, body, field, fragment, monkeypatch):
    # A machine with no key at all: the env is empty AND .env is not consulted,
    # or this author's own .env would quietly supply one.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("airsbench.agents.llm.load_dotenv", lambda *a, **k: None)
    response = client.post("/api/session", json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["input"] == field and fragment in error["message"]


def test_a_question_without_its_plan_is_refused(client):
    session = open_session(client)
    response = client.post("/api/ask", json={"session_id": session["session_id"],
                                             "question": "which is cheapest?"})
    assert response.status_code == 422
    assert "never the answerer's" in response.json()["error"]["message"]


def test_a_supplied_plan_is_what_the_answer_is_checked_against(client):
    session = open_session(client, source="demo-healthy")
    stream = dict(events(client, session["session_id"],
                         plan={"type": "count_where",
                               "where": [{"field": "stock", "op": "==", "value": 0}]},
                         question="How many are out of stock?"))
    assert stream["tick"]["question"]["plan"]["type"] == "count_where"
    assert isinstance(stream["tick"]["decision"]["value"], (int, float))


def test_an_unknown_route_still_answers_in_the_one_error_shape(client):
    response = client.post("/api/nope")
    assert response.status_code == 404 and response.json()["error"]["input"] is None


# ---- pasted records: the one source that may arrive in a request ------------

RECORDS = "\n".join([
    '{"id": "A", "payload": {"sku": "A", "price": 9.5, "stock": 4}}',
    '{"id": "B", "payload": {"sku": "B", "price": 3.0, "stock": 0}}',
    '{"id": "C", "payload": {"sku": "C", "price": 7.25, "stock": 2}}',
])
UPSTREAM = "\n".join([
    '{"id": "A", "payload": {"sku": "A", "price": 9.5, "stock": 4}}',
    '{"id": "B", "payload": {"sku": "B", "price": 3.0, "stock": 6}}',
    '{"id": "C", "payload": {"sku": "C", "price": 7.25, "stock": 2}}',
])
CHEAPEST = {"type": "min_by", "measure": "price",
            "where": [{"field": "stock", "op": ">", "value": 0}]}


def test_a_session_can_be_opened_over_pasted_records(client):
    """The records ARE the request body, so no file or connection is opened for
    a request — the firewall holds (author decision, 20 Sep)."""
    session = open_session(client, source="inline", records=RECORDS, upstream=UPSTREAM)
    assert session["source"] == "inline"
    stream = dict(events(client, session["session_id"], plan=CHEAPEST,
                         question="Which is cheapest in stock?"))
    tick = stream["tick"]
    decision = tick["decision"]
    assert decision["value"] == "C"           # B is cheaper but out of stock here
    assert decision["correct"] is False       # upstream says B is back in stock
    # A pasted source has no history, so it cannot be read as of the moment the
    # delivered values were true: pipeline lag necessarily shows up as values
    # changed in transit rather than as the answer key moving (brief correction
    # 15). The Tick says so rather than implying a partition it cannot make.
    assert decision["attribution"] == "corrupted_in_transit"
    assert any("as of a past time" in note for note in tick["notes"])
    assert [change["field"] for change in decision["changed_fields"]] == ["stock"]


def test_pasted_records_without_an_upstream_cannot_be_verified(client):
    session = open_session(client, source="inline", records=RECORDS)
    stream = dict(events(client, session["session_id"], plan=CHEAPEST))
    tick = stream["tick"]
    assert tick["decision"]["verifiable"] is False
    assert any("no upstream" in note for note in tick["notes"])


def test_malformed_pasted_records_name_the_line(client):
    response = client.post("/api/session", json={"source": "inline", "records": "{oops"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["input"] == "records" and "line" in error["message"].lower() or error["line"]


def test_a_source_with_no_built_in_question_asks_for_a_plan(client):
    session = open_session(client, source="inline", records=RECORDS)
    response = client.post("/api/ask", json={"session_id": session["session_id"]})
    assert response.status_code == 422
    assert "has no built-in question" in response.json()["error"]["message"]


def test_a_session_can_run_the_semantic_stripping_injector(client):
    """The toggle the console offers: the study's own fault, on the chosen source."""
    session = open_session(client, source="demo-healthy", strip_semantics=True)
    assert session["strip_semantics"] is True
    stream = dict(events(client, session["session_id"]))
    tick = stream["tick"]
    assert tick["airs"]["dimensions"]["semantic"]["score"] < 50.0
    assert tick["airs"]["dimensions"]["consistency"]["score"] == 100.0
    assert any("not by your pipeline" in note for note in tick["notes"])


def test_the_toggle_defaults_to_off(client):
    session = open_session(client, source="demo-healthy")
    assert session["strip_semantics"] is False


# ---- the recommended policy (A9) --------------------------------------------

def test_the_recommendation_is_the_cheapest_real_trade_on_the_corpus(client):
    """Not a heuristic: every policy is replayed over the runs the gate findings
    were computed from, and the recommendation is the cheapest by exchange rate
    among those that actually refuse something and still answer."""
    body = client.post("/api/recommend", json={"task": "retrieval"}).json()
    best = body["recommended"]
    assert best["exchange_rate"] == min(row["exchange_rate"] for row in body["considered"])
    assert best["refused_batches"] > 0 and best["admitted_decisions"] > 0
    # The published trade for retrieval (docs/gate_findings.md).
    assert best["policy"]["min_dimension"] == {"consistency": 90.0}
    assert best["exchange_rate"] == pytest.approx(2.26, abs=0.01)


def test_the_recommendation_states_both_costs_and_the_floor_it_cannot_reach(client):
    body = client.post("/api/recommend", json={"task": "retrieval"}).json()
    assert "2.26" in body["note"] and "7.0" in body["note"]
    assert "agent-intrinsic" in body["note"]
    assert body["fault_free"]["rate"] == pytest.approx(0.1417, abs=0.001)


def test_a_session_filters_the_list_but_never_invents_a_floor(client):
    """What the session measured may only REMOVE policies its pipeline could
    never clear; the floors themselves always come from the corpus sweep."""
    session = open_session(client, source="demo-drift", policy=None)
    for _ in range(2):
        events(client, session["session_id"])
    body = client.post("/api/recommend",
                       json={"task": "retrieval",
                             "session_id": session["session_id"]}).json()
    assert body["filtered_by_session"] is True
    assert body["observed"]["consistency"]["n"] == 2
    # demo-drift delivers consistency well below 90, so that policy is marked
    # unusable here even though it is the corpus's best trade.
    by_name = {row["description"]: row for row in body["considered"]}
    drifted = [row for row in by_name.values()
               if row["policy"]["min_dimension"].get("consistency", 0) >= 90]
    assert drifted and all(row["feasible_here"] is False for row in drifted)
    assert body["recommended"]["feasible_here"] is True


def test_recommending_for_a_task_with_no_runs_is_refused(client):
    response = client.post("/api/recommend", json={"task": "sentiment"})
    assert response.status_code == 422
    assert response.json()["error"]["input"] == "task"
