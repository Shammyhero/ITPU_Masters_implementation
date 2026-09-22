"""The refetch arm's batch runner (docs/refetch_arm.md, build step 2).

    python -m airsbench.runner.run --refetch-arm --dry-run
    python -m airsbench.runner.run --refetch-arm --max-cost 1.60 [--offset N --limit M]

Every question goes through the Analyst's own loop (`analyst/loop.py`) — the one
the API and the console run — so the arm measures the product rather than a
re-implementation of it. What this module adds is the experiment around the loop:

- **The grid** is `config.build_refetch_arm`: 21 runs, paired across cells and
  across states (invariant 2).
- **Provenance** is the arm's own. Every Tick is stamped `arm: "refetch"` with
  the 90 000–100 000 block, and every artifact's `config.seed` sits in it, so
  `run_arm` attributes it and no corpus analysis pools it (`NEVER_POOLED`).
- **The dry-run is exact on input.** It runs the real loop over every question of
  the grid with a counting answerer in place of the model, and counts the very
  prompts the model would be sent with the model's own tokenizer. Two figures:
  *expected* (no agent re-reads) and *worst case* (every agent question
  re-reads). Output is budgeted at `OUTPUT_TOKENS_PER_CALL` (measured ~90).
- **Spend is capped three ways.** The worst case must fit `--max-cost` before the
  campaign starts; each run's worst case must fit what is left before that run
  starts; and every call passes an analyst `Budget` with the same cap. The
  arm's spend is recorded in each artifact's `usage` — the canonical record —
  and never in `~/.airs/spend.json`, which is live accounting.
- **An artifact is written only when its run completes.** A transport failure
  loses that run's questions and nothing else (invariant 6: only transport is
  retried, and the client already did).

Run artifacts store no records, as in the corpus: the demo slice is committed and
the seeds regenerate every question exactly.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from ..analyst.answerers import Answerer, AnswererError, LiteralAnswerer, Usage, make_answerer
from ..analyst.budget import Budget, SpendRefused, cost_of
from ..analyst.loop import Loop
from ..analyst.plan import RECORD_ANSWERS, answers_equal, execute
from ..analyst.prompts import analyst_messages, refetch_messages, reread_messages
from ..analyst.session import DEMO_PLAN, demo_question
from ..analyst.verifier import AgentAnswer, rows
from ..gate.policy import Policy
from ..sources.demo import Condition, demo_pair
from .config import REFETCH_SEED_RANGE, RunConfig, refetch_cell
from .execute import RunResult

ARM_PROVENANCE = {"arm": "refetch", "seed_block": list(REFETCH_SEED_RANGE)}
# Any threshold between the healthy 0.05 s and the stale 5.05 s behaves the same,
# because age is fixed per state: the gate is a perfect detector here, and the
# design says so (docs/refetch_arm.md §4). 2.0 s is the loop tests' strict policy.
AGE_POLICY_SECONDS = 2.0
# Budgeted per call. gpt-4o-mini measured ~90 on the demo question (A5); the
# margin covers a longer "why" and an answer sentence that runs on.
OUTPUT_TOKENS_PER_CALL = 150
# The dry-run's stand-in for a model's reason when it asks to re-read — about the
# length a model writes, so the replayed request is not under-counted.
PLACEHOLDER_WHY = ("The listed prices and stock levels may have changed since these records "
                   "were read, so reading them again could change which product is cheapest "
                   "and currently in stock.")


class ArmLedger:
    """An in-memory day ledger: the arm's spend lives in its artifacts, not ~/.airs."""

    path = "memory (the refetch arm records its spend in each run artifact)"

    def __init__(self) -> None:
        self.total = 0.0

    def spent(self) -> float:
        return self.total

    def add(self, model: str, charge: float) -> float:
        self.total = round(self.total + charge, 8)
        return self.total


# ---- one run -------------------------------------------------------------------------

def question_seed(config: RunConfig, index: int) -> int:
    """Question i of a replication, identical in every cell and both states."""
    return config.sample_seed * 1_000 + index


