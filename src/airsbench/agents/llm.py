"""LLM client wrapper: one call in, parsed JSON + token usage out.

Failure-handling commitment (methodology): when the model returns
unparseable output, that is recorded as an agent failure, not as an
infrastructure error to retry. Refusing, hallucinating, or emitting
malformed output under degraded data are exactly the production failure
modes this study measures. Only transport errors (network, rate limit)
are retried.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Locally-served open-weight models, addressed as "ollama/<model>". Ollama
# exposes an OpenAI-compatible endpoint, so the same client drives it and no
# extra dependency is needed. They are absent from PRICING, which is what makes
# them free: estimate_cost_usd and LLMUsage.cost_usd both return 0.0 for a
# model they do not price.
ANTHROPIC_PREFIX = "claude-"
OLLAMA_PREFIX = "ollama/"
GEMINI_PREFIX = "gemini/"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
# Local inference is far slower than a hosted API, especially on first load
# while weights page in. A 60 s timeout fails runs that would have succeeded.
LOCAL_TIMEOUT_S = 300

# Pricing (USD per token), for run-level cost accounting and the budget guard.
# Locally-served models are deliberately absent — see OLLAMA_PREFIX above.
PRICING = {
    "gpt-4o-mini": {"input": 0.15 / 1e6, "output": 0.60 / 1e6},
    "gpt-4.1-mini": {"input": 0.40 / 1e6, "output": 1.60 / 1e6},
    "claude-haiku-4-5": {"input": 1.00 / 1e6, "output": 5.00 / 1e6},
    "claude-sonnet-5": {"input": 2.00 / 1e6, "output": 10.00 / 1e6},
}
# Prices the user declares for models this table does not carry, so nothing here
# is a guess at someone else's price list and no hosted call is ever budgeted at
# $0 (author decision, 17 Sep; plan A5 "declare or refuse").
#
#     models:
#       gpt-5-mini:      {input_per_mtok: 0.25, output_per_mtok: 2.00}
#       gemini/gemini-2.5-flash: {input_per_mtok: 0.30, output_per_mtok: 2.50}
PRICING_FILE = Path.home() / ".airs" / "pricing.yaml"
_DECLARED: dict[str, dict[str, float]] | None = None


class UnpricedModel(RuntimeError):
    """A hosted model with no price: refused rather than budgeted as free."""
JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader — avoids a dependency for one small job."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    parse_failures: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    def add(self, input_tokens: int, output_tokens: int, latency_ms: float) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1
        self.latencies_ms.append(latency_ms)

    def cost_usd(self, model: str) -> float:
        price = price_of(model)
        if price is None:
            return 0.0
        return self.input_tokens * price["input"] + self.output_tokens * price["output"]


def declared_prices(path: Path | str = PRICING_FILE,
                    refresh: bool = False) -> dict[str, dict[str, float]]:
    """Per-token prices the user declared for models `PRICING` does not carry."""
    global _DECLARED
    if _DECLARED is not None and not refresh:
        return _DECLARED
    path = Path(path)
    prices: dict[str, dict[str, float]] = {}
    if path.exists():
        import yaml

        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        models = document.get("models") if isinstance(document, dict) else None
        if not isinstance(models, dict):
            raise UnpricedModel(f"{path}: expected models: mapping each model to "
                                f"{{input_per_mtok, output_per_mtok}}")
        for model, spec in models.items():
            try:
                prices[str(model)] = {"input": float(spec["input_per_mtok"]) / 1e6,
                                      "output": float(spec["output_per_mtok"]) / 1e6}
            except (TypeError, KeyError, ValueError):
                raise UnpricedModel(f"{path}: {model} needs input_per_mtok and "
                                    f"output_per_mtok in USD per million tokens") from None
    _DECLARED = prices
    return prices


def price_of(model: str) -> dict[str, float] | None:
    """This model's per-token price: shipped, declared, or None for a local model."""
    if is_local_model(model):
        return None
    return PRICING.get(model) or declared_prices().get(model)


def require_price(model: str) -> dict[str, float] | None:
    """The price, or a refusal. A hosted model is never budgeted as free.

    Local models are free by construction — nothing is billed for them, and that
    is why they are absent from `PRICING`. For anything else, an absent price
    used to mean $0, which would have let a spend cap pass a call it could not
    price (plan A5, "the trap to close").
    """
    if is_local_model(model):
        return None
    price = price_of(model)
    if price is None:
        raise UnpricedModel(
            f"no price for {model!r}, so its spend cannot be capped. Declare it in "
            f"{PRICING_FILE} as models: {{{model}: {{input_per_mtok: <usd>, "
            f"output_per_mtok: <usd>}}}}, or use a local model (ollama/<name>), "
            f"which is free")
    return price


def is_gemini_model(model: str) -> bool:
    return model.startswith(GEMINI_PREFIX)


def is_local_model(model: str) -> bool:
    """True for open-weight models served locally rather than by an API."""
    return model.startswith(OLLAMA_PREFIX)


