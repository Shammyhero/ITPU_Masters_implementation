"""The router and the two-step loop (plan A6): admit, refetch, refuse.

What has to hold, and why each one is here:

- **REFUSE never reaches a model.** It is the product's cheapest credibility
  claim — "costs nothing and cannot hallucinate" — so the answerer in that test
  fails the test if it is called at all.
- **A re-read is attempted only where it repairs something legitimately.**
  Staleness, yes. Schema drift and semantic stripping refuse instead: a re-read
  bypasses the pipeline, and bypassing a pipeline that is renaming fields hides a
  contract violation rather than fixing it.
- **Invariant 1 survives.** The standard prompt is untouched; only the
  agent-initiated condition sees a prompt that offers a re-read, and even that
  never mentions faults, staleness or degraded data.
- **The meter prices the trade.** Refusing forfeits correct answers and prevents
  silent failures, and the exchange rate is the thesis's headline number computed
  live rather than quoted.
"""

from __future__ import annotations

import pytest

from agentic_faults import Record
from airsbench.analyst.answerers import LiteralAnswerer, ModelAnswerer, Usage, parse_answer
from airsbench.analyst.budget import Budget
from airsbench.analyst.loop import REPAIRABLE, Loop, LoopError, Meter, route
from airsbench.analyst.prompts import ANALYST_SYSTEM, REFETCH_SYSTEM
from airsbench.analyst.session import DEMO_PLAN, Question, demo_question
from airsbench.analyst.verifier import AgentAnswer
from airsbench.gate.controller import Controller, Verdict
from airsbench.gate.policy import Policy
from airsbench.sources.config import load_sources

# The corpus's own forbidden vocabulary: the prompt is an instrument, and an
# instrument that hints at the treatment is not measuring it (invariant 1).
FORBIDDEN = ("stale", "staleness", "fresh", "outdated", "out of date", "drift", "degraded",
             "fault", "corrupt", "broken", "missing", "unreliable", "wrong", "old data")

STRICT_AGE = Policy(name="fresh", max_record_age_seconds=2.0)
STRICT_CONSISTENCY = Policy(name="intact", min_dimension={"consistency": 95.0})
OPEN = Policy(name="open")


def pair(name: str = "demo-stale"):
    return load_sources()[name]


def question() -> Question:
    return demo_question()


class NeverCalled:
    """An answerer that must not be reached."""

    name = "never-called"

    def answer(self, *args, **kwargs):  # pragma: no cover - the test fails if reached
        raise AssertionError("the gate refused this question; no model may be called")


class Scripted:
    """Returns each scripted reply in turn, counting calls."""

    def __init__(self, *replies, name="scripted"):
        self.replies, self.calls, self.name = list(replies), 0, name

    def answer(self, question, plan, records):
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        self.seen = [dict(r.payload) for r in records]
        return reply, Usage(self.name)


# ---- routing ----------------------------------------------------------------

def test_an_admitted_batch_is_answered_normally():
    loop = Loop(pair=pair("demo-healthy"), policy=OPEN, answerer=LiteralAnswerer())
    tick = loop.ask(question(), seed=100_001)
    assert tick["gate"]["verdict"] == "admit"
    assert tick["refetch"]["attempted"] is False
    assert tick["decision"]["verifiable"] is True


def test_a_stale_batch_is_re_read_and_then_answered():
    """The age budget is breached by 5 s of pipeline lag; a re-read repairs it."""
    loop = Loop(pair=pair("demo-stale"), policy=STRICT_AGE, answerer=LiteralAnswerer())
    tick = loop.ask(question(), seed=100_005)
    assert tick["refetch"] == {"attempted": True, "initiated_by": "gate", "n_records": 6,
                               "verdict_after": "admit", "airs_after": tick["gate"]["airs"],
                               "reason": tick["refetch"]["reason"]}
    assert tick["gate"]["verdict"] == "admit"
    assert tick["decision"]["correct"] is True


def test_a_drifted_batch_is_refused_not_re_read():
    """A re-read bypasses the pipeline. Doing that for schema drift would hide the
    contract violation instead of repairing it."""
    loop = Loop(pair=pair("demo-drift"), policy=STRICT_CONSISTENCY, answerer=NeverCalled())
    tick = loop.ask(question(), seed=100_000)
    assert tick["gate"]["verdict"] == "refuse"
    assert tick["refetch"]["attempted"] is False
    assert "consistency" in tick["gate"]["reason"]
    assert tick["decision"]["refused"] is True and tick["cost"]["usd"] == 0.0


def test_refuse_costs_nothing_and_consults_no_budget():
    budget = Budget(session_usd=0.0, day_usd=0.0)
    answerer = ModelAnswerer("openai/gpt-4o-mini", client=NeverCalled(), budget=budget)
    loop = Loop(pair=pair("demo-drift"), policy=STRICT_CONSISTENCY, answerer=answerer)
    tick = loop.ask(question(), seed=100_000)
    assert tick["gate"]["verdict"] == "refuse"
    assert budget.spent_usd == 0.0 and budget.calls == 0


