"""The live-source case study: Fig 4.11 and H-L (RQs v2 §9).

    python -m airsbench.analysis.livecase [--db data/livecase/velib.db]
                                          [--figure docs/figures/fig4_11_livecase.png]

Design: docs/live_case_study.md. The only analysis that reads arm `livecase`;
every corpus loader drops it (`NEVER_POOLED`).

Three kinds of evidence, kept apart:

- **The recording itself** — how fast the feed moved, how old the records were.
- **Exposure at scale, $0** — the literal answerer (the question's plan executed on
  the served records at face value) over `EXPOSURE_N` questions per cache: how
  often each pipeline's lag moved the answer key, with no model involved. The paid
  runs' questions are the first of these, so the two agree where they overlap.
- **The paid cells** — two models x two caches, the same questions: outcomes, the
  four attribution labels, and **H-L**: does AIRS rank the answers that fail above
  the answers that do not? Reported as an AUC with a bootstrap interval, beside
  freshness alone and the model's own confidence (RQ4's comparison, on real data).
  A null is reportable.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

from ..runner.config import LIVECASE_CACHES, run_arm

EXPOSURE_N = 600
BOOTSTRAP = 2_000
RNG_SEED = 20260923
LABELS = ("correct", "answer_key_moved", "both", "corrupted_in_transit", "agent_impairment")


def load_arm(results_dir: Path) -> list[dict[str, Any]]:
    runs = (json.loads(p.read_text()) for p in sorted(results_dir.glob("*.json")))
    return [run for run in runs if run_arm(run) == "livecase"]


def cache_of(run: dict[str, Any]) -> int:
    return int(run["config"]["pipeline"].removeprefix("velib-cache-").removesuffix("min"))


# ---- the recording ----------------------------------------------------------------------

def recording_summary(db: Path) -> dict[str, Any]:
    with closing(sqlite3.connect(f"{Path(db).resolve().as_uri()}?mode=ro", uri=True)) as c:
        first, last, polls = c.execute("SELECT MIN(at), MAX(at), COUNT(*) FROM polls "
                                       "WHERE kind = 'upstream'").fetchone()
        errors = dict(c.execute("SELECT kind, COUNT(*) FROM polls WHERE status != 'ok' "
                                "GROUP BY kind").fetchall())
        changes = c.execute("SELECT COUNT(*) FROM upstream").fetchone()[0]
        stations = c.execute("SELECT COUNT(DISTINCT station_id) FROM upstream").fetchone()[0]
        snapshots = {m: c.execute(f"SELECT COUNT(DISTINCT recorded_at) FROM cache_{m}")
                     .fetchone()[0] for m in LIVECASE_CACHES}
    minutes = (last - first) / 60 if last and first else 0.0
    return {"first": first, "last": last, "minutes": minutes, "polls": polls,
            "errors": errors, "stations": stations,
            # Every station's first sighting is a row; the rest are changes.
            "changes_per_minute": (changes - stations) / minutes if minutes else None,
            "snapshots": snapshots}


# ---- exposure at scale, $0 ---------------------------------------------------------------

def exposure(db: Path, n: int = EXPOSURE_N) -> dict[str, Any]:
    """The literal answerer over `n` questions per cache — the same seeds as the paid
    runs — for flip rates, lags and record ages, with no model involved."""
    from ..analyst.answerers import LiteralAnswerer
    from ..analyst.loop import Loop
    from ..gate.policy import Policy
    from ..livecase.questions import question, question_type
    from ..livecase.replay import Recording
    from ..runner.config import build_livecase
    from ..runner.refetch import question_seed

    recording = Recording(db)
    config = build_livecase(n_queries=n)[0]
    out: dict[str, Any] = {}
    for minutes in recording.caches:
        loop = Loop(pair=recording.pair(minutes), policy=Policy(name="open"),
                    answerer=LiteralAnswerer(), mode="off")
        rows = []
        for index in range(n):
            tick = loop.ask(question(index), seed=question_seed(config, index))
            decision, records = tick["decision"], tick["records"]
            rows.append({
                "type": question_type(index), "verifiable": decision["verifiable"],
                "flipped": bool(decision.get("flipped")),
                "cache_age": records["simulated_time"]
                - recording.snapshot_at(minutes, records["simulated_time"]),
                "record_age": tick["gate"]["record_age_seconds"],
                "airs": tick["gate"]["airs"],
                "consistency": tick["airs"]["dimensions"]["consistency"]["score"],
            })
        out[minutes] = rows
    return out


def rate(k: int, n: int) -> dict[str, Any]:
    from .refetch import exact_rate

    return exact_rate(k, n)


def exposure_table(rows_by_cache: dict[int, list[dict]]) -> dict[tuple[int, str], dict]:
    table = {}
    for minutes, rows in rows_by_cache.items():
        for kind in ("all", "bikes", "docks", "empty"):
            chosen = [r for r in rows if r["verifiable"] and (kind == "all" or r["type"] == kind)]
            table[(minutes, kind)] = rate(sum(r["flipped"] for r in chosen), len(chosen))
    return table


# ---- the paid cells ----------------------------------------------------------------------

def outcomes(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in sorted(runs, key=lambda r: (r["config"]["model"], cache_of(r))):
        decisions = [d for d in run["decisions"] if d["verifiable"]]
        labels = Counter(d["attribution"] for d in decisions if d["attribution"])
        rows.append({
            "model": run["config"]["model"], "cache": cache_of(run), "n": len(decisions),
            "correct": sum(bool(d["correct"]) for d in decisions),
            "silent": sum(bool(d["silent_failure"]) for d in decisions),
            "abstained": sum(bool(d["abstained"]) for d in decisions),
            "unanswered": sum(bool(d["parse_failed"]) for d in decisions),
            "flipped": sum(bool(d["flipped"]) for d in decisions),
            "labels": {label: labels.get(label, 0) for label in LABELS},
            "usd": run["usage"]["cost_usd"],
        })
    return rows


class LoggedAnswers:
    """Answers the logged decision gave, replayed — no model is called."""

    name = "logged"

    def __init__(self) -> None:
        self.current: dict[str, Any] = {}

    def answer(self, question, plan, records):
        from ..analyst.answerers import Usage
        from ..analyst.verifier import AgentAnswer

        d = self.current
        return AgentAnswer(value=d["value"], confidence=d["confidence"] or 0.0,
                           abstained=bool(d["abstained"]), parse_failed=bool(d["parse_failed"]),
                           text=""), Usage(self.name)


def reverify(runs: list[dict[str, Any]], db: Path, reference: str = "version",
             freshness_target_s: float | None = None) -> list[dict[str, Any]]:
    """The paid answers, graded again against a chosen consistency reference, at $0.

    Every question regenerates from the committed recording and its seed, and the
    model's logged answer is replayed into the same loop, so only the grading
    reference changes. Under `reference="clock"` — how the runs were executed —
    this must reproduce every logged label exactly (`agreement`); that is what
    licenses reading the `version` re-grading as a correction, not a new run.
    """
    import copy

    from ..analyst.loop import Loop
    from ..gate.policy import Policy
    from ..livecase.questions import question, question_type
    from ..livecase.replay import Recording
    from ..runner.refetch import decision

    recording = Recording(db, reference=reference)
    replayed = []
    for run in runs:
        answers = LoggedAnswers()
        loop = Loop(pair=recording.pair(cache_of(run), freshness_target_s),
                    policy=Policy(name="open"), answerer=answers, mode="off")
        out = copy.deepcopy(run)
        for index, logged in enumerate(run["decisions"]):
            if question_type(index) != logged["question_type"]:
                raise ValueError(f"question {index} is not the logged question")
            answers.current = logged
            tick = loop.ask(question(index), seed=logged["question_seed"])
            if tick["records"]["ids"] != logged["ids"]:
                raise ValueError(f"question {index} regenerated different stations")
            row = decision(tick, tick["decision"].get("flipped"))
            for key in ("question_type", "question", "cache_age_seconds", "usage",
                        "plan_matches_question", "agent_plan_agrees"):
                row[key] = logged.get(key)
            out["decisions"][index] = row
        replayed.append(out)
    return replayed


GRADED = ("correct", "silent_failure", "attribution", "flipped", "verifiable")


def agreement(logged: list[dict[str, Any]], regraded: list[dict[str, Any]]) -> dict[str, Any]:
    """How many decisions the re-grading reproduces, field by field."""
    pairs = [(a, b) for r1, r2 in zip(logged, regraded)
             for a, b in zip(r1["decisions"], r2["decisions"])]
    same = sum(all(a[k] == b[k] for k in GRADED) and
               abs((a["airs_first"] or 0) - (b["airs_first"] or 0)) < 1e-9 for a, b in pairs)
    return {"decisions": len(pairs), "identical": same}


def _auc(labels: list[int], scores: list[float]) -> float | None:
    from .airs_calibration import auc

    if len(set(labels)) < 2:
        return None
    return auc(labels, scores)


def discrimination(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """H-L: how well each signal ranks silent failures above everything else.

    Scores are oriented so higher = riskier: 100 − AIRS, the records' age, and
    1 − the model's confidence. Over committed or abstained verifiable answers;
    an interval by resampling questions (2 000 draws).

    **The cache's own age** is a reference signal, not one AIRS could have: it is the
    pipeline's lag (time since its copy), which the pipeline never stamps on the
    records. The records' `last_reported` is the station's report time — and a
    quiet station reports rarely, so it can be old while the numbers are current.
    Beside AIRS it shows what a freshness measure fed the right clock would see.
    """
    import numpy as np

    rows = [d for run in runs for d in run["decisions"]
            if d["verifiable"] and d["airs_first"] is not None]
    if not rows:
        return {}
    labels = np.array([int(bool(d["silent_failure"])) for d in rows])
    signals = {
        "AIRS": np.array([100 - d["airs_first"] for d in rows]),
        "record age": np.array([d["gate"]["record_age_seconds"] or 0.0 for d in rows]),
        "cache age": np.array([d.get("cache_age_seconds") or 0.0 for d in rows]),
        "confidence": np.array([1 - (d["confidence"] or 0.0) for d in rows]),
    }
    rng = np.random.default_rng(RNG_SEED)
    out: dict[str, Any] = {"n": len(rows), "silent": int(labels.sum())}
    for name, scores in signals.items():
        point = _auc(labels.tolist(), scores.tolist())
        draws = []
        for _ in range(BOOTSTRAP):
            index = rng.integers(0, len(rows), len(rows))
            value = _auc(labels[index].tolist(), scores[index].tolist())
            if value is not None:
                draws.append(value)
        lo, hi = (np.percentile(draws, [2.5, 97.5]) if draws else (None, None))
        out[name] = {"auc": point, "lo": None if lo is None else float(lo),
                     "hi": None if hi is None else float(hi)}
    return out


def cache_contrast(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Silent failure, 15-min cache − 5-min cache, per model, paired by question."""
    import numpy as np

    from .refetch import paired

    out = {}
    for model in sorted({r["config"]["model"] for r in runs}):
        by_cache = {cache_of(r): {d["question_seed"]: d for d in r["decisions"]}
                    for r in runs if r["config"]["model"] == model}
        if not {5, 15} <= set(by_cache):
            continue
        seeds = sorted(set(by_cache[5]) & set(by_cache[15]))
        keep = [s for s in seeds if by_cache[5][s]["verifiable"]]
        x = np.array([bool(by_cache[15][s]["silent_failure"]) for s in keep])
        y = np.array([bool(by_cache[5][s]["silent_failure"]) for s in keep])
        out[model] = paired(x, y, np.ones(len(keep), dtype=int))
    return out


