"""Model options and spend caps (plan A5): free local, or your key, never a surprise bill.

Four things must hold before a hosted model is allowed anywhere near a question:

1. **An unpriced hosted model is refused, not free.** `PRICING` omits local models
   deliberately, and `cost_usd` returned 0.0 for anything absent — which would have
   let a cap pass a call it could not price.
2. **The cap is checked before the request.** A refusal must cost nothing, so the
   client is a fake that fails the test if it is ever called.
3. **The key never leaves the environment.** Not into a Tick, not into a log line.
4. **Local stays free and local.** `ollama/<name>` consults no budget and its Tick
   says the records stayed on this machine.
"""

from __future__ import annotations

import json

import pytest

from agentic_faults import Record
from airsbench.agents.llm import (
    PRICING,
    UnpricedModel,
    declared_prices,
    is_gemini_model,
    price_of,
    require_price,
)
from airsbench.analyst.answerers import (
    AnswererError,
    ModelAnswerer,
    make_answerer,
    model_id,
    provider_of,
)
from airsbench.analyst.budget import Budget, DayLedger, SpendRefused, cost_of
from airsbench.analyst.plan import Plan
from airsbench.analyst.session import DEMO_PLAN, Question, ask
from airsbench.sources.config import load_sources

KEY = "sk-test-DO-NOT-LEAK-6Yx9"
REPLY = {"answer": "B is cheapest", "plan": DEMO_PLAN.to_dict(), "value": "B",
         "confidence": 0.9, "abstain": False}


class FakeUsage:
    input_tokens = 0
    output_tokens = 0
    parse_failures = 0


class FakeClient:
    """Counts calls; a test that refuses before calling asserts `calls == 0`."""

    def __init__(self, reply=REPLY, tokens=(1400, 80)):
        self.reply, self.tokens, self.calls = reply, tokens, 0
        self.usage = FakeUsage()

    def call_json(self, messages):
        self.calls += 1
        self.usage.input_tokens += self.tokens[0]
        self.usage.output_tokens += self.tokens[1]
        return self.reply


@pytest.fixture
def ledger(tmp_path):
    return DayLedger(path=tmp_path / "spend.json", today=lambda: "2026-09-18")


@pytest.fixture(autouse=True)
def _no_user_pricing_file(tmp_path, monkeypatch):
    """Never read the author's real ~/.airs/pricing.yaml in a test."""
    monkeypatch.setattr("airsbench.agents.llm.PRICING_FILE", tmp_path / "absent.yaml")
    declared_prices(tmp_path / "absent.yaml", refresh=True)
    yield
    declared_prices(tmp_path / "absent.yaml", refresh=True)


# ---- 1. unpriced means refused ----------------------------------------------

def test_a_hosted_model_with_no_price_is_refused_not_billed_at_zero():
    """The A5 trap: `PRICING.get(...) or 0.0` made every unknown model free."""
    with pytest.raises(UnpricedModel, match="no price for 'gpt-9-ultra'"):
        require_price("gpt-9-ultra")
    with pytest.raises(AnswererError, match="no price"):
        make_answerer("openai/gpt-9-ultra", budget=Budget())


def test_a_local_model_is_free_by_construction():
    assert require_price("ollama/llama3.1:8b") is None
    assert price_of("ollama/llama3.1:8b") is None
    assert cost_of("ollama/llama3.1:8b", 100_000, 10_000) == 0.0


def test_a_declared_price_makes_a_model_usable(tmp_path, monkeypatch):
    path = tmp_path / "pricing.yaml"
    path.write_text("models:\n  gpt-9-ultra: {input_per_mtok: 1.0, output_per_mtok: 4.0}\n")
    monkeypatch.setattr("airsbench.agents.llm.PRICING_FILE", path)
    declared_prices(path, refresh=True)
    assert cost_of("gpt-9-ultra", 1_000_000, 1_000_000) == pytest.approx(5.0)
    assert "gpt-9-ultra" not in PRICING  # declared by the user, not shipped


def test_a_malformed_pricing_file_is_refused_with_the_fix(tmp_path):
    path = tmp_path / "pricing.yaml"
    path.write_text("models:\n  gpt-9-ultra: {input: 1.0}\n")
    with pytest.raises(UnpricedModel, match="input_per_mtok"):
        declared_prices(path, refresh=True)


# ---- 2. the cap is checked before the call ----------------------------------

def test_the_cap_refuses_before_the_request_so_a_refusal_costs_nothing(ledger):
    budget = Budget(session_usd=0.0001, day_usd=1.0, ledger=ledger)
    client = FakeClient()
    answerer = ModelAnswerer("openai/gpt-4o-mini", client=client, budget=budget)
    with pytest.raises(SpendRefused, match="refused before calling gpt-4o-mini"):
        answerer.answer("Which is cheapest?", DEMO_PLAN, [])
    assert client.calls == 0 and budget.spent_usd == 0.0 and ledger.spent() == 0.0


