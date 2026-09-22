"""Who answers a question: a literal rule, or a model.

    literal          executes the question's plan over the delivered records at face
                     value, and abstains when they do not support it. Not a model —
                     a reference showing what the delivered data implies. $0.
    ollama/<model>   a model in the user's local Ollama, through the corpus's own
                     `LLMClient` (same JSON parsing, same retry rule). $0, and the
                     records never leave the machine.
    openai/<model>   a hosted model. THE RECORDS ARE SENT TO THAT PROVIDER, which
    anthropic/<m>    the Tick records and the CLI says out loud. Every call passes a
    gemini/<model>   spend cap first (`budget.py`), and a model with no declared
                     price is refused rather than budgeted as free.

Keys come from the environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`), never from a flag or a request, and never reach a Tick, a log
or a URL — `tests/test_model_options.py` asserts it.

Invariant 6 is kept: output that cannot be parsed as JSON is a parse failure — an
agent failure, recorded and never retried. A transport failure (Ollama not
running, a timeout after the client's own retries) is not an agent failure; it
stops the question with an `AnswererError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from agentic_faults import Record

from ..agents.llm import UnpricedModel, is_local_model, require_price
from ..runner.config import TASK_TEMPERATURE
from .budget import Budget, SpendRefused
from .plan import Plan, execute
from .prompts import analyst_messages, refetch_messages, reread_messages
from .verifier import AgentAnswer, rows

OLLAMA_PREFIX = "ollama/"
# How a provider prefix maps to the model id `LLMClient` routes on: OpenAI ids
# carry no prefix of their own, Anthropic ids start with `claude-`, and Gemini
# keeps `gemini/` because its ids are otherwise unmarked.
PROVIDERS = {"openai/": "", "anthropic/": "", "gemini/": "gemini/"}
MAX_ANSWER_TEXT = 500
# A question is asked over a handful of candidates; a request naming more ids
# than that is not a considered re-read.
MAX_REFETCH_IDS = 20
# One question's prompt is the records plus the plan grammar. Measured on the
# demo source at 6 records: ~1,500 in, ~90 out. The estimate only has to be
# honest enough to cap spend before the call; `record` then charges the truth.
ESTIMATED_INPUT_TOKENS = 1_600
ESTIMATED_OUTPUT_TOKENS = 150
# The continued exchange after a re-read carries the records twice (as first
# delivered, then as read again), plus the replayed request. Measured once on the
# demo (23 Sep, llama3.1:8b's tokenizer): 3,509 in, 93 out.
ESTIMATED_REREAD_INPUT_TOKENS = 3_600


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


class ModelAnswerer:
    """A model, local or hosted, through the corpus's LLMClient.

    Hosted calls are metered: `budget.check` runs before the request with the
    projected cost, and `budget.record` charges what the response actually used.
    A local model never consults the budget — nothing is billed for it.
    """

    def __init__(self, spec: str, client: Any | None = None,
                 budget: Budget | None = None, offer_refetch: bool = False) -> None:
        self.name = spec
        # The tool-offering prompt is a separate instrument (A6, invariant 1).
        self.offer_refetch = offer_refetch
        self.model = model_id(spec)
        self.provider = provider_of(spec)
        self.local = is_local_model(self.model)
        self.budget = budget if not self.local else None
        if not self.local:
            require_price(self.model)  # refuse before a key is even read
        if client is None:
            try:
                from ..agents.llm import LLMClient
            except ImportError:
                raise AnswererError('answering with a model needs the agents extra: '
                                    'pip install "airs-bench[agents]"') from None
            try:
                client = LLMClient(self.model, temperature=TASK_TEMPERATURE["retrieval"])
            except (ImportError, RuntimeError) as exc:
                raise AnswererError(str(exc)) from None
        self.client = client

    def estimate_usd(self) -> float:
        """What one question is projected to cost. 0.0 for a local model."""
        from .budget import cost_of

        return cost_of(self.model, ESTIMATED_INPUT_TOKENS, ESTIMATED_OUTPUT_TOKENS)

    def answer(self, question: str, plan: Plan,
               records: Sequence[Record]) -> tuple[AgentAnswer, Usage]:
        messages = (refetch_messages(question, records) if self.offer_refetch
                    else analyst_messages(question, records))
        return self._call(messages, ESTIMATED_INPUT_TOKENS)

    def answer_after_reread(self, question: str, plan: Plan,
                            first_records: Sequence[Record], request: AgentAnswer,
                            records: Sequence[Record]) -> tuple[AgentAnswer, Usage]:
        """The same exchange, continued: the model's request, then the records read again."""
        messages = reread_messages(question, first_records, request.refetch_ids,
                                   request.text, records)
        return self._call(messages, ESTIMATED_REREAD_INPUT_TOKENS)

    def _call(self, messages: list[tuple[str, str]],
              estimated_input: int) -> tuple[AgentAnswer, Usage]:
        if self.budget is not None:
            # Before the request, not around it: a refusal costs nothing.
            self.budget.check(self.model, estimated_input, ESTIMATED_OUTPUT_TOKENS)
        before = (self.client.usage.input_tokens, self.client.usage.output_tokens)
        try:
            result = self.client.call_json(messages)
        except Exception as exc:  # transport: the client already retried
            raise AnswererError(
                f"{self.name} could not be reached ({type(exc).__name__}: {exc})"
                + ("; is Ollama running? start it with `ollama serve`" if self.local else
                   f"; check {self.provider.upper()}_API_KEY and the network")
            ) from None
        used_in = self.client.usage.input_tokens - before[0]
        used_out = self.client.usage.output_tokens - before[1]
        usd = self.budget.record(self.model, used_in, used_out) if self.budget is not None \
            else 0.0
        return parse_answer(result), Usage(self.name, used_in, used_out, usd)


