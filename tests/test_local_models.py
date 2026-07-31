"""Locally-served open-weight models must go through the identical harness.

RQ5 asks whether the RANKING of infrastructure properties holds across model
classes. That is only a claim about models if everything else is held constant,
so a local model must reach the same prompts, the same parser, and the same
treatment of unparseable output as a failure rather than an error. Ollama
speaks the OpenAI protocol, so the integration is a base-URL swap and nothing
downstream changes — these tests pin that nothing else did.
"""

from __future__ import annotations

import pytest

from airsbench.agents.llm import (
    DEFAULT_OLLAMA_BASE_URL,
    OLLAMA_PREFIX,
    PRICING,
    LLMClient,
    LLMUsage,
    estimate_cost_usd,
    is_anthropic_model,
    is_local_model,
    local_model_name,
    ollama_base_url,
)

LOCAL = f"{OLLAMA_PREFIX}llama3.1:8b"


# ---- routing ---------------------------------------------------------------

def test_local_models_are_recognised_and_hosted_ones_are_not():
    assert is_local_model(LOCAL)
    assert not is_local_model("gpt-4o-mini")
    assert not is_local_model("claude-haiku-4-5")


def test_the_prefix_is_stripped_before_the_name_reaches_the_server():
    assert local_model_name(LOCAL) == "llama3.1:8b"
    assert local_model_name("gpt-4o-mini") == "gpt-4o-mini"


def test_a_colon_in_the_model_tag_survives():
    """Ollama tags are 'name:size'; only the routing prefix may be removed."""
    assert local_model_name(f"{OLLAMA_PREFIX}qwen2.5:14b-instruct") == "qwen2.5:14b-instruct"


def test_base_url_is_overridable_for_a_remote_ollama_host(monkeypatch):
    assert ollama_base_url() == DEFAULT_OLLAMA_BASE_URL
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://gpu-box:11434/v1")
    assert ollama_base_url() == "http://gpu-box:11434/v1"


# ---- cost ------------------------------------------------------------------

def test_local_models_are_free_and_stay_out_of_pricing():
    assert LOCAL not in PRICING
    assert estimate_cost_usd(LOCAL, 10_000, 1150, 30) == 0.0

    usage = LLMUsage()
    usage.add(input_tokens=500_000, output_tokens=50_000, latency_ms=1.0)
    assert usage.cost_usd(LOCAL) == 0.0


def test_a_hosted_model_is_still_priced():
    """The zero above must come from being local, not from pricing being broken."""
    assert estimate_cost_usd("gpt-4o-mini", 10_000, 1150, 30) > 0.0


# ---- client construction ---------------------------------------------------

def test_a_local_client_needs_no_api_key(monkeypatch):
    monkeypatch.setattr("airsbench.agents.llm.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = LLMClient(LOCAL, temperature=0.2)
    assert client.model == LOCAL
    assert client.chat.model_name == "llama3.1:8b"


def test_a_hosted_client_still_refuses_without_a_key(monkeypatch):
    """The local path must not have weakened the guard for hosted models."""
    monkeypatch.setattr("airsbench.agents.llm.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        LLMClient("gpt-4o-mini", temperature=0.2)


def test_a_local_client_points_at_the_local_endpoint(monkeypatch):
    monkeypatch.setattr("airsbench.agents.llm.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-be-used")
    client = LLMClient(LOCAL, temperature=0.0)
    assert str(client.chat.openai_api_base) == DEFAULT_OLLAMA_BASE_URL


def test_local_inference_gets_a_longer_timeout(monkeypatch):
    """A 60 s timeout fails local runs that would otherwise have succeeded."""
    monkeypatch.setattr("airsbench.agents.llm.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert (
        LLMClient(LOCAL, temperature=0.0).chat.request_timeout
        > LLMClient("gpt-4o-mini", temperature=0.0).chat.request_timeout
    )


def test_temperature_reaches_the_local_model_unchanged(monkeypatch):
    """Held-constant variable: it must not be silently dropped on this path."""
    monkeypatch.setattr("airsbench.agents.llm.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert LLMClient(LOCAL, temperature=0.2).chat.temperature == pytest.approx(0.2)


# ---- the grid --------------------------------------------------------------

def test_a_local_model_builds_the_same_reduced_factorial():
    from airsbench.runner.config import build_cross_model_subset

    local = build_cross_model_subset(LOCAL)
    hosted = build_cross_model_subset("claude-haiku-4-5")
    assert len(local) == len(hosted)
    assert all(cfg.model == LOCAL for cfg in local)
    assert [c.seed for c in local] == [c.seed for c in hosted]


def test_the_cross_model_grid_costs_nothing_to_estimate_for_a_local_model():
    from airsbench.runner.config import build_cross_model_subset
    from airsbench.runner.run import estimate_grid_cost

    grid = build_cross_model_subset(LOCAL)
    for cfg in grid:
        cfg.n_queries = 100
    assert estimate_grid_cost(grid) == 0.0


# ---- Anthropic routing -----------------------------------------------------
#
# Claude goes through langchain-anthropic rather than the Anthropic SDK so the
# harness stays identical across arms — same prompts, same parser, same
# treatment of unparseable output. RQ5 must compare models, not harnesses.

HAIKU = "claude-haiku-4-5"


def test_claude_models_route_to_anthropic_and_nothing_else_does():
    assert is_anthropic_model(HAIKU)
    assert not is_anthropic_model("gpt-4o-mini")
    assert not is_anthropic_model(LOCAL)
    assert not is_local_model(HAIKU)


def test_haiku_is_priced_and_matches_the_published_rate():
    """$1.00 / $5.00 per million tokens."""
    assert PRICING[HAIKU]["input"] == pytest.approx(1.00 / 1e6)
    assert PRICING[HAIKU]["output"] == pytest.approx(5.00 / 1e6)


def test_no_priced_claude_id_carries_a_date_suffix():
    """The aliases are complete as written; a date-suffixed variant 404s."""
    import re

    for model in (m for m in PRICING if is_anthropic_model(m)):
        assert not re.search(r"-20\d{6}$", model), f"{model} looks date-suffixed"


def test_an_anthropic_client_needs_its_own_key(monkeypatch):
    monkeypatch.setattr("airsbench.agents.llm.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LLMClient(HAIKU, temperature=0.2)


def test_temperature_reaches_haiku_unchanged(monkeypatch):
    """Held-constant variable. Haiku 4.5 still accepts sampling parameters —
    Sonnet 5 and Opus 4.7+ reject them, which is why this arm uses Haiku."""
    monkeypatch.setattr("airsbench.agents.llm.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert LLMClient(HAIKU, temperature=0.2).chat.temperature == pytest.approx(0.2)


def test_the_cross_model_arm_costs_what_the_roadmap_budgeted():
    from airsbench.runner.config import build_cross_model_subset
    from airsbench.runner.run import estimate_grid_cost

    grid = build_cross_model_subset(HAIKU)
    for cfg in grid:
        cfg.n_queries = 100
    assert estimate_grid_cost(grid) == pytest.approx(1.68, abs=0.05)
