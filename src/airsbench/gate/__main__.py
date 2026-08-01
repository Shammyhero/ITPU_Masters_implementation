"""`airs gate` — admit or refuse a batch of records against a declared policy.

The enforcement half of `airs probe`. The probe *reports* a pipeline's
readiness; the gate *acts* on it, returning a non-zero exit status when the
batch violates the contract so a scheduler or a pipeline step can stop before
an agent is ever asked.

    python -m airsbench.gate --records delivered.jsonl --source upstream.jsonl \\
        --policy examples/gate/retrieval.json
    python -m airsbench.gate --records delivered.jsonl --policy p.json --shadow

Exit status: 0 admitted, 1 refused, 2 bad input. The refusal names the rule and
the observed value, because a refusal an operator cannot act on is only a
slower failure.

`--shadow` runs the policy in warn-only mode: the batch is always admitted and
the violations are reported. Use it to price a candidate policy against live
traffic before it gates anything — `docs/gate_findings.md` shows why that
matters, since every worthwhile policy also forfeits correct answers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..probe import ProbeError, load_records, load_weights
from .controller import Controller
from .policy import Policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="airs gate", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--records", type=Path, required=True,
                        help="JSONL of records as the pipeline delivers them")
    parser.add_argument("--source", type=Path, default=None,
                        help="the same records upstream, matched on 'id' "
                             "(required to check a consistency floor)")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--task", default="retrieval",
                        help="which calibrated weight profile to apply")
    parser.add_argument("--shadow", action="store_true",
                        help="warn instead of refusing, and always exit 0")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        delivered = load_records(args.records)
        source = load_records(args.source) if args.source else None
        policy = Policy.load(args.policy)
        weights, _ = load_weights(
            Path(__file__).parents[1] / "airs" / "calibrated_weights.json", args.task
        )
    except (ProbeError, ValueError, OSError) as exc:
        print(f"error: {exc}")
        return 2

    if args.shadow:
        policy = policy.shadow()
    verdict = Controller(policy, weights).evaluate(delivered, source)

    if args.json:
        print(json.dumps(verdict.to_dict(), indent=2))
        return 0 if verdict.admitted else 1

    print(f"airs gate — {verdict.n_records} records, policy '{policy.name}', "
          f"task profile '{args.task}'")
    print(f"  {policy.describe()}\n")
    for dim, entry in verdict.dimensions.items():
        score = "UNMEASURED" if entry["score"] is None else f"{entry['score']:.1f}"
        print(f"  {dim:<14}{score:>11}   {entry['detail']}")
    if verdict.airs is not None:
        print(f"\n  AIRS {verdict.airs:.1f} over {verdict.weight_covered:.0%} "
              f"of the calibrated weight")

    print()
    if not verdict.violations:
        print("  ADMITTED — the batch satisfies every declared rule.")
        return 0
    for violation in verdict.violations:
        print(f"  ✗ {violation.rule}: {violation.detail}")
    if verdict.admitted:
        print("\n  ADMITTED (shadow mode) — these violations would have refused "
              "the batch\n  under enforcement. No agent call was blocked.")
        return 0
    print("\n  REFUSED — the agent was not asked. This is an operations problem "
          "with\n  an owner, which is what a silent failure is not.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
