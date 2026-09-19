"""Live traffic must never be able to reach a published number (plan A7).

The corpus in `results/runs/` is the canonical dataset: every figure and every
claim in the thesis is derived from it (invariant 7). The Analyst answers live
questions on someone's laptop, over their data, with a model of their choosing —
unpaired, unreplicated, and chosen by whoever is holding the mouse. If one of
those answers ever entered an analysis, a number in the thesis would depend on a
demo someone gave in October.

Three independent walls, each asserted here rather than assumed:

1. **Different place.** Sessions are written to the user's own directory, and
   `session_path` refuses a destination under `results/runs/`.
2. **Marked.** Every live Tick carries `arm: "live"` and a seed from the reserved
   block, so its provenance survives being copied somewhere by hand.
3. **Excluded.** Every analysis entry point selects runs by arm, and none of them
   accepts `live` — tested by handing each loader a corpus with a live artifact
   in it and checking it is dropped.

The fourth guarantee is about secrets: no key, DSN or token may appear in a Tick,
and the writer refuses one that does.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from airsbench.analyst.answerers import LiteralAnswerer
from airsbench.analyst.budget import Budget
from airsbench.analyst.session import LIVE_SEED_BLOCK, demo_question
from airsbench.analyst.sessions import (
    Session,
    SessionError,
    contains_secret,
    open_session,
    read_session,
    session_path,
)
from airsbench.gate.policy import Policy
from airsbench.runner.config import SEED_BLOCKS, arm_of, run_arm
from airsbench.sources.config import load_sources

LIVE_SEED = LIVE_SEED_BLOCK[0] + 5


def live_run(seed: int = LIVE_SEED) -> dict:
    """A live artifact shaped enough like a run that a loader would read it."""
    return {
        "run_id": "live" + "0" * 28,
        "config": {"task": "retrieval", "pipeline": "streaming", "fault_type": "freshness",
                   "severity": "severe", "model": "gpt-4o-mini", "seed": seed,
                   "sample_seed": 10_001, "n_queries": 3, "replication": 1},
        "airs": {"freshness": 19.8, "latency": 100.0, "consistency": 100.0,
                 "semantic": 100.0, "total": 89.6},
        "metrics": {"accuracy": 0.0, "silent_failure_rate": 1.0, "abstention_rate": 0.0,
                    "n": 3, "parse_failures": 0},
        "usage": {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0},
        "decisions": [{"query": "q", "chosen": "A", "ground_truth": "B", "correct": False,
                       "confidence": 1.0, "parse_failed": False, "abstained": False}],
    }


def session(tmp_path, **overrides):
    pair = load_sources()[overrides.pop("source", "demo-stale")]
    return open_session(pair, LiteralAnswerer(), policy=Policy(name="open"),
                        budget=Budget(), question=demo_question(),
                        directory=tmp_path / "sessions", **overrides)


# ---- 1. somewhere else entirely ---------------------------------------------

def test_a_session_writes_to_the_users_directory_not_the_corpus(tmp_path):
    live = session(tmp_path)
    list(live.stream())
    written = list((tmp_path / "sessions").glob("*.jsonl"))
    assert [path.name for path in written] == [f"{live.id}.jsonl"]
    assert not list(Path("results/runs").glob("live*.json"))


@pytest.mark.parametrize("directory", ["results/runs", "results/runs/live", "results"])
def test_writing_sessions_into_the_corpus_is_refused(directory):
    with pytest.raises(SessionError, match="experimental corpus"):
        session_path("a" * 12, Path(directory))


def test_a_session_id_must_look_like_one(tmp_path):
    with pytest.raises(SessionError, match="not a session id"):
        session_path("../../results/runs/sneaky", tmp_path)


# ---- 2. marked in the artifact ----------------------------------------------

def test_every_live_tick_is_marked_live_and_seeded_from_the_reserved_block(tmp_path):
    live = session(tmp_path)
    for _ in range(2):
        list(live.stream())
    ticks = read_session(live.id, tmp_path / "sessions")
    assert len(ticks) == 2
    for tick in ticks:
        assert tick["provenance"]["arm"] == "live"
        assert tick["provenance"]["seed_block"] == list(LIVE_SEED_BLOCK)
        low, high = LIVE_SEED_BLOCK
        assert low <= tick["provenance"]["seed"] < high
        assert arm_of(tick["provenance"]["seed"]) == "live"


def test_the_live_block_is_registered_and_owns_no_experimental_seed():
    assert SEED_BLOCKS["live"] == LIVE_SEED_BLOCK
    assert run_arm(live_run()) == "live"
    for arm, (low, _high) in SEED_BLOCKS.items():
        if arm not in ("live", "refetch"):
            assert arm_of(low) == arm


# ---- 3. excluded by every analysis ------------------------------------------

def test_no_analysis_entry_point_accepts_a_live_run(tmp_path):
    """Hand each loader a corpus containing one live artifact; it must drop it.

    These are the functions every figure and findings document goes through. A
    new analysis that reads `results/runs/` directly, without selecting by arm,
    is exactly what this test exists to catch — add it here when you write it.
    """
    from airsbench.analysis.airs_calibration import build_frame
    from airsbench.analysis.flip_partition import load_retrieval_runs
    from airsbench.analysis.verifier_agreement import load_runs

    corpus = tmp_path / "runs"
    corpus.mkdir()
    (corpus / "live.json").write_text(json.dumps(live_run()))

    assert load_retrieval_runs(corpus) == []
    assert load_runs(corpus) == []
    assert load_retrieval_runs(corpus, include_other_arms=True) == [], (
        "include_other_arms admits research arms, never live traffic")
    frame = build_frame(corpus, Path("data/ecommerce"))
    assert frame.empty or "live" not in set(frame["arm"])


def test_a_live_run_is_dropped_even_beside_real_ones(tmp_path):
    """The dangerous case is not a live-only directory — it is one live file that
    someone copied into the corpus next to 300 real runs."""
    from airsbench.analysis.flip_partition import load_retrieval_runs

    corpus = tmp_path / "runs"
    corpus.mkdir()
    real = sorted(Path("results/runs").glob("*.json"))[:3]
    if not real:
        pytest.skip("no run artifacts on disk")
    for path in real:
        (corpus / path.name).write_text(path.read_text())
    (corpus / "live.json").write_text(json.dumps(live_run()))

    loaded = load_retrieval_runs(corpus)
    assert all(run_arm(run) == "main" for run in loaded)
    assert "live" + "0" * 28 not in {run["run_id"] for run in loaded}


# ---- 4. no credential ever reaches an artifact ------------------------------

@pytest.mark.parametrize("secret", [
    "sk-proj-abcdefghijklmnop0123456789",
    "postgres://user:hunter2@db.internal:5432/catalog",
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_abcdefghijklmnopqrstuvwxyz0123",
])
def test_a_tick_carrying_anything_credential_shaped_is_not_written(tmp_path, secret):
    live = session(tmp_path)
    tick = {"decision": {"answer": f"the connection string is {secret}"}}
    assert contains_secret(tick) is not None
    with pytest.raises(SessionError, match="credential"):
        live.write(tick)
    assert read_session(live.id, tmp_path / "sessions") == []


def test_a_real_tick_carries_no_credential_and_no_local_path(tmp_path, monkeypatch):
    key = "sk-proj-abcdefghijklmnop0123456789"
    monkeypatch.setenv("OPENAI_API_KEY", key)
    live = session(tmp_path)
    tick = [event for event in live.stream() if event["stage"] == "tick"][0]["tick"]
    text = json.dumps(tick)
    assert contains_secret(tick) is None
    # The key itself, not a prefix: real product titles contain strings like
    # "desk-projector", which a naive "sk-proj" search matches.
    assert key not in text and str(Path.home()) not in text
    assert tick["source"]["pair"] == "demo-stale"  # the declared id, not a location


def test_the_session_summary_never_reports_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-abcdefghijklmnop0123456789")
    summary = json.dumps(session(tmp_path).to_dict())
    assert "sk-ant" not in summary and contains_secret(json.loads(summary)) is None


def test_a_session_that_wrote_nothing_reads_back_as_empty(tmp_path):
    assert read_session(Session(id="b" * 12, loop=None, budget=Budget(),
                                question=demo_question()).id, tmp_path) == []
