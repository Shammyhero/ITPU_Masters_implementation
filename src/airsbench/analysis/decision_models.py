"""Decision-level models — RQ2 and RQ3, per research_questions_v2.md §5.

Binary outcomes are modelled at the level of the individual decision (~11 400 of
them) rather than as 144 run-level proportions. A proportion computed from 80
decisions is not a datum with its own error bar; treating it as one throws away
the sample size that produced it and misstates the precision.

**Inference method — a documented substitution.** The declared plan specifies a
run-level random intercept, `outcome ~ fault * severity + task + (1 | run_id)`.
statsmodels' only mixed logit is `BinomialBayesMixedGLM`, a variational-Bayes
approximation whose posterior SDs are not the frequentist standard errors the
plan reports. This module instead fits the same fixed-effects logistic model
with **cluster-robust standard errors grouped by `run_id`**. Both target the
identical problem — decisions within a run are correlated, so naive SEs are too
small — and the cluster-robust form does it without approximating the
likelihood, at the cost of not estimating the variance component itself (which
nothing in the RQs asks for).

**The impairment model is the one that matters.** Under freshness, a retrieval
decision can be wrong for a purely mechanical reason: staleness moved the
correct answer, so no agent could be right. Pooling those in measures the
answer-flip rate. The primary silent-failure model therefore excludes
mechanically-unanswerable decisions, and the pooled model is reported beside it
to show what that exclusion is worth.

    python -m airsbench.analysis.decision_models
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Any

from ..runner.config import run_arm
from .flip_partition import Replayer

FAULTS = ("none", "freshness", "latency", "schema_drift", "semantic_stripping")


def build_frame(results_dir: Path, data_dir: Path):
    """One row per decision, with the covariates the models need.

    `flipped` marks retrieval decisions staleness made unanswerable. It is False
    for classification, where the label is a property of the flight and cannot
    move — not missing, genuinely not applicable.
    """
    import pandas as pd

    replayer = Replayer(data_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        if run_arm(run) != "main":
            continue
        cfg = run["config"]
        if cfg["task"] == "retrieval":
            flags = [o.flipped for o in replayer.outcomes(run)]
        else:
            flags = [False] * len(run["decisions"])

        for decision, flipped in zip(run["decisions"], flags):
            silent = (
                not decision["correct"]
                and not decision["abstained"]
                and not decision["parse_failed"]
            )
            rows.append({
                "run_id": run["run_id"],
                "pipeline": cfg["pipeline"],
                "task": cfg["task"],
                "fault": cfg["fault_type"],
                "severity": cfg["severity"],
                "replication": cfg["replication"],
                "correct": int(decision["correct"]),
                "abstained": int(decision["abstained"]),
                "silent": int(silent),
                "confidence": decision["confidence"],
                "flipped": bool(flipped),
            })
    frame = pd.DataFrame(rows)
    # "severity" is "none" only for the baseline, so fault and severity are not
    # crossed there. A single ordered factor keeps the design estimable and the
    # baseline as the reference level.
    frame["condition"] = frame.apply(
        lambda r: "baseline" if r["fault"] == "none" else f"{r['fault']}_{r['severity']}",
        axis=1,
    )
    return frame


def fit_logit(frame, outcome: str, formula: str):
    """Logistic GLM with cluster-robust SEs grouped by run."""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.glm(f"{outcome} ~ {formula}", data=frame,
                        family=sm.families.Binomial())
        return model.fit(cov_type="cluster",
                         cov_kwds={"groups": frame["run_id"]})


def odds_table(result, label: str) -> None:
    """Odds ratios with cluster-robust 95% intervals."""
    import numpy as np

    params, conf = result.params, result.conf_int()
    print(f"\n  {label}")
    print(f"    {'term':<40}{'OR':>8}{'95% CI':>20}{'p':>10}")
    print("    " + "-" * 78)
    for term in params.index:
        if term == "Intercept":
            continue
        lo, hi = np.exp(conf.loc[term, 0]), np.exp(conf.loc[term, 1])
        stars = "***" if result.pvalues[term] < 0.001 else (
            "**" if result.pvalues[term] < 0.01 else (
                "*" if result.pvalues[term] < 0.05 else ""))
        pretty = term.replace("C(condition)[T.", "").replace("C(task)[T.", "task=")
        pretty = pretty.replace("C(pipeline)[T.", "pipe=").replace("]", "")
        print(f"    {pretty:<40}{np.exp(params[term]):>8.2f}"
              f"   [{lo:>5.2f}, {hi:>6.2f}]{result.pvalues[term]:>10.4f} {stars}")


def run_level_anova(frame) -> None:
    """RQ2: two-way ANOVA on run-level accuracy, with eta-squared.

    Baseline runs are excluded: `severity` has no level for them, so a crossed
    fault x severity design is not estimable with them in. The baseline is
    reported separately as the reference.
    """
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    from scipy import stats

    runs = frame.groupby(
        ["run_id", "pipeline", "task", "fault", "severity"], as_index=False
    )["correct"].mean().rename(columns={"correct": "accuracy"})

    baseline = runs[runs["fault"] == "none"]
    factorial = runs[runs["fault"] != "none"].copy()

    print(f"\n  Run-level accuracy: {len(runs)} runs "
          f"(baseline {len(baseline)}, factorial {len(factorial)})")

    shapiro = stats.shapiro(factorial["accuracy"])
    print(f"    Shapiro-Wilk on run accuracy: W = {shapiro.statistic:.3f}, "
          f"p = {shapiro.pvalue:.4f}"
          f"{'  (non-normal -> Kruskal-Wallis reported below)' if shapiro.pvalue < 0.05 else ''}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.ols("accuracy ~ C(fault) * C(severity) + C(task) + C(pipeline)",
                        data=factorial).fit()
        table = sm.stats.anova_lm(model, typ=2)

    total = table["sum_sq"].sum()
    print(f"\n    {'effect':<28}{'F':>10}{'p':>12}{'eta^2':>10}")
    print("    " + "-" * 60)
    for effect in table.index:
        if effect == "Residual":
            continue
        eta = table.loc[effect, "sum_sq"] / total
        print(f"    {effect.replace('C(', '').replace(')', ''):<28}"
              f"{table.loc[effect, 'F']:>10.2f}{table.loc[effect, 'PR(>F)']:>12.2e}"
              f"{eta:>10.3f}")

    if shapiro.pvalue < 0.05:
        groups = [g["accuracy"].values for _, g in factorial.groupby("fault")]
        kw = stats.kruskal(*groups)
        print(f"\n    Kruskal-Wallis across faults: H = {kw.statistic:.2f}, "
              f"p = {kw.pvalue:.2e}")

    # Cohen's d against baseline, per fault at severe.
    print("\n    Cohen's d on RAW accuracy. For freshness this mixes two")
    print("    mechanisms (answer-key movement in retrieval, feature attenuation")
    print("    in classification) and is not a clean impairment estimate.")
    print(f"\n    {'fault (severe) vs baseline':<34}{'d':>8}{'reading':>14}")
    print("    " + "-" * 58)
    base = baseline["accuracy"]
    for fault in FAULTS[1:]:
        sel = factorial[(factorial["fault"] == fault) & (factorial["severity"] == "severe")]
        if sel.empty:
            continue
        pooled = (
            ((len(base) - 1) * base.std() ** 2 + (len(sel) - 1) * sel["accuracy"].std() ** 2)
            / max(len(base) + len(sel) - 2, 1)
        ) ** 0.5
        d = (sel["accuracy"].mean() - base.mean()) / pooled if pooled else 0.0
        size = ("large" if abs(d) >= 0.8 else "medium" if abs(d) >= 0.5
                else "small" if abs(d) >= 0.2 else "negligible")
        print(f"    {fault:<34}{d:>8.2f}{size:>14}")


def report(frame) -> int:
    n_runs = frame["run_id"].nunique()
    print(f"Decision-level models — {len(frame):,} decisions from {n_runs} "
          f"main-factorial runs\n")
    print("Logistic GLM with cluster-robust SEs grouped by run_id, substituting")
    print("for the declared random intercept (see module docstring). Reference")
    print("condition is the no-fault baseline; task reference is classification.")

    print("\n" + "=" * 84)
    print("RQ3 — SILENT FAILURE")

    formula = "C(condition) + C(task) + C(pipeline)"

    # The primary model: mechanically-unanswerable decisions removed, so the
    # coefficients describe impairment rather than answer-key movement.
    answerable = frame[~frame["flipped"]]
    odds_table(
        fit_logit(answerable, "silent", formula),
        f"PRIMARY — answerable decisions only (n = {len(answerable):,}); "
        "coefficients are impairment",
    )
    odds_table(
        fit_logit(frame, "silent", formula),
        f"POOLED — every decision (n = {len(frame):,}); freshness here is "
        "inflated by\n           the answer-flip rate and is NOT a claim about the agent",
    )

    # Freshness reaches the two tasks by different routes, and pooling hides it:
    # in retrieval it moves the answer key (mechanical, removed above), while in
    # classification it attenuates the DepDelay feature (genuine impairment).
    # A pooled coefficient averages a null and a real effect into a misleading
    # middle. Split.
    print("\n  BY TASK — freshness damages the two tasks by different mechanisms")
    per_task = "C(condition) + C(pipeline)"
    retrieval = answerable[answerable["task"] == "retrieval"]
    odds_table(
        fit_logit(retrieval, "silent", per_task),
        f"retrieval, answerable only (n = {len(retrieval):,}) — staleness moves the "
        "answer key,\n           and that component has been removed, so freshness "
        "should read ~1.0",
    )
    classification = frame[frame["task"] == "classification"]
    odds_table(
        fit_logit(classification, "silent", per_task),
        f"classification (n = {len(classification):,}) — staleness attenuates the "
        "DepDelay\n           feature, which is genuine impairment and should read >> 1",
    )

    print("\n" + "=" * 84)
    print("RQ3 — ABSTENTION")
    odds_table(fit_logit(frame, "abstained", formula),
               f"every decision (n = {len(frame):,})")

    print("\n" + "=" * 84)
    print("RQ2 — FAULT RANKING")
    run_level_anova(frame)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    args = parser.parse_args(argv)
    return report(build_frame(args.results, args.data_dir))


if __name__ == "__main__":
    raise SystemExit(main())
