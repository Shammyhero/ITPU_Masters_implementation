"""The Analyst — gated question answering, verified against the system of record.

    plan.py       checkable question plans, executed deterministically (no model)
    verifier.py   correctness against upstream, then the four-way attribution
    answerers.py  who answers: a literal rule, or a local Ollama model
    prompts.py    the plan-returning prompt (invariant 1: never mentions faults)
    session.py    one question end to end, as a Tick
    __main__.py   `airs analyst ask`

The verifier checks an answer against the QUESTION's plan, never the agent's own
(author decision, 15 Sep): an agent that misreads "cheapest" as "most expensive"
and then computes its own plan correctly must not grade itself correct.
"""

from .plan import Plan, PlanError, Result, Row, answers_equal, execute
from .verifier import LABELS, AgentAnswer, Verification, changed_fields, verify

__all__ = [
    "LABELS", "AgentAnswer", "Plan", "PlanError", "Result", "Row", "Verification",
    "answers_equal", "changed_fields", "execute", "verify",
]
