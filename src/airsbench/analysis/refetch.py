"""The refetch arm: Fig 4.9 and the tests declared in RQs v2 §9 (refined 23 Sep).

    python -m airsbench.analysis.refetch [--results results/runs]
                                         [--figure docs/figures/fig4_9_refetch.png]

Design: docs/refetch_arm.md. The only analysis that reads arm `refetch`; every
other loader drops it (`NEVER_POOLED`), because the arm is a different instrument.

**The unit is the question.** Every cell and both states of a replication asked
the same questions at the same simulated moments, so questions are matched by
`(replication, question_seed)` — never by position — and the bootstrap resamples
matched questions within each replication. Alignment is checked, not assumed:
the same question seeds in every cell, exposure (`flipped_as_delivered`)
identical across the cells of a state, and verifiability identical across all.

**Declared (confirmatory, Holm-corrected together):**
  H-R1a  re-read requests, agent with age shown: stale − healthy
  H-R1b  accuracy on stale questions FLIPPED as first delivered:
         agent with age shown − baseline
**Declared (descriptive):** H-R1c, the age-hidden request rate; H-R2, the verdict
menu — refuse (priced from the baseline), gate re-read, agent — each with its
correct answers forfeited per silent failure prevented, raw and true cost.
**Validation:** the gate's re-read on stale data against the healthy baseline,
question by question — the assumption `gate/replay.py` prices its re-read on.
**Exploratory (noticed 23 Sep during the campaign, never counted toward H-R1):**
the tool-offering prompt against the baseline on HEALTHY data, where a re-read
cannot help — the effect of offering the tool at all.

A rate of 0 has a degenerate bootstrap interval, so request rates carry exact
Clopper–Pearson intervals, and a zero count its one-sided 95% upper bound: "never
asked" is reported as a measured ceiling, not as an absence of data.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..runner.config import REFETCH_CELLS, refetch_cell, run_arm

CELLS = tuple(cell for cell, *_ in REFETCH_CELLS)
STATES = ("healthy", "stale")
DESIGN = tuple((cell, state) for cell, _, _, on_healthy in REFETCH_CELLS
               for state in STATES if state == "stale" or on_healthy)
BOOTSTRAP = 10_000
RNG_SEED = 20260923
LABELS = {"baseline": "baseline (no re-read)", "gate": "gate re-read",
          "agent_hidden": "agent, age hidden", "agent_shown": "agent, age shown",
          "refuse": "refuse"}


class AlignmentError(RuntimeError):
    """The cells did not ask the same questions — no paired contrast is valid."""


def load_arm(results_dir: Path) -> list[dict[str, Any]]:
    runs = (json.loads(p.read_text()) for p in sorted(results_dir.glob("*.json")))
    return [run for run in runs if run_arm(run) == "refetch"]


def cell_state(run: dict[str, Any]) -> tuple[str, str]:
    state = "healthy" if run["config"]["fault_type"] == "none" else "stale"
    return refetch_cell(run["config"]), state


# ---- alignment -----------------------------------------------------------------------

@dataclass
class Aligned:
    """Decisions of every (cell, state), index-aligned question by question."""

    replications: list[int]
    rep: Any                   # np.ndarray[int], the replication of each question
    seeds: list[tuple[int, int]]
    decisions: dict[tuple[str, str], list[dict[str, Any]]]
    verifiable: Any            # np.ndarray[bool]
    flipped: dict[str, Any]    # state -> np.ndarray[bool]; False where unverifiable

    @property
    def n(self) -> int:
        return len(self.seeds)

    def vector(self, cell: str, state: str, outcome: str):
        import numpy as np

        decisions = self.decisions[(cell, state)]
        if outcome == "asked":
            values = [d["refetch"]["initiated_by"] == "agent" for d in decisions]
        elif outcome == "reread":
            values = [bool(d["refetch"]["attempted"]) for d in decisions]
        elif outcome == "correct":
            values = [bool(d["correct"]) for d in decisions]
        elif outcome == "silent":
            values = [bool(d["silent_failure"]) for d in decisions]
        elif outcome == "abstained":
            values = [bool(d["abstained"]) for d in decisions]
        elif outcome == "unanswered":
            values = [bool(d["parse_failed"] or d["unanswered_action"]) for d in decisions]
        else:
            raise ValueError(f"unknown outcome {outcome!r}")
        return np.array(values, dtype=bool)

    def usd(self, cell: str, state: str) -> float:
        return sum(d["usage"]["usd"] for d in self.decisions[(cell, state)])


def align(runs: list[dict[str, Any]]) -> Aligned:
    """Match every cell's decisions question by question, or refuse to.

    Only replications holding every cell of the design are used: a partially run
    replication would unbalance each contrast it entered.
    """
    import numpy as np

    by_rep: dict[int, dict[tuple[str, str], dict]] = {}
    for run in runs:
        slot = by_rep.setdefault(run["config"]["replication"], {})
        key = cell_state(run)
        if key in slot:
            raise AlignmentError(f"replication {run['config']['replication']}: "
                                 f"{key} was run twice — which one counts is not "
                                 f"for the analysis to guess")
        slot[key] = run
    complete = sorted(rep for rep, slot in by_rep.items() if set(slot) == set(DESIGN))
    if not complete:
        raise AlignmentError(f"no replication holds all {len(DESIGN)} cells yet "
                             f"(have: {sorted((r, len(s)) for r, s in by_rep.items())})")

    seeds: list[tuple[int, int]] = []
    decisions: dict[tuple[str, str], list[dict]] = {key: [] for key in DESIGN}
    for rep in complete:
        per_cell = {key: {d["question_seed"]: d for d in by_rep[rep][key]["decisions"]}
                    for key in DESIGN}
        order = sorted(per_cell[DESIGN[0]])
        for key, found in per_cell.items():
            if sorted(found) != order:
                raise AlignmentError(f"replication {rep}: {key} asked different questions "
                                     f"from {DESIGN[0]} — the pairing is broken")
        for seed in order:
            seeds.append((rep, seed))
            for key in DESIGN:
                decisions[key].append(per_cell[key][seed])

    verifiable = np.array([d["verifiable"] for d in decisions[DESIGN[0]]], dtype=bool)
    for key in DESIGN:
        if [d["verifiable"] for d in decisions[key]] != verifiable.tolist():
            raise AlignmentError(f"{key}: a different set of questions is verifiable — "
                                 f"the answer key must not depend on the cell")
    flipped = {}
    for state in STATES:
        keys = [key for key in DESIGN if key[1] == state]
        first = [d["flipped_as_delivered"] for d in decisions[keys[0]]]
        for key in keys[1:]:
            if [d["flipped_as_delivered"] for d in decisions[key]] != first:
                raise AlignmentError(f"{key}: exposure as first delivered differs from "
                                     f"{keys[0]} in the same state — it cannot, by design")
        flipped[state] = np.array([bool(f) for f in first], dtype=bool) & verifiable
    return Aligned(complete, np.array([rep for rep, _ in seeds]), seeds, decisions,
                   verifiable, flipped)


# ---- statistics ----------------------------------------------------------------------

def paired(x, y, rep, mask=None, *, boot: int = BOOTSTRAP) -> dict[str, Any]:
    """Mean(x) − mean(y) over matched questions, bootstrapped within replication.

    Returned with the discordant counts — questions where the two cells disagree
    — because only those carry information about a paired difference.
    """
    import numpy as np

    mask = np.ones(len(x), dtype=bool) if mask is None else mask
    xs, ys, reps = x[mask].astype(float), y[mask].astype(float), rep[mask]
    n = len(xs)
    out = {"n": int(n), "x": float(xs.mean()) if n else None,
           "y": float(ys.mean()) if n else None,
           "b": int(((xs == 1) & (ys == 0)).sum()), "c": int(((xs == 0) & (ys == 1)).sum())}
    if n == 0:
        return {**out, "point": None, "lo": None, "hi": None, "p": None}
    point = float(xs.mean() - ys.mean())
    if out["b"] == 0 and out["c"] == 0:
        return {**out, "point": point, "lo": 0.0, "hi": 0.0, "p": 1.0}
    rng = np.random.default_rng(RNG_SEED)
    columns = []
    for r in np.unique(reps):
        group = np.flatnonzero(reps == r)
        columns.append(group[rng.integers(0, len(group), size=(boot, len(group)))])
    index = np.concatenate(columns, axis=1)
    draws = xs[index].mean(axis=1) - ys[index].mean(axis=1)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    p = float(min(1.0, 2 * min((draws <= 0).mean(), (draws >= 0).mean())))
    return {**out, "point": point, "lo": float(lo), "hi": float(hi), "p": p}


def exact_rate(k: int, n: int) -> dict[str, Any]:
    """Clopper–Pearson 95%; for k = 0, the one-sided 95% upper bound."""
    from scipy.stats import beta

    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "lo": None, "hi": None}
    if k == 0:
        return {"k": 0, "n": n, "rate": 0.0, "lo": 0.0, "hi": 1 - 0.05 ** (1 / n),
                "one_sided": True}
    lo = beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(0.975, k + 1, n - k)
    return {"k": k, "n": n, "rate": k / n, "lo": float(lo), "hi": float(hi),
            "one_sided": False}


def holm(pvalues: dict[str, float | None]) -> dict[str, float | None]:
    """Holm step-down adjustment over the declared confirmatory tests."""
    known = sorted((p, name) for name, p in pvalues.items() if p is not None)
    adjusted: dict[str, float | None] = {name: None for name in pvalues}
    running = 0.0
    for i, (p, name) in enumerate(known):
        running = max(running, min(1.0, (len(known) - i) * p))
        adjusted[name] = running
    return adjusted


# ---- the analyses ----------------------------------------------------------------------

def rates(a: Aligned) -> dict[tuple[str, str], dict[str, Any]]:
    v = a.verifiable
    out = {}
    for cell, state in DESIGN:
        asked = a.vector(cell, state, "asked")
        out[(cell, state)] = {
            "n": a.n, "n_verifiable": int(v.sum()),
            "accuracy": float(a.vector(cell, state, "correct")[v].mean()),
            "silent": float(a.vector(cell, state, "silent")[v].mean()),
            "abstained": float(a.vector(cell, state, "abstained")[v].mean()),
            "unanswered": float(a.vector(cell, state, "unanswered")[v].mean()),
            "reread": float(a.vector(cell, state, "reread").mean()),
            "asked": exact_rate(int(asked.sum()), a.n),
            "usd": a.usd(cell, state),
        }
    return out


def hypotheses(a: Aligned) -> dict[str, Any]:
    stale_flipped = a.flipped["stale"]
    h1a = paired(a.vector("agent_shown", "stale", "asked"),
                 a.vector("agent_shown", "healthy", "asked"), a.rep)
    h1b = paired(a.vector("agent_shown", "stale", "correct"),
                 a.vector("baseline", "stale", "correct"), a.rep, stale_flipped)
    h1b_silent = paired(a.vector("agent_shown", "stale", "silent"),
                        a.vector("baseline", "stale", "silent"), a.rep, stale_flipped)
    adjusted = holm({"H-R1a": h1a["p"], "H-R1b": h1b["p"]})
    return {"H-R1a": {**h1a, "p_holm": adjusted["H-R1a"]},
            "H-R1b": {**h1b, "p_holm": adjusted["H-R1b"]},
            "H-R1b_silent": h1b_silent,
            "H-R1c": {state: exact_rate(int(a.vector("agent_hidden", state, "asked").sum()),
                                        a.n) for state in STATES}}


def menu(a: Aligned) -> list[dict[str, Any]]:
    """H-R2: every verdict on the stale questions, against admitting them all.

    A silent failure is GENUINELY prevented only if the healthy baseline got the
    same question right or abstained — otherwise the model was always going to
    fail it and the fault did not cause it. That is the true-cost denominator,
    per question, for every verdict alike.
    """
    v = a.verifiable
    admit_silent = a.vector("baseline", "stale", "silent")[v]
    admit_correct = a.vector("baseline", "stale", "correct")[v]
    floor_silent = a.vector("baseline", "healthy", "silent")[v]
    rows = [{
        "verdict": "refuse", "prevented": int(admit_silent.sum()), "introduced": 0,
        "genuine": int((admit_silent & ~floor_silent).sum()),
        "forfeited": int(admit_correct.sum()), "gained": 0, "reads": 0, "usd": 0.0,
    }]
    for cell in ("gate", "agent_hidden", "agent_shown"):
        silent = a.vector(cell, "stale", "silent")[v]
        correct = a.vector(cell, "stale", "correct")[v]
        rows.append({
            "verdict": cell,
            "prevented": int((admit_silent & ~silent).sum()),
            "introduced": int((~admit_silent & silent).sum()),
            "genuine": int((admit_silent & ~silent & ~floor_silent).sum()),
            "forfeited": int((admit_correct & ~correct).sum()),
            "gained": int((~admit_correct & correct).sum()),
            "reads": int(a.vector(cell, "stale", "reread").sum()),
            "usd": a.usd(cell, "stale"),
        })
    for row in rows:
        row["raw"] = row["forfeited"] / row["prevented"] if row["prevented"] else None
        row["true"] = row["forfeited"] / row["genuine"] if row["genuine"] else None
        row["reads_per_prevented"] = (row["reads"] / row["prevented"]
                                      if row["prevented"] and row["reads"] else None)
    return rows


def gate_vs_healthy(a: Aligned) -> dict[str, Any]:
    """Is a re-read the healthy pipeline? The assumption gate/replay.py prices on."""
    v = a.verifiable
    gate = a.vector("gate", "stale", "correct")
    healthy = a.vector("baseline", "healthy", "correct")
    return {"correct": paired(gate, healthy, a.rep, v),
            "silent": paired(a.vector("gate", "stale", "silent"),
                             a.vector("baseline", "healthy", "silent"), a.rep, v),
            "agreement": float((gate[v] == healthy[v]).mean())}


def prompt_effect(a: Aligned) -> dict[str, Any]:
    """EXPLORATORY. The tool-offering prompt vs the standard one, on healthy data."""
    v = a.verifiable
    out = {}
    for cell in ("agent_hidden", "agent_shown"):
        out[cell] = {outcome: paired(a.vector(cell, "healthy", outcome),
                                     a.vector("baseline", "healthy", outcome), a.rep, v)
                     for outcome in ("correct", "silent", "abstained")}
    return out


# ---- the figure ------------------------------------------------------------------------

COLOURS = {"correct": "#4C9A6A", "silent": "#C8553D", "abstained": "#8A8FA3",
           "unanswered": "#E3B23C"}


def figure(a: Aligned, out_path: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    table = rates(a)
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.6),
                             gridspec_kw={"width_ratios": [1, 1.5, 1.25]})

    # ---- A: re-read requests -----------------------------------------------------------
    ax = axes[0]
    positions, heights, errors, colours, ticks = [], [], [[], []], [], []
    for i, cell in enumerate(("agent_hidden", "agent_shown")):
        for j, state in enumerate(STATES):
            r = table[(cell, state)]["asked"]
            positions.append(i * 2.6 + j)
            heights.append(100 * r["rate"])
            errors[0].append(100 * (r["rate"] - r["lo"]))
            errors[1].append(100 * (r["hi"] - r["rate"]))
            colours.append("#9DB4C0" if state == "healthy" else "#3D5A80")
            ticks.append(f"{'hidden' if cell == 'agent_hidden' else 'shown'}\n{state}")
    ax.bar(positions, heights, color=colours, width=0.8)
    ax.errorbar(positions, heights, yerr=errors, fmt="none", ecolor="#222", capsize=4)
    for x, h, r in zip(positions, heights, [table[(c, s)]["asked"] for c in
                                            ("agent_hidden", "agent_shown") for s in STATES]):
        ax.text(x, h + errors[1][positions.index(x)] + 0.3, f"{r['k']}/{r['n']}",
                ha="center", fontsize=8)
    ax.set_xticks(positions, ticks, fontsize=8)
    ax.set_ylabel("questions where the agent asked to re-read (%)")
    ax.set_title("A. Offered a re-read, does the agent ask?", fontsize=10, loc="left")
    ax.text(0.02, 0.97, "age: hidden / shown to the agent\nbars: exact 95% CI "
            "(one-sided upper bound at 0)\ngate: re-reads 100% of stale, 0% of healthy",
            transform=ax.transAxes, va="top", fontsize=7.5, color="#444")
    ax.set_ylim(0, max(10, max(h + e for h, e in zip(heights, errors[1])) * 1.35))

    # ---- B: outcomes on stale questions, flipped vs unflipped --------------------------
    ax = axes[1]
    rows = [("baseline", "healthy")] + [(c, "stale") for c in CELLS]
    groups = (("flipped", a.flipped["stale"]),
              ("unflipped", a.verifiable & ~a.flipped["stale"]))
    y, labels = 0.0, []
    for g, (name, mask) in enumerate(groups):
        for cell, state in rows:
            left = 0.0
            for outcome in ("correct", "silent", "abstained", "unanswered"):
                share = float(a.vector(cell, state, outcome)[mask].mean()) if mask.any() else 0
                ax.barh(y, 100 * share, left=100 * left, color=COLOURS[outcome],
                        edgecolor="white", height=0.8)
                left += share
            labels.append((y, f"{LABELS[cell]}{' (healthy)' if state == 'healthy' else ''}"))
            y -= 1
        ax.text(101, y + len(rows) / 2 + 0.5, f"{name}\nn={int(mask.sum())}",
                fontsize=8, va="center")
        y -= 0.8
    ax.set_yticks([p for p, _ in labels], [t for _, t in labels], fontsize=8)
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of questions (%) — the same questions in every row")
    ax.set_title("B. Outcomes on stale questions, by exposure as first delivered",
                 fontsize=10, loc="left")
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOURS[o]) for o in COLOURS]
    ax.legend(handles, list(COLOURS), fontsize=7.5, loc="lower right", ncol=4,
              bbox_to_anchor=(1.0, -0.2), frameon=False)

    # ---- C: the verdict menu -----------------------------------------------------------
    ax = axes[2]
    # The agents usually sit on top of each other near the origin; their labels
    # go above and below, refusal's to the left of its point.
    offsets = {"refuse": ((-8, 8), "right"), "gate": ((8, -4), "left"),
               "agent_hidden": ((8, 16), "left"), "agent_shown": ((8, -22), "left")}
    for row in menu(a):
        net_forfeited = row["forfeited"] - row["gained"]
        ax.scatter(row["prevented"], net_forfeited, s=70, color="#3D5A80", zorder=3)
        raw = "—" if row["raw"] is None else f"{row['raw']:.2f}"
        true = "—" if row["true"] is None else f"{row['true']:.2f}"
        extra = f", {row['reads']} re-reads" if row["reads"] else ""
        offset, align_to = offsets[row["verdict"]]
        ax.annotate(f"{LABELS[row['verdict']]}\nraw {raw} · true {true}{extra}",
                    (row["prevented"], net_forfeited), textcoords="offset points",
                    xytext=offset, ha=align_to, fontsize=7.5)
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_xlabel("silent failures prevented (vs admitting every stale answer)")
    ax.set_ylabel("correct answers forfeited, net")
    ax.set_title("C. The verdict menu on stale data", fontsize=10, loc="left")
    ax.margins(x=0.35, y=0.25)

    reps = len(a.replications)
    fig.suptitle(f"Fig 4.9 — The refetch arm: gpt-4o-mini, {a.n} matched questions per "
                 f"cell ({reps} replication{'s' if reps != 1 else ''}), "
                 f"freshness 5.05 s vs healthy",
                 fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ---- the report ---------------------------------------------------------------------------

def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def _interval(r: dict[str, Any]) -> str:
    if r["point"] is None:
        return "no questions"
    # A bootstrap cannot show p below one in BOOTSTRAP resamples.
    p = (f"p<{1 / BOOTSTRAP:g}" if r["p"] == 0
         else f"p={r['p']:.4f}" if r["p"] < 0.001 else f"p={r['p']:.3f}")
    return (f"{100 * r['point']:+.1f} pp [{100 * r['lo']:+.1f}, {100 * r['hi']:+.1f}] "
            f"{p} · discordant {r['b']}/{r['c']} · n={r['n']}")


def _rate(r: dict[str, Any]) -> str:
    if r["rate"] is None:
        return "—"
    if r.get("one_sided"):
        return f"{r['k']}/{r['n']} (≤ {100 * r['hi']:.2f}% at 95%)"
    return f"{r['k']}/{r['n']} = {_pct(r['rate'])} [{_pct(r['lo'])}, {_pct(r['hi'])}]"


def report(a: Aligned) -> int:
    table = rates(a)
    print(f"Refetch arm — {len(a.replications)} complete replication(s) "
          f"{a.replications}, {a.n} matched questions per cell, "
          f"{int(a.verifiable.sum())} verifiable")
    print(f"Exposure as first delivered: {int(a.flipped['stale'].sum())} stale questions "
          f"flipped ({_pct(a.flipped['stale'].sum() / a.verifiable.sum())}), "
          f"{int(a.flipped['healthy'].sum())} healthy\n")

    print(f"  {'cell':<24}{'state':<9}{'accuracy':>9}{'silent':>8}{'abstain':>9}"
          f"{'unansw':>8}{'re-read':>9}  {'agent asked':<30}{'$':>8}")
    print("  " + "-" * 114)
    for (cell, state), r in table.items():
        print(f"  {LABELS[cell]:<24}{state:<9}{_pct(r['accuracy']):>9}{_pct(r['silent']):>8}"
              f"{_pct(r['abstained']):>9}{_pct(r['unanswered']):>8}{_pct(r['reread']):>9}  "
              f"{_rate(r['asked']):<30}{r['usd']:>8.4f}")

    h = hypotheses(a)
    print("\nDeclared — confirmatory (Holm over H-R1a, H-R1b):")
    print(f"  H-R1a  asked, age shown, stale − healthy:  {_interval(h['H-R1a'])}"
          f"  Holm p={h['H-R1a']['p_holm']:.3f}")
    print(f"  H-R1b  accuracy on flipped, age shown − baseline:  {_interval(h['H-R1b'])}"
          + (f"  Holm p={h['H-R1b']['p_holm']:.3f}" if h["H-R1b"]["p_holm"] is not None
             else ""))
    print(f"         silent failure on flipped, same contrast:  {_interval(h['H-R1b_silent'])}")
    print("Declared — descriptive:")
    for state in STATES:
        print(f"  H-R1c  asked, age hidden, {state}: {_rate(h['H-R1c'][state])}")

    print("\n  H-R2   the verdict menu on stale questions (against admitting them all):")
    print(f"  {'verdict':<24}{'prevented':>10}{'genuine':>9}{'introduced':>11}"
          f"{'forfeited':>10}{'gained':>8}{'raw':>7}{'true':>7}{'re-reads':>10}{'$':>9}")
    for row in menu(a):
        raw = "—" if row["raw"] is None else f"{row['raw']:.2f}"
        true = "—" if row["true"] is None else f"{row['true']:.2f}"
        print(f"  {LABELS[row['verdict']]:<24}{row['prevented']:>10}{row['genuine']:>9}"
              f"{row['introduced']:>11}{row['forfeited']:>10}{row['gained']:>8}{raw:>7}"
              f"{true:>7}{row['reads']:>10}{row['usd']:>9.4f}")
    print("  genuine = prevented where the healthy baseline did not fail the same question;"
          " raw/true =\n  forfeited per prevented / per genuine. Refusal spends nothing "
          "because no model is called.")

    g = gate_vs_healthy(a)
    print("\nValidation — a gate re-read on stale data vs the healthy baseline "
          "(what gate/replay.py assumes):")
    print(f"  accuracy {_interval(g['correct'])}")
    print(f"  silent   {_interval(g['silent'])}")
    print(f"  same correctness on {_pct(g['agreement'])} of questions")

    e = prompt_effect(a)
    print("\nEXPLORATORY (noticed 23 Sep during the campaign; not part of H-R1) — the "
          "tool-offering\nprompt against the standard one on HEALTHY data, where a "
          "re-read cannot help:")
    for cell, outcomes in e.items():
        for outcome, r in outcomes.items():
            print(f"  {LABELS[cell]:<20} {outcome:<10} {_interval(r)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--figure", type=Path, default=None,
                        help="write Fig 4.9 to this path")
    args = parser.parse_args(argv)
    runs = load_arm(args.results)
    if not runs:
        print("No refetch-arm runs found (seeds 90000-100000). "
              "Run: python -m airsbench.runner.run --refetch-arm --dry-run")
        return 1
    try:
        aligned = align(runs)
    except AlignmentError as exc:
        print(f"Cannot analyse the refetch arm: {exc}")
        return 1
    status = report(aligned)
    if args.figure:
        print(f"\n  figure: {figure(aligned, args.figure)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
