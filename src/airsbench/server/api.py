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
from fastapi.responses import JSONResponse, StreamingResponse

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
from ..sources import SourceError
from .schemas import (
    AskRequest,
    GateRequest,
    RecommendRequest,
    ReplayRequest,
    ScoreRequest,
    SessionRequest,
)

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


# ---- the Analyst: sources, models, sessions, and one question at a time -----
#
# Every route here is transport. The answering itself is `analyst/loop.py`, the
# same code the CLI and the refetch arm run, so what the console shows and what
# the thesis measured cannot drift apart (plan A7).

def _declared(request: Request) -> dict[str, Any]:
    sources = getattr(request.app.state, "sources", None) or {}
    if not sources:
        from ..sources.config import load_sources

        sources = load_sources(None)  # the bundled demo pairs are always available
        request.app.state.sources = sources
    return sources


def _pair(request: Request, source_id: str):
    """A source by its declared id — never a path, DSN or URL from a request."""
    sources = _declared(request)
    if source_id not in sources:
        raise InputError("source", f"no source {source_id!r} is declared on this machine. "
                                   f"Available: {', '.join(sources)}. Sources are declared "
                                   f"in sources.yaml and passed with `airs serve --sources`, "
                                   f"never named in a request.")
    return sources[source_id]


def _source_summary(pair) -> dict[str, Any]:
    from ..sources.manifest import semantic_layer

    layer = semantic_layer(pair)
    upstream = pair.upstream
    return {
        "id": pair.id,
        "kind": pair.kind,
        "description": pair.description,
        "upstream": upstream.name if upstream is not None else None,
        "supports_as_of": bool(upstream is not None and upstream.describe().supports_as_of),
        "verifiable": upstream is not None,
        "semantic": layer.to_dict(),
    }


@router.get("/sources")
def list_sources(request: Request):
    """What this machine has declared. The page picks from here and nowhere else."""
    return {"sources": [_source_summary(pair) for pair in _declared(request).values()]}


@router.post("/sources/{source_id}/test")
def test_source(source_id: str, request: Request):
    """Read the declared source and report what came back, or why it could not."""
    from ..sources import SourceError

    pair = _pair(request, source_id)
    try:
        schema = pair.delivered.describe()
        sample = pair.delivered.sample(min(3, 6))
    except SourceError as exc:
        raise InputError("source", str(exc)) from None
    except (OSError, ValueError) as exc:
        raise InputError("source", f"{source_id}: could not be read — {exc}") from None
    return {**_source_summary(pair), "schema": schema.to_dict(),
            "sample": [dict(record.payload) for record in sample.records[:3]]}


@router.get("/models")
def models():
    """What can answer here: `literal`, whatever Ollama has, and configured keys.

    A provider appears as configured only when its key is already in this
    machine's environment. The page never sends a key, and this route never
    returns one — only whether one is present.
    """
    import os

    from ..agents.llm import PRICING, load_dotenv, ollama_base_url
    from ..analyst.answerers import PROVIDERS

    # The same .env the answerers read, or this route would report a key as
    # absent that `airs analyst` happily uses.
    load_dotenv()

    local: list[str] = []
    reachable, detail = False, "Ollama was not reachable; start it with `ollama serve`"
    try:
        import urllib.request

        url = ollama_base_url().rstrip("/").removesuffix("/v1") + "/api/tags"
        with urllib.request.urlopen(url, timeout=2) as response:
            local = sorted(model["name"] for model in json.load(response).get("models", []))
        reachable, detail = True, f"{len(local)} local model(s), free, nothing leaves this machine"
    except Exception:  # noqa: BLE001 - a missing Ollama is a normal state, not an error
        pass

    keys = {provider.rstrip("/"): f"{provider.rstrip('/').upper()}_API_KEY"
            for provider in PROVIDERS}
    providers = [
        # Whether a key is present, never the key itself.
        {"provider": provider, "configured": bool(os.environ.get(variable)),
         "env": variable,
         "note": "records are sent to this provider; spend is capped before each call"}
        for provider, variable in sorted(keys.items())
    ]
    return {
        "literal": {"note": "the question executed over the delivered records at face "
                            "value — no model, $0"},
        "local": {"reachable": reachable, "models": [f"ollama/{name}" for name in local],
                  "note": detail},
        "providers": providers,
        "priced": sorted(PRICING),
    }


