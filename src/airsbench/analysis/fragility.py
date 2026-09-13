"""Are some questions fragile? Testing whether silent failure concentrates.

RQ6 found that two faults together never compound — five of eight pairs
saturate — and a preliminary look at that arm suggested why: different faults
fail the same queries. `gate_findings.md` separately found ~75% of silent
failure present on a fault-free pipeline. Both point at one possibility: silent
failure is not spread evenly over questions, but concentrated on a pool of
fragile ones that fail under almost any degradation. This module tests that,
over every gpt-4o-mini run that shares the main factorial's questions.

## Why pooling across arms is legitimate

The query sample depends only on (task, replication) — invariant 2 — so a given
replication asks the SAME questions in every arm. The detectability and
interaction arms reproduce the main factorial's sequence exactly, and every
freshness-sweep question is drawn from it. That is verified by content (the
retrieval query text; the flight's origin, destination and label), not assumed
from position, and questions are keyed by their position in the main sequence
so that a flight appearing twice is never counted twice. Each question is
observed under a median of ~35 conditions, which is what makes a per-question
property measurable at all.

## The null model

"Some questions fail more often" is trivially true if conditions differ in how
harmful they are. But every question sees the same conditions — the design is
paired — so condition severity cannot make one question look more fragile than
another. The null permutes silent-failure labels across questions WITHIN each
run: every run keeps exactly its own failure count, preserving condition
severity, and only the link between a failure and a particular question is
broken. Concentration beyond that null is a property of the questions.

## What is reported

1. Concentration — the spread of per-question silent-failure counts against
   the null, and the share of faulted silent failures carried by the most
   fragile 10% of questions.
2. Carry-over — the share of faulted silent failures that land on questions
   already silent on the fault-free streaming pipeline.
3. Overlap — Jaccard overlap between the silent-failure sets of pairs of
   faults, and a re-ask reference: baseline against latency, which changes
   nothing the agent reads and so measures how stable silent failure is when
   the identical inputs are simply asked again.

    python -m airsbench.analysis.fragility
    python -m airsbench.analysis.fragility --figure docs/figures/fig4_8_fragility.png
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..runner.config import run_arm
from ..runner.scoring import is_silent_failure

MODEL = "gpt-4o-mini"
SHARED_ARMS = ("main", "freshness_sweep", "interaction", "detectability")
PERMUTATIONS = 2000
SEED = 20260913
TOP_SHARE = 0.10
IMPAIRING_PAIRS = (
    ("freshness", "schema_drift"),
    ("freshness", "semantic_stripping"),
    ("schema_drift", "semantic_stripping"),
)


def question_id(task: str, decision: dict[str, Any]) -> str:
    """Content identity of the question a decision answered."""
    if task == "retrieval":
        return json.dumps(decision.get("query"), sort_keys=True)
    return json.dumps([decision.get("origin"), decision.get("dest"), decision.get("label")])


def align(sequence: list[str], reference: list[str]) -> list[int | None]:
    """Reference position for each question in `sequence`.

    An identical or prefix sequence maps position i to i. Otherwise questions are
    matched by content, left to right, so a question that appears twice in the
    reference is assigned its occurrences in order instead of collapsing onto
    the first — the error that would double-count a duplicated flight. A question
    absent from the reference maps to None.
    """
    if sequence == reference[: len(sequence)]:
        return list(range(len(sequence)))
    slots: dict[str, deque[int]] = defaultdict(deque)
    for position, question in enumerate(reference):
        slots[question].append(position)
    return [slots[q].popleft() if slots.get(q) else None for q in sequence]


@dataclass
class Panel:
    """One (task, replication): questions as rows, runs as columns."""

    task: str
    replication: int
    questions: list[str]
    columns: list[dict[str, Any]]
    silent: np.ndarray  # (questions, runs): 1.0 silent, 0.0 not, nan unobserved
    unmapped: int = 0

    @property
    def faulted(self) -> list[int]:
        return [i for i, c in enumerate(self.columns) if c["fault"] != "none"]

    @property
    def baseline(self) -> int | None:
        """The main arm's streaming, fault-free run — the single clean reference.

        Batch 'none' carries 3 s of inherent staleness and is not fault-free; the
        interaction and detectability baselines are extra replicates of a clean
        condition and are excluded from both roles rather than counted twice.
        """
        for i, c in enumerate(self.columns):
            if (c["arm"] == "main" and c["fault"] == "none"
                    and c["pipeline"] == "streaming" and not c["age"]):
                return i
        return None


def build_panels(runs: list[dict[str, Any]]) -> list[Panel]:
    members: dict[tuple[str, int], list[tuple[str, dict]]] = defaultdict(list)
    for run in runs:
        config = run["config"]
        arm = run_arm(run)
        if config.get("model") == MODEL and arm in SHARED_ARMS:
            members[(config["task"], config["replication"])].append((arm, run))

    panels = []
    for (task, replication), group in sorted(members.items()):
        mains = [run for arm, run in group if arm == "main"]
        if not mains:
            continue
        reference_run = next(
            (r for r in mains if r["config"]["fault_type"] == "none"
             and r["config"]["pipeline"] == "streaming"), mains[0])
        reference = [question_id(task, d) for d in reference_run["decisions"]]

        columns, vectors, unmapped = [], [], 0
        for arm, run in sorted(group, key=lambda m: (m[0], m[1]["run_id"])):
            config = run["config"]
            positions = align([question_id(task, d) for d in run["decisions"]], reference)
            vector = np.full(len(reference), np.nan)
            for decision, position in zip(run["decisions"], positions):
                if position is None:
                    unmapped += 1
                    continue
                vector[position] = 1.0 if is_silent_failure(decision) else 0.0
            columns.append({
                "arm": arm, "run_id": run["run_id"], "pipeline": config["pipeline"],
                "fault": config["fault_type"], "severity": config["severity"],
                "age": bool(config.get("emit_record_age", False)),
            })
            vectors.append(vector)
        panels.append(Panel(task, replication, reference, columns,
                            np.column_stack(vectors), unmapped))
    return panels


def null_sums(values: np.ndarray, rng: np.random.Generator, permutations: int) -> np.ndarray:
    """(permutations, questions) per-question totals under the within-run null.

    Each column's observed entries are shuffled among that column's observed
    rows. Column totals — each run's failure count — and the positions of
    unobserved cells are preserved exactly.
    """
    sums = np.zeros((permutations, values.shape[0]))
    for column in range(values.shape[1]):
        rows = np.flatnonzero(~np.isnan(values[:, column]))
        if rows.size == 0:
            continue
        order = np.argsort(rng.random((permutations, rows.size)), axis=1)
        sums[:, rows] += values[rows, column][order]
    return sums


def lorenz(counts: np.ndarray, observations: np.ndarray) -> np.ndarray:
    """Cumulative share of failures, questions ordered most fragile first."""
    rates = np.divide(counts, observations, out=np.zeros(len(counts)),
                      where=observations > 0)
    order = np.lexsort((-counts, -rates))
    cumulative = np.cumsum(counts[order])
    total = cumulative[-1] if cumulative.size and cumulative[-1] > 0 else 1.0
    return cumulative / total


def _summary(values: np.ndarray) -> dict[str, float]:
    return {"mean": float(np.mean(values)),
            "lo": float(np.percentile(values, 2.5)),
            "hi": float(np.percentile(values, 97.5))}


def _column(panel: Panel, arm: str, fault: str, severity: str,
            pipeline: str = "streaming") -> int | None:
    for i, c in enumerate(panel.columns):
        if (c["arm"] == arm and c["fault"] == fault and c["severity"] == severity
                and c["pipeline"] == pipeline and not c["age"]):
            return i
    return None


def _jaccard_null(a: np.ndarray, b: np.ndarray, rng: np.random.Generator,
                  permutations: int) -> tuple[int, int, np.ndarray, np.ndarray]:
    common = ~np.isnan(a) & ~np.isnan(b)
    in_a = (a == 1.0) & common
    in_b = (b == 1.0) & common
    observed_b = np.flatnonzero(~np.isnan(b))
    shuffled = np.zeros((permutations, b.size))
    order = np.argsort(rng.random((permutations, observed_b.size)), axis=1)
    shuffled[:, observed_b] = b[observed_b][order]
    in_b_null = (shuffled == 1.0) & common[None, :]
    return (int((in_a & in_b).sum()), int((in_a | in_b).sum()),
            (in_b_null & in_a[None, :]).sum(axis=1),
            (in_b_null | in_a[None, :]).sum(axis=1))


def pair_overlap(panels: list[Panel], rng: np.random.Generator,
                 permutations: int) -> list[dict[str, Any]]:
    """Pooled Jaccard (sum of intersections / sum of unions) across replications."""
    specs = [(f"{a} + {b}", ("main", a, "severe"), ("main", b, "severe"))
             for a, b in IMPAIRING_PAIRS]
    specs.append(("re-ask: baseline vs latency, severe",
                  ("main", "none", "none"), ("main", "latency", "severe")))
    rows = []
    for label, spec_a, spec_b in specs:
        inter = union = used = 0
        inter_null = np.zeros(permutations)
        union_null = np.zeros(permutations)
        for panel in panels:
            ca, cb = _column(panel, *spec_a), _column(panel, *spec_b)
            if ca is None or cb is None:
                continue
            i, u, i_null, u_null = _jaccard_null(panel.silent[:, ca], panel.silent[:, cb],
                                                 rng, permutations)
            inter += i
            union += u
            inter_null += i_null
            union_null += u_null
            used += 1
        if not used or not union:
            continue
        observed = inter / union
        null = np.divide(inter_null, union_null, out=np.zeros(permutations),
                         where=union_null > 0)
        rows.append({
            "pair": label, "replications": used, "j": observed, "null": _summary(null),
            "ratio": observed / null.mean() if null.mean() > 0 else float("nan"),
            "p": (1 + int((null >= observed).sum())) / (1 + permutations),
        })
    return rows


def analyse(panels: list[Panel], permutations: int = PERMUTATIONS,
            seed: int = SEED) -> dict[str, dict[str, Any]]:
    rng = np.random.default_rng(seed)
    results: dict[str, dict[str, Any]] = {}
    for task in sorted({p.task for p in panels}):
        task_panels = [p for p in panels if p.task == task]
        counts, observations, expected, nulls = [], [], [], []
        on_baseline = total = 0.0
        on_baseline_null = np.zeros(permutations)
        baseline_hits = baseline_seen = 0

        for panel in task_panels:
            columns = panel.faulted
            if not columns:
                continue
            faulted = panel.silent[:, columns]
            seen = ~np.isnan(faulted)
            count = np.nansum(faulted, axis=1)
            run_rates = np.array([
                np.nanmean(faulted[:, j]) if seen[:, j].any() else 0.0
                for j in range(faulted.shape[1])])
            null = null_sums(faulted, rng, permutations)
            counts.append(count)
            observations.append(seen.sum(axis=1))
            expected.append((seen * run_rates).sum(axis=1))
            nulls.append(null)

            base_column = panel.baseline
            if base_column is not None:
                baseline = panel.silent[:, base_column]
                silent_at_baseline = baseline == 1.0
                baseline_hits += int(silent_at_baseline.sum())
                baseline_seen += int((~np.isnan(baseline)).sum())
                on_baseline += float(count[silent_at_baseline].sum())
                total += float(count.sum())
                on_baseline_null += null[:, silent_at_baseline].sum(axis=1)

        if not counts:
            continue
        count = np.concatenate(counts)
        seen = np.concatenate(observations)
        expected_count = np.concatenate(expected)
        null = np.concatenate(nulls, axis=1)
        keep = seen > 0
        count, seen = count[keep], seen[keep]
        expected_count, null = expected_count[keep], null[:, keep]

        statistic = float(((count - expected_count) ** 2).sum())
        null_statistic = ((null - expected_count) ** 2).sum(axis=1)
        curve = lorenz(count, seen)
        null_curves = np.array([lorenz(row, seen) for row in null])
        top = max(1, int(round(TOP_SHARE * len(count))))

        results[task] = {
            "replications": len(task_panels),
            "questions": int(len(count)),
            "median_observations": float(np.median(seen)),
            "unmapped": sum(p.unmapped for p in task_panels),
            "permutations": permutations,
            "concentration_ratio": (statistic / float(null_statistic.mean())
                                    if null_statistic.mean() > 0 else float("nan")),
            "p_concentration": (1 + int((null_statistic >= statistic).sum())) / (1 + permutations),
            "top_n": top,
            "top_share": float(curve[top - 1]),
            "top_share_null": _summary(null_curves[:, top - 1]),
            "curve": curve,
            "null_band": np.percentile(null_curves, [2.5, 50, 97.5], axis=0),
            "baseline_rate": baseline_hits / baseline_seen if baseline_seen else float("nan"),
            "carryover": on_baseline / total if total else float("nan"),
            "carryover_null": _summary(on_baseline_null / total) if total else None,
            "overlap": pair_overlap(task_panels, rng, permutations),
        }
    return results


def _p(p: float, permutations: int) -> str:
    floor = 1 / (permutations + 1)
    return f"<{floor:.4f}" if p <= floor * 1.0001 else f"{p:.4f}"


def report(results: dict[str, dict[str, Any]]) -> int:
    print(f"Query fragility — {MODEL}, pooled over arms: {', '.join(SHARED_ARMS)}\n")
    print("Null: silent-failure labels permuted across questions WITHIN each run, so")
    print("every run keeps its own failure count and only the question it lands on is")
    print("randomised. Condition severity therefore cannot pass for fragility.\n")
    for task, r in results.items():
        P = r["permutations"]
        print(f"  {task}: {r['replications']} replications, {r['questions']} questions, "
              f"median {r['median_observations']:.0f} faulted observations per question, "
              f"{r['unmapped']} decisions unmapped")
        print(f"    1. concentration  {r['concentration_ratio']:.2f}x the null   "
              f"permutation p {_p(r['p_concentration'], P)}")
        n = r["top_share_null"]
        print(f"       most fragile {TOP_SHARE:.0%} of questions ({r['top_n']}) carry "
              f"{r['top_share']:.1%} of faulted silent failures "
              f"(null {n['mean']:.1%} [{n['lo']:.1%}, {n['hi']:.1%}])")
        c = r["carryover_null"]
        if c:
            print(f"    2. carry-over     {r['baseline_rate']:.1%} of questions are silent on the "
                  f"fault-free streaming pipeline;")
            print(f"       they carry {r['carryover']:.1%} of faulted silent failures "
                  f"(null {c['mean']:.1%} [{c['lo']:.1%}, {c['hi']:.1%}])")
        print("    3. overlap        main arm, streaming, pooled across replications")
        print(f"       {'pair':<40}{'J':>7}{'null J':>9}{'ratio':>9}{'p':>11}")
        for row in r["overlap"]:
            print(f"       {row['pair']:<40}{row['j']:>7.2f}{row['null']['mean']:>9.2f}"
                  f"{row['ratio']:>8.1f}x{_p(row['p'], P):>11}")
        print()
    return 0


def figure(results: dict[str, dict[str, Any]], out_path: Path) -> Path:
    """Figure 4.8 — concentration curves against the within-run null."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tasks = list(results)
    fig, axes = plt.subplots(1, len(tasks), figsize=(5.8 * len(tasks), 4.4), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, task in zip(axes, tasks):
        r = results[task]
        n = len(r["curve"])
        x = 100 * np.arange(1, n + 1) / n
        lo, mid, hi = (100 * band for band in r["null_band"])
        ax.fill_between(x, lo, hi, color="#c9d6e0", linewidth=0, label="null, 95% band")
        ax.plot(x, mid, color="#8a96a3", linewidth=1.2, linestyle="--", label="null, median")
        ax.plot(x, 100 * r["curve"], color="#0e6f7a", linewidth=2.2, label="observed")
        ax.plot([0, 100], [0, 100], color="#dfe5ea", linewidth=0.8, zorder=0)
        cut = 100 * r["top_n"] / n
        ax.axvline(cut, color="#5a6675", linewidth=0.7, linestyle=":")
        ax.annotate(f"most fragile {TOP_SHARE:.0%}:\n{r['top_share']:.0%} observed, "
                    f"{r['top_share_null']['mean']:.0%} null",
                    xy=(cut, 100 * r["top_share"]), xytext=(cut + 12, 100 * r["top_share"] - 22),
                    fontsize=9, color="#0e6f7a",
                    arrowprops=dict(arrowstyle="-", color="#0e6f7a", linewidth=0.6))
        ax.set_title(task, fontsize=11)
        ax.set_xlabel("questions, most fragile first (%)")
        ax.grid(color="#eef2f5", linewidth=0.8)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    axes[0].set_ylabel("cumulative share of faulted silent failures (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, ncols=3,
               loc="lower center", bbox_to_anchor=(0.5, -0.09))
    concentrated = all(r["p_concentration"] < 0.05 for r in results.values())
    fig.suptitle("Silent failure concentrates on a pool of fragile questions" if concentrated
                 else "How silent failure is distributed across questions",
                 fontsize=12, y=1.03)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--permutations", type=int, default=PERMUTATIONS)
    parser.add_argument("--figure", type=Path, default=None, help="also write Figure 4.8 here")
    args = parser.parse_args(argv)
    runs = [json.loads(p.read_text()) for p in sorted(args.results.glob("*.json"))]
    results = analyse(build_panels(runs), permutations=args.permutations)
    status = report(results)
    if args.figure is not None:
        print(f"  figure: {figure(results, args.figure)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
