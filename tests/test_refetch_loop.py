"""The loop as the refetch arm will drive it (docs/refetch_arm.md, build step 1).

What has to hold before a cent is spent, and why each one is here:

- **The re-read continues the conversation (D1 a).** The model sees its own
  request, then the records read again, and is offered nothing further — so the
  exchange ends in an answer or an abstention, by construction.
- **An action is never an answer.** A reply that is still a request to re-read
  was graded as a committed wrong answer until 23 Sep — a silent failure the
  model never claimed (§2.5). It is unusable output now, and never silent.
- **Invariant 1 holds in the second turn too.** The follow-up says what
  happened, never why it might matter.
- **Age is the detectability treatment, and only that.** Shown through the
  runner's own `attach_record_age`, in meta, so no AIRS dimension moves
  (invariant 5); a re-read's records show their own true age.
- **Provenance is the caller's.** Live stays the default; the arm's Ticks say
  they are the arm's, or every loader would drop them as live traffic.
- **Paired (invariant 2).** One question seed gives one query, one simulated
  moment and one candidate set, whatever the mode, prompt or age setting.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from airsbench.analyst.answerers import LiteralAnswerer, ModelAnswerer, Usage
from airsbench.analyst.loop import Loop
from airsbench.analyst.prompts import REFETCH_SYSTEM, REREAD_USER, render_analyst_records
from airsbench.analyst.session import DEMO_PLAN, LIVE_SEED_BLOCK, demo_question
from airsbench.analyst.verifier import AgentAnswer, verify
from airsbench.gate.policy import Policy
from airsbench.runner.config import REFETCH_SEED_RANGE, arm_of
from airsbench.runner.execute import RECORD_AGE_META_KEY
from airsbench.sources.demo import BUILT_IN, demo_pair

OPEN = Policy(name="open")
STRICT_AGE = Policy(name="fresh", max_record_age_seconds=2.0)
ARM = {"arm": "refetch", "seed_block": list(REFETCH_SEED_RANGE)}
SEED = 90_001
# sample_seed × 1 000 + i, as the arm draws it: replication 1, question 4 — one
# with all six candidates, so a partial re-read leaves some records untouched.
QUESTION_SEED = 10_001_004

# Both word lists the repository already holds the analyst prompts to (the loop's
# and the stricter session one), because the follow-up is a prompt like any other.
FORBIDDEN = ("stale", "staleness", "fresh", "outdated", "out of date", "drift", "degraded",
             "fault", "corrupt", "broken", "missing", "unreliable", "wrong", "old data",
             "age", "old", "recent", "timestamp", "degrad", "strip", "latency", "delay",
             "incomplete", "quality", "trust")


def arm_pair(state: str = "demo-stale", *, age: bool = False, clock=None):
    kwargs = {"clock": clock} if clock is not None else {}
    return demo_pair(state, BUILT_IN[state], seed=SEED, emit_record_age=age, **kwargs)


def sample_ids(state: str = "demo-stale") -> list[str]:
    return arm_pair(state).delivered.sample(6, seed=QUESTION_SEED).ids


class FakeClient:
    """Stands in for LLMClient: scripted JSON replies, every message list kept."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []
        self.usage = SimpleNamespace(input_tokens=0, output_tokens=0)

    def call_json(self, messages):
        self.sent.append(messages)
        self.usage.input_tokens += 1_000
        self.usage.output_tokens += 50
        return self.replies[min(len(self.sent) - 1, len(self.replies) - 1)]


class Capturing:
    """A test answerer that asks for a re-read once and keeps what it was shown."""

    name = "capturing"

    def __init__(self, ask_for):
        self.ask_for, self.shown = tuple(ask_for), []

    def answer(self, question, plan, records):
        self.shown.append(list(records))
        if len(self.shown) == 1:
            return AgentAnswer(refetch_ids=self.ask_for, text="check these"), Usage(self.name)
        return AgentAnswer(value=records[0].meta["record_id"], confidence=0.9,
                           plan=DEMO_PLAN.to_dict()), Usage(self.name)


def agent(fake: FakeClient) -> ModelAnswerer:
    return ModelAnswerer("ollama/x", client=fake, offer_refetch=True)


# ---- D1 a: the re-read continues the conversation -----------------------------------

