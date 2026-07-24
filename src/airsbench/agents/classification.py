"""Classification agent (airline delay prediction) — Week 3 deliverable.

LangGraph workflow (research plan §6.3): receives flight features from
the pipeline (through the fault injector), reasons over them, outputs a
binary decision (delayed / on-time). Scored against the BTS ArrDel15
ground-truth label; F1 and AUC-ROC computed by the harness.

Temperature is fixed at 0 for this task (methodological commitment:
model constant, deterministic decisions).
"""

from __future__ import annotations

from typing import Any

from agentic_faults import FaultChain


class ClassificationAgent:
    """Skeleton — implemented in Week 3 (agent harness)."""

    def __init__(self, model: str, temperature: float, fault_chain: FaultChain) -> None:
        self.model = model
        self.temperature = temperature
        self.fault_chain = fault_chain

    def classify(self, flight_features: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Week 3: LangGraph classification workflow")
