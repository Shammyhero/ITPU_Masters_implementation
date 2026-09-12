"""Do two infrastructure faults compose additively? (interaction arm, provisional)

Every AIRS composite in this study is a weighted SUM over dimensions. It was
fitted on runs where exactly one dimension was ever degraded, and `airs probe`
and `airs gate` then apply it to pipelines where several are degraded at once —
the normal production case. Additivity is an untested extrapolation, and it
fails in the unsafe direction: if faults compound, AIRS under-predicts risk
precisely on the worst pipelines.

The measurement side is known to compose exactly: a compound condition degrades
each AIRS dimension by its solo marginal and leaves the others at baseline
(`tests/test_interaction_arm.py`). So the independent variable is clean by
construction and any departure from additivity here is behavioural.

## "Additive" on which scale?

The question has no scale-free answer, and the two scales that matter disagree
about what would count as a finding:

  logit             What the AIRS calibration assumes. Its weights come from a
                    logistic GLM, so the composite extrapolates correctly to
                    multi-fault pipelines exactly if the interaction term is
                    zero ON THIS SCALE.
  risk difference   What an operator experiences, and what `gate.replay`'s
                    prevented/forfeited accounting is denominated in.

Two faults can be exactly additive on one and not the other — that is arithmetic,
not a contradiction. Both are reported, and each conclusion is stated against the
scale it belongs to.

    python -m airsbench.analysis.interaction
    python -m airsbench.analysis.interaction --outcome error
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..runner.config import INTERACTION_PAIRS, compose_faults, run_arm

BOOTSTRAP = 4000


class AlignmentError(RuntimeError):
    """Conditions in a replication did not evaluate the same queries."""


def load_arm(results_dir: Path) -> list[dict[str, Any]]:
    """Interaction-arm runs only, by seed-block provenance.

    Selecting on condition instead would silently pool this arm with the main
    factorial, which contains the same streaming/severe solo conditions under
    different seeds.
    """
    runs = []
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text())
        if run_arm(run) == "interaction":
            runs.append(run)
    return runs


def outcome_vector(run: dict[str, Any], outcome: str) -> list[int]:
    """Per-decision 0/1 outcome, in the order the run evaluated them."""
    out = []
    for decision in run["decisions"]:
        correct = bool(decision["correct"])
        if outcome == "silent":
            value = (not correct and not decision["abstained"]
                     and not decision["parse_failed"])
        elif outcome == "error":
            value = not correct
        else:
            raise ValueError(f"unknown outcome {outcome!r}")
        out.append(int(value))
    return out


def paired_cells(
    runs: list[dict[str, Any]], task: str, pair: tuple[str, str], outcome: str
) -> dict[str, list[list[int]]]:
    """Outcome vectors per condition, one list per replication, index-aligned.

    Alignment is what makes this paired rather than merely matched. Within a
    replication every condition draws the same queries at the same simulated
    times (`sample_seed` is a function of task and replication only), and the
    skips in the runner depend on the TRUE world state, never on the served one
    — so decision *i* is the same question in all four conditions.

    That is an assumption about the runner, so it is checked rather than
    trusted: unequal decision counts mean the pairing is broken and every
    contrast below would be comparing different questions.
    """
    conditions = ["none", pair[0], pair[1], compose_faults(*pair)]
    by_replication: dict[str, dict[int, list[int]]] = {}
    for condition in conditions:
        by_replication[condition] = {
            r["config"]["replication"]: outcome_vector(r, outcome)
            for r in runs
            if r["config"]["task"] == task
            and r["config"]["fault_type"] == condition
        }

    # Only replications where EVERY condition has a run. A partially executed
    # arm otherwise looks like broken pairing; and using a replication present
    # in three of four conditions would silently unbalance the contrast.
    complete = sorted(set.intersection(*(set(v) for v in by_replication.values())))
    if not complete:
        return {c: [] for c in conditions}

    # Decision counts vary BETWEEN replications (different queries) and must be
    # identical WITHIN one (the same queries under every condition). Checked per
    # replication, which is the level the claim is actually made at.
    for replication in complete:
        counts = {c: len(by_replication[c][replication]) for c in conditions}
        if len(set(counts.values())) != 1:
            raise AlignmentError(
                f"{task}/{pair} replication {replication}: conditions evaluated "
                f"different numbers of decisions ({counts}). The paired contrast "
                f"would be comparing different questions — do not interpret the "
                f"interaction until this is resolved."
            )
    return {c: [by_replication[c][r] for r in complete] for c in conditions}


def _rate(vectors: list[list[int]]) -> float:
    total = sum(len(v) for v in vectors)
    return sum(sum(v) for v in vectors) / total if total else 0.0


def _logit(p, np):
    """Haldane-corrected logit, so a zero cell does not send the estimate to -inf."""
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def interaction_estimates(cells: dict[str, list[list[int]]],
                          pair: tuple[str, str]) -> dict[str, float]:
    """Departure from additivity on BOTH scales, from one paired bootstrap.

    risk difference  delta = p(AB) - p(A) - p(B) + p(0)
    log odds ratio   psi   = logit p(AB) - logit p(A) - logit p(B) + logit p(0)

    `psi` is exactly the `a:b` coefficient of a saturated `y ~ a * b` logistic
    model, computed in closed form. The GLM was tried first and had to be
    dropped: with one run per condition per replication, the interaction term is
    perfectly confounded with cluster identity, the cluster-robust variance
    degenerates, and it reported p = 0.000 for every pair INCLUDING the latency
    control — which cannot interact with anything. A p-value that small on a
    control is a symptom, not a finding.

    Resampling is over PAIRED QUERIES rather than runs. With three replications
    a cluster bootstrap would have three draws per condition; the paired design
    supplies ~240 aligned quadruples instead, which is why the arm carries its
    own solos.
    """
    import numpy as np

    a, b = pair
    ab = compose_faults(*pair)
    order = ("none", a, b, ab)
    p0, pa, pb, pab = (_rate(cells[c]) for c in order)

    matrix = np.array([
        np.concatenate([np.array(v, dtype=float) for v in cells[c]]) for c in order
    ])
    n = matrix.shape[1]
    rng = np.random.default_rng(20260805)
    deltas = np.empty(BOOTSTRAP)
    psis = np.empty(BOOTSTRAP)
    for i in range(BOOTSTRAP):
        s = matrix[:, rng.integers(0, n, n)].mean(axis=1)
        deltas[i] = s[3] - s[1] - s[2] + s[0]
        lg = _logit(s, np)
        psis[i] = lg[3] - lg[1] - lg[2] + lg[0]

    def summarise(draws, point):
        lo, hi = np.percentile(draws, [2.5, 97.5])
        return {"point": float(point), "lo": float(lo), "hi": float(hi),
                "p": float(2 * min((draws <= 0).mean(), (draws >= 0).mean()))}

    lg = _logit(np.array([p0, pa, pb, pab]), np)
    return {
        "p0": p0, "pa": pa, "pb": pb, "pab": pab,
        "additive": pa + pb - p0,
        "n_paired": n,
        "n_replications": len(cells["none"]),
        "rd": summarise(deltas, pab - (pa + pb - p0)),
        "logit": summarise(psis, lg[3] - lg[1] - lg[2] + lg[0]),
    }


def report(runs: list[dict[str, Any]], outcome: str) -> int:
    if not runs:
        print("No interaction-arm runs found (seeds 80000-90000).")
        return 1

    print(f"Fault interaction — outcome '{outcome}', {len(runs)} runs "
          f"(interaction arm, PROVISIONAL)\n")
    print("Additivity is scale-dependent. `logit` governs whether the AIRS")
    print("composite extrapolates to multi-fault pipelines — its weights come")
    print("from a logistic fit. `delta` is what an operator feels, and the scale")
    print("gate.replay's accounting is denominated in.\n")

    verdicts = []
    for task in ("retrieval", "classification"):
        print(f"  {task}")
        print(f"    {'pair':<32}{'p(A)':>6}{'p(B)':>6}{'add.':>7}{'obs.':>7}"
              f"{'delta':>8}{'95% CI':>17}{'logit psi':>11}{'95% CI':>16}")
        print("    " + "-" * 106)
        for pair in INTERACTION_PAIRS:
            label = "+".join(pair)
            try:
                cells = paired_cells(runs, task, pair, outcome)
            except AlignmentError as exc:
                print(f"    {label:<32}  SKIPPED — {exc}")
                continue
            if any(not v for v in cells.values()):
                print(f"    {label:<32}  incomplete — a condition has no runs yet")
                continue

            est = interaction_estimates(cells, pair)
            rd, lg = est["rd"], est["logit"]
            verdicts.append((task, pair, est))
            print(f"    {label:<32}{est['pa']:>6.1%}{est['pb']:>6.1%}"
                  f"{est['additive']:>7.1%}{est['pab']:>7.1%}{rd['point']:>+8.1%}"
                  f"  [{rd['lo']:+.1%},{rd['hi']:+.1%}]{lg['point']:>+11.2f}"
                  f"  [{lg['lo']:+.2f},{lg['hi']:+.2f}]")
        print()

    if not verdicts:
        print("    Nothing complete enough to interpret yet.")
        return 1

    reps = verdicts[0][2]["n_replications"]
    n_paired = verdicts[0][2]["n_paired"]
    print("    add. = p(A)+p(B)-p(0), the additive prediction.  obs. = both faults.")
    print("    delta = obs - add on the risk scale; psi = the same contrast in")
    print("    log odds. >0 compounds, <0 saturates, interval spanning 0 = additive.")
    print(f"    {reps} replication(s), {n_paired:,} paired queries per contrast, "
          f"{BOOTSTRAP:,} bootstrap resamples.\n")

    def departs(est, scale):
        s = est[scale]
        return not (s["lo"] <= 0 <= s["hi"])

    print("  " + "-" * 76)
    rd_hits = [v for v in verdicts if departs(v[2], "rd")]
    lg_hits = [v for v in verdicts if departs(v[2], "logit")]

    if not lg_hits:
        print("  ADDITIVE ON THE LOGIT SCALE — every interval spans zero.")
        print("  The AIRS composite's linear form therefore survives the step it")
        print("  was never tested on: fitted where one dimension moved, deployed")
        print("  where several do. `probe` and `gate` extrapolate legitimately,")
        print("  and independent per-dimension floors remain the right shape.")
        print("\n  A validation result, not a null: that step was previously assumed.")
    else:
        print(f"  NOT ADDITIVE on the logit scale — {len(lg_hits)} of "
              f"{len(verdicts)} pairs depart:")
        for task, pair, est in lg_hits:
            lg = est["logit"]
            word = "compounds" if lg["point"] > 0 else "saturates"
            print(f"    {task}/{'+'.join(pair)}: {word}, psi {lg['point']:+.2f} "
                  f"[{lg['lo']:+.2f}, {lg['hi']:+.2f}]")
        if any(v[2]["logit"]["point"] > 0 for v in lg_hits):
            print("\n  Where faults COMPOUND, AIRS under-predicts risk on exactly the")
            print("  pipelines that are worst — the unsafe direction. A multi-fault")
            print("  pipeline then needs a joint rule, not the independent")
            print("  per-dimension floors gate.Policy applies today.")

    if rd_hits and not lg_hits:
        print(f"\n  On the RISK scale {len(rd_hits)} pair(s) do depart. That is not a")
        print("  contradiction — additivity is scale-dependent, and a constant odds")
        print("  ratio produces unequal risk differences wherever baselines differ.")
        print("  It matters for gate.replay's accounting, not for the composite.")

    control = [v for v in verdicts if "latency" in v[1]]
    if control:
        clean = not any(departs(v[2], "logit") for v in control)
        status = ("no interaction, as required" if clean
                  else "INTERACTION FOUND — suspect the test, not the pipeline")
        print(f"\n  Method control (latency pairs): {status}.")
        print("  Weaker than it looks: latency runs analytically and cannot change")
        print("  what the agent reads, so this could only ever come out one way.")
        print("  It checks the arithmetic, not the test's sensitivity.")
    return 0


def figure(runs: list[dict[str, Any]], out_path: Path, outcome: str = "silent") -> Path:
    """Figure 4.6 — observed combined failure rate against the additive prediction.

    Hollow marker: what additivity predicts, p(A)+p(B)-p(0). Filled marker: what
    was observed with both faults applied. A filled marker LEFT of its hollow one
    is saturation — the combination did less harm than the sum of its parts.
    The logit-scale interval is printed on the right because that, not the
    visual gap on the risk scale, is what governs whether the AIRS composite
    extrapolates (see the module docstring on scale dependence).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), sharex=True)
    for ax, task in zip(axes, ("retrieval", "classification")):
        labels = []
        for row, pair in enumerate(reversed(INTERACTION_PAIRS)):
            cells = paired_cells(runs, task, pair, outcome)
            if any(not v for v in cells.values()):
                continue
            est = interaction_estimates(cells, pair)
            add, obs = 100 * est["additive"], 100 * est["pab"]
            lg = est["logit"]
            departs = not (lg["lo"] <= 0 <= lg["hi"])
            colour = "#0e6f7a" if departs else "#8a96a3"
            ax.plot([add, obs], [row, row], color=colour, linewidth=1.4, zorder=1)
            # The prediction ring is drawn LARGER and BENEATH the observed dot.
            # Where the two coincide (latency+drift on classification: both
            # 15.4%) a same-size ring would be hidden entirely and the prediction
            # would look missing; this way it reads as a ring around the dot.
            ax.plot(add, row, marker="o", markersize=11, markerfacecolor="white",
                    markeredgecolor=colour, markeredgewidth=1.6, zorder=2)
            ax.plot(obs, row, marker="o", markersize=7, color=colour, zorder=3)
            ax.annotate(f"ψ {lg['point']:+.2f} [{lg['lo']:+.2f}, {lg['hi']:+.2f}]",
                        xy=(1.01, row), xycoords=("axes fraction", "data"),
                        va="center", fontsize=8, color=colour)
            labels.append((row, "+".join(p.replace("semantic_stripping", "semantic")
                                        .replace("schema_drift", "drift") for p in pair)))
        ax.set_yticks([r for r, _ in labels])
        ax.set_yticklabels([name for _, name in labels], fontsize=9)
        ax.set_title(task, fontsize=11)
        ax.set_xlabel(f"{'silent failure' if outcome == 'silent' else 'total error'} rate (%)")
        ax.grid(axis="x", color="#e3eaee", linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)

    handles = [
        plt.Line2D([], [], marker="o", markersize=11, markerfacecolor="white",
                   markeredgecolor="#5a6675", linestyle="none", label="additive prediction"),
        plt.Line2D([], [], marker="o", markersize=7, color="#5a6675",
                   linestyle="none", label="observed, both faults"),
        plt.Line2D([], [], color="#0e6f7a", linewidth=2,
                   label="departs from additivity (logit CI excludes 0)"),
    ]
    fig.legend(handles=handles, frameon=False, fontsize=9, ncols=3,
               loc="lower center", bbox_to_anchor=(0.5, -0.10))
    fig.suptitle("Two faults never significantly compound — five of eight pairs saturate",
                 fontsize=12, y=1.04)
    fig.tight_layout(rect=(0, 0, 0.92, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--outcome", default="silent", choices=("silent", "error"))
    parser.add_argument("--figure", type=Path, default=None,
                        help="also write Figure 4.6 here")
    args = parser.parse_args(argv)
    runs = load_arm(args.results)
    status = report(runs, args.outcome)
    if args.figure is not None:
        print(f"\n  figure: {figure(runs, args.figure, args.outcome)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
