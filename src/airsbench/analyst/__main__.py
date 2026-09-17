"""`airs analyst ask` — ask questions of a source, verify every answer, attribute the wrong ones.

    airs analyst ask demo-stale
    airs analyst ask demo-stale --answerer ollama/qwen2.5:14b-instruct --questions 3
    airs analyst ask demo-drift --json
    airs analyst --sources sources.yaml ask exports \\
        --plan '{"type": "count_where", "where": [{"field": "stock", "op": "==", "value": 0}]}'

The demo sources ask the corpus's own question — the cheapest product in stock —
about a bundled customer query. Any other source needs --plan (and optionally
--question for its wording). Answerers: `literal` (the plan over the delivered
records at face value, $0), a local model `ollama/<name>` ($0, records stay on this
machine), or a hosted one — `openai/<model>`, `anthropic/<model>`, `gemini/<model>`,
whose key comes from the environment and whose records are SENT TO THAT PROVIDER.

Every hosted call passes a spend cap first: `--max-cost` for the session,
`--max-cost-day` across today's sessions (kept in ~/.airs/spend.json). The cap is
checked before the request, with the projected cost of that request, so a refusal
costs nothing. `--estimate` prints the projection and calls nothing at all. A
hosted model with no declared price is refused outright, never treated as free.

Nothing is written: Ticks go to stdout. Exit status 0 when every question ran,
2 when a source, plan or answerer is unusable, 3 when a spend cap refused a call.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ..probe import ProbeError
from ..sources import SourceError
from .answerers import AnswererError, make_answerer
from .budget import DEFAULT_DAY_USD, DEFAULT_SESSION_USD, Budget, SpendRefused, usd
from .plan import Plan, PlanError
from .session import LIVE_SEED_BLOCK, Question, ask, demo_question

VERDICTS = {
    "correct": "✓ CORRECT",
    "answer_key_moved": "✗ SILENT FAILURE · ANSWER KEY MOVED — the pipeline served values that "
                        "have since changed, and the answer followed them",
    "both": "✗ SILENT FAILURE · BOTH — the answer key moved, and the answer did not follow the "
            "values served either",
    "corrupted_in_transit": "✗ SILENT FAILURE · CORRUPTED IN TRANSIT — fields this answer "
                            "needs were changed on the way",
    "agent_impairment": "✗ SILENT FAILURE · AGENT IMPAIRMENT — the records arrived intact "
                        "and support the right answer",
}


def summarise(ticks: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = [tick["decision"] for tick in ticks]
    labels = Counter(d.get("attribution") for d in decisions if d.get("attribution"))
    return {
        "questions": len(ticks),
        "verified": sum(bool(d.get("verifiable")) for d in decisions),
        "attribution": {label: labels.get(label, 0) for label in VERDICTS},
        "abstained": sum(bool(d["abstained"]) for d in decisions),
        "parse_failed": sum(bool(d["parse_failed"]) for d in decisions),
        "silent_failures": sum(bool(d.get("silent_failure")) for d in decisions),
        "usd": round(sum(tick["cost"]["usd"] for tick in ticks), 6),
        "hosted": any(tick["cost"].get("hosted") for tick in ticks),
    }


DIMENSION_LABELS = {"freshness": "fresh", "latency": "lat", "consistency": "cons",
                    "semantic": "sem"}


def _short(value: Any, width: int = 40) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    return text if len(text) <= width else text[: width - 1] + "…"


def _fields(payload: dict[str, Any] | None, names: list[str], width: int = 34) -> str:
    """Only the fields the question reads — the rest of a record is not evidence."""
    if payload is None:
        return "—"
    parts = [f"{name} {_short(payload[name], 14)}" if name in payload else f"{name} (absent)"
             for name in names]
    text = " · ".join(parts)
    return text if len(text) <= width else text[: width - 1] + "…"


def _print_tick(tick: dict[str, Any], index: int, total: int) -> None:
    source, question, decision = tick["source"], tick["question"], tick["decision"]
    lag = tick["records"]["lag_seconds"]
    header = f"[{index}/{total}] {source['pair']} · {tick['answerer']}"
    if lag is not None:
        header += f" · delivered {lag:g} s behind upstream"
    print(header)
    print(f"  Q: {question['text']}")
    print(f"  checked as: {question['describe']}")
    changed = {(c["id"], c["field"]): c["change"] for c in decision.get("changed_fields", [])}
    upstream = tick["records"]["upstream"] or {}
    served = tick["records"]["served"] or {}
    names = list(dict.fromkeys([question["plan"].get("measure")]
                               + [c["field"] for c in question["plan"].get("where", [])]))
    names = [name for name in names if name]
    moved = bool(decision.get("flipped"))
    middle = f"{'served (upstream then)':<36}" if moved else ""
    print(f"\n    {'id':<13}{'delivered (as received)':<36}{middle}upstream at answer time")
    for record_id, payload in zip(tick["records"]["ids"], tick["records"]["delivered"]):
        marks = [f"{f} {c}" for (i, f), c in changed.items() if i == record_id and f]
        then = f"{_fields(served.get(record_id), names):<36}" if moved else ""
        print(f"    {str(record_id):<13}{_fields(payload, names):<36}{then}"
              f"{_fields(upstream.get(record_id), names)}"
              f"{'   ← ' + '; '.join(marks) if marks else ''}")
    if decision["parse_failed"]:
        answered = "unparseable output"
    elif decision["abstained"]:
        answered = f"abstained ({decision['answer']})"
    else:
        answered = f"{_short(decision['value'], 30)} at confidence {decision['confidence']:.2f}"
    print(f"\n  answered: {answered}")
    if decision.get("verifiable"):
        truth = decision["answer_upstream"]["value"]
        print(f"  truth:    {_short(truth, 30)}"
              + (f"   (the served values implied {_short(decision['answer_served']['value'], 30)})"
                 if decision.get("flipped") else ""))
        if decision["attribution"]:
            print(f"  → {VERDICTS[decision['attribution']]}")
    else:
        print(f"  → not verified: {decision.get('reason')}")
    airs = tick["airs"]
    dims = " · ".join(
        f"{DIMENSION_LABELS.get(d, d)} {'—' if v['score'] is None else format(v['score'], '.1f')}"
        for d, v in airs["dimensions"].items())
    total_score = "no score" if airs["airs"] is None else f"{airs['airs']:.1f} {airs['band']}"
    print(f"  AIRS at this moment: {dims} → {total_score}")
    for note in tick["notes"]:
        print(f"  note: {note}")
    print()


def _summary_line(summary: dict[str, Any]) -> str:
    counts = " · ".join(f"{label} {count}" for label, count in summary["attribution"].items())
    # Hosted spend is often fractions of a cent; $0.00 would read as "free".
    usd = f"${summary['usd']:.4f}" if summary.get("hosted") else f"${summary['usd']:.2f}"
    return (f"{summary['questions']} questions, {summary['verified']} verified: {counts} · "
            f"abstained {summary['abstained']} · unparseable {summary['parse_failed']} · "
            f"silent failures {summary['silent_failures']} · {usd}")


def _estimate(answerer, budget, questions: int) -> int:
    """What this run would cost, without calling anything (plan A5)."""
    each = getattr(answerer, "estimate_usd", lambda: 0.0)()
    total = each * questions
    if not each:
        print(f"{answerer.name}: $0.00 — nothing is billed for this answerer, and the "
              f"records stay on this machine.")
        return 0
    remaining = budget.remaining()
    print(f"{answerer.name}: about {usd(each)} per question, {usd(total)} for "
          f"{questions} — an estimate from measured prompt sizes, not a quote.")
    print(f"  caps: {usd(budget.session_usd)} this session ({usd(remaining['session'])} "
          f"left), {usd(budget.day_usd)} today ({usd(remaining['day'])} left)")
    if total > remaining["session"] or total > remaining["day"]:
        print("  this run would be refused before the first call that crosses a cap")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="airs analyst", description=__doc__.splitlines()[0])
    parser.add_argument("--sources", type=Path, default=None,
                        help="a sources.yaml declaring your sources (demo pairs always available)")
    actions = parser.add_subparsers(dest="action", required=True)
    ask_parser = actions.add_parser("ask", help="ask, verify and attribute")
    ask_parser.add_argument("pair")
    ask_parser.add_argument("--answerer", default="literal",
                            help="literal, a local model as ollama/<name>, or a hosted one "
                                 "as openai/<model>, anthropic/<model>, gemini/<model>")
    ask_parser.add_argument("--max-cost", type=float, default=DEFAULT_SESSION_USD,
                            help=f"USD cap for this session (default {DEFAULT_SESSION_USD:.2f}); "
                                 f"checked before every hosted call")
    ask_parser.add_argument("--max-cost-day", type=float, default=DEFAULT_DAY_USD,
                            help=f"USD cap across today's sessions (default "
                                 f"{DEFAULT_DAY_USD:.2f}), kept in ~/.airs/spend.json")
    ask_parser.add_argument("--estimate", action="store_true",
                            help="print the projected cost and exit without calling anything")
    ask_parser.add_argument("--questions", type=int, default=5)
    ask_parser.add_argument("--seed", type=int, default=LIVE_SEED_BLOCK[0],
                            help="first sampling seed; question i uses seed + i")
    ask_parser.add_argument("--key", default=None, help="a query id on the demo source")
    ask_parser.add_argument("--plan", default=None, help="the question's plan, as JSON")
    ask_parser.add_argument("--question", default=None, help="the question's wording")
    ask_parser.add_argument("--n", type=int, default=6, help="records per question")
    ask_parser.add_argument("--task", default="retrieval", help="AIRS weight profile")
    ask_parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    ticks: list[dict[str, Any]] = []
    try:
        from ..sources.config import load_sources

        if args.questions < 1:
            raise PlanError("--questions must be at least 1")
        pairs = load_sources(args.sources)
        pair = pairs.get(args.pair)
        if pair is None:
            raise SourceError(f"no source {args.pair!r}; available: {', '.join(pairs)}")
        if args.plan is not None:
            try:
                plan = Plan.from_dict(json.loads(args.plan))
            except json.JSONDecodeError as exc:
                raise PlanError(f"--plan is not valid JSON — {exc}") from None
            question = Question(args.question or f"What is {plan.describe()}?", plan,
                                key=args.key, n=args.n)
        elif args.question is not None:
            raise PlanError("--question needs --plan: an answer is verified against the "
                            "question's plan, never the answerer's")
        elif pair.kind == "demo":
            question = demo_question(args.key)
        else:
            raise PlanError(f"{pair.id} has no built-in question; give --plan (and --question)")
        budget = Budget(session_usd=args.max_cost, day_usd=args.max_cost_day)
        answerer = make_answerer(args.answerer, budget=budget)
        if args.estimate:
            return _estimate(answerer, budget, args.questions)
        session_id = None
        for index in range(args.questions):
            tick = ask(pair, question, answerer, seed=args.seed + index, task=args.task,
                       session_id=session_id)
            session_id = tick["session_id"]
            ticks.append(tick)
            if not args.json:
                _print_tick(tick, index + 1, args.questions)
    except SpendRefused as exc:
        # Mid-run: the questions already answered are real and are reported.
        print(f"refused: {exc}", file=sys.stderr)
        if ticks:
            print(_summary_line(summarise(ticks)), file=sys.stderr)
        return 3
    except (SourceError, ProbeError, PlanError, AnswererError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    summary = summarise(ticks)
    if args.json:
        print(json.dumps({"session_id": session_id, "ticks": ticks, "summary": summary},
                         indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    print(_summary_line(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