# ---- the figure --------------------------------------------------------------------------

def figure(summary, exposure_rows, runs, out_path: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from sklearn.metrics import roc_curve

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.4),
                             gridspec_kw={"width_ratios": [1.1, 1.2, 1]})

    # A: exposure by cache interval and question type ($0, literal)
    ax = axes[0]
    table = exposure_table(exposure_rows)
    kinds = ("bikes", "docks", "empty", "all")
    width = 0.38
    for j, minutes in enumerate(sorted(exposure_rows)):
        xs = np.arange(len(kinds)) + (j - 0.5) * width
        vals = [table[(minutes, k)] for k in kinds]
        rates = [100 * v["rate"] if v["rate"] is not None else 0 for v in vals]
        err = [[100 * (v["rate"] - v["lo"]) for v in vals], [100 * (v["hi"] - v["rate"])
                                                             for v in vals]]
        ax.bar(xs, rates, width, label=f"cache every {minutes} min",
               color="#9DB4C0" if minutes == min(exposure_rows) else "#3D5A80")
        ax.errorbar(xs, rates, yerr=err, fmt="none", ecolor="#222", capsize=3)
    ax.set_xticks(np.arange(len(kinds)), kinds)
    ax.set_ylabel("questions whose answer the lag moved (%)")
    n = len(next(iter(exposure_rows.values())))
    ax.set_title(f"A. Exposure: how often the pipeline moved the answer\n"
                 f"({n} questions per cache, no model, exact 95% CI)", fontsize=10, loc="left")
    ax.legend(fontsize=8, frameon=False)

    # B: outcomes by model and cache (paid)
    ax = axes[1]
    colours = {"correct": "#4C9A6A", "silent": "#C8553D", "abstained": "#8A8FA3",
               "unanswered": "#E3B23C"}
    rows = outcomes(runs)
    for i, row in enumerate(rows):
        left = 0.0
        for key in colours:
            share = row[key] / row["n"] if row["n"] else 0
            ax.barh(i, 100 * share, left=100 * left, color=colours[key], edgecolor="white")
            left += share
        moved = row["labels"]["answer_key_moved"] + row["labels"]["both"]
        ax.text(101, i, f"{moved} of {row['silent']} silent\nfrom the lag", fontsize=7,
                va="center")
    ax.set_yticks(range(len(rows)), [f"{r['model']}\ncache {r['cache']} min" for r in rows],
                  fontsize=8)
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of verifiable questions (%)")
    ax.set_title("B. Outcomes, same questions in every row", fontsize=10, loc="left")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colours.values()]
    ax.legend(handles, list(colours), fontsize=7.5, ncol=4, frameon=False, loc="lower right",
              bbox_to_anchor=(1.0, -0.22))

    # C: ROC — does AIRS rank the failures first? (pooled, paid)
    ax = axes[2]
    disc = discrimination(runs)
    decisions = [d for run in runs for d in run["decisions"]
                 if d["verifiable"] and d["airs_first"] is not None]
    if decisions and disc:
        labels = [int(bool(d["silent_failure"])) for d in decisions]
        scores = {"AIRS": [100 - d["airs_first"] for d in decisions],
                  "record age": [d["gate"]["record_age_seconds"] or 0.0 for d in decisions],
                  "cache age": [d.get("cache_age_seconds") or 0.0 for d in decisions],
                  "confidence": [1 - (d["confidence"] or 0.0) for d in decisions]}
        for name, colour in (("AIRS", "#3D5A80"), ("record age", "#98C1D9"),
                             ("cache age", "#E3B23C"), ("confidence", "#C8553D")):
            if disc[name]["auc"] is None:
                continue
            fpr, tpr, _ = roc_curve(labels, scores[name])
            ax.plot(fpr, tpr, color=colour,
                    label=f"{name}: AUC {disc[name]['auc']:.2f} "
                          f"[{disc[name]['lo']:.2f}, {disc[name]['hi']:.2f}]")
    ax.plot([0, 1], [0, 1], color="#bbb", lw=0.8, ls="--")
    ax.set_xlabel("false positive rate")
    ax.set_ylabel("true positive rate (silent failures)")
    ax.set_title("C. H-L: does the signal rank failures first?", fontsize=10, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="lower right")

    fig.suptitle(f"Fig 4.11 — Live source: Vélib' Métropole, recorded "
                 f"{summary['minutes']:.0f} min; caches refreshed every "
                 f"{' and '.join(str(m) for m in sorted(exposure_rows))} min",
                 fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


# ---- the report ----------------------------------------------------------------------------

def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def report(db: Path, runs: list[dict[str, Any]], exposure_rows,
           as_run: list[dict[str, Any]] | None = None,
           reproduced: dict[str, Any] | None = None) -> int:
    """`runs` are the decisions graded against the version-aligned reference;
    `as_run` the same answers as logged (clock reference), shown beside them."""
    import numpy as np

    s = recording_summary(db)
    print(f"Recording: {s['minutes']:.0f} min, {s['polls']} polls, errors {s['errors'] or 0}; "
          f"{s['stations']} stations, {s['changes_per_minute']:.0f} station changes a "
          f"minute; cache snapshots {s['snapshots']}")
    print("\nLag and exposure — the literal answerer, no model, $0:")
    table = exposure_table(exposure_rows)
    for minutes, rows in sorted(exposure_rows.items()):
        ages = np.array([r["record_age"] for r in rows if r["record_age"] is not None])
        cache = np.array([r["cache_age"] for r in rows])
        print(f"  cache {minutes:>2} min: cache age median {np.median(cache) / 60:.1f} min · "
              f"record age median {np.median(ages) / 60:.1f} min (p90 "
              f"{np.percentile(ages, 90) / 60:.1f})")
        for kind in ("bikes", "docks", "empty", "all"):
            r = table[(minutes, kind)]
            print(f"      {kind:<6} answer moved {r['k']:>4}/{r['n']:<4} = {_pct(r['rate'])} "
                  f"[{_pct(r['lo'])}, {_pct(r['hi'])}]")
    if not runs:
        print("\nNo paid runs yet (seeds 110000–120000). "
              "Run: python -m airsbench.livecase.run --dry-run")
        return 0
    if reproduced is not None:
        print(f"\nRe-grading the logged answers at $0: under the clock reference the runs used, "
              f"{reproduced['identical']}/{reproduced['decisions']} decisions reproduce "
              f"exactly;\nthe tables below grade them against the version-aligned reference "
              f"(docs/live_case_study.md §7).")
        from ..livecase.replay import Recording

        coverage = Recording(db).reference_coverage()
        print("  copies whose publication the recorder saw: " + ", ".join(
            f"cache {m} min {seen}/{total}" for m, (seen, total) in sorted(coverage.items())))
        for label, rs in (("as run (clock)", as_run or []), ("version-aligned", runs)):
            cons = sum(d["dimensions_first"]["consistency"] == 100
                       for r in rs for d in r["decisions"])
            n = sum(len(r["decisions"]) for r in rs)
            print(f"  {label:<16} consistency = 100 on {cons}/{n} questions")
    print("\nThe paid cells (same questions in every row):")
    print(f"  {'model':<18}{'cache':>6}{'n':>5}{'correct':>9}{'silent':>8}{'abst':>6}"
          f"{'flipped':>9}  labels (key moved / both / in transit / agent)   $")
    for r in outcomes(runs):
        lab = r["labels"]
        print(f"  {r['model']:<18}{r['cache']:>5}m{r['n']:>5}{r['correct']:>9}{r['silent']:>8}"
              f"{r['abstained']:>6}{r['flipped']:>9}  {lab['answer_key_moved']:>3} / "
              f"{lab['both']:>2} / {lab['corrupted_in_transit']:>2} / "
              f"{lab['agent_impairment']:>3}                 {r['usd']:.4f}")
    for label, rs in (("version-aligned", runs), ("as run (clock)", as_run)):
        if not rs:
            continue
        d = discrimination(rs)
        if not d:
            continue
        print(f"\nH-L, {label} — ranking silent failures first ({d['n']} answers, "
              f"{d['silent']} silent; AUC, 95% bootstrap):")
        for name in ("AIRS", "record age", "cache age", "confidence"):
            v = d[name]
            text = "undefined (one class)" if v["auc"] is None else \
                f"{v['auc']:.3f} [{v['lo']:.3f}, {v['hi']:.3f}]"
            print(f"  {name:<11} {text}")
    for model, r in cache_contrast(runs).items():
        print(f"  {model}: silent failure, 15-min − 5-min cache: {100 * r['point']:+.1f} pp "
              f"[{100 * r['lo']:+.1f}, {100 * r['hi']:+.1f}], discordant {r['b']}/{r['c']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=Path("data/livecase/velib.db"))
    parser.add_argument("--results", type=Path, default=Path("results/runs"))
    parser.add_argument("--exposure-n", type=int, default=EXPOSURE_N)
    parser.add_argument("--figure", type=Path, default=None)
    args = parser.parse_args(argv)
    from ..livecase.replay import recording_path

    args.db = recording_path(args.db)
    if not args.db.exists():
        print(f"No recording at {args.db}. See docs/live_case_study.md.")
        return 1
    as_run = load_arm(args.results)
    rows = exposure(args.db, args.exposure_n)
    if not as_run:
        return report(args.db, [], rows)
    reproduced = agreement(as_run, reverify(as_run, args.db, reference="clock"))
    if reproduced["identical"] != reproduced["decisions"]:
        print(f"Cannot re-grade: the clock reference reproduces only {reproduced['identical']}"
              f"/{reproduced['decisions']} logged decisions — the recording or the code "
              f"changed since the runs")
        return 1
    runs = reverify(as_run, args.db, reference="version")
    status = report(args.db, runs, rows, as_run=as_run, reproduced=reproduced)
    if args.figure:
        print(f"\n  figure: {figure(recording_summary(args.db), rows, runs, args.figure)}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
