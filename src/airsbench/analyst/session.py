"""One question, end to end: sample, score, answer, re-read upstream, verify.

`ask` returns a Tick — the one message shape the console will render (plan stage
A8). The gate, refetch and running meter join it in A6–A7; this is the verified
core they wrap.

    t0   sample what the pipeline delivers; read upstream as of when those values
         were true; score with `airsbench.probe` against that reference
    —    the answerer answers from the delivered records only
    t1   read upstream as of the answer — the answer key — and verify

On the demo source both upstream reads are exact as-of reads, so the gap between
t0 and t1 is zero and reported as zero. On a source with no history the reads are
taken before and after answering; the gap is measured and the Tick notes that
pipeline lag cannot be told apart from values changed in transit there.

Nothing here writes a run artifact. Live traffic is quarantined from the evidence
(invariant 7): live seeds sit in their own block, and artifacts arrive in A7
under `~/.airs/sessions/`, never `results/runs/`.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ..probe import score
from ..sources import SourcePair, to_probe_entry
from ..sources.manifest import semantic_layer
from .answerers import Answerer
from .plan import Plan
from .verifier import AgentAnswer, verify

LIVE_SEED_BLOCK = (100_000, 110_000)
DEFAULT_CANDIDATES = 6

DEMO_QUESTION = ('A customer searched for "{query}". Among these catalog records, which '
                 'product is the cheapest one currently in stock?')
DEMO_PLAN = Plan.from_dict({"type": "min_by", "measure": "price",
                            "where": [{"field": "stock", "op": ">", "value": 0}]})


@dataclass(frozen=True)
class Question:
    text: str
    plan: Plan
    key: str | None = None
    n: int = DEFAULT_CANDIDATES
    options: dict[str, Any] = field(default_factory=dict)


def demo_question(key: str | None = None) -> Question:
    """The corpus's retrieval task, asked about one bundled customer query."""
    return Question(DEMO_QUESTION, DEMO_PLAN, key=key)


def _payloads(records) -> dict[str, dict[str, Any]]:
    return {record.meta.get("record_id"): dict(record.payload) for record in records}


def ask(pair: SourcePair, question: Question, answerer: Answerer, *, seed: int | None = None,
        task: str = "retrieval", session_id: str | None = None,
        clock: Callable[[], float] = time.time) -> dict[str, Any]:
    started = clock()
    layer = semantic_layer(pair)
    sample = pair.delivered.sample(question.n, key=question.key, seed=seed)
    # The semantic layer the agent reads and the probe scores: a reviewed manifest
    # rendered onto bare records, or nothing added (brief correction 2).
    sample.records = layer.apply(sample.records)
    text = question.text.replace("{query}", str(sample.meta.get("query", "")))
    ids = [record_id for record_id in sample.ids if record_id is not None]

    upstream = pair.upstream
    as_of = upstream is not None and upstream.describe().supports_as_of
    served = None
    if upstream is not None:
        served = (upstream.fetch(ids, as_of=sample.meta.get("served_as_of", sample.as_of))
                  if as_of else upstream.fetch(ids))
    delivered_entries = [to_probe_entry(record, record_id)
                         for record, record_id in zip(sample.records, sample.ids)]
    airs = score(delivered_entries,
                 [to_probe_entry(record) for record in served] if served is not None else None,
                 task, semantic_unmeasured=layer.unmeasured_reason)

    t0 = clock()
    answer, usage = answerer.answer(text, question.plan, sample.records)
    truth = None
    if upstream is not None:
        truth = upstream.fetch(ids, as_of=sample.as_of) if as_of else upstream.fetch(ids)
    t1 = clock()

    verification = (verify(question.plan, answer, delivered=sample.records, served=served,
                           truth=truth) if upstream is not None else None)
    return build_tick(
        pair=pair, question=question, text=text, sample=sample, answer=answer, usage=usage,
        answerer_obj=answerer,
        airs=airs, verification=verification, served=served, truth=truth, as_of=as_of,
        semantic=layer,
        seed=seed, session_id=session_id or uuid.uuid4().hex[:12], answerer=answerer.name,
        started=started, t0=t0, t1=t1,
    )


def build_tick(*, pair, question, text, sample, answer: AgentAnswer, usage, airs, verification,
               served, truth, as_of, seed, session_id, answerer, started, t0, t1,
               semantic=None, answerer_obj=None) -> dict[str, Any]:
    staleness = sample.meta.get("staleness_seconds")
    notes = []
    if pair.upstream is None:
        notes.append("no upstream declared: consistency is unmeasured and answers cannot be "
                     "verified")
    elif not as_of:
        notes.append("this source cannot be read as of a past time, so pipeline lag shows up "
                     "as values changed in transit rather than as the answer key moving")
    if semantic is not None and not semantic.measured:
        notes.append(semantic.reason)
    provider = getattr(answerer_obj, "provider", None)
    hosted = provider is not None and not getattr(answerer_obj, "local", True)
    if hosted:
        notes.append(f"these records were sent to {provider} to be answered by "
                     f"{answerer}; everything else stayed on this machine")
    decision = {
        "answer": answer.text,
        "plan": answer.plan,
        "value": answer.value,
        "confidence": answer.confidence,
        "abstained": answer.abstained,
        "parse_failed": answer.parse_failed,
        **(verification.to_dict() if verification is not None else {
            "verifiable": False, "reason": notes[0], "attribution": None,
            "correct": None, "silent_failure": None}),
    }
    return {
        "t": started,
        "mode": "analyst",
        "session_id": session_id,
        "source": {
            "pair": pair.id,
            "kind": pair.kind,
            "delivered": pair.delivered.name,
            "upstream": pair.upstream.name if pair.upstream is not None else None,
            "supports_as_of": as_of,
            "condition": sample.meta.get("condition"),
            "semantic": semantic.to_dict() if semantic is not None else None,
        },
        "question": {"text": text, "plan": question.plan.to_dict(),
                     "describe": question.plan.describe(), "key": sample.key,
                     "query": sample.meta.get("query")},
        "answerer": answerer,
        "airs": airs,
        "records": {
            "ids": sample.ids,
            "delivered": [dict(record.payload) for record in sample.records],
            "served": _payloads(served) if served is not None else None,
            "upstream": _payloads(truth) if truth is not None else None,
            "simulated_time": sample.as_of,
            "served_as_of": sample.meta.get("served_as_of"),
            "lag_seconds": staleness,
            "t0_t1_gap_seconds": 0.0 if as_of else max(0.0, t1 - t0),
        },
        "decision": decision,
        "cost": {**usage.to_dict(), "provider": provider if provider else "none",
                 "hosted": bool(hosted),
                 "budget": (answerer_obj.budget.to_dict(answerer_obj.model)
                            if getattr(answerer_obj, "budget", None) is not None else None)},
        "notes": notes,
        "provenance": {"arm": "live", "seed_block": list(LIVE_SEED_BLOCK), "seed": seed,
                       "session_id": session_id},
    }
