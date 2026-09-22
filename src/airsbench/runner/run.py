"""Benchmark runner CLI.

    python -m airsbench.runner.run --grid --dry-run       # inspect the design
    python -m airsbench.runner.run --smoke                # tiny paid test run
    python -m airsbench.runner.run --pilot                # 30-run go/no-go pilot

Every mode that spends money estimates the cost first and refuses to
exceed --max-cost without an explicit override.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from ..agents.llm import estimate_cost_usd
from .config import (
    RunConfig,
    build_cross_model_subset,
    build_detectability_arm,
    build_freshness_sweep,
    build_grid,
    build_interaction_arm,
)

# Token profiles per model family, calibrated against measured usage in
# results/runs/*.json. Re-derive after any material prompt change.
#
# There are TWO figures per task because output length varies far more by model
# than input length does, and output is priced 5x input on Claude. A single
# global output figure (30 tokens, measured on gpt-4o-mini) under-estimated the
# Haiku arm by 1.8x and tripped the spend guard 12 runs in: Haiku emits 102
# output tokens per retrieval call and 192 per classification call, not 30.
# Input was close (1.09x / 1.34x); output was 3.4x / 6.4x off.
TOKEN_PROFILES: dict[str, dict[str, tuple[int, int]]] = {
    # (avg input tokens, avg output tokens) per call
    "default": {"retrieval": (1150, 30), "classification": (420, 30)},
    "claude": {"retrieval": (1250, 105), "classification": (565, 195)},
}

# Kept for callers that only need the input figure (and for the tests that
# pinned the original calibration).
AVG_INPUT_TOKENS = {
    task: tokens[0] for task, tokens in TOKEN_PROFILES["default"].items()
}
AVG_OUTPUT_TOKENS = 30


def token_profile(model: str) -> dict[str, tuple[int, int]]:
    """Per-call token estimates for this model's family."""
    from ..agents.llm import is_anthropic_model

    return TOKEN_PROFILES["claude" if is_anthropic_model(model) else "default"]


SMOKE_CONDITIONS = [
    # (task, fault_type, severity) — baseline vs. the two faults the
    # working hypothesis is about, on both tasks.
    ("classification", "none", "none"),
    ("classification", "semantic_stripping", "severe"),
    ("classification", "freshness", "severe"),
    ("retrieval", "none", "none"),
    ("retrieval", "semantic_stripping", "severe"),
    ("retrieval", "freshness", "severe"),
]


def build_smoke_grid(n_queries: int) -> list[RunConfig]:
    from .config import SEVERITY_PARAMS

    configs = []
    for i, (task, fault, severity) in enumerate(SMOKE_CONDITIONS):
        params = {} if fault == "none" else SEVERITY_PARAMS[fault][severity]
        configs.append(
            RunConfig(
                pipeline="streaming",
                task=task,
                fault_type=fault,
                severity=severity,
                replication=1,
                injector_params=dict(params),
                n_queries=n_queries,
                seed=9000 + i,
            )
        )
    return configs


def estimate_grid_cost(configs: list[RunConfig]) -> float:
    total = 0.0
    for cfg in configs:
        avg_in, avg_out = token_profile(cfg.model)[cfg.task]
        total += estimate_cost_usd(cfg.model, cfg.n_queries, avg_in, avg_out)
    return total


