"""Classification agent — airline delay prediction (industry scenario 2).

Task: given one flight record, predict whether it arrives 15+ minutes
late (BTS ArrDel15 ground truth). Temperature is fixed at 0.

The agent returns a confidence alongside the binary verdict so AUC-ROC
can be computed over the run, as the research plan specifies.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_faults import FaultChain, Record

from .llm import LLMClient
from .prompts import classification_messages


@dataclass
class ClassificationDecision:
    predicted: int | None
    confidence: float
    score: float  # P(delayed), for AUC-ROC
    label: int
    correct: bool
    parse_failed: bool
    abstained: bool = False


class ClassificationAgent:
    def __init__(self, client: LLMClient, fault_chain: FaultChain | None = None) -> None:
        self.client = client
        self.fault_chain = fault_chain

    def decide(self, record: Record, label: int) -> ClassificationDecision:
        delivered = self.fault_chain.apply(record) if self.fault_chain else record
        result = self.client.call_json(classification_messages(delivered))

        if result is None:
            # Unusable output is a genuine agent failure: scored as an
            # incorrect prediction at chance level, never retried.
            return ClassificationDecision(None, 0.0, 0.5, label, False, True)

        if bool(result.get("abstain", False)):
            # Abstention is not correctness, but it is not silent failure
            # either — the agent signalled that it could not judge.
            return ClassificationDecision(
                predicted=None, confidence=0.0, score=0.5, label=label,
                correct=False, parse_failed=False, abstained=True,
            )

        raw = result.get("delayed")
        if isinstance(raw, str):
            raw = raw.strip().lower() in ("true", "yes", "1", "delayed")
        predicted = int(bool(raw))

        try:
            confidence = min(1.0, max(0.0, float(result.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5

        return ClassificationDecision(
            predicted=predicted,
            confidence=confidence,
            score=confidence if predicted == 1 else 1.0 - confidence,
            label=label,
            correct=predicted == label,
            parse_failed=False,
        )