def test_the_day_cap_holds_across_sessions(ledger):
    first = Budget(session_usd=10.0, day_usd=0.001, ledger=ledger)
    client = FakeClient(tokens=(1_000_000, 0))
    ModelAnswerer("openai/gpt-4o-mini", client=client, budget=first).answer("q", DEMO_PLAN, [])
    assert client.calls == 1 and ledger.spent() == pytest.approx(0.15)

    later = Budget(session_usd=10.0, day_usd=0.001, ledger=ledger)  # a fresh session
    second = FakeClient()
    with pytest.raises(SpendRefused, match="daily cap"):
        ModelAnswerer("openai/gpt-4o-mini", client=second,
                      budget=later).answer("q", DEMO_PLAN, [])
    assert second.calls == 0


def test_what_the_call_actually_used_is_charged_not_the_estimate(ledger):
    budget = Budget(session_usd=1.0, day_usd=1.0, ledger=ledger)
    client = FakeClient(tokens=(10, 5))  # far below the pre-call estimate
    answerer = ModelAnswerer("openai/gpt-4o-mini", client=client, budget=budget)
    _answer, usage = answerer.answer("q", DEMO_PLAN, [])
    assert usage.usd == pytest.approx(cost_of("gpt-4o-mini", 10, 5))
    assert budget.spent_usd == usage.usd < answerer.estimate_usd()


def test_a_yesterday_entry_does_not_count_against_today(tmp_path):
    path = tmp_path / "spend.json"
    path.write_text(json.dumps({"2026-09-17": {"usd": 99.0, "models": {}}}))
    assert DayLedger(path=path, today=lambda: "2026-09-18").spent() == 0.0


def test_an_unreadable_spend_file_never_stops_the_tool(tmp_path):
    path = tmp_path / "spend.json"
    path.write_text("{ not json")
    ledger = DayLedger(path=path, today=lambda: "2026-09-18")
    assert ledger.spent() == 0.0
    assert ledger.add("gpt-4o-mini", 0.01) == 0.01


# ---- 3. keys stay in the environment ----------------------------------------

def test_no_key_ever_reaches_a_tick(monkeypatch, ledger):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    budget = Budget(session_usd=1.0, day_usd=1.0, ledger=ledger)
    answerer = ModelAnswerer("openai/gpt-4o-mini", client=FakeClient(), budget=budget)
    tick = ask(load_sources()["demo-healthy"], Question("Which is cheapest?", DEMO_PLAN, n=3),
               answerer, seed=100_001)
    text = json.dumps(tick)
    assert KEY not in text and "sk-" not in text
    assert tick["cost"]["hosted"] is True and tick["cost"]["provider"] == "openai"
    assert tick["cost"]["budget"]["session_cap_usd"] == 1.0
    assert any("were sent to openai" in note for note in tick["notes"])


def test_a_local_tick_says_the_records_stayed_here(ledger):
    answerer = ModelAnswerer("ollama/test-model", client=FakeClient(),
                             budget=Budget(session_usd=0.0, day_usd=0.0, ledger=ledger))
    tick = ask(load_sources()["demo-healthy"], Question("Which is cheapest?", DEMO_PLAN, n=3),
               answerer, seed=100_001)
    assert answerer.budget is None  # a local model consults no cap
    assert tick["cost"]["hosted"] is False and tick["cost"]["usd"] == 0.0
    assert not any("were sent to" in note for note in tick["notes"])


# ---- 4. addressing ----------------------------------------------------------

@pytest.mark.parametrize("spec, provider, model", [
    ("ollama/llama3.1:8b", "ollama", "ollama/llama3.1:8b"),
    ("openai/gpt-4o-mini", "openai", "gpt-4o-mini"),
    ("anthropic/claude-haiku-4-5", "anthropic", "claude-haiku-4-5"),
    ("gemini/gemini-2.5-flash", "gemini", "gemini/gemini-2.5-flash"),
])
def test_a_spec_names_its_provider_and_routes_to_the_right_model(spec, provider, model):
    assert (provider_of(spec), model_id(spec)) == (provider, model)


def test_gemini_keeps_its_prefix_because_its_ids_are_otherwise_unmarked():
    """`gpt-*` and `claude-*` announce themselves; `gemini-2.5-flash` would route
    to the OpenAI client, which would try to bill an OpenAI key for it."""
    assert is_gemini_model(model_id("gemini/gemini-2.5-flash"))
    assert not is_gemini_model(model_id("openai/gpt-4o-mini"))


def test_a_hosted_model_needs_a_budget_object_at_all():
    with pytest.raises(AnswererError, match="needs a spend cap"):
        make_answerer("openai/gpt-4o-mini")


def test_estimate_is_free_and_charges_nothing(ledger):
    budget = Budget(session_usd=1.0, day_usd=1.0, ledger=ledger)
    answerer = ModelAnswerer("openai/gpt-4o-mini", client=FakeClient(), budget=budget)
    assert answerer.estimate_usd() > 0.0
    assert budget.spent_usd == 0.0 and ledger.spent() == 0.0


def test_the_literal_answerer_still_needs_nothing():
    answerer = make_answerer("literal")
    answer, usage = answerer.answer("q", Plan.from_dict(DEMO_PLAN.to_dict()),
                                    [Record(payload={"price": 1.0, "stock": 1},
                                            meta={"record_id": "A"})])
    assert (answer.value, usage.usd) == ("A", 0.0)
