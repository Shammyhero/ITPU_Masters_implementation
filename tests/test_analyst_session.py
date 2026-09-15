"""One question end to end, the answerers, the prompt, and `airs analyst ask`.

The literal answerer is a probe of the verifier itself: it follows the delivered
records exactly, so on each demo condition only certain labels are possible. If
any other label appears, the verifier or the source has drifted.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from airsbench.analyst.answerers import (
    AnswererError,
    LiteralAnswerer,
    OllamaAnswerer,
    make_answerer,
    parse_answer,
)
from airsbench.analyst.plan import Plan
from airsbench.analyst.prompts import ANALYST_SYSTEM, ANALYST_USER, analyst_messages
from airsbench.analyst.session import DEMO_PLAN, DEMO_QUESTION, LIVE_SEED_BLOCK, Question, ask
from airsbench.analyst.verifier import AgentAnswer
from airsbench.sources import SourcePair
from airsbench.sources.config import load_sources
from airsbench.sources.files import FilesSource

SEEDS = range(LIVE_SEED_BLOCK[0], LIVE_SEED_BLOCK[0] + 40)
PAIRS = load_sources()


def CLOCK():
    return 1_800_000_000.0


def run(pair_id, answerer, seeds=SEEDS, question=None):
    pair = PAIRS[pair_id]
    question = question or Question(DEMO_QUESTION, DEMO_PLAN)
    return [ask(pair, question, answerer, seed=seed, clock=CLOCK) for seed in seeds]


def labels(ticks):
    """Attributions of verified, committed answers (abstentions carry none)."""
    return Counter(t["decision"]["attribution"] for t in ticks
                   if t["decision"]["verifiable"] and t["decision"]["attribution"])


# ---- the literal answerer, per condition -----------------------------------------

def test_on_a_healthy_pipeline_the_literal_answerer_is_always_right():
    assert set(labels(run("demo-healthy", LiteralAnswerer()))) == {"correct"}


def test_on_a_stale_pipeline_every_error_is_the_answer_key_moving():
    ticks = run("demo-stale", LiteralAnswerer())
    counts = labels(ticks)
    assert set(counts) <= {"correct", "answer_key_moved"}
    flipped = sum(bool(t["decision"]["flipped"]) for t in ticks if t["decision"]["verifiable"])
    assert counts["answer_key_moved"] == flipped > 0


def test_on_drifted_or_stripped_records_the_literal_answerer_never_blames_the_model():
    for pair_id in ("demo-drift", "demo-stripped"):
        ticks = run(pair_id, LiteralAnswerer())
        assert set(labels(ticks)) <= {"correct", "corrupted_in_transit"}, pair_id
        assert not any(t["decision"]["flipped"] for t in ticks if t["decision"]["verifiable"])
    stripped = run("demo-stripped", LiteralAnswerer())
    assert sum(t["decision"]["abstained"] for t in stripped) > len(stripped) / 2


class WrongOnPurpose:
    """Answers with a record that is not the best — over records that arrived intact."""

    name = "wrong-on-purpose"

    def answer(self, question, plan, records):
        from airsbench.analyst.plan import execute
        from airsbench.analyst.verifier import rows

        best = execute(plan, rows(records)).value
        other = next(r.meta["record_id"] for r in records if r.meta["record_id"] != best)
        from airsbench.analyst.answerers import Usage
        return AgentAnswer(value=other, confidence=1.0), Usage(self.name)


def test_a_wrong_answer_over_intact_records_is_agent_impairment_end_to_end():
    ticks = run("demo-healthy", WrongOnPurpose(), seeds=range(100_000, 100_015))
    assert set(labels(ticks)) == {"agent_impairment"}
    assert all(t["decision"]["silent_failure"] for t in ticks if t["decision"]["verifiable"])


# ---- the Tick -----------------------------------------------------------------------

def test_a_demo_tick_is_json_safe_quarantined_and_exact_about_time():
    (tick,) = run("demo-stale", LiteralAnswerer(), seeds=[100_003])
    json.dumps(tick, allow_nan=False)
    assert tick["provenance"]["arm"] == "live"
    assert LIVE_SEED_BLOCK[0] <= tick["provenance"]["seed"] < LIVE_SEED_BLOCK[1]
    assert tick["records"]["lag_seconds"] == pytest.approx(5.05)
    assert tick["records"]["t0_t1_gap_seconds"] == 0.0
    assert tick["airs"]["dimensions"]["consistency"]["score"] == pytest.approx(100.0)
    assert tick["question"]["plan"] == DEMO_PLAN.to_dict()
    assert "{query}" not in tick["question"]["text"]
    assert tick["cost"] == {"model": "literal", "input_tokens": 0, "output_tokens": 0, "usd": 0.0}


def test_no_credential_shaped_text_appears_in_a_tick():
    ticks = run("demo-drift", LiteralAnswerer(), seeds=range(100_000, 100_005))
    text = json.dumps(ticks)
    assert not re.search(r"(postgres(ql)?|mysql)://|api[_-]?key|password|secret", text, re.I)


def _jsonl(path: Path, entries) -> Path:
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


def test_a_files_pair_verifies_and_says_lag_cannot_be_separated(tmp_path):
    _jsonl(tmp_path / "d.jsonl", [{"id": "A", "payload": {"stock": 0}},
                                  {"id": "B", "payload": {"stock": 2}}])
    _jsonl(tmp_path / "u.jsonl", [{"id": "A", "payload": {"stock": 3}},
                                  {"id": "B", "payload": {"stock": 2}}])
    (tmp_path / "sources.yaml").write_text(
        "sources:\n  ex:\n    type: files\n    delivered: d.jsonl\n    upstream: u.jsonl\n")
    pair = load_sources(tmp_path / "sources.yaml")["ex"]
    plan = Plan.from_dict({"type": "count_where",
                           "where": [{"field": "stock", "op": ">", "value": 0}]})
    tick = ask(pair, Question("How many are in stock?", plan), LiteralAnswerer(), seed=1)
    decision = tick["decision"]
    assert (decision["value"], decision["answer_upstream"]["value"]) == (1, 2)
    assert decision["attribution"] == "corrupted_in_transit"
    assert decision["changed_fields"][0]["change"] == "value changed"
    assert tick["source"]["supports_as_of"] is False
    assert "cannot be read as of a past time" in tick["notes"][0]


def test_without_an_upstream_nothing_is_verified_and_the_tick_says_why(tmp_path):
    delivered = FilesSource("solo/delivered", _jsonl(tmp_path / "d.jsonl", [
        {"id": "A", "payload": {"price": 2.0, "stock": 1}}]))
    pair = SourcePair(id="solo", kind="files", delivered=delivered, upstream=None)
    tick = ask(pair, Question("Cheapest?", DEMO_PLAN), LiteralAnswerer(), seed=1)
    assert tick["decision"]["verifiable"] is False
    assert tick["decision"]["attribution"] is None
    assert tick["airs"]["dimensions"]["consistency"]["score"] is None
    assert "no upstream" in tick["notes"][0]


# ---- answerers ----------------------------------------------------------------------

class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.usage = SimpleNamespace(input_tokens=0, output_tokens=0)
        self.messages = None

    def call_json(self, messages):
        self.messages = messages
        self.usage.input_tokens += 120
        self.usage.output_tokens += 30
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_a_local_model_answer_is_parsed_verified_and_costs_nothing():
    reply = {"answer": "B is cheapest", "plan": DEMO_PLAN.to_dict(), "value": "B",
             "confidence": 0.9, "abstain": False}
    answerer = OllamaAnswerer("ollama/test-model", client=FakeClient(reply))
    (tick,) = run("demo-healthy", answerer, seeds=[100_001])
    assert tick["cost"] == {"model": "ollama/test-model", "input_tokens": 120,
                            "output_tokens": 30, "usd": 0.0}
    assert tick["decision"]["plan_matches_question"] is True
    system, user = dict(answerer.client.messages)["system"], dict(answerer.client.messages)["user"]
    assert system == ANALYST_SYSTEM and tick["question"]["text"] in user
    assert '"id":' in user


def test_unparseable_output_is_a_parse_failure_and_a_transport_failure_is_an_error():
    answerer = OllamaAnswerer("ollama/test-model", client=FakeClient(None))
    (tick,) = run("demo-healthy", answerer, seeds=[100_002])
    decision = tick["decision"]
    assert (decision["parse_failed"], decision["silent_failure"], decision["attribution"]) == \
        (True, False, None)
    broken = OllamaAnswerer("ollama/test-model", client=FakeClient(ConnectionError("refused")))
    with pytest.raises(AnswererError, match="ollama serve"):
        run("demo-healthy", broken, seeds=[100_002])


@pytest.mark.parametrize("result, expected", [
    ({"abstain": True, "answer": "cannot tell"}, AgentAnswer(text="cannot tell", abstained=True)),
    ({"value": "B", "confidence": "high"}, AgentAnswer(value="B", confidence=0.5)),
    ({"value": 3, "confidence": 7}, AgentAnswer(value=3, confidence=1.0)),
    ({"value": "B", "plan": "min price"}, AgentAnswer(value="B", confidence=0.5)),
    (["not", "an", "object"], AgentAnswer(parse_failed=True)),
])
def test_model_output_is_read_the_way_the_corpus_agents_read_theirs(result, expected):
    assert parse_answer(result) == expected


@pytest.mark.parametrize("spec", ["gpt-4o-mini", "claude-haiku-4-5", "gemini-2.5-flash"])
def test_hosted_models_are_refused_until_spend_caps_exist(spec):
    with pytest.raises(AnswererError, match="spend caps"):
        make_answerer(spec)


def test_an_empty_local_model_name_is_refused():
    with pytest.raises(AnswererError, match="ollama/<name>"):
        OllamaAnswerer("ollama/")


# ---- invariant 1 --------------------------------------------------------------------

FORBIDDEN = ("stale", "fresh", "age", "old", "outdated", "recent", "timestamp",
             "fault", "degrad", "corrupt", "drift", "strip", "latency", "delay",
             "missing", "incomplete", "quality", "trust")


@pytest.mark.parametrize("text", [ANALYST_SYSTEM, ANALYST_USER, DEMO_QUESTION])
def test_the_analyst_prompt_never_hints_at_the_data_being_degraded(text):
    lowered = text.lower()
    for word in FORBIDDEN:
        assert word not in lowered, f"prompt hints at degraded data: {word!r}"


def test_the_prompt_is_identical_whatever_the_pipeline_did():
    stale = PAIRS["demo-stale"].delivered.sample(seed=4)
    healthy = PAIRS["demo-healthy"].delivered.sample(seed=4)
    a = dict(analyst_messages("Q", stale.records))
    b = dict(analyst_messages("Q", healthy.records))
    assert a["system"] == b["system"]
    assert a["user"].split("Records")[0] == b["user"].split("Records")[0]


# ---- airs analyst ask ------------------------------------------------------------------

def test_airs_analyst_ask_prints_verified_ticks(capsys):
    from airsbench.cli import main

    assert main(["analyst", "ask", "demo-stale", "--questions", "3", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["ticks"]) == report["summary"]["questions"] == 3
    assert {t["session_id"] for t in report["ticks"]} == {report["session_id"]}

    assert main(["analyst", "ask", "demo-stale", "--questions", "1"]) == 0
    out = capsys.readouterr().out
    assert "checked as: the record with the lowest price where stock > 0" in out
    assert "questions, 1 verified" in out


@pytest.mark.parametrize("args, message", [
    (["analyst", "ask", "nope"], "no source 'nope'"),
    (["analyst", "ask", "demo-stale", "--question", "cheapest?"], "--question needs --plan"),
    (["analyst", "ask", "demo-stale", "--answerer", "gpt-4o-mini"], "spend caps"),
    (["analyst", "ask", "demo-stale", "--plan", "{not json"], "not valid JSON"),
    (["analyst", "ask", "demo-stale", "--plan", '{"type": "median"}'], "plan type"),
])
def test_airs_analyst_refuses_bad_requests_with_the_fix(capsys, args, message):
    from airsbench.cli import main

    assert main(args) == 2
    assert message in capsys.readouterr().err
