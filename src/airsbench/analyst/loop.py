"""The router and the two-step loop: admit, refetch, or refuse — before the model.

    question → sample delivered → probe.measure → Controller.evaluate(policy)
                    ┌──────────────────────────────┼───────────────────────┐
                 ADMIT                         REFETCH                  REFUSE
            answer normally           re-read upstream, re-score,     no model call
                                      then answer from what came      the rule and the
                                      back                            observed value, $0

Written once, here, because two callers need exactly this: the API (A7) and the
refetch arm's batch runner (W6). The arm's two conditions are the two ways a
re-read can start:

    gate-initiated    the router decides, from the policy — no model involved
    agent-initiated   the agent is offered a re-read and decides for itself

**Three properties this file exists to keep.**

*REFUSE costs nothing.* It never reaches an answerer, so no budget is consulted
and nothing can be hallucinated — it is arithmetic over measured values, and the
Tick carries the rule and the observed number that produced it.

*A re-read is only attempted where it could help.* Staleness is repaired by
reading again; schema drift and semantic stripping are not — the same pipeline
returns the same broken records — so those refuse instead of spending an upstream
read to learn nothing (author decision, 18 Sep). `REPAIRABLE` is that rule, and
it is stated rather than inferred.

*Invariant 1 survives.* The standard prompt never mentions faults, staleness or
re-reading, and is untouched. Only the agent-initiated condition uses the
tool-offering prompt, which is a **different instrument** and a separately
declared condition: its rates are not pooled with the corpus's or with the other
live modes (Chapter 3, brief correction 11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from agentic_faults import Record

from ..gate.controller import Controller, Verdict
from ..gate.policy import Policy
from ..probe import DEFAULT_WEIGHTS, load_weights
from ..sources import SourcePair, to_probe_entry
from ..sources.manifest import semantic_layer
from .answerers import Answerer
from .budget import SpendRefused
from .session import Question, build_tick
from .verifier import AgentAnswer, verify

# Rules a re-read repairs *legitimately*. Only staleness: record age and
# freshness are about WHEN the values were true, and reading the system of record
# again answers exactly that.
#
# Consistency and semantic completeness are deliberately absent, and the reason is
# not mechanical — a re-read of upstream would raise both, because upstream is by
# definition intact. It is that a re-read BYPASSES the pipeline. Quietly going
# around a pipeline that is renaming fields or dropping the semantic layer turns a
# contract violation into an invisible workaround, and the agent keeps answering
# from a source the pipeline is no longer able to deliver. Those refuse, loudly,
# with the rule and the observed value (author decision, 18 Sep).
#
# `min_airs` is absent for a related reason: a composite floor can be breached by
# any dimension, so it does not say what a re-read would be fixing.
REPAIRABLE = ("max_record_age_seconds", "min_dimension.freshness")
MODES = ("off", "gate", "agent")
MAX_REFETCHES = 1


class LoopError(RuntimeError):
    """The loop could not run — a source or a mode that cannot do what was asked."""


@dataclass
class Meter:
    """The session meter: what enforcement bought, and what it cost.

    The exchange rate is the thesis's headline trade (Fig 4.5) computed live:
    correct answers forfeited per silent failure prevented. It is only
    meaningful once a refusal has actually happened, and is None until then.
    """

    asked: int = 0
    answered: int = 0
    refused: int = 0
    refetched: int = 0
    correct: int = 0
    silent_failures: int = 0
    prevented: int = 0
    forfeited: int = 0
    usd: float = 0.0

    @property
    def exchange_rate(self) -> float | None:
        return round(self.forfeited / self.prevented, 2) if self.prevented else None

    def record(self, tick: dict[str, Any]) -> None:
        decision, gate = tick["decision"], tick["gate"]
        self.asked += 1
        self.usd = round(self.usd + tick["cost"]["usd"], 8)
        if tick["refetch"]["attempted"]:
            self.refetched += 1
        if gate["verdict"] == "refuse":
            self.refused += 1
            # What the refusal bought, and what it cost: the question was never
            # asked, so this is what the delivered records WOULD have produced.
            if gate["would_have"] == "silent_failure":
                self.prevented += 1
            elif gate["would_have"] == "correct":
                self.forfeited += 1
            return
        self.answered += 1
        self.correct += bool(decision.get("correct"))
        self.silent_failures += bool(decision.get("silent_failure"))

    def to_dict(self) -> dict[str, Any]:
        return {"asked": self.asked, "answered": self.answered, "refused": self.refused,
                "refetched": self.refetched, "correct": self.correct,
                "silent_failures": self.silent_failures, "prevented": self.prevented,
                "forfeited": self.forfeited, "exchange_rate": self.exchange_rate,
                "usd": round(self.usd, 6)}


def route(verdict: Verdict, pair: SourcePair, mode: str) -> str:
    """admit, refetch or refuse — the router's whole decision.

    A shadow-mode policy (`on_violation: warn`) admits, and says so in the
    verdict; the loop does not second-guess that.

    The two refetch conditions differ **only in who decides** about a violation a
    re-read could repair, which is what makes the arm's contrast clean:

        gate    the router re-reads, without involving the model
        agent   the question is admitted WITH the re-read offered, and the model
                decides for itself — the treatment that answers kill question 3

    Anything a re-read cannot legitimately repair refuses in both, because an
    agent cannot fix schema drift by asking for the same records again either.
    Found live on 18 Sep: refusing in agent mode never asked the model anything,
    so the condition measured nothing.
    """
    if verdict.admitted:
        return "admit"
    if pair.upstream is None or mode == "off":
        return "refuse"
    rules = {v.rule for v in verdict.violations}
    if not (rules and rules <= set(REPAIRABLE)):
        return "refuse"
    return "refetch" if mode == "gate" else "admit"


@dataclass
class Loop:
    """One question, end to end, under a policy. Reusable across questions."""

    pair: SourcePair
    policy: Policy
    answerer: Answerer
    mode: str = "gate"
    task: str = "retrieval"
    max_refetches: int = MAX_REFETCHES
    meter: Meter = field(default_factory=Meter)
    session_id: str | None = None
    # Set by a re-read: from then on, THESE records are what the pipeline
    # delivered, so the verifier's in-transit comparison must move with them.
    _refreshed: list[Record] | None = None
    clock: Callable[[], float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise LoopError(f"mode must be one of {list(MODES)}, got {self.mode!r}")
        if self.mode == "agent" and self.pair.upstream is None:
            raise LoopError(f"{self.pair.id} declares no upstream, so there is nothing to "
                            f"re-read; use --refetch off or gate")
        import time

        self.clock = self.clock or time.time
        weights, _meta = load_weights(DEFAULT_WEIGHTS, self.task)
        self.controller = Controller(self.policy, weights)
        self.layer = semantic_layer(self.pair)

    # ---- one question -------------------------------------------------------

    def ask(self, question: Question, *, seed: int | None = None) -> dict[str, Any]:
        started = self.clock()
        sample = self.pair.delivered.sample(question.n, key=question.key, seed=seed)
        sample.records = self.layer.apply(sample.records)
        text = question.text.replace("{query}", str(sample.meta.get("query", "")))
        ids = [record_id for record_id in sample.ids if record_id is not None]

        self._refreshed = None
        verdict = self._evaluate(sample.records, sample.ids, sample, ids)
        decision = route(verdict, self.pair, self.mode)

        refetch = {"attempted": False, "initiated_by": None, "n_records": 0,
                   "verdict_after": None, "airs_after": None, "reason": None}
        records = list(sample.records)
        if decision == "refetch":
            records, verdict, refetch = self._refetch(
                sample, ids, verdict, initiated_by="gate")
            decision = "admit" if verdict.admitted else "refuse"

        gate = self._gate_block(verdict, decision, question, records, sample, ids)
        if decision == "refuse":
            return self._tick(question, text, sample, records, ids, gate, refetch,
                              answer=None, usage=None, started=started)

        answer, usage = self.answerer.answer(text, question.plan, records)
        if self.mode == "agent" and getattr(answer, "refetch_ids", None) \
                and not refetch["attempted"]:
            records, verdict, refetch = self._refetch(
                sample, ids, verdict, initiated_by="agent",
                asked_for=answer.refetch_ids)
            gate = self._gate_block(verdict, "admit", question, records, sample, ids)
            answer, second = self.answerer.answer(text, question.plan, records)
            usage = _add_usage(usage, second)
        return self._tick(question, text, sample, records, ids, gate, refetch,
                          answer=answer, usage=usage, started=started)

    # ---- the pieces ---------------------------------------------------------

    def _entries(self, records: Sequence[Record], ids: Sequence[str | None]):
        return [to_probe_entry(record, record_id)
                for record, record_id in zip(records, ids)]

    def _served(self, sample, ids: list[str]) -> list[Record] | None:
        """Upstream as of when the delivered values were true — A1's reference."""
        upstream = self.pair.upstream
        if upstream is None:
            return None
        if upstream.describe().supports_as_of:
            return upstream.fetch(ids, as_of=sample.meta.get("served_as_of", sample.as_of))
        return upstream.fetch(ids)

    def _evaluate(self, records, record_ids, sample, ids) -> Verdict:
        served = self._served(sample, ids)
        return self.controller.evaluate(
            self._entries(records, record_ids),
            [to_probe_entry(record) for record in served] if served is not None else None,
        )

    def _refetch(self, sample, ids: list[str], before: Verdict, *, initiated_by: str,
                 asked_for: Sequence[str] | None = None):
        """Read the same ids again, now, and score what came back.

        This is the pipeline re-reading its own source, so the records are
        upstream's state *at the question's moment* — which is what a real refetch
        buys, and why the arm can price it.

        Stated plainly, because it shapes what the arm can claim: on a source that
        can be read as of a past time, and with no read latency modelled, a
        refetch returns exactly the records the answer is graded against. So a
        refetched answer on the demo is correct unless the model itself errs. The
        arm's question is therefore not "does re-reading fix staleness" (it does,
        by construction) but "does the agent ask, and what does asking cost".
        """
        wanted = [i for i in (asked_for or ids) if i in ids] or ids
        upstream = self.pair.upstream
        # "Now" is the question's own moment. On a simulated source, reading
        # without an `as_of` returns the end of the stream — later than the answer
        # key this question is graded against, i.e. the future. Found in the first
        # live run of the loop (18 Sep).
        fresh = (upstream.fetch(wanted, as_of=sample.as_of)
                 if upstream.describe().supports_as_of else upstream.fetch(wanted))
        by_id = {record.meta.get("record_id"): record for record in fresh}
        records = [by_id.get(record_id) or original
                   for record_id, original in zip(ids, sample.records)]
        records = self.layer.apply(records)
        # What the pipeline has now delivered. Without this, a wrong answer after a
        # re-read was labelled `corrupted_in_transit` — the fields differ from the
        # ORIGINAL served state, which is the point of re-reading, not a corruption
        # (found comparing the two conditions live, 18 Sep).
        self._refreshed = list(records)
        after = self.controller.evaluate(
            self._entries(records, ids),
            [to_probe_entry(record) for record in fresh],
        )
        return records, after, {
            "attempted": True,
            "initiated_by": initiated_by,
            "n_records": len(fresh),
            "verdict_after": "admit" if after.admitted else "refuse",
            "airs_after": after.airs,
            "reason": before.reason,
        }

    def _gate_block(self, verdict: Verdict, decision: str, question: Question,
                    records, sample, ids) -> dict[str, Any]:
        """The verdict, plus what a refusal cost — priced against real ground truth."""
        block = verdict.to_dict()
        block["verdict"] = decision
        block["would_have"] = None
        if decision == "admit" and not verdict.admitted:
            block["delegated"] = True
            block["reason"] = (f"admitted for the agent to decide, with a re-read offered: "
                               f"{verdict.reason}")
        if decision == "refuse":
            block["would_have"] = self._would_have(question, records, sample, ids)
        return block

    def _would_have(self, question: Question, records, sample, ids) -> str | None:
        """What the refused question would have produced, from the records alone.

        The meter's exchange rate needs both halves of the trade: a refusal that
        prevented a silent failure, and one that forfeited a correct answer. No
        model is called — this is the delivered records' own implication, which
        is the `literal` answerer's rule, checked against upstream.
        """
        upstream = self.pair.upstream
        if upstream is None:
            return None
        from .answerers import LiteralAnswerer

        answer, _usage = LiteralAnswerer().answer("", question.plan, records)
        if answer.abstained:
            # The delivered records do not support the question at all: refusing
            # forfeited nothing and prevented nothing.
            return "abstained"
        truth = (upstream.fetch(ids, as_of=sample.as_of)
                 if upstream.describe().supports_as_of else upstream.fetch(ids))
        result = verify(question.plan, answer, delivered=records,
                        served=self._served(sample, ids), truth=truth)
        if not result.verifiable:
            return None
        if result.correct:
            return "correct"
        return "silent_failure" if result.silent_failure else "wrong"

    def _tick(self, question: Question, text: str, sample, records, ids,
              gate: dict[str, Any], refetch: dict[str, Any], *, answer, usage,
              started: float) -> dict[str, Any]:
        upstream = self.pair.upstream
        as_of = upstream is not None and upstream.describe().supports_as_of
        served = self._refreshed if self._refreshed is not None else self._served(sample, ids)
        t0 = self.clock()
        truth = None
        if upstream is not None and answer is not None:
            truth = upstream.fetch(ids, as_of=sample.as_of) if as_of else upstream.fetch(ids)
        t1 = self.clock()

        if answer is None:  # refused: no model was called, so nothing was decided
            answer = AgentAnswer(text=gate["reason"])
            from .answerers import Usage

            usage = Usage(self.answerer.name)
            verification = None
        else:
            verification = (verify(question.plan, answer, delivered=records, served=served,
                                   truth=truth) if upstream is not None else None)

        sample.records = records
        tick = build_tick(
            pair=self.pair, question=question, text=text, sample=sample, answer=answer,
            usage=usage, airs=self._airs(gate), verification=verification, served=served,
            truth=truth, as_of=as_of, seed=None, session_id=self.session_id,
            answerer=self.answerer.name, started=started, t0=t0, t1=t1,
            semantic=self.layer, answerer_obj=self.answerer,
        )
        self.session_id = tick["session_id"]
        tick["mode"] = f"analyst/{self.mode}"
        tick["gate"] = gate
        tick["refetch"] = refetch
        if gate["verdict"] == "refuse":
            tick["decision"]["refused"] = True
            tick["decision"]["reason"] = (
                f"the gate refused this batch before any model was called: {gate['reason']}")
            tick["notes"].append(
                f"refused before any model call, at no cost: {gate['reason']}")
        self.meter.record(tick)
        tick["running"] = self.meter.to_dict()
        return tick

    def _airs(self, gate: dict[str, Any]) -> dict[str, Any]:
        """The gate's own measurement, in the Tick's `airs` shape (one scorer)."""
        weights = self.controller.weights
        from ..probe import band

        score = gate["airs"]
        label, note = band(score) if score is not None else (None, None)
        return {
            "task": self.task,
            "n_records": gate["n_records"],
            "dimensions": {dim: {**value, "weight": weights.get(dim, 0.0)}
                           for dim, value in gate["dimensions"].items()},
            "weights": weights,
            "airs": score,
            "weight_covered": gate["weight_covered"],
            "unmeasured": [d for d, v in gate["dimensions"].items() if v["score"] is None],
            "band": label,
            "band_note": note,
        }


def _add_usage(first, second):
    """Two model calls in one question: the Tick reports the pair, not the last."""
    from .answerers import Usage

    return Usage(first.model, first.input_tokens + second.input_tokens,
                 first.output_tokens + second.output_tokens,
                 round(first.usd + second.usd, 8))


def run(pair: SourcePair, question: Question, answerer: Answerer, policy: Policy, *,
        questions: int = 1, seed: int | None = None, mode: str = "gate",
        task: str = "retrieval") -> tuple[list[dict[str, Any]], Meter]:
    """Ask `questions` questions under one policy. Used by the CLI, API and arm."""
    loop = Loop(pair=pair, policy=policy, answerer=answerer, mode=mode, task=task)
    ticks = []
    for index in range(questions):
        try:
            ticks.append(loop.ask(question, seed=None if seed is None else seed + index))
        except SpendRefused:
            raise
    return ticks, loop.meter