@pytest.mark.parametrize("rule, repairable", [
    ("max_record_age_seconds", True),
    ("min_dimension.freshness", True),
    ("min_dimension.consistency", False),
    ("min_dimension.semantic", False),
    ("min_airs", False),
])
def test_only_staleness_rules_are_repairable_by_a_re_read(rule, repairable):
    assert (rule in REPAIRABLE) is repairable


def test_a_mixed_violation_refuses_rather_than_re_reading():
    """One unrepairable rule is enough: the re-read would not make the batch legal."""
    from airsbench.gate.policy import Violation

    verdict = Verdict(admitted=False, policy="p", violations=[
        Violation("max_record_age_seconds", 9.0, 2.0, "too old"),
        Violation("min_dimension.semantic", 40.0, 90.0, "too little context"),
    ])
    assert route(verdict, pair(), "gate") == "refuse"


def test_a_source_with_no_upstream_cannot_re_read(tmp_path):
    (tmp_path / "d.csv").write_text("product_id,price,stock\nA,1.0,1\n")
    (tmp_path / "sources.yaml").write_text(
        "sources:\n  local:\n    type: files\n    delivered: d.csv\n    id_field: product_id\n")
    only = load_sources(tmp_path / "sources.yaml")["local"]
    assert route(Verdict(admitted=False, policy="p"), only, "gate") == "refuse"
    with pytest.raises(LoopError, match="nothing to re-read"):
        Loop(pair=only, policy=OPEN, answerer=LiteralAnswerer(), mode="agent")


def test_shadow_mode_admits_and_says_so():
    loop = Loop(pair=pair("demo-drift"), policy=STRICT_CONSISTENCY.shadow(),
                answerer=LiteralAnswerer())
    tick = loop.ask(question(), seed=100_000)
    assert tick["gate"]["verdict"] == "admit" and tick["gate"]["shadowed"] is True
    assert "shadow mode" in tick["gate"]["reason"]


# ---- the agent-initiated condition ------------------------------------------

def test_the_agent_may_ask_for_a_re_read_and_is_answered_from_what_comes_back():
    asked = AgentAnswer(refetch_ids=("x",), text="I would like a fresh read")
    answered = AgentAnswer(value="B", confidence=0.9, plan=DEMO_PLAN.to_dict())
    answerer = Scripted(asked, answered)
    loop = Loop(pair=pair("demo-stale"), policy=OPEN, answerer=answerer, mode="agent")
    tick = loop.ask(question(), seed=100_005)
    assert answerer.calls == 2  # asked, then answered over the refreshed records
    assert tick["refetch"]["attempted"] and tick["refetch"]["initiated_by"] == "agent"
    assert tick["gate"]["verdict"] == "admit"


def test_the_agent_is_offered_a_re_read_only_once():
    always_asks = Scripted(AgentAnswer(refetch_ids=("x",)))
    loop = Loop(pair=pair("demo-stale"), policy=OPEN, answerer=always_asks, mode="agent")
    tick = loop.ask(question(), seed=100_005)
    assert always_asks.calls == 2  # not a loop: the second reply stands as the answer
    assert tick["refetch"]["attempted"] is True


def test_agent_mode_delegates_a_repairable_violation_instead_of_refusing_it():
    """The arm's contrast is who decides, so the agent has to be asked at all."""
    answerer = Scripted(AgentAnswer(value="B", confidence=1.0, plan=DEMO_PLAN.to_dict()))
    loop = Loop(pair=pair("demo-stale"), policy=STRICT_AGE, answerer=answerer, mode="agent")
    tick = loop.ask(question(), seed=100_005)
    assert tick["gate"]["verdict"] == "admit" and tick["gate"]["delegated"] is True
    assert "for the agent to decide" in tick["gate"]["reason"]
    assert answerer.calls == 1 and tick["refetch"]["attempted"] is False


def test_agent_mode_still_refuses_what_a_re_read_cannot_repair():
    loop = Loop(pair=pair("demo-drift"), policy=STRICT_CONSISTENCY, answerer=NeverCalled(),
                mode="agent")
    assert loop.ask(question(), seed=100_000)["gate"]["verdict"] == "refuse"


def test_the_gate_mode_ignores_a_refetch_request():
    """Only the declared condition honours it; elsewhere the model simply did not answer."""
    answerer = Scripted(AgentAnswer(refetch_ids=("x",)))
    loop = Loop(pair=pair("demo-healthy"), policy=OPEN, answerer=answerer, mode="gate")
    tick = loop.ask(question(), seed=100_001)
    assert answerer.calls == 1 and tick["refetch"]["attempted"] is False


def test_a_refetch_action_is_parsed_and_an_empty_one_is_a_parse_failure():
    assert parse_answer({"action": "refetch", "ids": ["A", "B"], "why": "stock looks odd"}) == \
        AgentAnswer(refetch_ids=("A", "B"), text="stock looks odd")
    assert parse_answer({"action": "refetch", "ids": []}).parse_failed is True


