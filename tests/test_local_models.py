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