def is_anthropic_model(model: str) -> bool:
    return model.startswith(ANTHROPIC_PREFIX)


def local_model_name(model: str) -> str:
    """Strip the routing prefix: 'ollama/llama3.1:8b' -> 'llama3.1:8b'."""
    return model[len(OLLAMA_PREFIX):] if is_local_model(model) else model


def gemini_model_name(model: str) -> str:
    return model[len(GEMINI_PREFIX):] if is_gemini_model(model) else model


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)


class LLMClient:
    """Thin wrapper over ChatOpenAI with usage accounting.

    Also drives locally-served open-weight models: Ollama speaks the OpenAI
    protocol, so a base-URL swap is the whole integration. Everything
    downstream — prompts, parsing, the treatment of unparseable output as a
    failure rather than an error — is identical by construction, which is what
    makes the cross-model comparison in RQ5 a comparison of models rather than
    of harnesses.
    """

    def __init__(self, model: str, temperature: float, max_retries: int = 3) -> None:
        load_dotenv()
        self.model = model

        if is_anthropic_model(model):
            self.chat = self._anthropic_chat(model, temperature, max_retries)
            self.usage = LLMUsage()
            return

        if is_gemini_model(model):
            self.chat = self._gemini_chat(model, temperature, max_retries)
            self.usage = LLMUsage()
            return

        from langchain_openai import ChatOpenAI

        local = is_local_model(model)
        if not local and not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY not set (put it in .env)")

        options: dict[str, Any] = {
            "model": local_model_name(model),
            "temperature": temperature,
            "max_retries": max_retries,
            "timeout": LOCAL_TIMEOUT_S if local else 60,
            "model_kwargs": {"response_format": {"type": "json_object"}},
        }
        if local:
            # No key is required by Ollama, but the OpenAI client insists on
            # one being present.
            options["openai_api_base"] = ollama_base_url()
            options["openai_api_key"] = "ollama"
        self.chat = ChatOpenAI(**options)
        self.usage = LLMUsage()

    @staticmethod
    def _anthropic_chat(model: str, temperature: float, max_retries: int):
        """Claude via langchain-anthropic, on the same LangChain path as the rest.

        The Anthropic SDK would be the idiomatic client, but this harness must
        stay identical across arms or RQ5 measures harnesses rather than models.
        Same prompts, same parser, same treatment of unparseable output.

        One asymmetry, recorded rather than hidden: the OpenAI path pins
        `response_format: json_object`, and the Anthropic Messages API has no
        equivalent knob exposed here. Claude is therefore held to the prompt's
        "Respond with JSON only" instruction plus `call_json`'s block-extraction
        fallback. Any residual failure is counted as a parse failure — which is
        an agent failure by invariant 6, and is reported per run.

        Haiku 4.5 still accepts `temperature`; Sonnet 5 and Opus 4.7+ reject
        non-default sampling parameters, which is why this arm uses Haiku.
        Model IDs carry no date suffix.
        """
        from langchain_anthropic import ChatAnthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set (put it in .env)")
        return ChatAnthropic(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            timeout=60,
            # Task outputs are a single short JSON object; 1024 is ample
            # headroom without inviting a long generation.
            max_tokens=1024,
        )

    @staticmethod
    def _gemini_chat(model: str, temperature: float, max_retries: int):
        """Gemini on the same LangChain path as the rest (plan A5).

        Addressed as `gemini/<model>` because Google's ids carry no prefix of
        their own and the router has to tell providers apart from the id alone.
        Like the Anthropic path it has no `response_format` knob here, so it is
        held to the prompt plus `call_json`'s block extraction; unusable output
        is a parse failure, which is an agent failure (invariant 6).
        """
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise RuntimeError('Gemini needs the gemini extra: '
                               'pip install "airs-bench[gemini]"') from None

        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set (put it in .env)")
        return ChatGoogleGenerativeAI(
            model=gemini_model_name(model), temperature=temperature,
            max_retries=max_retries, timeout=60, google_api_key=key,
        )

    def call_json(self, messages: list[tuple[str, str]]) -> dict[str, Any] | None:
        """Return parsed JSON, or None when the agent's output is unusable."""
        start = time.perf_counter()
        response = self.chat.invoke(messages)
        latency_ms = (time.perf_counter() - start) * 1000.0

        meta = getattr(response, "usage_metadata", None) or {}
        self.usage.add(
            input_tokens=meta.get("input_tokens", 0),
            output_tokens=meta.get("output_tokens", 0),
            latency_ms=latency_ms,
        )

        text = response.content if isinstance(response.content, str) else str(response.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = JSON_BLOCK.search(text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        self.usage.parse_failures += 1
        return None


def estimate_cost_usd(
    model: str, n_calls: int, avg_input_tokens: int, avg_output_tokens: int
) -> float:
    """Projected spend. Free for local models; refuses an unpriced hosted one."""
    price = require_price(model)
    if price is None:
        return 0.0
    return n_calls * (
        avg_input_tokens * price["input"] + avg_output_tokens * price["output"]
    )