@router.post("/session")
def open_session_route(body: SessionRequest, request: Request):
    from ..analyst.answerers import AnswererError, make_answerer
    from ..analyst.budget import DEFAULT_DAY_USD, DEFAULT_SESSION_USD, Budget
    from ..analyst.loop import MODES, LoopError
    from ..analyst.session import demo_question
    from ..analyst.sessions import open_session

    pair = _inline_pair(body) if body.records else _pair(request, body.source)
    _weights(body.task)
    if body.refetch not in MODES:
        raise InputError("refetch", f"refetch must be one of {list(MODES)}")
    policy = _policy(body.policy) if body.policy else Policy(name="open")
    budget = Budget(session_usd=DEFAULT_SESSION_USD if body.max_cost is None else body.max_cost,
                    day_usd=DEFAULT_DAY_USD if body.max_cost_day is None else body.max_cost_day)
    try:
        answerer = make_answerer(body.answerer, budget=budget)
    except AnswererError as exc:
        raise InputError("answerer", str(exc)) from None
    _require_key(body.answerer)
    # Only the demo source ships a question of its own; everything else is asked
    # with an explicit plan, because an answer is checked against the question's
    # plan and the server must not invent one.
    question = demo_question() if pair.kind == "demo" else None
    try:
        session = open_session(pair, answerer, policy=policy, budget=budget,
                               question=question, mode=body.refetch, task=body.task,
                               strip_semantics=body.strip_semantics)
    except LoopError as exc:
        raise InputError("refetch", str(exc)) from None
    request.app.state.sessions[session.id] = session
    return session.to_dict()


def _inline_pair(body: SessionRequest):
    """A session over records pasted into the page.

    This is the one source that may arrive in a request, and it is not an
    exception to the firewall: the records ARE the request body. The server
    still opens no file, path, DSN or URL because something asked it to
    (author decision, 20 Sep). The pair is held for this session only and never
    written anywhere.
    """
    from ..sources import SourcePair
    from ..sources.inline import InlineSource

    delivered = InlineSource("inline/delivered", body.records)
    try:
        delivered.entries()
    except (SourceError, ProbeError) as exc:
        raise InputError("records", str(exc)) from None
    upstream = None
    if body.upstream and body.upstream.strip():
        upstream = InlineSource("inline/upstream", body.upstream, unique_ids=True)
        try:
            upstream.entries()
        except (SourceError, ProbeError) as exc:
            raise InputError("upstream", str(exc)) from None
    return SourcePair(
        id="inline", kind="inline", delivered=delivered, upstream=upstream,
        description=("Records pasted into this page, held in memory for this session"
                     + ("" if upstream else
                        " — with no system of record, answers cannot be verified")),
    )


def _require_key(spec: str) -> None:
    """A hosted model needs its key before the session opens.

    Without this the session opens happily and fails on the first question,
    halfway through a stream, which is the worst possible moment to discover it.
    """
    import os

    from ..agents.llm import load_dotenv
    from ..analyst.answerers import provider_of

    if spec == "literal" or spec.startswith("ollama/"):
        return
    load_dotenv()
    provider = provider_of(spec)
    variable = f"{provider.upper()}_API_KEY"
    if not os.environ.get(variable):
        raise InputError("answerer", f"{spec} needs {variable} in this machine's "
                                     f"environment, and it is not set. Put it in .env and "
                                     f"restart `airs serve`, or answer with a local model "
                                     f"(ollama/<name>) or `literal`, which cost nothing.")


def _session(request: Request, session_id: str):
    session = request.app.state.sessions.get(session_id)
    if session is None:
        raise InputError("session_id", f"no open session {session_id!r}; open one with "
                                       f"POST /api/session")
    return session


@router.get("/session/{session_id}")
def session_meter(session_id: str, request: Request):
    """The running meter: what was answered, refused, prevented and forfeited."""
    return _session(request, session_id).to_dict()


@router.post("/ask")
def ask(body: AskRequest, request: Request):
    """One question, streamed stage by stage as Server-Sent Events.

    gate → (refetch) → answer → tick. The order is the point: the viewer sees the
    answer, forms an expectation, and only then the verifier resolves it.
    """
    from ..analyst.answerers import AnswererError
    from ..analyst.budget import SpendRefused
    from ..analyst.plan import Plan, PlanError
    from ..analyst.session import DEFAULT_CANDIDATES, Question
    from ..analyst.sessions import SessionError

    session = _session(request, body.session_id)
    question = session.question
    if question is None and body.plan is None:
        raise InputError("plan", f"{session.loop.pair.id} has no built-in question: send "
                                 f"`plan` (and `question` for its wording) with each ask. "
                                 f"Plans are min_by, max_by, top_k, count_where, sum_where "
                                 f"or lookup.")
    if body.plan is not None:
        try:
            plan = Plan.from_dict(body.plan)
        except PlanError as exc:
            raise InputError("plan", str(exc)) from None
        question = Question(body.question or f"What is {plan.describe()}?", plan,
                            n=body.n or (question.n if question is not None
                                         else DEFAULT_CANDIDATES))
    elif body.question is not None:
        raise InputError("question", "a question needs its plan: an answer is verified "
                                     "against the question's plan, never the answerer's")
    elif body.n is not None and question is not None:
        question = Question(question.text, question.plan, key=question.key, n=body.n)

    def events():
        try:
            for event in session.stream(question):
                # `event: tick` carries the Tick itself — one documented shape,
                # not a Tick inside an envelope the console would have to unwrap.
                payload = event["tick"] if event["stage"] == "tick" else event
                yield f"event: {event['stage']}\ndata: " + json.dumps(
                    payload, ensure_ascii=False, allow_nan=False) + "\n\n"
        except (SpendRefused, AnswererError, SessionError, ProbeError) as exc:
            payload = {"error": {"input": "answerer", "line": None, "message": str(exc)}}
            yield "event: error\ndata: " + json.dumps(payload) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store",
                                      "X-Accel-Buffering": "no"})


