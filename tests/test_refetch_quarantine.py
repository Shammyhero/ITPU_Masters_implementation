"""The refetch arm is data — and never pooled with the corpus.

Its artifacts sit in `results/runs/` beside the corpus's (invariant 7; author's
choice 4a, 23 Sep), which makes this the dangerous case: every loader reads that
directory. The arm is a different instrument — the Analyst's plan-returning prompt
through the loop (brief correction 11), a tool-offering prompt in two cells — so
pooling it would quietly change corpus numbers. `include_other_arms=True` means
other research arms of the same instrument, never this one.

Each loader below is handed a directory holding a REAL arm artifact (produced by
the arm's own runner at $0) beside real corpus runs, and must drop it. A new
analysis that reads `results/runs/` directly belongs in this list.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from airsbench.analyst.answerers import LiteralAnswerer
from airsbench.runner.config import NEVER_POOLED, build_refetch_arm, run_arm
from airsbench.runner.refetch import run_refetch

REAL = sorted(Path("results/runs").glob("*.json"))


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """Three real corpus runs (if present) plus one genuine refetch-arm artifact."""
    directory = tmp_path_factory.mktemp("runs")
    for path in REAL[:3]:
        (directory / path.name).write_text(path.read_text())
    stale_baseline = next(c for c in build_refetch_arm(replications=1, n_queries=3)
                          if c.fault_type == "freshness" and c.refetch_mode == "off")
    result = run_refetch(stale_baseline, LiteralAnswerer(), out_dir=directory)
    return directory, result.run_id


def _ids(runs):
    return {run["run_id"] for run in runs}


def test_the_artifact_is_attributed_to_the_arm(corpus):
    directory, run_id = corpus
    artifact = json.loads((directory / f"{run_id}.json").read_text())
    assert run_arm(artifact) == "refetch" and "refetch" in NEVER_POOLED


def test_flip_partition_drops_it_even_when_asked_for_other_arms(corpus):
    from airsbench.analysis.flip_partition import load_retrieval_runs

    directory, run_id = corpus
    assert run_id not in _ids(load_retrieval_runs(directory))
    assert run_id not in _ids(load_retrieval_runs(directory, include_other_arms=True))


def test_the_phase1_check_drops_it_even_when_asked_for_other_arms(corpus):
    from airsbench.analysis.phase1_check import load_runs

    directory, _ = corpus
    corpus_only = sum(run_arm(json.loads(p.read_text())) not in NEVER_POOLED
                      for p in directory.glob("*.json"))
    assert len(load_runs(directory, include_other_arms=True)) == corpus_only


def test_the_silent_definition_table_gains_no_row(corpus):
    from airsbench.analysis.silent_definition import load_runs, sensitivity

    directory, run_id = corpus
    runs = load_runs(directory)
    assert run_id not in _ids(runs)
    assert all(arm not in NEVER_POOLED for (arm, _, _), _ in sensitivity(runs))


def test_the_allow_list_loaders_drop_it(corpus):
    from airsbench.analysis.fragility import SHARED_ARMS, build_panels
    from airsbench.analysis.verifier_agreement import ARMS, load_runs
    from airsbench.gate.replay import load_batches

    directory, run_id = corpus
    assert run_id not in _ids(load_runs(directory)) and "refetch" not in ARMS
    assert all(batch.run_id != run_id for batch in load_batches(directory))
    # Fragility pools by allow-list; with only three corpus runs there may be no
    # panel at all, so the allow-list itself is what is pinned.
    assert "refetch" not in SHARED_ARMS
    everything = [json.loads(p.read_text()) for p in directory.glob("*.json")]
    for panel in build_panels(everything):
        assert run_id not in {column["run_id"] for column in panel.columns}


@pytest.mark.skipif(not Path("data/ecommerce").exists(), reason="needs data/ecommerce")
def test_airs_calibration_drops_it(corpus):
    from airsbench.analysis.airs_calibration import build_frame

    directory, _ = corpus
    frame = build_frame(directory, Path("data/ecommerce"))
    assert frame.empty or not set(frame["arm"]) & set(NEVER_POOLED)
