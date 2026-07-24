"""Retrieval agent — e-commerce product QA (industry scenario 1).

Task: given a customer query and the catalog records retrieved for it,
identify the cheapest product currently in stock and report its price.

Why this task: the answer depends on values that CHANGE (price, stock),
so a stale record produces an objectively wrong answer; and it depends on
knowing which field means what, so a stripped semantic layer produces a
wrong or refused answer. Both faults are therefore behaviorally visible,
which is what RQ1 needs.

Ground truth is always computed from the true catalog state at query
time, regardless of what the agent was served.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentic_faults import FaultChain, Record

from .llm import LLMClient
from .prompts import retrieval_messages


@dataclass
class RetrievalDecision:
    product_id: str | None
    price: float | None
    confidence: float
    correct: bool
    ground_truth_id: str
    parse_failed: bool


class RetrievalAgent:
    def __init__(self, client: LLMClient, fault_chain: FaultChain | None = None) -> None:
        self.client = client
        self.fault_chain = fault_chain

    @staticmethod
    def ground_truth(products: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Cheapest in-stock product in the TRUE catalog state."""
        in_stock = [p for p in products if p["stock"] > 0]
        return min(in_stock, key=lambda p: p["price"]) if in_stock else None

    def decide(
        self, query: str, records: list[Record], truth: dict[str, Any]
    ) -> RetrievalDecision:
        delivered = records
        if self.fault_chain is not None:
            delivered = [self.fault_chain.apply(r) for r in records]

        result = self.client.call_json(retrieval_messages(query, delivered))
        if result is None:
            return RetrievalDecision(None, None, 0.0, False, truth["product_id"], True)

        product_id = result.get("product_id")
        price = result.get("price")
        confidence = result.get("confidence", 0.5)
        try:
            confidence = min(1.0, max(0.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.5

        return RetrievalDecision(
            product_id=str(product_id) if product_id is not None else None,
            price=float(price) if isinstance(price, (int, float)) else None,
            confidence=confidence,
            correct=str(product_id) == truth["product_id"],
            ground_truth_id=truth["product_id"],
            parse_failed=False,
        )