def _corpus_batches(task: str):
    corpus = _replay_corpus()
    batches = [Batch(**row) for row in corpus["batches"] if row["task"] == task]
    if not batches:
        raise InputError("task", f"the replay corpus has no runs for task {task!r}")
    return batches, corpus


def _feasible(policy: Policy, observed: dict[str, dict[str, float]]) -> bool:
    """Would this policy admit anything on what this session has measured?

    A recommendation the user's own pipeline fails on every question is not
    advice; it is a refusal machine. Judged on the WORST value seen, because a
    gate refuses per batch, not on average.
    """
    for dimension, floor in policy.min_dimension.items():
        seen = observed.get(dimension)
        if seen and seen["min"] < floor:
            return False
    if policy.min_airs is not None:
        seen = observed.get("airs")
        if seen and seen["min"] < policy.min_airs:
            return False
    return True


@router.post("/recommend")
def recommend(body: RecommendRequest, request: Request):
    """A policy to start from, priced on the study's own runs.

    Not a heuristic: every policy in the sweep is replayed over the corpus the
    gate findings were computed from, and the one recommended is the cheapest by
    exchange rate among those that actually refuse something and still answer.
    What the session has measured only FILTERS that list — it never invents a
    floor (author decision, 21 Sep).

    The two costs are reported separately and labelled, because they are not the
    same number: the sweep's raw rate credits a policy with every silent failure
    in a refused batch, while the attribution rate credits only the excess over
    what a fault-free pipeline produces anyway — 2.26 against 7.0 on retrieval.
    """
    from ..gate.replay import SWEEPS, fault_free_baseline, replay

    weights, _meta = _weights(body.task)
    batches, corpus = _corpus_batches(body.task)
    observed: dict[str, dict[str, float]] = {}
    if body.session_id:
        observed = _session(request, body.session_id).to_dict()["observed"]

    rows = []
    for sweep in SWEEPS.values():
        for policy in sweep(body.task):
            outcome = replay(batches, policy, weights)
            if not (outcome.refused_batches and outcome.admitted_decisions):
                continue  # refuses nothing, or refuses everything: not a trade
            # The outcome carries its own `policy` (the name), so it is spread
            # FIRST and the structured policy overrides it — the console applies
            # this object to the router, and a name is not applicable.
            rows.append({**outcome.to_dict(),
                         "policy_name": outcome.policy,
                         "policy": policy.to_dict(),
                         "description": policy.describe(),
                         "feasible_here": _feasible(policy, observed)})

    priced = [row for row in rows if row["exchange_rate"] is not None]
    affordable = [row for row in priced if row["feasible_here"]] or priced
    best = min(affordable, key=lambda row: row["exchange_rate"]) if affordable else None
    return {
        "task": body.task,
        "recommended": best,
        "considered": sorted(priced, key=lambda row: row["exchange_rate"]),
        "filtered_by_session": bool(observed),
        "observed": observed,
        "fault_free": fault_free_baseline(batches),
        "corpus": {key: corpus[key] for key in ("runs", "decisions", "models", "arms")},
        "note": ("Priced on the study's own runs, not on your data. `exchange_rate` is "
                 "the sweep's raw rate: correct answers forfeited per silent failure "
                 "prevented, crediting the gate with every silent failure inside a "
                 "refused batch. The attribution 'true cost' is higher — it credits only "
                 "the excess over what a fault-free pipeline produces anyway (2.26 "
                 "against 7.0 on retrieval), because ~75% of silent failure is "
                 "agent-intrinsic and no gate can reach it."),
    }


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                  include_in_schema=False)
def unknown_route(path: str, request: Request):
    return error_response(None, f"no API route {request.method} /api/{path}", status=404)
