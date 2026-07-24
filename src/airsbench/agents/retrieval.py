"""Retrieval agent (e-commerce product QA) — Week 3 deliverable.

LangGraph workflow with three nodes (research plan §6.3):
  1. question reception   — receives a product question, e.g.
                            "What is the current price of <product>?"
  2. catalog retrieval    — queries the configured pipeline (Kafka or
                            batch/Postgres) through the fault injector
  3. answer composition   — GPT-4o-mini composes the answer from the
                            retrieved (possibly faulted) records

Scored against catalog ground truth *at query time* — prices and stock
change via the update stream, so staleness produces objectively wrong
answers. This is what makes the freshness dimension behaviorally
observable in this task (industry-scenario design decision, Week 0).
"""

from __future__ import annotations

from typing import Any

from agentic_faults import FaultChain


class RetrievalAgent:
    """Skeleton — implemented in Week 3 (agent harness)."""

    def __init__(self, model: str, temperature: float, fault_chain: FaultChain) -> None:
        self.model = model
        self.temperature = temperature
        self.fault_chain = fault_chain

    def answer(self, question: str) -> dict[str, Any]:
        raise NotImplementedError("Week 3: LangGraph retrieval workflow")
