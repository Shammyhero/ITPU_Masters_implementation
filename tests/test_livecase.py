"""The live case study's replay and runner (docs/live_case_study.md).

A synthetic evening, recorded by the real recorder from a scripted feed: twelve
stations on a small grid whose counts move every minute. What has to hold:

- **Paired (invariant 2).** A question — moment, anchor, the six stations — is the
  same whichever cache is asked and whichever model answers.
- **Read at the question's moment.** A replayed record's age is measured at t, not
  today; the recorder's own timestamps never reach the agent.
- **The corpus's attribution, on real-shaped data.** Because upstream is a history,
  a lagging cache's wrong answer reads `answer_key_moved`, not
  `corrupted_in_transit` — the reason the study records and then replays.
- **Quarantined.** Artifacts carry the `livecase` seed block, and no corpus analysis
  reads them.
"""

from __future__ import annotations

import json
from argparse import Namespace

import pytest

from airsbench.analyst.answerers import LiteralAnswerer
from airsbench.analyst.loop import Loop
from airsbench.gate.policy import Policy
from airsbench.livecase import questions as qs
from airsbench.livecase.record import Recorder
from airsbench.livecase.replay import PAYLOAD, Recording
from airsbench.livecase.run import (
    CLAUDE_TOKEN_FACTOR,
    PROVENANCE,
    estimate_usd,
    execute,
    run_livecase,
)
from airsbench.runner.config import NEVER_POOLED, build_livecase, run_arm
from airsbench.runner.refetch import question_seed