def arm_policy(config: RunConfig) -> Policy:
    """The age policy: enforced for the gate, in shadow for the baseline.

    In shadow the baseline is admitted and every decision still records whether
    the gate WOULD have refused it — which is how refusal is priced at $0, from
    what the model actually did on exactly those questions (§4).
    """
    return Policy(name=f"age-{AGE_POLICY_SECONDS:g}s", max_record_age_seconds=AGE_POLICY_SECONDS,
                  on_violation="warn" if config.refetch_mode == "off" else "reject")


def arm_pair(config: RunConfig):
    state = "healthy" if config.fault_type == "none" else "stale"
    return demo_pair(f"refetch-{state}",
                     Condition(config.fault_type, config.severity, config.pipeline),
                     seed=config.seed, emit_record_age=config.emit_record_age)


def answerer_spec(model: str) -> str:
    """`<provider>/<model>`, the only form the analyst answerers accept."""
    if "/" in model:
        return model
    return f"anthropic/{model}" if model.startswith("claude") else f"openai/{model}"


def arm_loop(config: RunConfig, answerer: Answerer) -> Loop:
    if config.refetch_mode is None:
        raise ValueError(f"{config.label()} is not a refetch-arm config")
    return Loop(pair=arm_pair(config), policy=arm_policy(config), answerer=answerer,
                mode=config.refetch_mode, task="retrieval", provenance=ARM_PROVENANCE)


def flipped_as_delivered(loop: Loop, tick: dict[str, Any]) -> bool | None:
    """Was this question's answer key moved by the pipeline, before anyone acted?

    The verifier's own `flipped` compares against the refreshed records once a
    re-read happened (A6), so a re-read question reads unflipped. The arm pairs
    on exposure as first delivered, which is identical in every cell of a state:
    upstream as of when the delivered values were true, against the answer key.
    """
    records = tick["records"]
    ids = [record_id for record_id in records["ids"] if record_id is not None]
    upstream = loop.pair.upstream
    served = execute(DEMO_PLAN, rows(upstream.fetch(ids, as_of=records["served_as_of"])))
    truth = execute(DEMO_PLAN, rows(upstream.fetch(ids, as_of=records["simulated_time"])))
    if not (served.computable and truth.computable):
        return None
    if DEMO_PLAN.type in RECORD_ANSWERS and truth.value is None:
        return None  # no well-defined answer: the verifier calls this unverifiable too
    return not answers_equal(DEMO_PLAN, served.value, truth.value)


def decision(tick: dict[str, Any], flipped_first: bool | None) -> dict[str, Any]:
    """One question, as the arm's analysis reads it. No records (as in the corpus)."""
    verdict, gate, refetch = tick["decision"], tick["gate"], tick["refetch"]
    first = refetch["attempted"]
    return {
        "question_seed": tick["provenance"]["seed"],
        "question_key": tick["question"]["key"],
        "query": tick["question"]["query"],
        "simulated_time": tick["records"]["simulated_time"],
        "served_as_of": tick["records"]["served_as_of"],
        "ids": tick["records"]["ids"],
        "value": verdict["value"],
        "confidence": verdict["confidence"],
        "abstained": verdict["abstained"],
        "parse_failed": verdict["parse_failed"],
        "unanswered_action": verdict["unanswered_action"],
        "verifiable": verdict["verifiable"],
        "correct": verdict["correct"],
        "silent_failure": verdict["silent_failure"],
        "attribution": verdict["attribution"],
        "flipped": verdict.get("flipped"),
        "flipped_as_delivered": flipped_first,
        "changed_fields": verdict.get("changed_fields"),
        "plan_matches_question": verdict.get("plan_matches_question"),
        "agent_plan_agrees": verdict.get("agent_plan_agrees"),
        # The first reading, before any re-read: what the gate decided on.
        "airs_first": refetch["airs_before"] if first else gate["airs"],
        "dimensions_first": (refetch["dimensions_before"] if first else
                             {dim: value["score"]
                              for dim, value in tick["airs"]["dimensions"].items()}),
        "gate": {"verdict": gate["verdict"], "shadowed": gate["shadowed"],
                 "rules": [violation["rule"] for violation in gate["violations"]],
                 "record_age_seconds": gate["record_age_seconds"],
                 "reason": gate["reason"]},
        "refetch": {key: refetch[key] for key in
                    ("attempted", "initiated_by", "asked_ids", "why", "n_records",
                     "verdict_after", "reason")},
        "usage": {"input_tokens": tick["cost"]["input_tokens"],
                  "output_tokens": tick["cost"]["output_tokens"],
                  "usd": tick["cost"]["usd"]},
    }


