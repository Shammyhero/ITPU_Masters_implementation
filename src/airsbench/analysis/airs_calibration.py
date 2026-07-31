"""RQ4 — calibrate the AIRS weights, and test whether AIRS earns its keep.

AIRS claims to predict silent failure from pipeline telemetry alone, before an
agent is deployed. That claim has to survive two tests, and this module runs
both:

1. **Held-out validation.** Weights are fitted on 80% of runs and scored on the
   remaining 20%. Splitting by RUN, never by decision — decisions inside a run
   share one AIRS vector, so a decision-level split leaks the answer.
2. **A baseline that already exists.** Agent self-reported confidence is
   available for free once the agent has run. If AIRS cannot beat it, its value
   is not accuracy but *availability* — it is computable before deployment —
   and that is a much weaker claim. Compared by AUC with DeLong's test.

Three campaign results shape the design:

- **Calibrate per task, not pooled** (RQ5). The fault ranking inverts between
  retrieval and classification, so one shared weight vector would average two
  opposite orderings into a vector describing neither.
- **AIRS values come from `corrected_airs`**, never `run["airs"]` off disk —
  16 early runs carry a double-counted freshness dimension.
- **Silent failure is not the whole story.** A fault that drives refusal lowers
  silent failure while destroying accuracy, so a weight vector fitted only on
  silent failure will under-weight the dimension the agent detects best. The
  report scores an accuracy-loss target beside it.

The primary target is the **unconditional** silent-failure rate — what an
operator actually observes. A flip-conditioned target is reported alongside,
because for freshness the unconditional rate partly reflects the answer-flip
rate, which the AIRS freshness dimension is measuring the *cause* of; fitting
only on that is mildly circular.

    python -m airsbench.analysis.airs_calibration
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Any

from ..runner.config import run_arm
from .airs_correction import corrected_airs
from .flip_partition import Replayer

DIMENSIONS = ("freshness", "latency", "consistency", "semantic")
PRIMARY_MODEL = "gpt-4o-mini"
# Arms whose runs vary AIRS through infrastructure alone. The detectability arm
# is excluded: it varies a treatment (delivered record age) that AIRS does not
# score, so its runs share an AIRS vector while differing in outcome.
TRAINING_ARMS = ("main", "freshness_sweep")
HELD_OUT_FRACTION = 0.2
SPLIT_SEED = 20260731


def build_frame(results_dir: Path, data_dir: Path):
    """Decision-level frame carrying each run's corrected AIRS vector."""
    import pandas as pd

    replayer = Replayer(data_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        arm = run_arm(run)
        if arm not in (*TRAINING_ARMS, "cross_model"):
            continue
        cfg = run["config"]
        airs = corrected_airs(run)

        flags = (
            [o.flipped for o in replayer.outcomes(run)]
            if cfg["task"] == "retrieval"
            else [False] * len(run["decisions"])
        )
        for decision, flipped in zip(run["decisions"], flags):
            rows.append({
                "run_id": run["run_id"],
                "arm": arm,
                "model": cfg["model"],
                "task": cfg["task"],
                "fault": cfg["fault_type"],
                **{d: airs[d] for d in DIMENSIONS},
                "correct": int(decision["correct"]),
                "abstained": int(decision["abstained"]),
                "silent": int(
                    not decision["correct"]
                    and not decision["abstained"]
                    and not decision["parse_failed"]
                ),
                "wrong": int(not decision["correct"]),
                "confidence": float(decision["confidence"]),
                "flipped": bool(flipped),
            })
    return pd.DataFrame(rows)


def split_by_run(frame, seed: int = SPLIT_SEED, fraction: float = HELD_OUT_FRACTION):
    """80/20 split at the RUN level.

    Decisions within a run share one AIRS vector, so splitting by decision
    would put the same predictor row on both sides and inflate held-out
    performance towards the training fit.
    """
    import numpy as np

    runs = frame["run_id"].unique()
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(runs)
    n_held = max(1, int(round(len(shuffled) * fraction)))
    held = set(shuffled[:n_held])
    return frame[~frame["run_id"].isin(held)], frame[frame["run_id"].isin(held)]


def fit_weights(train, target: str):
    """Logistic regression of `target` on the four AIRS dimensions."""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    formula = f"{target} ~ " + " + ".join(DIMENSIONS)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.glm(formula, data=train, family=sm.families.Binomial())
        return model.fit(cov_type="cluster", cov_kwds={"groups": train["run_id"]})


def normalised_weights(result) -> dict[str, float]:
    """Turn logistic coefficients into AIRS composite weights summing to 1.

    A dimension protects against silent failure when its coefficient is
    negative (higher score, lower risk). Weight is proportional to that
    protective magnitude; a non-protective dimension gets zero rather than a
    negative weight, since a negative weight in a readiness score would mean
    "degrade this to improve the score".
    """
    protective = {
        dim: max(0.0, -float(result.params[dim])) for dim in DIMENSIONS
    }
    total = sum(protective.values())
    if total == 0:
        return {dim: 0.0 for dim in DIMENSIONS}
    return {dim: value / total for dim, value in protective.items()}


def auc(labels, scores) -> float:
    from sklearn.metrics import roc_auc_score

    if len(set(labels)) < 2:
        return float("nan")
    return float(roc_auc_score(labels, scores))


def delong_test(labels, scores_a, scores_b) -> tuple[float, float, float]:
    """DeLong's test for two correlated ROC curves.

    Returns (auc_a, auc_b, two-sided p). The two scores are computed on the
    same decisions, so their AUCs are correlated and an independent-sample
    comparison would overstate significance.
    """
    import numpy as np
    from scipy import stats

    labels = np.asarray(labels)
    a = np.asarray(scores_a, dtype=float)
    b = np.asarray(scores_b, dtype=float)
    pos, neg = labels == 1, labels == 0
    m, n = int(pos.sum()), int(neg.sum())
    if m == 0 or n == 0:
        return float("nan"), float("nan"), float("nan")

    def structural(scores):
        x, y = scores[pos], scores[neg]
        # V10[i] = P(a random negative scores below positive i), ties at 0.5
        v10 = np.array([( (y < xi).sum() + 0.5 * (y == xi).sum() ) / n for xi in x])
        v01 = np.array([( (x > yj).sum() + 0.5 * (x == yj).sum() ) / m for yj in y])
        return v10, v01, v10.mean()

    a10, a01, auc_a = structural(a)
    b10, b01, auc_b = structural(b)

    s10 = np.cov(np.vstack([a10, b10]))
    s01 = np.cov(np.vstack([a01, b01]))
    var = (s10 / m + s01 / n)
    diff_var = var[0, 0] + var[1, 1] - 2 * var[0, 1]
    if diff_var <= 0:
        return float(auc_a), float(auc_b), float("nan")
    z = (auc_a - auc_b) / np.sqrt(diff_var)
    return float(auc_a), float(auc_b), float(2 * stats.norm.sf(abs(z)))


def run_level_ranking(frame, weights: dict[str, float], target: str):
    """Spearman between the AIRS composite and each run's failure rate.

    This is the fair test of what AIRS actually claims. AIRS is a property of a
    pipeline, constant across every decision in a run, so it can only ever rank
    RUNS. A decision-level AUC asks it to separate decisions inside a run —
    something it is structurally incapable of — and therefore understates it.
    """
    from scipy.stats import spearmanr

    runs = frame.groupby("run_id").agg(
        rate=(target, "mean"),
        **{d: (d, "first") for d in DIMENSIONS},
    )
    composite = sum(weights[d] * runs[d] for d in DIMENSIONS)
    if len(runs) < 3 or runs["rate"].nunique() < 2:
        return float("nan"), float("nan"), len(runs)
    result = spearmanr(composite, runs["rate"])
    return float(result.statistic), float(result.pvalue), len(runs)


def collinearity(train) -> dict[str, float]:
    """VIF per dimension. Faults move one dimension each, so check the four
    predictors are actually separable before attributing weights to them."""
    import numpy as np
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    matrix = np.column_stack(
        [np.ones(len(train))] + [train[d].to_numpy(dtype=float) for d in DIMENSIONS]
    )
    return {
        dim: float(variance_inflation_factor(matrix, i + 1))
        for i, dim in enumerate(DIMENSIONS)
    }


def report(frame) -> int:
    primary = frame[
        (frame["model"] == PRIMARY_MODEL) & (frame["arm"].isin(TRAINING_ARMS))
    ]
    if primary.empty:
        print("No primary-model runs to calibrate on.")
        return 1

    print(f"AIRS calibration (RQ4) — {len(primary):,} decisions from "
          f"{primary['run_id'].nunique()} runs of {PRIMARY_MODEL}\n")
    print("Weights fitted per task (RQ5: the fault ranking inverts between them).")
    print("AIRS values are the corrected ones; the split is by run, not decision.\n")

    for task in ("retrieval", "classification"):
        task_frame = primary[primary["task"] == task]
        if task_frame.empty:
            continue
        train, held = split_by_run(task_frame)
        print("=" * 78)
        print(f"{task.upper()} — {train['run_id'].nunique()} train runs / "
              f"{held['run_id'].nunique()} held-out runs")

        vif = collinearity(train)
        flagged = [d for d, v in vif.items() if v > 5.0]
        print("\n  Collinearity (VIF): " + "  ".join(
            f"{d}={v:.1f}" for d, v in vif.items()))
        if flagged:
            print(f"  ! {', '.join(flagged)} exceed 5 — coefficients for these are "
                  "not separately\n    attributable; read the composite, not the "
                  "individual weight.")

        for target, label in (
            ("silent", "silent failure (unconditional — what an operator sees)"),
            ("wrong", "any wrong answer (counts refusal-masked damage too)"),
        ):
            result = fit_weights(train, target)
            weights = normalised_weights(result)
            print(f"\n  TARGET: {label}")
            print(f"    {'dimension':<16}{'coef':>10}{'p':>10}{'weight':>10}")
            print("    " + "-" * 46)
            for dim in DIMENSIONS:
                print(f"    {dim:<16}{result.params[dim]:>10.4f}"
                      f"{result.pvalues[dim]:>10.4f}{weights[dim]:>10.1%}")

            score = -(sum(weights[d] * held[d] for d in DIMENSIONS))
            a_auc, b_auc, p = delong_test(
                held[target].to_numpy(), score.to_numpy(),
                -held["confidence"].to_numpy(),
            )
            verdict = ("AIRS wins" if a_auc > b_auc else "confidence wins") + (
                "" if p < 0.05 else ", n.s.")
            print(f"    decision-level AUC — AIRS {a_auc:.3f} vs agent confidence "
                  f"{b_auc:.3f}\n      DeLong p = {p:.4f} ({verdict})")

            rho, rho_p, n_runs = run_level_ranking(held, weights, target)
            print(f"    run-level Spearman (AIRS vs run failure rate, "
                  f"n={n_runs} held-out runs):\n      rho = {rho:+.3f} "
                  f"(p = {rho_p:.4f})  <- the fair test of what AIRS claims")

        # ---- portability: does a gpt-4o-mini calibration transfer? --------
        weights = normalised_weights(fit_weights(train, "silent"))
        print("\n  PORTABILITY of the silent-failure weights fitted above,")
        print("  applied unchanged to models they were not fitted on:")
        for other in sorted(frame[frame["model"] != PRIMARY_MODEL]["model"].unique()):
            external = frame[(frame["model"] == other) & (frame["task"] == task)]
            if external.empty or external["silent"].nunique() < 2:
                continue
            rho, rho_p, n_runs = run_level_ranking(external, weights, "silent")
            score = -(sum(weights[d] * external[d] for d in DIMENSIONS))
            print(f"    {other:<30} AUC {auc(external['silent'], score):.3f}"
                  f"   rho {rho:+.3f} (n={n_runs} runs)")

    print("\n" + "=" * 78)
    print("Reading this: AIRS is constant within a run, so it can only separate")
    print("RUNS, never decisions inside one. Agent confidence varies per decision")
    print("and is therefore playing an easier game at this resolution. AIRS's")
    print("claim is availability — it is computable from telemetry before any")
    print("agent runs — not that it out-resolves a deployed agent's own signal.")
    return 0


def export_weights(frame, out_path: Path, target: str = "wrong") -> dict[str, Any]:
    """Write the calibrated per-task weights for `airs probe` to consume.

    Target defaults to total error, not silent failure — see RQ4 §3. The split
    between silent failure and refusal is a property of the agent, so a
    pipeline score should be fitted against pipeline-caused harm.
    """
    import datetime

    primary = frame[
        (frame["model"] == PRIMARY_MODEL) & (frame["arm"].isin(TRAINING_ARMS))
    ]
    profiles: dict[str, dict[str, float]] = {}
    provenance: dict[str, Any] = {}
    for task in sorted(primary["task"].unique()):
        task_frame = primary[primary["task"] == task]
        train, held = split_by_run(task_frame)
        weights = normalised_weights(fit_weights(train, target))
        rho, rho_p, n_runs = run_level_ranking(held, weights, target)
        profiles[task] = {d: round(weights[d], 4) for d in DIMENSIONS}
        provenance[task] = {
            "train_runs": int(train["run_id"].nunique()),
            "held_out_runs": int(held["run_id"].nunique()),
            "held_out_spearman": round(rho, 4),
            "held_out_p": round(rho_p, 6),
            "n_held_out_for_rho": n_runs,
        }

    payload = {
        "schema": "airs-weights/1",
        "calibrated_at": datetime.date.today().isoformat(),
        "target": target,
        "target_note": (
            "Total error, not silent failure. The silent/refusal split is an "
            "agent property; a pipeline score predicts pipeline-caused harm."
        ),
        "fitted_on": {
            "model": PRIMARY_MODEL,
            "arms": list(TRAINING_ARMS),
            "decisions": int(len(primary)),
            "split_seed": SPLIT_SEED,
        },
        "profiles": profiles,
        "validation": provenance,
        "caveat": (
            "Weights are fitted on synthetic faults in one study. AIRS is a "
            "method to recalibrate per deployment, not a universal constant. "
            "Per-task profiles are required: the ranking inverts across tasks."
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    parser.add_argument(
        "--export",
        type=Path,
        default=None,
        metavar="PATH",
        help="write calibrated per-task weights for `airs probe` and exit",
    )
    args = parser.parse_args(argv)
    frame = build_frame(args.results, args.data_dir)
    if args.export is not None:
        payload = export_weights(frame, args.export)
        print(f"Wrote {args.export} — target={payload['target']}")
        for task, weights in payload["profiles"].items():
            rho = payload["validation"][task]["held_out_spearman"]
            print(f"  {task:<16}" + "  ".join(f"{d}={w:.1%}" for d, w in weights.items())
                  + f"   (held-out rho {rho:+.3f})")
        return 0
    return report(frame)


if __name__ == "__main__":
    raise SystemExit(main())