def execute_configs(configs: list[RunConfig], args) -> int:
    from .execute import execute_run

    total_in_grid = len(configs)
    offset = getattr(args, "offset", 0) or 0
    limit = getattr(args, "limit", None)
    configs = configs[offset:]
    if limit is not None:
        configs = configs[:limit]
    if not configs:
        print(f"No runs selected (grid has {total_in_grid}, offset={offset}).")
        return 1
    if offset or limit is not None:
        print(f"Staged: runs {offset + 1}-{offset + len(configs)} of {total_in_grid}")

    estimated = estimate_grid_cost(configs)
    print(f"{len(configs)} runs x {configs[0].n_queries} queries "
          f"= {sum(c.n_queries for c in configs)} agent calls")
    print(f"Estimated cost: ${estimated:.3f} (guard: ${args.max_cost:.2f})")
    if estimated > args.max_cost:
        print(f"\nREFUSED: estimate exceeds --max-cost ${args.max_cost:.2f}. "
              f"Raise it deliberately if this is intended.")
        return 1
    if args.dry_run:
        print("(dry run — nothing executed)")
        return 0

    spent = 0.0
    failed: list[tuple[RunConfig, str]] = []
    print()
    for i, cfg in enumerate(configs, 1):
        print(f"[{i}/{len(configs)}] {cfg.label()} ... ", end="", flush=True)
        try:
            result = execute_run(
                cfg, data_root=Path(args.data_root), out_dir=Path(args.out)
            )
        except KeyboardInterrupt:
            print("interrupted")
            break
        except Exception as exc:  # noqa: BLE001 — one bad run must not end the campaign
            # A long campaign will meet transient failures (network drops, the
            # machine sleeping, rate limits that outlast the client's retries).
            # Crashing would forfeit every remaining run; completed runs are
            # already durable on disk, so record and continue. Failures are
            # listed at the end for targeted re-running.
            print(f"FAILED: {type(exc).__name__}: {exc}")
            failed.append((cfg, f"{type(exc).__name__}: {exc}"))
            continue
        spent += result.usage["cost_usd"]
        auc = result.metrics["auc_roc"]
        auc_text = f"{auc:.3f}" if auc is not None else "n/a"
        print(
            f"acc={result.metrics['accuracy']:.3f} "
            f"f1={result.metrics['f1']:.3f} "
            f"auc={auc_text}"
        )
        print(
            f"      AIRS={result.airs['total']:.1f} "
            f"(fresh={result.airs['freshness']:.0f} lat={result.airs['latency']:.0f} "
            f"cons={result.airs['consistency']:.0f} sem={result.airs['semantic']:.0f}) "
            f"n={result.metrics['n']} failures={result.metrics['parse_failures']} "
            f"${result.usage['cost_usd']:.4f}"
        )
        print(
            f"      abstained={result.metrics['abstention_rate']:.0%} "
            f"silent_failure={result.metrics['silent_failure_rate']:.0%}"
        )
        if spent > args.max_cost:
            print(f"\nSTOPPED: spend ${spent:.3f} exceeded guard ${args.max_cost:.2f}")
            return 1

    print(f"\nTotal spend: ${spent:.4f} | results in {args.out}")
    if failed:
        print(f"\n{len(failed)} run(s) FAILED and produced no artifact:")
        for cfg, reason in failed:
            print(f"  {cfg.label()} — {reason}")
        print("\nRe-run them once the cause is resolved. Completed runs are "
              "already on disk; recount and resume with --offset:")
        print(f"  ls {args.out}/*.json | wc -l")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIRS benchmark runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--grid", action="store_true", help="inspect the full factorial grid")
    mode.add_argument("--smoke", action="store_true", help="tiny paid end-to-end test")
    mode.add_argument("--main", action="store_true",
                      help="execute the main factorial (use --offset/--limit to stage it)")
    mode.add_argument("--pilot", action="store_true", help="30-run go/no-go pilot")
    mode.add_argument("--freshness-sweep", action="store_true",
                      help="multi-severity freshness sweep (RQ1 monotonicity test)")
    mode.add_argument("--cross-model", metavar="MODEL",
                      help="reduced factorial on a second model (generalization arm)")
    mode.add_argument("--detectability", action="store_true",
                      help="14-run arm: freshness severe, with and without record age")
    mode.add_argument("--refetch-arm", action="store_true",
                      help="21-run refetch arm (docs/refetch_arm.md): offered a re-read, "
                           "does the agent use it, and what does each verdict cost?")
    mode.add_argument("--interaction", action="store_true",
                      help="54-run arm (PROVISIONAL): do two faults compose "
                           "additively? baseline + solos + pairs, self-contained")
    # No global default: each mode's own replication count is part of its
    # design (main 4, sweep 3, detectability 3), so an unset flag must mean
    # "use this arm's design", not "use 4".
    parser.add_argument("--replications", type=int, default=None)
    # No global default: the refetch arm's design is 150 questions per run, every
    # other mode keeps the 12 it always had when the flag is omitted.
    parser.add_argument("--n-queries", type=int, default=None,
                        help="queries per run (default 12; the refetch arm: 150)")
    parser.add_argument("--max-cost", type=float, default=0.50, help="USD spend guard")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--out", default="results/runs")
    parser.add_argument("--dry-run", action="store_true")
    # Staged execution: phase 1 of the campaign is its own go/no-go checkpoint
    # (methodology §3.7.1), so it must be a prefix of the same seeded grid
    # rather than a separate pilot with different conditions.
    parser.add_argument("--offset", type=int, default=0,
                        help="skip the first N runs of the selected grid")
    parser.add_argument("--limit", type=int, default=None,
                        help="execute at most N runs (staged campaign phases)")
    args = parser.parse_args(argv)

    reps = args.replications

    if args.refetch_arm:
        from .config import REFETCH_N_QUERIES, build_refetch_arm
        from .refetch import execute_refetch_arm

        arm = build_refetch_arm(replications=reps or 3,
                                n_queries=args.n_queries or REFETCH_N_QUERIES)
        return execute_refetch_arm(arm, args)

    if args.n_queries is None:
        args.n_queries = 12

    if args.grid:
        grid = build_grid(replications=reps or 4)
        by_fault = Counter(cfg.fault_type for cfg in grid)
        print(f"Experiment grid: {len(grid)} runs "
              f"({reps or 4} replications per condition)")
        for fault, count in sorted(by_fault.items()):
            print(f"  {fault:>20}: {count} runs")
        print(f"\nEstimated full-campaign cost at {grid[0].n_queries} queries/run: "
              f"${estimate_grid_cost(grid):.2f}")
        return 0

    if args.smoke:
        return execute_configs(build_smoke_grid(args.n_queries), args)

    if args.main:
        grid = build_grid(replications=reps or 4)
        for cfg in grid:
            cfg.n_queries = args.n_queries
        return execute_configs(grid, args)

    if args.freshness_sweep:
        sweep = build_freshness_sweep(replications=reps or 3)
        for cfg in sweep:
            cfg.n_queries = args.n_queries
        return execute_configs(sweep, args)

    if args.interaction:
        arm = build_interaction_arm(replications=reps or 3)
        for cfg in arm:
            cfg.n_queries = args.n_queries
        return execute_configs(arm, args)

    if args.detectability:
        arm = build_detectability_arm(replications=reps or 3)
        for cfg in arm:
            cfg.n_queries = args.n_queries
        return execute_configs(arm, args)

    if args.cross_model:
        subset = build_cross_model_subset(args.cross_model, replications=reps or 2)
        for cfg in subset:
            cfg.n_queries = args.n_queries
        return execute_configs(subset, args)

    pilot = [cfg for cfg in build_grid(replications=1)][:30]
    for cfg in pilot:
        cfg.n_queries = args.n_queries
    return execute_configs(pilot, args)


if __name__ == "__main__":
    raise SystemExit(main())