START = 1_790_000_000.0
STATIONS = [{"station_id": 100 + i, "name": f"Station {i}", "lat": 48.85 + 0.001 * (i // 4),
             "lon": 2.35 + 0.001 * (i % 4), "capacity": 20} for i in range(12)]


class Evening:
    """A feed whose station counts move every minute, on a clock the test drives."""

    def __init__(self):
        self.t = START

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += max(seconds, 0.001)

    def fetch(self, url):
        if url.endswith("station_information.json"):
            return {"data": {"stations": STATIONS}}
        minute = int((self.t - START) // 60)
        stations = []
        for i, s in enumerate(STATIONS):
            bikes = (i * 3 + minute * (i % 5 + 1)) % 14   # every station moves differently
            stations.append({
                "station_id": s["station_id"], "num_bikes_available": bikes,
                "num_bikes_available_types": [{"mechanical": bikes // 2},
                                              {"ebike": bikes - bikes // 2}],
                "num_docks_available": 20 - bikes, "is_installed": 0 if i == 11 else 1,
                "is_renting": 1, "is_returning": 1, "last_reported": START + 60 * minute - 30})
        return {"lastUpdatedOther": START + 60 * minute, "data": {"stations": stations}}


@pytest.fixture(scope="module")
def recording(tmp_path_factory):
    db = tmp_path_factory.mktemp("rec") / "velib.db"
    evening = Evening()
    Recorder(db, caches=(5, 15), status_every=20, clock=evening,
             fetcher=evening.fetch).run(minutes=40, sleep=evening.sleep, say=lambda _: None)
    return Recording(db, caches=(5, 15))


# ---- the replay ---------------------------------------------------------------------------

def test_the_window_opens_once_every_cache_has_a_copy(recording):
    assert recording.start == max(s[0] for s in recording.snapshots.values())
    assert recording.end > recording.start
    assert len(recording.snapshots[5]) > len(recording.snapshots[15]) >= 2


def test_a_question_is_the_same_for_every_cache(recording):
    for seed in range(20):
        a = recording.pair(5).delivered.sample(seed=seed)
        b = recording.pair(15).delivered.sample(seed=seed)
        assert (a.as_of, a.key, a.ids) == (b.as_of, b.key, b.ids)
        assert a.meta["query"] == b.meta["query"] and a.key in a.ids
        assert "111" not in a.ids  # station 11 is uninstalled and never shown


def test_the_stations_shown_are_the_anchors_nearest_neighbours(recording):
    sample = recording.pair(5).delivered.sample(seed=3)
    installed = [str(s["station_id"]) for s in STATIONS[:11]]
    assert len(sample.ids) == 6 and set(sample.ids) <= set(installed)
    assert sample.ids[0] == sample.key  # nearest to the anchor is the anchor itself


def test_a_replayed_record_is_read_at_the_questions_moment(recording):
    sample = recording.pair(15).delivered.sample(seed=5)
    assert all(r.read_timestamp == sample.as_of for r in sample.records)
    assert set(sample.records[0].payload) == set(PAYLOAD)          # no recorder clocks
    assert 0 <= sample.meta["cache_age_seconds"] < 15 * 60 + 1
    assert sample.meta["served_as_of"] <= sample.as_of


def loop(recording, minutes):
    return Loop(pair=recording.pair(minutes), policy=Policy(name="open"),
                answerer=LiteralAnswerer(), mode="off", provenance=PROVENANCE)


def test_a_lagging_cache_moves_the_answer_key_and_is_attributed_to_the_pipeline(recording):
    labels = {}
    for seed in range(40):
        tick = loop(recording, 15).ask(qs.question(0), seed=seed)
        labels[tick["decision"]["attribution"]] = labels.get(tick["decision"]["attribution"],
                                                             0) + 1
        if tick["decision"]["flipped"]:
            # Literal answers take the served records at face value: wrong exactly when
            # the key moved, and never "corrupted in transit" — upstream has history.
            assert tick["decision"]["attribution"] == "answer_key_moved"
    assert labels.get("answer_key_moved", 0) > 0 and "corrupted_in_transit" not in labels
    assert tick["provenance"]["arm"] == "livecase"


def test_consistency_is_scored_against_the_caches_own_snapshot(recording):
    tick = loop(recording, 5).ask(qs.question(1), seed=7)
    assert tick["airs"]["dimensions"]["consistency"]["score"] == pytest.approx(100.0)
    assert tick["airs"]["dimensions"]["semantic"]["score"] is None   # no reviewed manifest


# ---- questions -------------------------------------------------------------------------------

def test_the_three_questions_rotate_and_name_the_anchor(recording):
    assert [qs.question_type(i) for i in range(6)] == ["bikes", "docks", "empty"] * 2
    tick = loop(recording, 5).ask(qs.question(2), seed=1)
    assert tick["question"]["text"].startswith("How many of these stations near Station ")
    assert tick["question"]["plan"]["type"] == "count_where"


@pytest.mark.parametrize("text", [t for t, _ in qs.QUESTIONS.values()])
def test_no_question_hints_at_the_data(text):
    lowered = text.lower()
    for word in ("stale", "fresh", "old", "age", "outdated", "recent", "cache", "delay",
                 "accurate", "reliable", "update"):
        assert word not in lowered, word


# ---- the runner ------------------------------------------------------------------------------

def test_the_grid_is_two_models_by_two_caches_on_the_same_questions():
    grid = build_livecase()
    assert [(c.model, c.pipeline) for c in grid] == [
        ("gpt-4o-mini", "velib-cache-5min"), ("gpt-4o-mini", "velib-cache-15min"),
        ("claude-haiku-4-5", "velib-cache-5min"), ("claude-haiku-4-5", "velib-cache-15min")]
    assert {run_arm({"config": c.to_dict()}) for c in grid} == {"livecase"}
    assert len({c.sample_seed for c in grid}) == 1 and "livecase" in NEVER_POOLED


def test_a_run_writes_a_livecase_artifact(recording, tmp_path):
    config = build_livecase(n_queries=6)[0]
    result = run_livecase(config, recording, LiteralAnswerer(), out_dir=tmp_path)
    artifact = json.loads((tmp_path / f"{result.run_id}.json").read_text())
    assert run_arm(artifact) == "livecase" and len(artifact["decisions"]) == 6
    first = artifact["decisions"][0]
    assert first["question_type"] == "bikes" and first["question_seed"] == \
        question_seed(config, 0)
    assert '"num_bikes_available"' not in json.dumps(artifact["decisions"])  # no records


def test_claude_is_estimated_with_a_margin(recording):
    gpt, claude = build_livecase(n_queries=3)[0], build_livecase(n_queries=3)[2]
    _, gpt_tokens = estimate_usd(gpt, recording)
    _, claude_tokens = estimate_usd(claude, recording)
    assert claude_tokens == int(gpt_tokens * CLAUDE_TOKEN_FACTOR)


def test_a_dry_run_spends_nothing(recording, tmp_path, capsys):
    args = Namespace(dry_run=True, max_cost=1.0, offset=0, limit=None, out=str(tmp_path))
    never = lambda *a: pytest.fail("a dry run built an answerer")  # noqa: E731
    assert execute(build_livecase(n_queries=3), recording, args, make=never) == 0
    assert "dry run" in capsys.readouterr().out and not list(tmp_path.glob("*.json"))


def test_the_study_runs_every_cell_at_zero_cost_with_a_literal_answerer(recording, tmp_path):
    args = Namespace(dry_run=False, max_cost=1.0, offset=0, limit=None, out=str(tmp_path))
    assert execute(build_livecase(n_queries=3), recording, args,
                   make=lambda spec, budget: LiteralAnswerer()) == 0
    assert len(list(tmp_path.glob("*.json"))) == 4


def test_no_corpus_loader_reads_a_livecase_artifact(recording, tmp_path):
    from airsbench.analysis.flip_partition import load_retrieval_runs
    from airsbench.analysis.silent_definition import load_runs

    run_livecase(build_livecase(n_queries=3)[0], recording, LiteralAnswerer(), out_dir=tmp_path)
    assert load_retrieval_runs(tmp_path, include_other_arms=True) == []
    assert load_runs(tmp_path) == []


# ---- the analysis (Fig 4.11, H-L) ------------------------------------------------------------

@pytest.fixture(scope="module")
def literal_runs(recording, tmp_path_factory):
    out = tmp_path_factory.mktemp("runs")
    for config in build_livecase(n_queries=30):
        run_livecase(config, recording, LiteralAnswerer(), out_dir=out)
    from airsbench.analysis.livecase import load_arm

    return load_arm(out)


def test_the_analysis_reads_the_arm_and_counts_outcomes(literal_runs):
    from airsbench.analysis.livecase import outcomes

    rows = outcomes(literal_runs)
    assert [(r["model"], r["cache"]) for r in rows] == [
        ("claude-haiku-4-5", 5), ("claude-haiku-4-5", 15), ("gpt-4o-mini", 5),
        ("gpt-4o-mini", 15)]
    for r in rows:  # literal answers: every wrong one is the key moving
        assert r["silent"] == r["labels"]["answer_key_moved"] + r["labels"]["both"]
        assert r["correct"] + r["silent"] + r["abstained"] + r["unanswered"] == r["n"]


def test_h_l_is_an_auc_with_an_interval_or_honestly_undefined(literal_runs):
    from airsbench.analysis.livecase import discrimination

    d = discrimination(literal_runs)
    assert d["n"] > 0
    for name in ("AIRS", "record age", "confidence"):
        v = d[name]
        assert v["auc"] is None or (0 <= v["auc"] <= 1 and v["lo"] <= v["auc"] <= v["hi"])
    # A literal answer is always fully confident: confidence cannot rank anything.
    assert d["confidence"]["auc"] in (None, 0.5)


def test_exposure_at_scale_uses_the_paid_runs_questions(recording, literal_runs):
    from airsbench.analysis.livecase import exposure, exposure_table

    rows = exposure(recording.db, n=30)
    assert set(rows) == {5, 15} and all(len(v) == 30 for v in rows.values())
    paid = next(r for r in literal_runs if r["config"]["pipeline"] == "velib-cache-15min")
    assert [bool(d["flipped"]) for d in paid["decisions"]] == [r["flipped"] for r in rows[15]]
    table = exposure_table(rows)
    assert table[(15, "all")]["n"] == sum(r["verifiable"] for r in rows[15])


def test_the_report_and_figure_are_produced(recording, literal_runs, tmp_path, capsys):
    from airsbench.analysis.livecase import exposure, figure, recording_summary, report

    rows = exposure(recording.db, n=12)
    assert report(recording.db, literal_runs, rows) == 0
    out = capsys.readouterr().out
    assert "H-L" in out and "answer moved" in out
    path = figure(recording_summary(recording.db), rows, literal_runs, tmp_path / "f.png")
    assert path.exists() and path.stat().st_size > 10_000


def test_the_indexed_draw_matches_reading_the_history(recording):
    """draw() indexes which stations were installed when, instead of reading the whole
    history per question (≈ 385x faster on the real recording). It must pick exactly
    the questions the full read picks — the paid runs were drawn the slow way."""
    import random

    from airsbench.livecase.replay import _distance_m

    for seed in range(40):
        rng = random.Random(seed)
        t = rng.uniform(recording.start, recording.end)
        state = recording.upstream.current(as_of=t)
        installed = sorted(sid for sid, e in state.items()
                           if e["payload"].get("is_installed") == 1 and sid in recording.coords)
        anchor = rng.choice(installed)
        here = recording.coords[anchor]
        ids = sorted(installed, key=lambda s: (_distance_m(here, recording.coords[s]), s))[:6]
        assert recording.draw(seed) == (t, anchor, ids)


# ---- the consistency reference (corrected 23 Sep) --------------------------------------------

def jittered(db):
    """A recording where one cache copy's publication is stamped a second off what the
    recorder saw, and another copies a publication the recorder never saw."""
    clock = Evening()
    stamps = iter([1000.0, 1001.0, 1100.0, 1500.0, 1600.0, 1600.0])

    def fetch(url):
        document = clock.fetch(url)
        if url.endswith("station_status.json"):
            document["lastUpdatedOther"] = next(stamps)
        return document

    recorder = Recorder(db, caches=(5,), clock=clock, fetcher=fetch)
    recorder.refresh_stations()
    clock.t = START
    recorder.record_upstream()          # recorder sees publication 1000
    clock.t = START + 5
    recorder.refresh_cache(5)           # the cache copies 1001: the same, a second off
    clock.t = START + 60
    recorder.record_upstream()          # recorder sees 1100
    clock.t = START + 305
    recorder.refresh_cache(5)           # the cache copies 1500: never seen by the recorder
    clock.t = START + 400
    recorder.record_upstream()          # 1600
    clock.t = START + 420
    recorder.record_upstream()
    return Recording(db, caches=(5,))


def test_a_copy_is_referenced_to_the_publication_it_copied(tmp_path):
    rec = jittered(tmp_path / "j.db")
    first, second = rec.snapshots[5]
    assert rec.reference_for(5, first) == START        # matched within the jitter
    assert rec.reference_for(5, second) == second      # never seen: falls back to the clock
    assert rec.reference_coverage() == {5: (1, 2)}
    clock_rec = Recording(tmp_path / "j.db", caches=(5,), reference="clock")
    assert clock_rec.reference_for(5, first) == first


def test_regrading_logged_answers_reproduces_them_under_the_same_reference(recording,
                                                                           literal_runs):
    from airsbench.analysis.livecase import agreement, reverify

    regraded = reverify(literal_runs, recording.db, reference="version")
    assert agreement(literal_runs, regraded) == {"decisions": sum(
        len(r["decisions"]) for r in literal_runs), "identical": sum(
        len(r["decisions"]) for r in literal_runs)}
