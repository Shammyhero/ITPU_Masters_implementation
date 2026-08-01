"""What would the gate have prevented? Replay the campaign and find out.

The thesis recommends enforcing a data contract outside the model. That is a
claim about consequences, so it is testable — and until now untested. Every
logged decision in the campaign carries the AIRS vector of the pipeline that
produced it, so a policy can be replayed over the whole corpus offline: refuse
the batches it would have refused, and count what changes.

The accounting is deliberately two-sided, because a gate is not free:

  prevented   silent failures that never reach a user, because the batch the
              agent would have answered from was refused first
  forfeited   correct answers lost with them — a refused batch takes the good
              decisions along with the bad
  residual    silent-failure rate among what still got through. The number an
              operator actually lives with.

A gate that refuses everything scores perfectly on `prevented` and is useless.
Reporting coverage beside it is what keeps the result honest.

    python -m airsbench.gate.replay
    python -m airsbench.gate.replay --sweep age --task retrieval
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..analysis.airs_correction import corrected_airs
from ..runner.config import RunConfig, run_arm
from ..runner.execute import value_staleness_s
from .controller import Verdict
from .policy import DIMENSIONS, Policy, Violation

CALIBRATED = Path(__file__).parents[1] / "airs" / "calibrated_weights.json"


@dataclass
class Batch:
    """One run, reduced to what the gate and the accounting need."""

    run_id: str
    task: str
    model: str
    fault: str
    severity: str
    dims: dict[str, float]
    record_age_seconds: float
    n: int
    correct: int
    silent: int
    abstained: int


def load_batches(
    results_dir: Path, arms: Iterable[str] = ("main", "freshness_sweep")
) -> list[Batch]:
    arms = set(arms)
    batches: list[Batch] = []
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        if run_arm(run) not in arms:
            continue
        cfg = run["config"]
        config = RunConfig(
            **{k: v for k, v in cfg.items() if k in RunConfig.__dataclass_fields__}
        )
        airs = corrected_airs(run)
        decisions = run["decisions"]
        batches.append(Batch(
            run_id=run["run_id"],
            task=cfg["task"],
            model=cfg["model"],
            fault=cfg["fault_type"],
            severity=cfg["severity"],
            dims={d: float(airs[d]) for d in DIMENSIONS},
            record_age_seconds=value_staleness_s(config),
            n=len(decisions),
            correct=sum(bool(d["correct"]) for d in decisions),
            silent=sum(
                bool(not d["correct"] and not d["abstained"] and not d["parse_failed"])
                for d in decisions
            ),
            abstained=sum(bool(d["abstained"]) for d in decisions),
        ))
    return batches


def evaluate_batch(batch: Batch, policy: Policy, weights: dict[str, float]) -> Verdict:
    """Apply a policy to an already-measured batch.

    The controller measures raw records; here the dimensions are already known
    from the run artifact, so the rules are applied directly. The rule semantics
    are the same, and a test pins that the two agree.
    """
    airs = sum(weights.get(d, 0.0) * batch.dims[d] for d in DIMENSIONS)
    violations: list[Violation] = []

    if policy.max_record_age_seconds is not None:
        if batch.record_age_seconds > policy.max_record_age_seconds:
            violations.append(Violation(
                "max_record_age_seconds", batch.record_age_seconds,
                policy.max_record_age_seconds,
                f"records are {batch.record_age_seconds:.2f}s old, budget is "
                f"{policy.max_record_age_seconds:.2f}s",
            ))
    for dim, floor in sorted(policy.min_dimension.items()):
        if batch.dims[dim] < floor:
            violations.append(Violation(
                f"min_dimension.{dim}", batch.dims[dim], floor,
                f"{dim} is {batch.dims[dim]:.1f}, floor is {floor:.0f}",
            ))
    if policy.min_airs is not None and airs < policy.min_airs:
        violations.append(Violation(
            "min_airs", airs, policy.min_airs,
            f"AIRS is {airs:.1f}, floor is {policy.min_airs:.0f}",
        ))

    shadowed = bool(violations) and policy.on_violation == "warn"
    return Verdict(
        admitted=not violations or shadowed,
        policy=policy.name,
        violations=violations,
        airs=airs,
        weight_covered=1.0,
        record_age_seconds=batch.record_age_seconds,
        n_records=batch.n,
        shadowed=shadowed,
    )


@dataclass
class Outcome:
    """The two-sided accounting for one policy over one corpus."""

    policy: str
    batches: int
    refused_batches: int
    decisions: int
    admitted_decisions: int
    silent_total: int
    silent_admitted: int
    correct_total: int
    correct_admitted: int

    @property
    def coverage(self) -> float:
        return self.admitted_decisions / self.decisions if self.decisions else 0.0

    @property
    def prevented(self) -> int:
        return self.silent_total - self.silent_admitted

    @property
    def prevented_share(self) -> float:
        return self.prevented / self.silent_total if self.silent_total else 0.0

    @property
    def forfeited(self) -> int:
        return self.correct_total - self.correct_admitted

    @property
    def forfeited_share(self) -> float:
        return self.forfeited / self.correct_total if self.correct_total else 0.0

    @property
    def baseline_silent_rate(self) -> float:
        return self.silent_total / self.decisions if self.decisions else 0.0

    @property
    def residual_silent_rate(self) -> float:
        return (
            self.silent_admitted / self.admitted_decisions
            if self.admitted_decisions else 0.0
        )

    @property
    def exchange_rate(self) -> float:
        """Correct answers forfeited per silent failure prevented.

        The number that decides whether a policy is worth running. Below 1.0
        the gate removes more bad answers than good ones.
        """
        return self.forfeited / self.prevented if self.prevented else float("inf")


def replay(batches: list[Batch], policy: Policy, weights: dict[str, float]) -> Outcome:
    admitted = [b for b in batches if evaluate_batch(b, policy, weights).admitted]
    return Outcome(
        policy=policy.name,
        batches=len(batches),
        refused_batches=len(batches) - len(admitted),
        decisions=sum(b.n for b in batches),
        admitted_decisions=sum(b.n for b in admitted),
        silent_total=sum(b.silent for b in batches),
        silent_admitted=sum(b.silent for b in admitted),
        correct_total=sum(b.correct for b in batches),
        correct_admitted=sum(b.correct for b in admitted),
    )


# ---- reporting -------------------------------------------------------------

def load_weights(task: str, path: Path = CALIBRATED) -> dict[str, float]:
    profiles = json.loads(path.read_text())["profiles"]
    if task not in profiles:
        raise SystemExit(
            f"no calibrated weight profile for task {task!r}; the weights invert "
            f"across tasks so another task's profile must not be substituted"
        )
    return profiles[task]


def age_sweep(task: str) -> list[Policy]:
    """Staleness budgets spanning the measured range, plus 'no gate'."""
    return [Policy(name="no gate")] + [
        Policy(name=f"age <= {b}s", max_record_age_seconds=b)
        for b in (0.1, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0)
    ]


def airs_sweep(task: str) -> list[Policy]:
    return [Policy(name="no gate")] + [
        Policy(name=f"AIRS >= {f:.0f}", min_airs=float(f))
        for f in (50, 70, 80, 85, 90, 95, 99)
    ]


def dimension_sweep(task: str) -> list[Policy]:
    """One floor per dimension, at the level that separates severe from mild."""
    return [Policy(name="no gate")] + [
        Policy(name="semantic >= 50", min_dimension={"semantic": 50.0}),
        Policy(name="consistency >= 90", min_dimension={"consistency": 90.0}),
        Policy(name="freshness >= 50", min_dimension={"freshness": 50.0}),
        Policy(name="semantic>=50 + consistency>=90",
               min_dimension={"semantic": 50.0, "consistency": 90.0}),
    ]


SWEEPS = {"age": age_sweep, "airs": airs_sweep, "dimension": dimension_sweep}


def attribution(batches: list[Batch], task: str) -> int:
    """Per-fault gate economics, charging the gate only for what it can claim.

    The sweep tables credit a policy with every silent failure inside a refused
    batch. That over-credits it: most of those decisions would have failed on a
    healthy pipeline too. Here the credit is only the EXCESS over the fault-free
    rate — the silent failure the fault actually caused — which is the quantity
    a gate can genuinely be said to prevent.

    The resulting ranking is a direct operational test of the RQ4 weights: the
    fault a gate should target first ought to be the one the weights say carries
    the task's risk.
    """
    selected = [b for b in batches if b.task == task]
    healthy = [b for b in selected if b.fault == "none"]
    if not healthy:
        print(f"no fault-free pipelines for {task!r} — cannot attribute excess")
        return 1
    base_rate = sum(b.silent for b in healthy) / sum(b.n for b in healthy)
    weights = load_weights(task)

    print(f"Gate attribution — {task}, fault-free silent rate {base_rate:.1%}\n")
    print(f"  {'refuse all':<20}{'runs':>6}{'silent':>9}{'excess':>9}"
          f"{'correct':>9}{'true cost':>11}{'weight':>9}")
    print("  " + "-" * 74)

    dim_of = {"freshness": "freshness", "latency": "latency",
              "schema_drift": "consistency", "semantic_stripping": "semantic"}
    rows = []
    for fault, dim in dim_of.items():
        group = [b for b in selected if b.fault == fault]
        if not group:
            continue
        n = sum(b.n for b in group)
        silent = sum(b.silent for b in group) / n
        correct = sum(b.correct for b in group)
        excess = silent - base_rate
        # Correct answers forfeited per silent failure the fault actually caused.
        cost = correct / (excess * n) if excess > 0 else float("inf")
        rows.append((fault, cost, weights[dim]))
        print(f"  {fault:<20}{len(group):>6}{silent:>9.1%}{excess:>9.1%}"
              f"{correct / n:>9.1%}"
              f"{('never' if cost == float('inf') else f'{cost:.1f}'):>11}"
              f"{weights[dim]:>9.0%}")

    print("\n  excess    = silent failure above the fault-free rate — what the "
          "fault caused")
    print("  true cost = correct answers forfeited per silent failure genuinely "
          "prevented")
    print("  'never'   = the fault causes no excess silent failure, so refusing "
          "for it is\n              pure loss at any threshold\n")

    ranked = sorted((r for r in rows if r[1] != float("inf")), key=lambda r: r[1])
    if ranked:
        print(f"  Gate this task on {ranked[0][0]} first "
              f"({ranked[0][1]:.0f} correct answers per prevented silent "
              f"failure);\n  it carries {ranked[0][2]:.0%} of the calibrated "
              f"weight for {task}.")
    return 0


def report(batches: list[Batch], task: str, sweep: str) -> int:
    weights = load_weights(task)
    selected = [b for b in batches if b.task == task]
    if not selected:
        print(f"no batches for task {task!r}")
        return 1

    base = replay(selected, Policy(name="no gate"), weights)
    # The share of silent failure no gate can ever remove: what a HEALTHY
    # pipeline still produces. A gate refuses degraded batches; it cannot make
    # the agent right about a hard query it was always going to get wrong.
    healthy = [b for b in selected if b.fault == "none"]
    floor = (sum(b.silent for b in healthy) / sum(b.n for b in healthy)
             if healthy else 0.0)
    # Reported as a range, not a point: silent failure clusters by run, so the
    # spread ACROSS healthy pipelines is the honest error bar. It also explains
    # why a very tight policy can print a residual below the mean — it admits a
    # handful of pipelines, not a representative sample of healthy ones.
    rates = sorted(b.silent / b.n for b in healthy) or [0.0]
    print(f"Gate replay — {task}, {len(selected)} pipelines, "
          f"{base.decisions:,} decisions")
    print("Weights: " + "  ".join(f"{d}={weights[d]:.0%}" for d in DIMENSIONS))
    print(f"\nWithout any gate: {base.baseline_silent_rate:.1%} of answers are "
          f"silent failures\n({base.silent_total:,} confidently wrong answers "
          f"reaching a user).")
    print(f"Fault-free baseline: {floor:.1%} "
          f"(range {rates[0]:.1%}-{rates[-1]:.1%} across {len(healthy)} clean "
          f"pipelines).\nRefusing a batch cannot make the agent right about a "
          f"query it was always\ngoing to get wrong, so only the "
          f"{100 * (base.baseline_silent_rate - floor):.1f}pp above this baseline is "
          f"fault-attributable\nand therefore reachable by any gate. A residual "
          f"printed below the baseline\nmeans the policy admitted an "
          f"unrepresentative handful, not that it beat it.\n")

    print(f"  {'policy':<30}{'coverage':>10}{'prevented':>11}{'forfeited':>11}"
          f"{'residual':>10}{'cost':>8}")
    print("  " + "-" * 80)
    rows = []
    for policy in SWEEPS[sweep](task):
        out = replay(selected, policy, weights)
        rows.append((policy, out))
        cost = "—" if out.exchange_rate == float("inf") else f"{out.exchange_rate:.2f}"
        print(f"  {policy.name:<30}{out.coverage:>9.0%} {out.prevented_share:>10.0%}"
              f"{out.forfeited_share:>11.0%}{out.residual_silent_rate:>10.1%}{cost:>8}")

    print("\n  coverage  = share of decisions still answered")
    print("  prevented = share of silent failures that never reached a user")
    print("  forfeited = share of correct answers lost with them")
    print("  residual  = silent-failure rate among what still got through")
    print("  cost      = correct answers forfeited per silent failure prevented")

    gated = [(p, o) for p, o in rows if o.refused_batches and o.admitted_decisions]
    if not gated:
        return 0

    policy, out = min(gated, key=lambda r: r[1].exchange_rate)
    print(f"\n  Best exchange rate here: {policy.name} — forfeits "
          f"{out.exchange_rate:.2f} correct answers\n  per silent failure "
          f"prevented, cutting silent failure {base.baseline_silent_rate:.1%} → "
          f"{out.residual_silent_rate:.1%}\n  while still answering "
          f"{out.coverage:.0%} of queries.")

    worst = max(gated, key=lambda r: r[1].exchange_rate)[1].exchange_rate
    if out.exchange_rate >= 1.0:
        print(f"\n  EVERY policy above costs more than it saves in raw counts "
              f"({out.exchange_rate:.2f}–{worst:.2f}\n  correct answers per "
              f"silent failure prevented).")
    else:
        print(f"\n  Exchange rates here span {out.exchange_rate:.2f}–"
              f"{worst:.2f} correct answers per silent\n  failure prevented — "
              f"the cheapest does break even on raw counts, but it also\n  "
              f"prevents only {out.prevented_share:.0%} of silent failures, so "
              f"it buys very little.")
    print(f"\n  A gate is not a free win: it is a trade, worth making only when "
          f"one\n  confidently wrong answer costs more than ~"
          f"{max(out.exchange_rate, 1.0):.0f} missed ones. That is a domain\n  "
          f"question, not a technical one — in a clinical or financial setting "
          f"the\n  asymmetry is enormous and the trade is obvious; for a "
          f"shopping assistant it\n  may well not be. The contribution is that "
          f"the exchange rate is now a\n  measured number rather than a guess.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--task", default="retrieval",
                        choices=("retrieval", "classification"))
    parser.add_argument("--sweep", default="age", choices=sorted(SWEEPS))
    parser.add_argument("--attribution", action="store_true",
                        help="per-fault gate economics, crediting a gate only "
                             "with the silent failure the fault actually caused")
    parser.add_argument("--policy", type=Path, default=None,
                        help="evaluate a single policy file instead of a sweep")
    args = parser.parse_args(argv)

    batches = load_batches(args.results)
    if args.attribution:
        return attribution(batches, args.task)
    if args.policy:
        policy = Policy.load(args.policy)
        weights = load_weights(args.task)
        out = replay([b for b in batches if b.task == args.task], policy, weights)
        print(policy.describe())
        print(json.dumps({
            "coverage": round(out.coverage, 4),
            "prevented_share": round(out.prevented_share, 4),
            "forfeited_share": round(out.forfeited_share, 4),
            "residual_silent_rate": round(out.residual_silent_rate, 4),
            "baseline_silent_rate": round(out.baseline_silent_rate, 4),
            "refused_batches": out.refused_batches,
        }, indent=2))
        return 0
    return report(batches, args.task, args.sweep)


if __name__ == "__main__":
    raise SystemExit(main())