def _rate(values: Sequence[bool | None]) -> float | None:
    known = [bool(v) for v in values if v is not None]
    return round(sum(known) / len(known), 6) if known else None


def metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Run-level rates. Correctness is over verifiable questions only."""
    verifiable = [d for d in decisions if d["verifiable"]]
    flipped = [d for d in verifiable if d["flipped_as_delivered"]]
    asked = [d for d in decisions if d["refetch"]["initiated_by"] == "agent"]
    return {
        "n": len(decisions),
        "n_verifiable": len(verifiable),
        "accuracy": _rate([d["correct"] for d in verifiable]),
        "abstention_rate": _rate([d["abstained"] for d in verifiable]),
        "silent_failure_rate": _rate([d["silent_failure"] for d in verifiable]),
        "parse_failures": sum(d["parse_failed"] for d in decisions),
        "unanswered_actions": sum(d["unanswered_action"] for d in decisions),
        "refetch_rate": _rate([d["refetch"]["attempted"] for d in decisions]),
        "agent_requests": len(asked),
        "gate_refetches": sum(d["refetch"]["initiated_by"] == "gate" for d in decisions),
        "would_refuse": sum(bool(d["gate"]["rules"]) and d["gate"]["shadowed"]
                            for d in decisions),
        "n_flipped_as_delivered": len(flipped),
        "accuracy_on_flipped": _rate([d["correct"] for d in flipped]),
        "silent_failure_on_flipped": _rate([d["silent_failure"] for d in flipped]),
    }


def airs_summary(decisions: list[dict[str, Any]]) -> dict[str, float | None]:
    """The run's mean first reading, in the corpus artifact's `airs` shape."""
    def mean(values):
        values = [v for v in values if v is not None]
        return round(statistics.fmean(values), 4) if values else None

    dims = sorted({dim for d in decisions for dim in d["dimensions_first"]})
    summary = {dim: mean([d["dimensions_first"].get(dim) for d in decisions]) for dim in dims}
    summary["total"] = mean([d["airs_first"] for d in decisions])
    return summary


def _calls(d: dict[str, Any]) -> int:
    """Model calls one question made: none if nothing was billed, two after an
    agent's re-read (the request, then the answer), otherwise one."""
    if d["usage"]["input_tokens"] == 0:
        return 0
    return 2 if d["refetch"]["initiated_by"] == "agent" else 1


def run_refetch(config: RunConfig, answerer: Answerer, out_dir: Path | None = Path("results/runs"),
                progress: Callable[[int], None] | None = None) -> RunResult:
    """One (cell, state, replication): `n_queries` questions through the loop.

    Saved only when every question is done; `out_dir=None` saves nothing.
    """
    started = datetime.now(timezone.utc)
    loop = arm_loop(config, answerer)
    decisions = []
    for index in range(config.n_queries):
        tick = loop.ask(demo_question(), seed=question_seed(config, index))
        decisions.append(decision(tick, flipped_as_delivered(loop, tick)))
        if progress is not None:
            progress(index + 1)
    result = RunResult(
        run_id=config.run_id or str(uuid.uuid4()),
        config=config.to_dict(),
        started_at=started.isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        metrics=metrics(decisions),
        airs=airs_summary(decisions),
        usage={
            "calls": sum(_calls(d) for d in decisions),
            "input_tokens": sum(d["usage"]["input_tokens"] for d in decisions),
            "output_tokens": sum(d["usage"]["output_tokens"] for d in decisions),
            "cost_usd": round(sum(d["usage"]["usd"] for d in decisions), 6),
        },
        decisions=decisions,
    )
    if out_dir is not None:
        result.save(out_dir)
    return result


