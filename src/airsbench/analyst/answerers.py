"""Who answers a question: a literal rule, or a model.

    literal          executes the question's plan over the delivered records at face
                     value, and abstains when they do not support it. Not a model —
                     a reference showing what the delivered data implies. $0.
    ollama/<model>   a model in the user's local Ollama, through the corpus's own
                     `LLMClient` (same JSON parsing, same retry rule). $0, and the
                     records never leave the machine.

Hosted models (OpenAI, Anthropic, Gemini) are refused here until per-session spend
caps sit in the request path (plan stage A5).

Invariant 6 is kept: output that cannot be parsed as JSON is a parse failure — an
agent failure, recorded and never retried. A transport failure (Ollama not
running, a timeout after the client's own retries) is not an agent failure; it
stops the question with an `AnswererError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from agentic_faults import Record

from ..runner.config import TASK_TEMPERATURE
from .plan import Plan, execute
from .prompts import analyst_messages
from .verifier import AgentAnswer, rows

OLLAMA_PREFIX = "ollama/"
MAX_ANSWER_TEXT = 500


class AnswererError(RuntimeError):
    """The answerer could not be built or reached — not an agent failure."""


@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"model": self.model, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "usd": self.usd}


class Answerer(Protocol):
    name: str

    def answer(self, question: str, plan: Plan,
               records: Sequence[Record]) -> tuple[AgentAnswer, Usage]: ...


class LiteralAnswerer:
    """The question's plan over the delivered records, taken at face value."""

    name = "literal"

    def answer(self, question: str, plan: Plan,
               records: Sequence[Record]) -> tuple[AgentAnswer, Usage]:
        result = execute(plan, rows(records))
        usage = Usage(self.name)
        if not result.computable:
            return AgentAnswer(plan=plan.to_dict(), abstained=True,
                               text=f"not answerable from these records: {result.reason}"), usage
        return AgentAnswer(value=result.value, plan=plan.to_dict(), confidence=1.0,
                           text=f"{plan.describe()}: {result.value!r}"), usage


class OllamaAnswerer:
    """A local model, through the corpus's LLMClient."""

    def __init__(self, model: str, client: Any | None = None) -> None:
        if not model.startswith(OLLAMA_PREFIX) or len(model) == len(OLLAMA_PREFIX):
            raise AnswererError(f"not a local model: {model!r}; use ollama/<name>")
        self.name = model
        if client is None:
            try:
                from ..agents.llm import LLMClient
            except ImportError:
                raise AnswererError('answering with a model needs the agents extra: '
                                    'pip install "airs-bench[agents]"') from None
            try:
                client = LLMClient(model, temperature=TASK_TEMPERATURE["retrieval"])
            except ImportError:
                raise AnswererError('answering with a model needs the agents extra: '
                                    'pip install "airs-bench[agents]"') from None
        self.client = client

    def answer(self, question: str, plan: Plan,
               records: Sequence[Record]) -> tuple[AgentAnswer, Usage]:
        before = (self.client.usage.input_tokens, self.client.usage.output_tokens)
        try:
            result = self.client.call_json(analyst_messages(question, records))
        except Exception as exc:  # transport: the client already retried
            raise AnswererError(
                f"{self.name} could not be reached ({type(exc).__name__}: {exc}); "
                f"is Ollama running? start it with `ollama serve`"
            ) from None
        usage = Usage(self.name, self.client.usage.input_tokens - before[0],
                      self.client.usage.output_tokens - before[1], 0.0)
        return parse_answer(result), usage


def parse_answer(result: Any) -> AgentAnswer:
    """A model's JSON, read the way the corpus agents read theirs."""
    if not isinstance(result, dict):
        return AgentAnswer(parse_failed=True)
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else None
    text = str(result.get("answer", ""))[:MAX_ANSWER_TEXT]
    if bool(result.get("abstain", False)):
        return AgentAnswer(plan=plan, text=text, abstained=True)
    try:
        confidence = min(1.0, max(0.0, float(result.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    return AgentAnswer(value=result.get("value"), plan=plan, text=text, confidence=confidence)


def make_answerer(spec: str) -> Answerer:
    if spec == "literal":
        return LiteralAnswerer()
    if spec.startswith(OLLAMA_PREFIX):
        return OllamaAnswerer(spec)
    raise AnswererError(
        f"{spec!r} is not available yet: hosted models (OpenAI, Anthropic, Gemini) need "
        f"per-session spend caps first. Use literal, or a local model as ollama/<name>"
    )
