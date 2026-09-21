"""Live sessions, and the wall between them and the experimental corpus.

A session is one conversation with one source under one policy: the loop, the
budget, the meter, and the Ticks it has produced. It lives in the user's own
directory —

    ~/.airs/sessions/<session_id>.jsonl      one Tick per line

— and **never** in `results/runs/`. That separation is the whole point. The run
artifacts are the canonical dataset every published number is derived from
(invariant 7); live traffic is answered on someone's laptop, over their data,
with a model of their choosing, and must never be able to reach a figure. Three
things keep it apart, and `tests/test_live_quarantine.py` asserts each:

1. **Somewhere else entirely.** `session_path` refuses to write under the results
   directory, so a misconfigured home cannot quietly cross the line.
2. **Marked in the artifact.** Every Tick carries `provenance.arm = "live"` and a
   seed from the reserved live block (100 000–110 000), so its origin survives
   being copied somewhere by hand.
3. **Excluded where it counts.** Every analysis selects runs by arm, and no
   analysis accepts `live` — checked over each entry point rather than assumed.

Nothing here writes a key, a DSN or a file path from the user's machine: a Tick
carries the source's declared id, never its location.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ..gate.policy import Policy
from ..sources import SourcePair
from .answerers import Answerer
from .budget import Budget
from .loop import Loop, Meter
from .session import LIVE_SEED_BLOCK, Question

SESSIONS_DIR = Path.home() / ".airs" / "sessions"
RESULTS_DIR = Path("results") / "runs"
SESSION_ID = re.compile(r"^[0-9a-f]{12}$")
# Anything that looks like a credential, checked against every Tick before it is
# written. A Tick has no business carrying any of these; if one ever appears the
# session stops rather than persisting it.
SECRET = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|xoxb-|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}"
    r"|postgres(?:ql)?://\S+:\S+@|mysql://\S+:\S+@|mongodb(?:\+srv)?://\S+:\S+@)",
    re.IGNORECASE,
)


class SessionError(RuntimeError):
    """A session that cannot be opened or continued, with the fix."""


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def session_path(session_id: str, directory: Path = SESSIONS_DIR) -> Path:
    """Where this session's Ticks live — never inside the results directory."""
    if not SESSION_ID.match(session_id):
        raise SessionError(f"{session_id!r} is not a session id")
    directory = Path(directory).expanduser().resolve()
    results = (Path.cwd() / RESULTS_DIR).resolve()
    if directory == results or results in directory.parents or directory in results.parents:
        raise SessionError(
            f"refusing to write live sessions to {directory}: live traffic must stay "
            f"out of {results}, which is the experimental corpus (invariant 7)")
    return directory / f"{session_id}.jsonl"


def contains_secret(tick: dict[str, Any]) -> str | None:
    """The first credential-shaped string in a Tick, or None."""
    match = SECRET.search(json.dumps(tick, ensure_ascii=False, default=str))
    return match.group(0)[:12] + "…" if match else None


@dataclass
class Session:
    """One conversation: the loop that answers it and the Ticks it has produced."""

    id: str
    loop: Loop
    budget: Budget
    question: Question
    seed: int = LIVE_SEED_BLOCK[0]
    # Resolved when a Tick is written, not when this class was defined, so the
    # destination can be configured (and a test can point it somewhere else).
    directory: Path | None = None
    ticks: int = 0
    # Every AIRS dimension this session has actually observed. A recommended
    # policy is filtered against these: a floor this pipeline never clears is
    # not advice, it is a refusal machine.
    observed: dict[str, list[float]] = field(default_factory=dict)
    _asked: int = field(default=0, repr=False)

    @property
    def meter(self) -> Meter:
        return self.loop.meter

    def next_seed(self) -> int:
        """A seed from the reserved live block, so a Tick's origin is legible."""
        low, high = LIVE_SEED_BLOCK
        seed = low + ((self.seed - low) + self._asked) % (high - low)
        self._asked += 1
        return seed

    def stream(self, question: Question | None = None) -> Iterator[dict[str, Any]]:
        """Ask one question, yielding each stage as it happens; persist the Tick."""
        for event in self.loop.stream(question or self.question, seed=self.next_seed()):
            if event["stage"] == "tick":
                self.write(event["tick"])
            yield event

    def write(self, tick: dict[str, Any]) -> Path:
        leaked = contains_secret(tick)
        if leaked is not None:
            raise SessionError(
                f"refusing to write this Tick: it contains something shaped like a "
                f"credential ({leaked}). Nothing was written; report this as a bug")
        for dimension, value in (tick.get("airs", {}).get("dimensions") or {}).items():
            if value.get("score") is not None:
                self.observed.setdefault(dimension, []).append(float(value["score"]))
        path = session_path(self.id, self.directory or SESSIONS_DIR)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(tick, ensure_ascii=False, allow_nan=False) + "\n")
        self.ticks += 1
        return path

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "source": self.loop.pair.id,
            "answerer": self.loop.answerer.name,
            "policy": self.loop.policy.to_dict(),
            "policy_description": self.loop.policy.describe(),
            "refetch": self.loop.mode,
            "strip_semantics": self.loop.strip_semantics,
            "task": self.loop.task,
            "budget": self.budget.to_dict(),
            "meter": self.meter.to_dict(),
            "ticks": self.ticks,
            "observed": {dimension: {"n": len(scores), "min": min(scores),
                                     "mean": sum(scores) / len(scores)}
                         for dimension, scores in self.observed.items()},
            "arm": "live",
            "seed_block": list(LIVE_SEED_BLOCK),
        }


def open_session(pair: SourcePair, answerer: Answerer, *, policy: Policy,
                 budget: Budget, question: Question, mode: str = "gate",
                 task: str = "retrieval", directory: Path | None = None,
                 session_id: str | None = None, strip_semantics: bool = False) -> Session:
    session_id = session_id or new_session_id()
    loop = Loop(pair=pair, policy=policy, answerer=answerer, mode=mode, task=task,
                session_id=session_id, strip_semantics=strip_semantics)
    return Session(id=session_id, loop=loop, budget=budget, question=question,
                   directory=directory)


def read_session(session_id: str, directory: Path | None = None) -> list[dict[str, Any]]:
    """The Ticks of one session, oldest first. Missing session → empty."""
    path = session_path(session_id, directory or SESSIONS_DIR)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
