"""What has been run, what remains, and the exact command to resume — free.

Resuming used to be "count the JSON files and pass that as `--offset`". That
stopped being true the moment a second arm existed: the results directory now
holds main-factorial runs, detectability-arm runs, and later the freshness sweep
and cross-model subset, while `--offset` indexes into `build_grid()` alone.
Counting files over-reports the offset and would silently skip runs — or, if
files were ever removed, re-run and pay for conditions already on disk.

This resolves the offset by matching each grid entry against the artifacts by
seed, so it stays correct however many arms accumulate. It also checks the
assumptions `--offset` relies on: that completed runs form a contiguous prefix,
that nothing is duplicated, and that nothing on disk is unaccounted for.

    python -m airsbench.analysis.campaign_state
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..runner.config import (
    build_cross_model_subset,
    build_detectability_arm,
    build_freshness_sweep,
    build_grid,
    run_arm,
)


# Identity of a run, independent of run_id and of execution order.
def _key(config: dict[str, Any]) -> tuple:
    return (
        config["pipeline"], config["task"], config["fault_type"],
        config["severity"], config["replication"], config["seed"],
        bool(config.get("emit_record_age", False)),
    )


ARMS = {
    "main": ("--main --n-queries 80", lambda: build_grid(replications=4)),
    "detectability": ("--detectability --n-queries 80", build_detectability_arm),
    "freshness_sweep": ("--freshness-sweep --n-queries 60", build_freshness_sweep),
    "cross_model": (
        "--cross-model claude-haiku-4-5 --n-queries 100",
        lambda: build_cross_model_subset("claude-haiku-4-5"),
    ),
}


def load(results_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(results_dir.glob("*.json"))]


def report(runs: list[dict[str, Any]]) -> int:
    on_disk: dict[str, list[dict]] = {}
    for run in runs:
        on_disk.setdefault(run_arm(run), []).append(run)

    total_cost = sum(r["usage"]["cost_usd"] for r in runs)
    print(f"{len(runs)} run artifacts on disk · ${total_cost:.3f} spent\n")

    problems: list[str] = []
    for arm, (flags, builder) in ARMS.items():
        grid = builder()
        done_runs = on_disk.get(arm, [])
        counts: dict[tuple, int] = {}
        for run in done_runs:
            key = _key(run["config"])
            counts[key] = counts.get(key, 0) + 1

        keys = [_key(cfg.to_dict()) for cfg in grid]
        status = [key in counts for key in keys]
        done, remaining = sum(status), len(status) - sum(status)

        label = f"{arm} ({len(grid)} runs)"
        if not done_runs:
            print(f"  {label:<34} not started")
            continue

        print(f"  {label:<34} {done}/{len(grid)} done · "
              f"${sum(r['usage']['cost_usd'] for r in done_runs):.3f}")

        duplicates = {k: v for k, v in counts.items() if v > 1}
        orphans = [k for k in counts if k not in set(keys)]
        if duplicates:
            problems.append(f"{arm}: {len(duplicates)} condition(s) run more than once")
        if orphans:
            problems.append(f"{arm}: {len(orphans)} artifact(s) match no grid entry")

        if remaining:
            first_todo = status.index(False)
            contiguous = all(status[:first_todo]) and not any(status[first_todo:])
            if contiguous:
                print(f"       resume:  python -m airsbench.runner.run {flags} "
                      f"--offset {first_todo} --limit {remaining} --max-cost X.XX")
            else:
                gaps = [i for i, ok in enumerate(status) if not ok]
                problems.append(
                    f"{arm}: completed runs are not a contiguous prefix "
                    f"(missing indices {gaps[:8]}{'...' if len(gaps) > 8 else ''}) — "
                    f"--offset cannot express this; re-run the gaps individually"
                )
        else:
            print("       complete")

    unknown = on_disk.get("unknown", [])
    if unknown:
        problems.append(f"{len(unknown)} artifact(s) have seeds outside every arm block")

    print()
    if problems:
        print("PROBLEMS — do not resume until these are understood:")
        for problem in problems:
            print(f"  ! {problem}")
        return 1
    print("Consistent: no duplicates, no orphans, every arm resumable by --offset.")
    print("ALWAYS --dry-run the resume command before spending.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    args = parser.parse_args(argv)
    return report(load(args.results))


if __name__ == "__main__":
    raise SystemExit(main())