def test_the_re_read_is_a_second_turn_of_the_same_exchange():
    ids = sample_ids()
    answer = {"answer": "the first one", "plan": DEMO_PLAN.to_dict(), "value": ids[0],
              "confidence": 0.8, "abstain": False}
    fake = FakeClient({"action": "refetch", "ids": ids[:2], "why": "prices vary"}, answer)
    loop = Loop(pair=arm_pair(), policy=OPEN, answerer=agent(fake), mode="agent")
    tick = loop.ask(demo_question(), seed=QUESTION_SEED)

    assert len(fake.sent) == 2
    first, second = fake.sent
    assert [role for role, _ in second] == ["system", "user", "assistant", "user"]
    assert second[:2] == first  # the exchange continues; nothing before it is rewritten
    assert second[0][1] == REFETCH_SYSTEM
    assert json.loads(second[2][1]) == {"action": "refetch", "ids": ids[:2],
                                        "why": "prices vary"}
    follow_up = second[3][1]
    assert f"({ids[0]}, {ids[1]}) were read again" in follow_up
    assert "cannot be read again" in follow_up  # no second offer
    # The whole candidate set comes back, the re-read records swapped in.
    for record_id in ids:
        assert f'"id": "{record_id}"' in follow_up

    assert tick["refetch"]["asked_ids"] == ids[:2]
    assert tick["refetch"]["why"] == "prices vary"
    assert tick["refetch"]["initiated_by"] == "agent"
    assert tick["decision"]["unanswered_action"] is False
    assert tick["cost"]["input_tokens"] == 2_000  # both calls, not the last


def test_a_model_that_keeps_asking_gets_two_calls_and_no_answer():
    ids = sample_ids()
    fake = FakeClient({"action": "refetch", "ids": ids[:1], "why": "again"})
    loop = Loop(pair=arm_pair(), policy=OPEN, answerer=agent(fake), mode="agent")
    tick = loop.ask(demo_question(), seed=QUESTION_SEED)
    assert len(fake.sent) == 2
    decision = tick["decision"]
    assert decision["parse_failed"] is True and decision["unanswered_action"] is True
    assert decision["silent_failure"] is False and decision["correct"] is False
    assert decision["attribution"] is None
    assert tick["running"]["silent_failures"] == 0
    assert any("counted as no answer" in note for note in tick["notes"])


def test_an_answerer_without_a_conversation_is_simply_asked_again():
    ids = sample_ids()
    answerer = Capturing(ids[:1])
    loop = Loop(pair=arm_pair(), policy=OPEN, answerer=answerer, mode="agent")
    tick = loop.ask(demo_question(), seed=QUESTION_SEED)
    assert len(answerer.shown) == 2 and tick["decision"]["unanswered_action"] is False


# ---- an action is never an answer ---------------------------------------------------

@pytest.mark.parametrize("mode", ["off", "gate"])
def test_an_action_where_none_was_offered_is_not_graded(mode):
    fake = FakeClient({"action": "refetch", "ids": sample_ids()[:1]})
    loop = Loop(pair=arm_pair(), policy=OPEN, answerer=ModelAnswerer("ollama/x", client=fake),
                mode=mode)
    tick = loop.ask(demo_question(), seed=QUESTION_SEED)
    assert len(fake.sent) == 1 and tick["refetch"]["attempted"] is False
    assert tick["decision"]["unanswered_action"] is True
    assert tick["decision"]["silent_failure"] is False


def test_the_verifier_never_commits_a_request_even_carrying_the_right_value():
    pair = arm_pair("demo-healthy")
    sample = pair.delivered.sample(6, seed=QUESTION_SEED)
    truth = pair.upstream.fetch(sample.ids, as_of=sample.as_of)
    right, _ = LiteralAnswerer().answer("", DEMO_PLAN, truth)
    sneaky = AgentAnswer(value=right.value, confidence=1.0, refetch_ids=("x",))
    result = verify(DEMO_PLAN, sneaky, delivered=sample.records, served=truth, truth=truth)
    assert result.correct is False and result.silent_failure is False
    assert result.attribution is None


def test_every_tick_carries_the_flag_including_refusals():
    loop = Loop(pair=arm_pair(), policy=STRICT_AGE, answerer=LiteralAnswerer(), mode="off")
    tick = loop.ask(demo_question(), seed=QUESTION_SEED)
    assert tick["gate"]["verdict"] == "refuse"
    assert tick["decision"]["unanswered_action"] is False


# ---- invariant 1 in the second turn -------------------------------------------------

