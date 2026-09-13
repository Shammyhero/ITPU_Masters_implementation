"""The /api routes. Thin by rule: no score is computed in this file.

Every number comes from `airsbench.probe` or `airsbench.gate` — the same code the
`airs` command runs — because a second implementation of a scoring rule drifts
from the first. `test_controller_and_replay_agree` exists for that reason, and
the TypeScript port in `demo/src/components/ProbeLive.tsx` had already drifted
(nested payloads, clock skew) when it was found.

Errors are one shape everywhere, status 422:

    {"error": {"input": "delivered" | "source" | "task" | "policy" | <field>,
               "line": 14 | null,
               "message": "delivered:14: ... and how to fix it"}}
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import __version__
from ..gate import Controller, Policy
from ..gate.replay import Batch, fault_free_baseline, replay
from ..probe import (
    BANDS,
    DEFAULT_WEIGHTS,
    DIMENSIONS,
    ProbeError,
    load_weights,
    parse_records,
    score,
)
from .schemas import GateRequest, ReplayRequest, ScoreRequest

SAMPLES = Path(__file__).parent / "data" / "samples.json"
REPLAY = Path(__file__).parent / "data" / "replay_corpus.json"
_LINE = re.compile(r"^(?:delivered|source):(\d+):")

router = APIRouter(prefix="/api")


class InputError(Exception):
    """Input the API refuses, and which input it was."""

    def __init__(self, input_name: str | None, message: str) -> None:
        super().__init__(message)
        self.input_name = input_name
        self.message = message


def error_response(input_name: str | None, message: str, status: int = 422) -> JSONResponse:
    match = _LINE.match(message)
    return JSONResponse(
        {"error": {"input": input_name,
                   "line": int(match.group(1)) if match else None,
                   "message": message}},
        status_code=status,
    )


def _weights(task: str):
    try:
        return load_weights(DEFAULT_WEIGHTS, task)
    except ProbeError as exc:
        raise InputError("task", str(exc)) from None


def _policy(data: dict[str, Any]) -> Policy:
    try:
        return Policy.from_dict(data)
    except ValueError as exc:
        raise InputError("policy", str(exc)) from None


def _records(text: str | None, name: str, unique_ids: bool = False):
    """Parsed records, or None when the input was left empty."""
    if text is None or not text.strip():
        if name == "delivered":
            raise InputError(name, "delivered: no records given; paste or drop the "
                                   "records as your pipeline delivers them")
        return None
    try:
        return parse_records(text, name, unique_ids=unique_ids)
    except ProbeError as exc:
        raise InputError(name, str(exc)) from None


@lru_cache(maxsize=1)
def _replay_corpus() -> dict[str, Any]:
    return json.loads(REPLAY.read_text(encoding="utf-8"))


@router.get("/meta")
def meta(request: Request):
    calibration = json.loads(DEFAULT_WEIGHTS.read_text(encoding="utf-8"))
    return {
        "version": __version__,
        "dimensions": list(DIMENSIONS),
        "bands": [{"min": floor, "label": label, "note": note}
                  for floor, label, note in BANDS],
        "calibration": {key: calibration.get(key) for key in
                        ("schema", "calibrated_at", "target", "target_note",
                         "fitted_on", "caveat")},
        "profiles": calibration["profiles"],
        "validation": calibration.get("validation", {}),
        "frontend_built": request.app.state.frontend_built,
        "preloaded": request.app.state.preloaded is not None,
    }


@router.get("/samples")
def samples(request: Request):
    return {**json.loads(SAMPLES.read_text(encoding="utf-8")),
            "preloaded": request.app.state.preloaded}


@router.post("/score")
def score_records(body: ScoreRequest):
    _weights(body.task)  # an unknown task is named before the records are read
    delivered = _records(body.delivered, "delivered")
    source = _records(body.source, "source", unique_ids=True)
    try:
        return score(delivered, source, body.task)
    except ProbeError as exc:
        raise InputError("delivered", str(exc)) from None


@router.post("/gate")
def gate_batch(body: GateRequest):
    weights, _ = _weights(body.task)
    policy = _policy(body.policy)
    if body.shadow:
        policy = policy.shadow()
    delivered = _records(body.delivered, "delivered")
    source = _records(body.source, "source", unique_ids=True)
    try:
        verdict = Controller(policy, weights).evaluate(delivered, source)
    except ProbeError as exc:
        raise InputError("delivered", str(exc)) from None
    return {**verdict.to_dict(), "task": body.task, "policy_description": policy.describe()}


@router.post("/replay")
def replay_policy(body: ReplayRequest):
    """What this policy would have prevented, and cost, across the study's runs.

    `gate.replay` over the baked corpus — the accounting behind
    `docs/gate_findings.md` — with the no-gate outcome and the fault-free floor
    beside it, because a price means nothing without what it is measured against.
    """
    weights, _ = _weights(body.task)
    policy = _policy(body.policy)
    corpus = _replay_corpus()
    batches = [Batch(**row) for row in corpus["batches"] if row["task"] == body.task]
    if not batches:
        raise InputError("task", f"the replay corpus has no runs for task {body.task!r}")
    return {
        "task": body.task,
        "policy_description": policy.describe(),
        "outcome": replay(batches, policy, weights).to_dict(),
        "no_gate": replay(batches, Policy(name="no gate"), weights).to_dict(),
        "fault_free": fault_free_baseline(batches),
        "corpus": {key: corpus[key] for key in
                   ("schema", "arms", "tasks", "models", "runs", "decisions", "note")},
    }


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                  include_in_schema=False)
def unknown_route(path: str, request: Request):
    return error_response(None, f"no API route {request.method} /api/{path}", status=404)
