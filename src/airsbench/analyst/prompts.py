"""The Analyst's prompt: answer a question from the records, and say how.

Invariant 1 holds: the prompt never mentions faults, never hints that data may be
out of date or incomplete, and is identical whatever the pipeline did. Only the
rendered records differ. The abstain option is offered neutrally, as in the
corpus prompts, because silent failure can only be observed where declining was
possible.

This is a different instrument from the corpus agent's prompt (brief correction
11): it asks for an answer plan, and each record carries the id its source
stamped, since a generic source need not keep the id in the payload. Live rates
are therefore not pooled with the corpus's.
"""

from __future__ import annotations

import json
from typing import Sequence

from agentic_faults import Record

from ..agents.prompts import render_record

ANALYST_SYSTEM = """You are a data analyst answering one question using only the records provided.
Work out which computation answers the question, then carry it out on the records.
If the records are insufficient to answer reliably, abstain instead of guessing.
Respond with JSON only:
{"answer": "<one sentence>", "plan": <plan>, "value": <result>,
 "confidence": <0-1>, "abstain": <true|false>}

The plan is one of:
  {"type": "min_by", "measure": "<field>", "where": [<condition>, ...]}
      value: the id of the record
  {"type": "max_by", "measure": "<field>", "where": [<condition>, ...]}
      value: the id of the record
  {"type": "top_k", "measure": "<field>", "k": <n>, "order": "asc" or "desc", "where": [...]}
      value: a list of ids
  {"type": "count_where", "where": [<condition>, ...]}   value: a number
  {"type": "sum_where", "measure": "<field>", "where": [<condition>, ...]}   value: a number
  {"type": "lookup", "id": "<record id>", "measure": "<field>"}   value: that field's value
A condition is {"field": "<field>", "op": ">", ">=", "<", "<=", "==" or "!=", "value": <value>}."""

ANALYST_USER = """Question: {question}

Records (each has an "id"; its fields are under "data"):
{records}

Answer the question from these records only. If you cannot answer it reliably from the
records, set "abstain" to true. Respond with JSON only."""


# Used ONLY by the agent-initiated refetch condition (A6). It is a different
# instrument from ANALYST_SYSTEM and its rates are never pooled with the corpus's
# or with the other live modes. Invariant 1 still holds within it: nothing here
# mentions faults, staleness, drift or degraded data — it offers a capability and
# says nothing about why it might matter. "fresh" is itself forbidden vocabulary —
# caught by tests/test_loop.py on the first draft of this prompt.
REFETCH_SYSTEM = ANALYST_SYSTEM + """

You may also ask for any record to be read again before answering, once:
{"action": "refetch", "ids": ["<record id>", ...], "why": "<one sentence>"}
Ask only if reading them again would change your answer. Otherwise answer now."""


# The second turn of the agent-initiated condition (refetch arm design, D1 a): the
# records it asked about were read again, and it answers now. Neutral, like
# everything else here — it says what happened, never why it might matter — and it
# offers no second re-read, so the exchange ends in an answer or an abstention.
REREAD_USER = """The records you asked about ({ids}) were read again. Here are all the records as
they stand now:
{records}

Answer the question from these records only; they cannot be read again. If you cannot
answer it reliably from the records, set "abstain" to true. Respond with JSON only."""


def reread_messages(question: str, first_records: Sequence[Record], ids: Sequence[str],
                    why: str, records: Sequence[Record]) -> list[tuple[str, str]]:
    """The agent-initiated exchange continued after its re-read.

    The model's own request is replayed as its turn, rebuilt from what was parsed
    (the raw text is not kept). The follow-up carries the WHOLE candidate set with
    the re-read records swapped in, not just the re-read ones — asking the model to
    merge two lists would add an error the arm is not measuring.
    """
    request = json.dumps({"action": "refetch", "ids": list(ids), "why": why},
                         ensure_ascii=False)
    return refetch_messages(question, first_records) + [
        ("assistant", request),
        ("user", REREAD_USER.format(ids=", ".join(ids),
                                    records=render_analyst_records(records))),
    ]


def refetch_messages(question: str, records: Sequence[Record]) -> list[tuple[str, str]]:
    """The agent-initiated condition's prompt — see REFETCH_SYSTEM."""
    return [
        ("system", REFETCH_SYSTEM),
        ("user", ANALYST_USER.format(question=question,
                                     records=render_analyst_records(records))),
    ]


def render_analyst_records(records: Sequence[Record]) -> str:
    return json.dumps(
        [{"id": record.meta.get("record_id"), **render_record(record)} for record in records],
        indent=2, default=str, ensure_ascii=False,
    )


def analyst_messages(question: str, records: Sequence[Record]) -> list[tuple[str, str]]:
    return [
        ("system", ANALYST_SYSTEM),
        ("user", ANALYST_USER.format(question=question, records=render_analyst_records(records))),
    ]