def test_the_follow_up_never_hints_at_the_data_being_degraded():
    lowered = REREAD_USER.lower()
    assert [word for word in FORBIDDEN if word in lowered] == []


# ---- age: the detectability treatment, and only that -------------------------------

@pytest.mark.parametrize(("state", "age"), [("demo-stale", 5.05), ("demo-healthy", 0.05)])
def test_age_shown_is_the_records_true_age(state, age):
    records = arm_pair(state, age=True).delivered.sample(6, seed=QUESTION_SEED).records
    assert {record.meta[RECORD_AGE_META_KEY] for record in records} == {age}
    assert '"_record_age_seconds"' in render_analyst_records(records)


def test_age_is_absent_unless_asked_for():
    records = arm_pair().delivered.sample(6, seed=QUESTION_SEED).records
    assert all(RECORD_AGE_META_KEY not in record.meta for record in records)
    assert "_record_age_seconds" not in render_analyst_records(records)


def test_showing_age_moves_no_airs_dimension():
    """Invariant 5: the treatment is what the agent reads, never what AIRS scores."""
    def dimensions(age):
        clock = lambda: 1_000_000.0  # noqa: E731 — identical timestamps in both reads
        loop = Loop(pair=arm_pair(age=age, clock=clock), policy=OPEN,
                    answerer=LiteralAnswerer(), mode="off", clock=clock)
        tick = loop.ask(demo_question(), seed=QUESTION_SEED)
        return {dim: value["score"] for dim, value in tick["airs"]["dimensions"].items()}

    assert dimensions(True) == dimensions(False)


def test_records_read_again_show_their_own_age():
    ids = sample_ids()
    assert len(ids) == 6  # otherwise the untouched half below is empty and proves nothing
    answerer = Capturing(ids[:2])
    loop = Loop(pair=arm_pair(age=True), policy=OPEN, answerer=answerer, mode="agent")
    loop.ask(demo_question(), seed=QUESTION_SEED)
    after = {record.meta["record_id"]: record.meta[RECORD_AGE_META_KEY]
             for record in answerer.shown[1]}
    assert {after[i] for i in ids[:2]} == {0.0}      # read just now
    assert {after[i] for i in ids[2:]} == {5.05}     # as first delivered


# ---- provenance ------------------------------------------------------------------------

def test_live_stays_the_default():
    tick = Loop(pair=arm_pair(), policy=OPEN, answerer=LiteralAnswerer(),
                mode="off").ask(demo_question(), seed=QUESTION_SEED)
    assert tick["provenance"]["arm"] == "live"
    assert tick["provenance"]["seed_block"] == list(LIVE_SEED_BLOCK)


def test_the_arm_stamps_its_own_provenance():
    tick = Loop(pair=arm_pair(), policy=OPEN, answerer=LiteralAnswerer(), mode="off",
                provenance=ARM).ask(demo_question(), seed=QUESTION_SEED)
    assert tick["provenance"] == {**ARM, "seed": QUESTION_SEED,
                                  "session_id": tick["session_id"]}
    assert arm_of(SEED) == "refetch"


# ---- paired (invariant 2) ---------------------------------------------------------------

def _where(tick):
    return (tick["question"]["key"], tick["records"]["simulated_time"], tick["records"]["ids"])


def test_one_question_seed_is_one_question_in_every_cell():
    cells = [("off", False), ("gate", False), ("agent", False), ("agent", True)]
    seen = set()
    for mode, age in cells:
        loop = Loop(pair=arm_pair(age=age), policy=OPEN, answerer=LiteralAnswerer(), mode=mode)
        tick = loop.ask(demo_question(), seed=QUESTION_SEED)
        seen.add(json.dumps(_where(tick)))
    assert len(seen) == 1


def test_healthy_and_stale_share_the_query_and_the_moment():
    ticks = [Loop(pair=arm_pair(state), policy=OPEN, answerer=LiteralAnswerer(),
                  mode="off").ask(demo_question(), seed=QUESTION_SEED)
             for state in ("demo-healthy", "demo-stale")]
    healthy, stale = (_where(tick) for tick in ticks)
    assert healthy[:2] == stale[:2]
    # The served moment is the one thing that differs: that is the treatment.
    assert ticks[0]["records"]["served_as_of"] - ticks[1]["records"]["served_as_of"] == \
        pytest.approx(5.0)
