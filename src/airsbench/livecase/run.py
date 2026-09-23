"""Ask the case study's questions over a recording (plan A11).

    python -m airsbench.livecase.run --dry-run                 # exact token count, $0
    python -m airsbench.livecase.run --max-cost 0.40 [--offset N --limit M]

The grid is `runner.config.build_livecase`: {gpt-4o-mini, claude-haiku-4-5} x
{cache 5 min, cache 15 min}, the same questions in every cell. Each question goes
through the Analyst's own loop — admit everything (`mode="off"`, an open policy):
the case study measures what a real pipeline's lag does to answers and whether
AIRS saw it coming, not a gate.

Spend follows the refetch arm's rules (`runner/refetch.py`): the dry-run runs the
real loop over every question with a $0 counting answerer and counts the exact
prompts; the estimate must fit `--max-cost` before anything starts, each run's
must fit what is left before it starts, and every call passes an analyst
`Budget`. Anthropic's tokenizer is not tiktoken's, so Claude's count is inflated
by `CLAUDE_TOKEN_FACTOR` and its output budgeted higher — the cap is checked
against that, and the artifact records what was actually billed.
"""

from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..analyst.answerers import Answerer, AnswererError, make_answerer
from ..analyst.budget import Budget, SpendRefused, cost_of
from ..analyst.loop import Loop
from ..gate.policy import Policy
from ..runner.config import LIVECASE_SEED_RANGE, RunConfig, build_livecase
from ..runner.execute import RunResult
from ..runner.refetch import (
    ArmLedger,
    TokenCounter,
    airs_summary,
    answerer_spec,
    decision,
    metrics,
    question_seed,
)
from .questions import question, question_type
from .replay import DEFAULT_DB as _DB
from .replay import Recording, recording_path

PROVENANCE = {"arm": "livecase", "seed_block": list(LIVECASE_SEED_RANGE)}
DEFAULT_DB = _DB
OUTPUT_TOKENS = {"default": 150, "claude": 200}
CLAUDE_TOKEN_FACTOR = 1.15


def cache_minutes(config: RunConfig) -> int:
    return int(config.pipeline.removeprefix("velib-cache-").removesuffix("min"))


def is_claude(model: str) -> bool:
    return model.startswith("claude")


def run_livecase(config: RunConfig, recording: Recording, answerer: Answerer,
                 out_dir: Path | None = Path("results/runs")) -> RunResult:
    """One (model, cache): `n_queries` questions over the recording; saved when complete."""
    started = datetime.now(timezone.utc)
    loop = Loop(pair=recording.pair(cache_minutes(config)), policy=Policy(name="open"),
                answerer=answerer, mode="off", task="retrieval", provenance=PROVENANCE)
    decisions = []
    for index in range(config.n_queries):
        tick = loop.ask(question(index), seed=question_seed(config, index))
        row = decision(tick, tick["decision"].get("flipped"))
        row["question_type"] = question_type(index)
        row["question"] = tick["question"]["text"]
        moment = tick["records"]["simulated_time"]
        # The pipeline's lag: time since ITS copy — not the consistency reference.
        row["cache_age_seconds"] = moment - recording.snapshot_at(cache_minutes(config),
                                                                  moment)
        decisions.append(row)
    result = RunResult(
        run_id=config.run_id or str(uuid.uuid4()),
        config=config.to_dict(),
        started_at=started.isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        metrics=metrics(decisions),
        airs=airs_summary(decisions),
        usage={
            "calls": sum(d["usage"]["input_tokens"] > 0 for d in decisions),
            "input_tokens": sum(d["usage"]["input_tokens"] for d in decisions),
            "output_tokens": sum(d["usage"]["output_tokens"] for d in decisions),
            "cost_usd": round(sum(d["usage"]["usd"] for d in decisions), 6),
        },
        decisions=decisions,
    )
    if out_dir is not None:
        result.save(out_dir)
    return result


def estimate_usd(config: RunConfig, recording: Recording) -> tuple[float, int]:
    """The run's cost from the exact prompts the loop would send; and their tokens."""
    counter = TokenCounter(config.model, offer_refetch=False)
    run_livecase(config, recording, counter, out_dir=None)
    tokens = sum(counter.first)
    output = OUTPUT_TOKENS["claude" if is_claude(config.model) else "default"]
    if is_claude(config.model):
        tokens = int(tokens * CLAUDE_TOKEN_FACTOR)
    return cost_of(config.model, tokens, output * len(counter.first)), tokens


