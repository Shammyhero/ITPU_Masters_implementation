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
    build_freshness_sweep,
    build_grid,
)

# Calibrated against observed token usage from smoke runs rather than
# estimated from the templates: the original estimates (1600/550/40) ran
# ~35% high, which made the spend guard refuse runs that would have fit.
# Re-derive these from `results/runs/*.json` usage fields if the prompts
# change materially.
AVG_INPUT_TOKENS = {"retrieval": 1150, "classification": 420}
AVG_OUTPUT_TOKENS = 30

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
    return sum(
        estimate_cost_usd(
            cfg.model, cfg.n_queries, AVG_INPUT_TOKENS[cfg.task], AVG_OUTPUT_TOKENS
        )
        for cfg in configs
    )


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
    print()
    for i, cfg in enumerate(configs, 1):
        print(f"[{i}/{len(configs)}] {cfg.label()} ... ", end="", flush=True)
        result = execute_run(cfg, data_root=Path(args.data_root), out_dir=Path(args.out))
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
    parser.add_argument("--replications", type=int, default=4)
    parser.add_argument("--n-queries", type=int, default=12, help="queries per smoke run")
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

    if args.grid:
        grid = build_grid(replications=args.replications)
        by_fault = Counter(cfg.fault_type for cfg in grid)
        print(f"Experiment grid: {len(grid)} runs "
              f"({args.replications} replications per condition)")
        for fault, count in sorted(by_fault.items()):
            print(f"  {fault:>20}: {count} runs")
        print(f"\nEstimated full-campaign cost at {grid[0].n_queries} queries/run: "
              f"${estimate_grid_cost(grid):.2f}")
        return 0

    if args.smoke:
        return execute_configs(build_smoke_grid(args.n_queries), args)

    if args.main:
        grid = build_grid(replications=args.replications)
        for cfg in grid:
            cfg.n_queries = args.n_queries
        return execute_configs(grid, args)

    if args.freshness_sweep:
        sweep = build_freshness_sweep(replications=args.replications)
        for cfg in sweep:
            cfg.n_queries = args.n_queries
        return execute_configs(sweep, args)

    if args.cross_model:
        subset = build_cross_model_subset(args.cross_model)
        for cfg in subset:
            cfg.n_queries = args.n_queries
        return execute_configs(subset, args)

    pilot = [cfg for cfg in build_grid(replications=1)][:30]
    for cfg in pilot:
        cfg.n_queries = args.n_queries
    return execute_configs(pilot, args)


if __name__ == "__main__":
    raise SystemExit(main())
