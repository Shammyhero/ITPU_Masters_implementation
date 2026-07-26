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

# Pricing (USD per token), for run-level cost accounting and the budget guard.
# Local models via Ollama are free and priced at zero.
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


class LLMClient:
    """Thin wrapper over ChatOpenAI with usage accounting."""

    def __init__(self, model: str, temperature: float, max_retries: int = 3) -> None:
        from langchain_openai import ChatOpenAI

        load_dotenv()
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY not set (put it in .env)")
        self.model = model
        self.chat = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=max_retries,
            timeout=60,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
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
