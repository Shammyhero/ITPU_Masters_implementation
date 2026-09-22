"""The refetch arm's analysis and the third verdict (docs/refetch_arm.md, step 6).

Everything here runs on a synthetic campaign produced by the arm's own runner at
$0, with scripted answerers whose behaviour is known — so the analysis can be
checked against the answer it must give:

- an agent that asks to re-read exactly when it is SHOWN an age over 1 s: H-R1a
  must come out at +100 pp, H-R1c at zero with a measured ceiling;
- literal answers on stale records are wrong exactly on flipped questions, and a
  re-read repairs every one of them — the menu's counts follow by arithmetic;
- a broken pairing must stop the analysis, not bias it.

The third verdict (gate/replay.py) is checked on hand-built batches, and against
the existing refuse-only replay on the real corpus when it is present.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from airsbench.analysis import refetch as analysis
from airsbench.analysis.refetch import AlignmentError, align, exact_rate, holm, paired
from airsbench.analyst.answerers import LiteralAnswerer, Usage
from airsbench.analyst.verifier import AgentAnswer
from airsbench.gate.policy import Policy
from airsbench.gate.replay import (
    Batch,
    Lineage,
    load_batches,
    load_lineage,
    load_weights,
    replay,
    replay_menu,
)
from airsbench.runner.config import build_refetch_arm, refetch_cell
from airsbench.runner.execute import RECORD_AGE_META_KEY
from airsbench.runner.refetch import run_refetch

# The first flipped stale questions fall at indices 40 and 43 (replication 1) and 46
# (replication 2); at 30 questions there is nothing for a re-read to repair.
N_QUESTIONS = 50


class AgeAware:
    """Asks to re-read every record exactly when shown an age over 1 s."""

    name = "age-aware"

    def answer(self, question, plan, records):
        ages = [r.meta.get(RECORD_AGE_META_KEY) for r in records]
        if any(age is not None and age > 1.0 for age in ages):
            ids = tuple(r.meta["record_id"] for r in records)
            return AgentAnswer(refetch_ids=ids, text="the records are old"), Usage(self.name)
        return LiteralAnswerer().answer(question, plan, records)

    def answer_after_reread(self, question, plan, first_records, request, records):
        return LiteralAnswerer().answer(question, plan, records)


def answerer_for(config):
    return AgeAware() if config.refetch_mode == "agent" else LiteralAnswerer()


@pytest.fixture(scope="module")
def campaign():
    runs = []
    for config in build_refetch_arm(replications=2, n_queries=N_QUESTIONS):
        result = run_refetch(config, answerer_for(config), out_dir=None)
        runs.append({"run_id": result.run_id, "config": result.config,
                     "metrics": result.metrics, "airs": result.airs,
                     "usage": result.usage, "decisions": result.decisions})
    return runs


@pytest.fixture(scope="module")
def aligned(campaign):
    return align(campaign)


# ---- alignment ---------------------------------------------------------------------------

def test_every_cell_is_matched_question_by_question(aligned):
    assert aligned.replications == [1, 2] and aligned.n == 2 * N_QUESTIONS
    assert set(aligned.decisions) == set(analysis.DESIGN) and len(analysis.DESIGN) == 7
    for decisions in aligned.decisions.values():
        assert [(rep, d["question_seed"]) for (rep, _), d in zip(aligned.seeds, decisions)] \
            == aligned.seeds


def _copy(runs):
    return json.loads(json.dumps(runs))


def test_a_cell_missing_a_question_breaks_the_pairing(campaign):
    runs = _copy(campaign)
    runs[3]["decisions"].pop()
    with pytest.raises(AlignmentError, match="different questions"):
        align(runs)


def test_exposure_that_differs_within_a_state_is_refused(campaign):
    runs = _copy(campaign)
    stale = [r for r in runs if analysis.cell_state(r) == ("gate", "stale")
             and r["config"]["replication"] == 1][0]
    first = stale["decisions"][0]
    first["flipped_as_delivered"] = not first["flipped_as_delivered"]
    with pytest.raises(AlignmentError, match="exposure"):
        align(runs)


def test_a_cell_run_twice_is_refused(campaign):
    with pytest.raises(AlignmentError, match="run twice"):
        align(_copy(campaign) + _copy(campaign[:1]))


def test_an_incomplete_replication_is_left_out_not_half_used(campaign):
    runs = [r for r in _copy(campaign)
            if not (r["config"]["replication"] == 2
                    and refetch_cell(r["config"]) == "agent_shown")]
    assert align(runs).replications == [1]


# ---- the declared tests, on a campaign whose answer is known ------------------------------

def test_h_r1a_finds_an_agent_that_asks_when_shown_an_old_age(aligned):
    h = analysis.hypotheses(aligned)
    assert h["H-R1a"]["point"] == 1.0 and h["H-R1a"]["b"] == aligned.n
    assert h["H-R1a"]["c"] == 0 and h["H-R1a"]["p"] == 0.0
    # Hidden age: never asked, reported as a measured ceiling, not as nothing.
    for state in ("healthy", "stale"):
        rate = h["H-R1c"][state]
        assert rate["k"] == 0 and rate["one_sided"]
        assert rate["hi"] == pytest.approx(1 - 0.05 ** (1 / aligned.n))


def test_h_r1b_sees_the_re_read_repair_every_flipped_question(aligned):
    flipped = aligned.flipped["stale"]
    assert flipped.sum() > 0, "the synthetic campaign must contain flipped questions"
    h = analysis.hypotheses(aligned)
    # Literal on stale records is wrong exactly when flipped; after a re-read, right.
    assert h["H-R1b"]["x"] == 1.0 and h["H-R1b"]["y"] == 0.0
    assert h["H-R1b"]["n"] == int(flipped.sum())
    assert h["H-R1b_silent"]["point"] == -1.0


def test_the_menu_is_the_arithmetic_of_the_cells(aligned):
    v = aligned.verifiable
    admit_silent = aligned.vector("baseline", "stale", "silent")[v]
    admit_correct = aligned.vector("baseline", "stale", "correct")[v]
    rows = {row["verdict"]: row for row in analysis.menu(aligned)}
    assert rows["refuse"]["prevented"] == admit_silent.sum()
    assert rows["refuse"]["forfeited"] == admit_correct.sum() and rows["refuse"]["usd"] == 0
    for verdict in ("gate", "agent_shown"):  # both re-read every stale question here
        assert rows[verdict]["prevented"] == admit_silent.sum()
        assert rows[verdict]["forfeited"] == 0 and rows[verdict]["raw"] == 0
        assert rows[verdict]["reads"] == aligned.n
    assert rows["agent_hidden"]["prevented"] == 0 and rows["agent_hidden"]["reads"] == 0
    assert all(row["genuine"] <= row["prevented"] for row in rows.values())


def test_a_gate_re_read_matches_the_healthy_pipeline_it_stands_for(aligned):
    g = analysis.gate_vs_healthy(aligned)
    assert g["agreement"] >= 0.9  # literal answers: only the 0.05 s lag can differ
    assert abs(g["correct"]["point"]) <= 0.1


def test_the_exploratory_prompt_contrast_is_zero_when_the_prompts_behave_alike(aligned):
    effect = analysis.prompt_effect(aligned)
    for outcomes in effect.values():
        for r in outcomes.values():
            assert r["point"] == 0.0 and r["b"] == r["c"] == 0 and r["p"] == 1.0


def test_the_report_and_the_figure_are_produced(aligned, tmp_path, capsys):
    assert analysis.report(aligned) == 0
    out = capsys.readouterr().out
    assert "H-R1a" in out and "EXPLORATORY" in out and "Validation" in out
    path = analysis.figure(aligned, tmp_path / "fig4_9.png")
    assert path.exists() and path.stat().st_size > 10_000


def test_the_cli_reads_only_the_arm(campaign, tmp_path, capsys):
    for run in campaign:
        (tmp_path / f"{run['run_id']}.json").write_text(json.dumps(run))
    for path in sorted(Path("results/runs").glob("*.json"))[:2]:  # corpus beside it
        (tmp_path / path.name).write_text(path.read_text())
    assert analysis.main(["--results", str(tmp_path)]) == 0
    assert "2 complete replication(s)" in capsys.readouterr().out
    assert len(analysis.load_arm(tmp_path)) == len(campaign)


# ---- the statistics ------------------------------------------------------------------------

def test_a_paired_bootstrap_resamples_within_replication():
    x = np.array([1, 1, 1, 0, 1, 0, 1, 1], dtype=bool)
    y = np.array([0, 1, 0, 0, 1, 0, 0, 1], dtype=bool)
    rep = np.array([1, 1, 1, 1, 2, 2, 2, 2])
    r = paired(x, y, rep)
    assert r["point"] == pytest.approx(0.375) and (r["b"], r["c"]) == (3, 0)
    assert r["lo"] <= r["point"] <= r["hi"] and r["p"] < 0.05


def test_exact_intervals_and_the_zero_ceiling():
    assert exact_rate(0, 450)["hi"] == pytest.approx(0.00663, abs=1e-5)
    r = exact_rate(5, 10)
    assert r["lo"] < 0.5 < r["hi"] and not r["one_sided"]


def test_holm_steps_down():
    assert holm({"a": 0.01, "b": 0.04}) == {"a": 0.02, "b": 0.04}
    assert holm({"a": 0.03, "b": None}) == {"a": 0.03, "b": None}


# ---- the third verdict (gate/replay.py) -------------------------------------------------

DIMS = {"freshness": 100.0, "latency": 100.0, "consistency": 100.0, "semantic": 100.0}


def batch(run_id, fault, age, n, correct, silent, **dims):
    return Batch(run_id=run_id, task="retrieval", model="m", fault=fault, severity="x",
                 dims={**DIMS, **dims}, record_age_seconds=age, n=n, correct=correct,
                 silent=silent, abstained=n - correct - silent)


BATCHES = [
    batch("healthy", "none", 0.05, 10, 8, 1),
    batch("stale", "freshness", 5.05, 20, 12, 6, freshness=20.0),
    batch("drift", "schema_drift", 0.05, 10, 5, 4, consistency=60.0),
]
LINEAGE = {run_id: Lineage("main", "streaming", 10_001)
           for run_id in ("healthy", "stale", "drift")}
POLICY = Policy(name="age+consistency", max_record_age_seconds=2.0,
                min_dimension={"consistency": 90.0})
WEIGHTS = {"freshness": 0.25, "latency": 0.25, "consistency": 0.25, "semantic": 0.25}


def test_staleness_is_re_read_from_the_matched_healthy_run_and_drift_still_refuses():
    m = replay_menu(BATCHES, POLICY, WEIGHTS, LINEAGE)
    assert (m.refetched_batches, m.refused_batches, m.untwinned_batches) == (1, 1, 0)
    # The stale batch answers at the healthy twin's rates: 1/10 silent, 8/10 correct.
    assert m.silent_after == pytest.approx(1 + 2.0)
    assert m.correct_after == pytest.approx(8 + 16.0)
    assert m.prevented == pytest.approx(11 - 3) and m.forfeited == pytest.approx(25 - 24)
    assert m.coverage == pytest.approx(30 / 40)
    assert m.reads_per_prevented == pytest.approx(20 / 8)


def test_refuse_only_is_the_existing_replay():
    m = replay_menu(BATCHES, POLICY, WEIGHTS, LINEAGE, refetch=False)
    out = replay(BATCHES, POLICY, WEIGHTS)
    assert (m.prevented, m.forfeited) == (out.prevented, out.forfeited)
    assert m.refetched_batches == 0 and m.coverage == out.coverage


def test_a_stale_batch_with_no_matched_healthy_run_is_refused_and_counted():
    lineage = {**LINEAGE, "healthy": Lineage("main", "streaming", 99)}
    m = replay_menu(BATCHES, POLICY, WEIGHTS, lineage)
    assert (m.refetched_batches, m.untwinned_batches, m.refused_batches) == (0, 1, 2)


def test_a_batch_pipeline_twin_does_not_stand_for_a_re_read():
    """A re-read reads the system of record: the healthy STREAMING run, 0.05 s old."""
    lineage = {**LINEAGE, "healthy": Lineage("main", "batch", 10_001)}
    assert replay_menu(BATCHES, POLICY, WEIGHTS, lineage).refetched_batches == 0


@pytest.mark.skipif(not list(Path("results/runs").glob("*.json")), reason="no corpus")
def test_on_the_corpus_refuse_only_agrees_with_replay_for_every_age_policy():
    results = Path("results/runs")
    batches = [b for b in load_batches(results) if b.task == "retrieval"]
    lineage = load_lineage(results)
    weights = load_weights("retrieval")
    for seconds in (0.1, 2.0, 5.0):
        policy = Policy(name=f"age <= {seconds}", max_record_age_seconds=seconds)
        m = replay_menu(batches, policy, weights, lineage, refetch=False)
        out = replay(batches, policy, weights)
        assert (m.prevented, m.forfeited) == (out.prevented, out.forfeited)
        assert replay_menu(batches, policy, weights, lineage).untwinned_batches == 0
