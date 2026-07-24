"""Benchmark runner CLI.

Week 1: builds and inspects the experiment grid (--grid --dry-run).
Week 3 wires in the agent harness so each RunConfig executes end-to-end
and writes one row to benchmark_runs.

Usage:
    python -m airsbench.runner.run --grid --dry-run
    python -m airsbench.runner.run --grid --replications 4
"""

from __future__ import annotations

import argparse
from collections import Counter

from .config import build_grid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIRS benchmark runner")
    parser.add_argument("--grid", action="store_true", help="build the full factorial grid")
    parser.add_argument("--replications", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="print the grid, execute nothing")
    args = parser.parse_args(argv)

    if not args.grid:
        parser.print_help()
        return 0

    grid = build_grid(replications=args.replications)
    by_fault = Counter(cfg.fault_type for cfg in grid)
    print(f"Experiment grid: {len(grid)} runs "
          f"({args.replications} replications per condition)")
    for fault, count in sorted(by_fault.items()):
        print(f"  {fault:>20}: {count} runs")
    print("\nFirst 5 runs:")
    for cfg in grid[:5]:
        print(f"  {cfg.label():<50} seed={cfg.seed} params={cfg.injector_params}")

    if not args.dry_run:
        raise SystemExit(
            "Run execution requires the agent harness (Week 3). "
            "Use --dry-run to inspect the grid."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