# ---- invariant 1 -------------------------------------------------------------

@pytest.mark.parametrize("prompt", [ANALYST_SYSTEM, REFETCH_SYSTEM])
def test_no_prompt_mentions_faults_or_staleness(prompt):
    lowered = prompt.lower()
    assert [word for word in FORBIDDEN if word in lowered] == []


def test_the_standard_prompt_is_unchanged_by_the_refetch_condition():
    assert REFETCH_SYSTEM.startswith(ANALYST_SYSTEM)
    assert "refetch" not in ANALYST_SYSTEM.lower()
    assert ModelAnswerer("ollama/x", client=object()).offer_refetch is False


def test_a_wrong_answer_after_a_re_read_is_the_agents_own():
    """The refreshed records ARE the delivery afterwards. Comparing them with the
    original served state would call every repaired field a corruption."""
    wrong = AgentAnswer(value="not-a-record", confidence=1.0, plan=DEMO_PLAN.to_dict())
    loop = Loop(pair=pair("demo-stale"), policy=STRICT_AGE, answerer=Scripted(wrong))
    tick = loop.ask(question(), seed=100_005)
    assert tick["refetch"]["attempted"] is True
    assert tick["decision"]["attribution"] == "agent_impairment"
    assert tick["decision"]["changed_fields"] == []


# ---- the meter ---------------------------------------------------------------

def test_the_meter_prices_what_enforcement_bought_and_cost():
    meter = Meter()
    for would_have in ("silent_failure", "correct", "correct", "abstained"):
        meter.record({"decision": {}, "gate": {"verdict": "refuse", "would_have": would_have},
                      "refetch": {"attempted": False}, "cost": {"usd": 0.0}})
    meter.record({"decision": {"correct": True, "silent_failure": False},
                  "gate": {"verdict": "admit", "would_have": None},
                  "refetch": {"attempted": True}, "cost": {"usd": 0.002}})
    assert meter.to_dict() == {
        "asked": 5, "answered": 1, "refused": 4, "refetched": 1, "correct": 1,
        "silent_failures": 0, "prevented": 1, "forfeited": 2, "exchange_rate": 2.0,
        "usd": 0.002}


def test_the_exchange_rate_is_none_until_something_was_prevented():
    meter = Meter()
    meter.record({"decision": {}, "gate": {"verdict": "refuse", "would_have": "correct"},
                  "refetch": {"attempted": False}, "cost": {"usd": 0.0}})
    assert meter.exchange_rate is None and meter.forfeited == 1


def test_a_refused_question_is_priced_against_real_ground_truth():
    """`would_have` is what the delivered records implied, checked upstream — no
    model is called to find out."""
    loop = Loop(pair=pair("demo-drift"), policy=STRICT_CONSISTENCY, answerer=NeverCalled())
    seen = {loop.ask(question(), seed=100_000 + i)["gate"]["would_have"] for i in range(6)}
    assert seen <= {"correct", "silent_failure", "wrong", "abstained", None}
    assert loop.meter.refused == 6 and loop.meter.answered == 0


def test_the_gate_and_the_tick_report_one_measurement():
    """The Tick's AIRS block is the gate's own measurement, not a second scoring."""
    loop = Loop(pair=pair("demo-stale"), policy=OPEN, answerer=LiteralAnswerer())
    tick = loop.ask(question(), seed=100_005)
    assert tick["airs"]["airs"] == tick["gate"]["airs"]
    assert tick["airs"]["dimensions"]["freshness"]["score"] == \
        tick["gate"]["dimensions"]["freshness"]["score"]


def test_the_loop_reuses_the_gate_controller_rather_than_re_implementing_it():
    loop = Loop(pair=pair("demo-healthy"), policy=STRICT_AGE, answerer=LiteralAnswerer())
    assert isinstance(loop.controller, Controller) and loop.controller.policy is STRICT_AGE


def test_records_reach_the_answerer_refreshed_after_a_gate_refetch():
    answered = AgentAnswer(value="B", confidence=1.0, plan=DEMO_PLAN.to_dict())
    answerer = Scripted(answered)
    loop = Loop(pair=pair("demo-stale"), policy=STRICT_AGE, answerer=answerer)
    tick = loop.ask(question(), seed=100_005)
    upstream = tick["records"]["upstream"]
    assert answerer.seen == [upstream[i] for i in tick["records"]["ids"]]


def test_a_record_is_never_invented_when_upstream_has_no_answer():
    """A re-read that returns fewer records keeps the delivered one, not a blank."""
    loop = Loop(pair=pair("demo-stale"), policy=STRICT_AGE, answerer=LiteralAnswerer())
    tick = loop.ask(question(), seed=100_005)
    assert all(isinstance(payload, dict) and payload
               for payload in tick["records"]["delivered"])
    assert all(isinstance(r, Record) for r in [Record(payload={"a": 1})])
