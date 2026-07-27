"""Prompt templates — held constant across every experimental condition.

Methodological commitment: the prompt is a control variable. It never
mentions faults, never hints that data may be stale or incomplete, and is
byte-identical across conditions. Only the rendered records differ.

Records are rendered with whatever semantic context survived injection —
that is the mechanism by which semantic stripping reaches the agent: the
values remain, the meaning does not.
"""

from __future__ import annotations

import json
from typing import Any

from agentic_faults import Record

# Abstention is offered deliberately and symmetrically in both tasks. The
# distinctive claim available to this study (see docs/literature_review.md
# §8.3) is not that degraded data lowers accuracy — that is established —
# but that agents fail SILENTLY rather than declining. An agent that cannot
# abstain cannot demonstrate that, so the option must exist and must be
# phrased neutrally, without hinting that the data may be faulty.

RETRIEVAL_SYSTEM = """You are a shopping assistant for an online marketplace.
You answer customer questions using only the catalog records provided.
Choose the single best product and report its price.
If the records are insufficient to answer reliably, abstain instead of guessing.
Respond with JSON only:
{"product_id": "<id>", "price": <number>, "confidence": <0-1>, "abstain": <true|false>}"""

RETRIEVAL_USER = """Customer query: "{query}"

Catalog records:
{records}

Task: among these records, identify the CHEAPEST product that is currently
in stock, and report its price. If you cannot determine this reliably from the
records, set "abstain" to true. Respond with JSON only."""

CLASSIFICATION_SYSTEM = """You are a flight operations analyst.
You predict whether a flight will arrive late, using only the record provided.
A flight counts as delayed when it arrives 15 or more minutes behind schedule.
If the record is insufficient to judge reliably, abstain instead of guessing.
Respond with JSON only:
{"delayed": <true|false>, "confidence": <0-1>, "abstain": <true|false>}"""

CLASSIFICATION_USER = """Flight record:
{record}

Task: will this flight arrive 15 or more minutes late? If you cannot judge this
reliably from the record, set "abstain" to true. Respond with JSON only."""


# Freshness metadata field, rendered only when the runner attached it
# (detectability arm — docs/detectability_arm.md). Named for what it is and
# nothing more: no unit prose, no "stale", no hint that old is bad. The
# templates above are unchanged and identical in both conditions, so the only
# difference between A and B is that the record carries its own age.
RECORD_AGE_FIELD = "_record_age_seconds"


def render_record(record: Record) -> dict[str, Any]:
    """Render a record as the agent sees it: values plus surviving context.

    ``meta`` is injector bookkeeping and is never shown — with the single
    deliberate exception of the record's age, which is the treatment in the
    detectability arm and is absent from every other condition.
    """
    rendered: dict[str, Any] = {"data": record.payload}
    if record.context:
        rendered["context"] = record.context
    age = record.meta.get("record_age_seconds")
    if age is not None:
        rendered[RECORD_AGE_FIELD] = age
    return rendered


def render_records(records: list[Record]) -> str:
    return json.dumps([render_record(r) for r in records], indent=2, default=str)


def retrieval_messages(query: str, records: list[Record]) -> list[tuple[str, str]]:
    return [
        ("system", RETRIEVAL_SYSTEM),
        ("user", RETRIEVAL_USER.format(query=query, records=render_records(records))),
    ]


def classification_messages(record: Record) -> list[tuple[str, str]]:
    return [
        ("system", CLASSIFICATION_SYSTEM),
        (
            "user",
            CLASSIFICATION_USER.format(
                record=json.dumps(render_record(record), indent=2, default=str)
            ),
        ),
    ]