# ---- the dry-run: the loop, with the model replaced by a counter --------------------

class TokenCounter:
    """Counts the exact prompts the loop would send, and answers at $0.

    With `offer_refetch` it asks to re-read every record on the first call — the
    worst case — so the second turn is rendered and counted exactly too. The
    answers themselves are the literal rule's, and are never used for anything
    but keeping the loop running.
    """

    name = "token-counter"

    def __init__(self, model: str, offer_refetch: bool) -> None:
        import tiktoken

        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:  # a model tiktoken does not know: the GPT-4o family's encoding
            self.encoding = tiktoken.get_encoding("o200k_base")
        self.offer_refetch = offer_refetch
        self.first: list[int] = []
        self.second: list[int] = []

    def count(self, messages: list[tuple[str, str]]) -> int:
        # OpenAI's chat accounting: ~4 tokens of framing per message, 3 to prime.
        return sum(len(self.encoding.encode(content)) + 4 for _, content in messages) + 3

    def answer(self, question, plan, records) -> tuple[AgentAnswer, Usage]:
        builder = refetch_messages if self.offer_refetch else analyst_messages
        self.first.append(self.count(builder(question, records)))
        if self.offer_refetch:
            ids = tuple(r.meta["record_id"] for r in records if r.meta.get("record_id"))
            return AgentAnswer(refetch_ids=ids, text=PLACEHOLDER_WHY), Usage(self.name)
        return LiteralAnswerer().answer(question, plan, records)

    def answer_after_reread(self, question, plan, first_records, request,
                            records) -> tuple[AgentAnswer, Usage]:
        self.second.append(self.count(reread_messages(
            question, first_records, request.refetch_ids, request.text, records)))
        return LiteralAnswerer().answer(question, plan, records)


@dataclass
class Estimate:
    config: RunConfig
    first_calls: int
    first_input: int
    second_calls: int
    second_input: int

    @property
    def expected_usd(self) -> float:
        return cost_of(self.config.model, self.first_input,
                       OUTPUT_TOKENS_PER_CALL * self.first_calls)

    @property
    def worst_usd(self) -> float:
        return self.expected_usd + cost_of(self.config.model, self.second_input,
                                           OUTPUT_TOKENS_PER_CALL * self.second_calls)


def estimate(config: RunConfig) -> Estimate:
    counter = TokenCounter(config.model, offer_refetch=config.refetch_mode == "agent")
    run_refetch(config, counter, out_dir=None)
    return Estimate(config, len(counter.first), sum(counter.first),
                    len(counter.second), sum(counter.second))


# ---- the campaign ---------------------------------------------------------------------

def _usd(amount: float) -> str:
    return f"${amount:.4f}"


