"""The questions a rider asks of a bike-share app — each one checkable.

Three, rotated so question *i* is type *i* mod 3. Each is worded as a person would
ask it and carries the plan it is graded by (the verifier grades against the
question's plan, never the agent's — brief correction 16). Invariant 1 holds:
nothing here mentions data quality or age; "right now" is how a rider asks.
"""

from __future__ import annotations

from ..analyst.plan import Plan
from ..analyst.session import Question
from .replay import N_STATIONS

QUESTIONS: dict[str, tuple[str, dict]] = {
    "bikes": (
        "I'm at {query}. Which of these nearby stations has the most bikes available "
        "right now?",
        {"type": "max_by", "measure": "num_bikes_available",
         "where": [{"field": "is_renting", "op": "==", "value": 1}]},
    ),
    "docks": (
        "I need to return a bike near {query}. Which of these nearby stations has the "
        "most free docks right now?",
        {"type": "max_by", "measure": "num_docks_available",
         "where": [{"field": "is_returning", "op": "==", "value": 1}]},
    ),
    "empty": (
        "How many of these stations near {query} have no bikes available right now?",
        {"type": "count_where",
         "where": [{"field": "num_bikes_available", "op": "==", "value": 0}]},
    ),
}
TYPES = tuple(QUESTIONS)


def question_type(index: int) -> str:
    return TYPES[index % len(TYPES)]


def question(index: int) -> Question:
    text, plan = QUESTIONS[question_type(index)]
    return Question(text, Plan.from_dict(plan), n=N_STATIONS)
