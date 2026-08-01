"""AIRS admission control — enforce the data contract outside the model.

The campaign's practitioner conclusion in executable form. `Policy` declares
what an agent may reason over; `Controller` refuses batches that violate it
before the agent is asked; `replay` measures what such a gate would have
prevented across the completed benchmark.
"""

from .controller import BatchRefused, Controller, Verdict
from .policy import DIMENSIONS, Policy, Violation

__all__ = [
    "BatchRefused", "Controller", "Verdict",
    "DIMENSIONS", "Policy", "Violation",
]