def execute_refetch_arm(configs: list[RunConfig], args,
                        make: Callable[[str, Budget, bool], Answerer] | None = None) -> int:
    """Dry-run or execute the arm, staged by --offset/--limit, capped by --max-cost.

    `make(spec, budget, offer_refetch)` builds each run's answerer; tests pass a
    scripted one, the default is the analyst's `make_answerer`.
    """
    make = make or (lambda spec, budget, offer: make_answerer(spec, budget=budget,
                                                              offer_refetch=offer))
    total = len(configs)
    offset = getattr(args, "offset", 0) or 0
    limit = getattr(args, "limit", None)
    selected = configs[offset:]
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        print(f"No runs selected (the arm has {total}, offset={offset}).")
        return 1
    if offset or limit is not None:
        print(f"Staged: runs {offset + 1}-{offset + len(selected)} of {total}")

    print("Counting every prompt the grid would send (exact, $0) ...", flush=True)
    estimates = [estimate(cfg) for cfg in selected]
    by_cell: dict[tuple[str, str], list[Estimate]] = {}
    for est in estimates:
        state = "healthy" if est.config.fault_type == "none" else "stale"
        by_cell.setdefault((refetch_cell(est.config), state), []).append(est)
    print(f"\n  {'cell':<14}{'state':<9}{'runs':>5}{'questions':>11}"
          f"{'input tok':>12}{'expected':>11}{'worst':>11}")
    for (cell, state), group in by_cell.items():
        print(f"  {cell:<14}{state:<9}{len(group):>5}"
              f"{sum(e.config.n_queries for e in group):>11}"
              f"{sum(e.first_input for e in group):>12,}"
              f"{_usd(sum(e.expected_usd for e in group)):>11}"
              f"{_usd(sum(e.worst_usd for e in group)):>11}")
    expected = sum(e.expected_usd for e in estimates)
    worst = sum(e.worst_usd for e in estimates)
    print(f"\n{len(selected)} runs x {selected[0].n_queries} questions "
          f"= {sum(c.n_queries for c in selected)} questions on {selected[0].model}")
    print(f"Estimated cost: {_usd(expected)} expected (no agent re-reads), "
          f"{_usd(worst)} worst case (every agent question re-reads); "
          f"output budgeted at {OUTPUT_TOKENS_PER_CALL} tokens per call")
    print(f"Guard: ${args.max_cost:.2f} against the worst case")
    if worst > args.max_cost:
        print(f"\nREFUSED: the worst case exceeds --max-cost ${args.max_cost:.2f}. "
              f"Raise it deliberately if this is intended.")
        return 1
    if args.dry_run:
        print("(dry run — nothing executed, nothing spent)")
        return 0

    budget = Budget(session_usd=args.max_cost, day_usd=args.max_cost, ledger=ArmLedger())
    spec = answerer_spec(selected[0].model)
    try:  # a missing key fails here, before anything is spent — not twenty-one times
        make(spec, budget, False)
    except AnswererError as exc:
        print(f"\nCannot start: {exc}")
        return 1

    out_dir = Path(args.out)
    failed: list[tuple[RunConfig, str]] = []
    print()
    for position, (cfg, est) in enumerate(zip(selected, estimates)):
        index = offset + position
        left = args.max_cost - budget.spent_usd
        if est.worst_usd > left:
            print(f"\nSTOPPED before run {index + 1}: its worst case {_usd(est.worst_usd)} "
                  f"exceeds the {_usd(left)} left under --max-cost. Nothing was cut short.")
            print(f"  resume: python -m airsbench.runner.run --refetch-arm "
                  f"--offset {index} --max-cost X.XX")
            return 1
        print(f"[{index + 1}/{total}] {refetch_cell(cfg)} · {cfg.label()} ... ",
              end="", flush=True)
        try:
            answerer = make(spec, budget, cfg.refetch_mode == "agent")
            result = run_refetch(cfg, answerer, out_dir=out_dir)
        except KeyboardInterrupt:
            print("interrupted — this run wrote nothing")
            break
        except SpendRefused as exc:
            print(f"\nSTOPPED: {exc}")
            print(f"  this run wrote nothing; resume: python -m airsbench.runner.run "
                  f"--refetch-arm --offset {index} --max-cost X.XX")
            return 1
        except Exception as exc:  # noqa: BLE001 — transport: one run lost, not the campaign
            print(f"FAILED: {type(exc).__name__}: {exc}")
            failed.append((cfg, f"{type(exc).__name__}: {exc}"))
            continue
        m = result.metrics
        acc = "n/a" if m["accuracy"] is None else f"{m['accuracy']:.3f}"
        silent = "n/a" if m["silent_failure_rate"] is None else f"{m['silent_failure_rate']:.1%}"
        print(f"acc={acc} silent={silent} refetch={m['refetch_rate']:.1%} "
              f"asked={m['agent_requests']} unanswered={m['unanswered_actions']} "
              f"flipped={m['n_flipped_as_delivered']} ${result.usage['cost_usd']:.4f}")

    print(f"\nTotal spend: {_usd(budget.spent_usd)} | results in {out_dir}")
    if failed:
        print(f"\n{len(failed)} run(s) FAILED and wrote no artifact:")
        for cfg, reason in failed:
            print(f"  {cfg.label()} — {reason}")
        print("\nRe-run them once the cause is resolved; `python -m "
              "airsbench.analysis.campaign_state` lists what is missing.")
        return 1
    return 0
