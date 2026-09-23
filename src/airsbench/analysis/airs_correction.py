"""Corrected AIRS scores for runs recorded before the freshness fix.

Runs executed before commit `acb3761` carry an AIRS freshness dimension
computed from a double-counted age: `execute` stamped the record with the total
value staleness, and `FreshnessInjector` then shifted `event_timestamp` back by
the injected delay a second time. Twelve of the first 66 runs — the freshness
conditions — are affected.

Nothing behavioural is affected. Records carry no timestamp unless the
detectability arm attaches one, so no agent in an affected run was ever shown an
age, and the loader served values stale by the intended amount throughout.
Accuracy, abstention, silent failure, confidence, every logged decision and the
whole flip partition stand as recorded.

Correcting it by re-running would discard behaviourally valid data and give the
replacements different fault realisations from their existing pairs. Since the
true age is a deterministic function of the run configuration, the correction
belongs here instead: run artifacts stay immutable records of what the
instrument actually emitted, and any analysis that consumes an AIRS dimension
calls `corrected_airs` rather than reading `run["airs"]` directly.

The fix is idempotent — a run recorded after the fix already agrees with the
recomputed value and passes through unchanged — so this stays correct as the
campaign completes and eventually becomes a no-op.

    python -m airsbench.analysis.airs_correction
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..airs import AIRSCalculator, freshness_score
from ..runner.config import NEVER_POOLED, RunConfig, run_arm
from ..runner.execute import value_staleness_s

# Below this the recorded score already matches the recomputed one and the run
# needs no correction.
TOLERANCE = 0.05


def _config_of(run: dict[str, Any]) -> RunConfig:
    return RunConfig(
        **{k: v for k, v in run["config"].items() if k in RunConfig.__dataclass_fields__}
    )


def true_freshness_score(run: dict[str, Any]) -> float:
    """AIRS freshness implied by the staleness the run's values actually had."""
    return freshness_score(value_staleness_s(_config_of(run)))


def corrected_airs(
    run: dict[str, Any], calculator: AIRSCalculator | None = None
) -> dict[str, float]:
    """This run's AIRS dimensions with freshness recomputed, composite refreshed.

    Only the freshness dimension can be wrong: latency, consistency and semantic
    completeness are measured from the delivered records themselves and were
    never touched by the double-count.
    """
    airs = dict(run["airs"])
    airs["freshness"] = true_freshness_score(run)
    calculator = calculator or AIRSCalculator()
    airs["total"] = calculator.composite({k: v for k, v in airs.items() if k != "total"})
    return airs


def needs_correction(run: dict[str, Any]) -> bool:
    """True if what the run *recorded* disagrees with the recomputed value.

    Never for an arm outside the corpus (`NEVER_POOLED`): the recomputation derives
    freshness from the corpus's simulated pipelines, which the live case study's
    real feed and the Analyst-driven arms do not have.

    Reads `airs_recorded` when present, so this answers the same question
    whether it is handed a raw artifact or one already passed through
    `load_corrected` — otherwise a corrected run would be compared against
    itself and always look clean.
    """
    if run_arm(run) in NEVER_POOLED:
        return False
    recorded = run.get("airs_recorded", run["airs"])
    return abs(recorded["freshness"] - true_freshness_score(run)) > TOLERANCE


def load_corrected(results_dir: Path) -> list[dict[str, Any]]:
    """Every CORPUS run, with `airs` corrected and `airs_recorded` kept for audit.

    The double-count this corrects was the corpus runner's; arms outside the corpus
    (`NEVER_POOLED`) never had it and are left out.
    """
    runs = []
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        if run_arm(run) in NEVER_POOLED:
            continue
        run["airs_recorded"] = dict(run["airs"])
        run["airs"] = corrected_airs(run)
        runs.append(run)
    return runs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    args = parser.parse_args(argv)

    runs = load_corrected(args.results)
    affected = [r for r in runs if needs_correction(r)]
    print(f"{len(runs)} runs on disk · {len(affected)} need the freshness correction\n")
    if not affected:
        print("No correction needed — every run agrees with the recomputed value.")
        return 0

    print(f"     {'condition':<40}{'recorded':>10}{'corrected':>11}{'AIRS tot':>10}")
    print("     " + "-" * 71)
    seen: set[tuple] = set()
    for run in affected:
        cfg = run["config"]
        key = (cfg["pipeline"], cfg["fault_type"], cfg["severity"])
        if key in seen:
            continue
        seen.add(key)
        label = f"{cfg['pipeline']}/{cfg['fault_type']}/{cfg['severity']}"
        print(f"     {label:<40}{run['airs_recorded']['freshness']:>10.2f}"
              f"{run['airs']['freshness']:>11.2f}"
              f"{run['airs_recorded']['total']:>7.1f}->{run['airs']['total']:.1f}")
    print()
    print("Artifacts are left unmodified. Analyses must read AIRS via")
    print("`load_corrected` / `corrected_airs`, never `run['airs']` off disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