# The old name, kept because A3's tests and docs use it.
OllamaAnswerer = ModelAnswerer


def provider_of(spec: str) -> str:
    """Which provider a spec addresses: ollama, openai, anthropic or gemini."""
    return spec.split("/", 1)[0] if "/" in spec else "openai"


def model_id(spec: str) -> str:
    """The model id `LLMClient` routes on, from an `<provider>/<model>` spec."""
    if spec.startswith(OLLAMA_PREFIX):
        return spec
    for prefix, keep in PROVIDERS.items():
        if spec.startswith(prefix):
            return keep + spec[len(prefix):]
    return spec


def parse_answer(result: Any) -> AgentAnswer:
    """A model's JSON, read the way the corpus agents read theirs.

    One addition for A6: `{"action": "refetch", "ids": [...]}` is a request for a
    fresh read rather than an answer. It is carried on the answer object and only
    ever honoured in the agent-initiated condition; every other mode ignores it,
    so a model that emits it elsewhere has simply not answered.
    """
    if not isinstance(result, dict):
        return AgentAnswer(parse_failed=True)
    if result.get("action") == "refetch":
        ids = result.get("ids")
        ids = tuple(str(i) for i in ids[:MAX_REFETCH_IDS]) if isinstance(ids, list) else ()
        if not ids:
            return AgentAnswer(parse_failed=True)
        return AgentAnswer(refetch_ids=ids, text=str(result.get("why", ""))[:MAX_ANSWER_TEXT])
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else None
    text = str(result.get("answer", ""))[:MAX_ANSWER_TEXT]
    if bool(result.get("abstain", False)):
        return AgentAnswer(plan=plan, text=text, abstained=True)
    try:
        confidence = min(1.0, max(0.0, float(result.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5
    return AgentAnswer(value=result.get("value"), plan=plan, text=text, confidence=confidence)


def make_answerer(spec: str, budget: Budget | None = None,
                  offer_refetch: bool = False) -> Answerer:
    """`literal`, `ollama/<name>`, or a hosted `<provider>/<model>`."""
    if spec == "literal":
        return LiteralAnswerer()
    known = (OLLAMA_PREFIX,) + tuple(PROVIDERS)
    if not spec.startswith(known):
        raise AnswererError(
            f"{spec!r} is not a model this tool can address. Use literal, a local model "
            f"as ollama/<name>, or a hosted one as "
            f"{', '.join(p + '<model>' for p in PROVIDERS)}")
    if len(spec) == len(spec.split("/", 1)[0]) + 1:
        raise AnswererError(f"{spec!r} names a provider but no model — "
                            f"ollama/<name>, openai/<model>, anthropic/<model> or "
                            f"gemini/<model>")
    if not spec.startswith(OLLAMA_PREFIX) and budget is None:
        raise AnswererError(f"{spec} is a hosted model: it needs a spend cap. Pass a "
                            f"Budget, or use a local model (ollama/<name>, $0)")
    try:
        return ModelAnswerer(spec, budget=budget, offer_refetch=offer_refetch)
    except UnpricedModel as exc:
        raise AnswererError(str(exc)) from None


__all__ = ["Answerer", "AnswererError", "Budget", "LiteralAnswerer", "ModelAnswerer",
           "OllamaAnswerer", "SpendRefused", "Usage", "make_answerer", "model_id",
           "parse_answer", "provider_of"]