def execute(configs: list[RunConfig], recording: Recording, args,
            make: Callable[[str, Budget], Answerer] | None = None) -> int:
    make = make or (lambda spec, budget: make_answerer(spec, budget=budget))
    total, offset = len(configs), getattr(args, "offset", 0) or 0
    selected = configs[offset:]
    if getattr(args, "limit", None) is not None:
        selected = selected[:args.limit]
    if not selected:
        print(f"No runs selected (the study has {total}, offset={offset}).")
        return 1
    print(f"Recording: {recording.db.name}, {(recording.end - recording.start) / 60:.0f} min "
          f"of questions window; caches {recording.caches}")
    print("Counting every prompt the grid would send (exact, $0) ...", flush=True)
    estimates = [estimate_usd(cfg, recording) for cfg in selected]
    for cfg, (usd, tokens) in zip(selected, estimates):
        print(f"  {cfg.model:<20} cache {cache_minutes(cfg):>2} min  {cfg.n_queries:>4} "
              f"questions  {tokens:>9,} input tokens  ${usd:.4f}")
    worst = sum(usd for usd, _ in estimates)
    print(f"Estimated cost: ${worst:.4f} (Claude counted at x{CLAUDE_TOKEN_FACTOR} and "
          f"{OUTPUT_TOKENS['claude']} output tokens a call); guard ${args.max_cost:.2f}")
    if worst > args.max_cost:
        print(f"\nREFUSED: the estimate exceeds --max-cost ${args.max_cost:.2f}.")
        return 1
    if args.dry_run:
        print("(dry run — nothing executed, nothing spent)")
        return 0

    budget = Budget(session_usd=args.max_cost, day_usd=args.max_cost, ledger=ArmLedger())
    try:  # a missing key fails here, before anything is spent
        for model in dict.fromkeys(cfg.model for cfg in selected):
            make(answerer_spec(model), budget)
    except AnswererError as exc:
        print(f"\nCannot start: {exc}")
        return 1

    failed = []
    for position, (cfg, (usd, _)) in enumerate(zip(selected, estimates)):
        index = offset + position
        left = args.max_cost - budget.spent_usd
        if usd > left:
            print(f"\nSTOPPED before run {index + 1}: its estimate ${usd:.4f} exceeds the "
                  f"${left:.4f} left. Resume: python -m airsbench.livecase.run --offset "
                  f"{index} --max-cost X.XX")
            return 1
        print(f"[{index + 1}/{total}] {cfg.model} · cache {cache_minutes(cfg)} min ... ",
              end="", flush=True)
        try:
            result = run_livecase(cfg, recording, make(answerer_spec(cfg.model), budget),
                                  out_dir=Path(args.out))
        except KeyboardInterrupt:
            print("interrupted — this run wrote nothing")
            break
        except SpendRefused as exc:
            print(f"\nSTOPPED: {exc}\n  this run wrote nothing; resume with --offset {index}")
            return 1
        except Exception as exc:  # noqa: BLE001 — transport: one run lost, not the study
            print(f"FAILED: {type(exc).__name__}: {exc}")
            failed.append(cfg)
            continue
        m = result.metrics
        acc = "n/a" if m["accuracy"] is None else f"{m['accuracy']:.3f}"
        silent = "n/a" if m["silent_failure_rate"] is None else f"{m['silent_failure_rate']:.1%}"
        print(f"acc={acc} silent={silent} flipped={m['n_flipped_as_delivered']} "
              f"${result.usage['cost_usd']:.4f}")
    print(f"\nTotal spend: ${budget.spent_usd:.4f} | results in {args.out}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--n-queries", type=int, default=None)
    parser.add_argument("--max-cost", type=float, default=0.40)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default="results/runs")
    args = parser.parse_args(argv)
    grid = build_livecase(**({} if args.n_queries is None else {"n_queries": args.n_queries}))
    return execute(grid, Recording(recording_path(args.db)), args)



if __name__ == "__main__":
    raise SystemExit(main())
