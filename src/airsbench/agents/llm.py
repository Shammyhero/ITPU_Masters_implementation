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
OLLAMA_PREFIX = "ollama/"
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
        price = PRICING.get(model)
        if price is None:
            return 0.0
        return self.input_tokens * price["input"] + self.output_tokens * price["output"]


def is_local_model(model: str) -> bool:
    """True for open-weight models served locally rather than by an API."""
    return model.startswith(OLLAMA_PREFIX)


def local_model_name(model: str) -> str:
    """Strip the routing prefix: 'ollama/llama3.1:8b' -> 'llama3.1:8b'."""
    return model[len(OLLAMA_PREFIX):] if is_local_model(model) else model


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
        from langchain_openai import ChatOpenAI

        load_dotenv()
        self.model = model
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
    price = PRICING.get(model)
    if price is None:
        return 0.0
    return n_calls * (
        avg_input_tokens * price["input"] + avg_output_tokens * price["output"]
    )
