"""Would a confidence threshold change the silent-failure count?

Chapter 3 and RQs v2 originally defined silent failure as committed, wrong and
reported at confidence >= 0.7, and promised that the threshold's sensitivity
was "checked across 0.5/0.6/0.7/0.8/0.9 in the analysis notebook". No such check
existed. Meanwhile nine analysis modules computed silent failure with no
threshold at all, so the thesis carried two constructs under one name.

The definition is now threshold-free everywhere
(`runner/scoring.py::is_silent_failure`). This module is the check that was
promised: for every arm, model and task it reports the silent-failure rate
under the definition and under each threshold, so the choice is evidenced
rather than asserted.

A threshold can only REMOVE decisions from the count, never add them, so every
shift reported here is non-negative.

    python -m airsbench.analysis.silent_definition
    python -m airsbench.analysis.silent_definition --markdown
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from ..runner.config import NEVER_POOLED, run_arm
from ..runner.scoring import HIGH_CONFIDENCE, is_silent_failure

THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)
PRIMARY_MODEL = "gpt-4o-mini"
# Shifts at or above this many percentage points are flagged in the report.
FLAG_PP = 1.0


def rates(decisions: list[dict], thresholds: Iterable[float] = THRESHOLDS) -> dict[str, Any]:
    """Silent-failure rate under the definition and under each threshold."""
    thresholds = tuple(thresholds)
    n = len(decisions)
    if n == 0:
        return {"n": 0, "default": 0.0,
                "by_threshold": {t: 0.0 for t in thresholds}, "below_reference": 0.0}
    silent = [d for d in decisions if is_silent_failure(d)]
    below = sum(1 for d in silent if float(d.get("confidence") or 0.0) < HIGH_CONFIDENCE)
    return {
        "n": n,
        "default": len(silent) / n,
        "by_threshold": {t: sum(is_silent_failure(d, t) for d in decisions) / n
                         for t in thresholds},
        # Share of silent failures the retired 0.7 threshold would have dropped.
        "below_reference": below / len(silent) if silent else 0.0,
    }


def shift_pp(result: dict[str, Any], threshold: float = HIGH_CONFIDENCE) -> float:
    """Percentage points the rate falls if `threshold` is applied (always >= 0)."""
    return 100.0 * (result["default"] - result["by_threshold"][threshold])


def load_runs(results_dir: Path) -> list[dict[str, Any]]:
    """Every corpus arm. Not the refetch arm, nor live traffic: a different
    instrument would add a row to this robustness table that the corpus never had."""
    runs = (json.loads(p.read_text()) for p in sorted(results_dir.glob("*.json")))
    return [run for run in runs if run_arm(run) not in NEVER_POOLED]


def sensitivity(runs: list[dict[str, Any]]) -> list[tuple[tuple[str, str, str], dict[str, Any]]]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for run in runs:
        config = run["config"]
        groups[(run_arm(run), config["model"], config["task"])].extend(run["decisions"])
    return [(key, rates(decisions)) for key, decisions in sorted(groups.items())]


def verdict(rows: list[tuple[tuple[str, str, str], dict[str, Any]]]) -> dict[str, Any]:
    primary = [shift_pp(r) for (_, model, _), r in rows if model == PRIMARY_MODEL]
    others = [((arm, model, task), shift_pp(r)) for (arm, model, task), r in rows
              if model != PRIMARY_MODEL]
    worst = max(others, key=lambda item: item[1]) if others else None
    return {
        "primary_max_pp": max(primary) if primary else 0.0,
        "other_max_pp": worst[1] if worst else 0.0,
        "other_worst_group": worst[0] if worst else None,
    }


def report(rows) -> int:
    print("Silent-failure definition — would a confidence threshold change the count?\n")
    print("Definition: committed, parseable, wrong; no threshold. Each threshold")
    print("column applies `confidence >= t` on top. A threshold only removes")
    print("decisions, so every rate at or right of the definition is <= it.\n")
    header = (f"  {'arm':<16}{'model':<28}{'task':<15}{'n':>6}{'defn':>8}"
              + "".join(f"{'>=' + str(t):>8}" for t in THRESHOLDS)
              + f"{'<0.7 of silent':>16}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for (arm, model, task), r in rows:
        flag = "  <<" if shift_pp(r) >= FLAG_PP else ""
        print(f"  {arm:<16}{model[:27]:<28}{task:<15}{r['n']:>6}{r['default']:>8.1%}"
              + "".join(f"{r['by_threshold'][t]:>8.1%}" for t in THRESHOLDS)
              + f"{r['below_reference']:>16.1%}{flag}")

    v = verdict(rows)
    print(f"\n  {PRIMARY_MODEL}: the 0.7 threshold moves the rate by at most "
          f"{v['primary_max_pp']:.1f} pp in any arm.")
    if v["other_worst_group"]:
        arm, model, task = v["other_worst_group"]
        print(f"  Other models: at most {v['other_max_pp']:.1f} pp "
              f"({model}, {task}, {arm} arm).")
    print(f"  << marks groups where the 0.7 threshold would move the rate by "
          f">= {FLAG_PP:.0f} pp.")
    return 0


def markdown(rows) -> str:
    cols = ["arm", "model", "task", "n", "definition",
            *[f"≥ {t}" for t in THRESHOLDS], "silent failures < 0.7"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for (arm, model, task), r in rows:
        cells = [arm, model, task, f"{r['n']:,}", f"**{r['default']:.1%}**",
                 *[f"{r['by_threshold'][t]:.1%}" for t in THRESHOLDS],
                 f"{r['below_reference']:.1%}"]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--markdown", action="store_true",
                        help="print the table as Markdown for the findings doc")
    args = parser.parse_args(argv)
    rows = sensitivity(load_runs(args.results))
    if args.markdown:
        print(markdown(rows))
        return 0
    return report(rows)


if __name__ == "__main__":
    raise SystemExit(main())
