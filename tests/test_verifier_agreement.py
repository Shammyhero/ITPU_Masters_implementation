"""The live verifier must reproduce the corpus, and must say so loudly when it does not.

`analysis/verifier_agreement.py` is the admissibility argument for everything the
Analyst reports live: the same verifier, run over 6,714 logged decisions whose
answers are already known, has to agree decision by decision. Two things are
pinned here — that the check actually fails when it should (otherwise it proves
nothing), and, where the datasets are present, that it passes on the corpus.

The corpus test is the real one. It skips without `data/ecommerce`, which is not
committed (ESCI ≈ 100 MB), so `make test` stays green on a fresh clone while the
author's machine and `make figures` still run it.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from airsbench.analysis.verifier_agreement import (
    PUBLISHED_RAW,
    PUBLISHED_RESIDUAL,
    RunAgreement,
    _accuracy,
    load_runs,
    report,
    run,
)

DATA_DIR = Path("data/ecommerce")
RESULTS_DIR = Path("results/runs")

needs_corpus = pytest.mark.skipif(
    not (DATA_DIR / "updates.jsonl").exists(), reason="prepared catalog not present"
)


def agreement(**overrides) -> RunAgreement:
    base = dict(run_id="0" * 32, arm="main", condition=("streaming", "none", "none"),
                decisions=10, labels=Counter({"correct": 9, "agent_impairment": 1}),
                flips=Counter({(False, True): 9, (False, False): 1}),
                airs={"consistency": (100.0, 100.0), "semantic": (100.0, 100.0)})
    return RunAgreement(**{**base, **overrides})


def test_a_clean_run_reports_success():
    assert report([agreement()]) == 0


def test_one_disagreeing_decision_fails_the_whole_report():
    """A verifier that disagrees with the corpus is wrong; it does not average out."""
    assert report([agreement(), agreement(disagreements=["run x: correct — True vs False"])]) == 1


def test_a_realization_that_does_not_regenerate_fails_the_report():
    """Without the exact delivered records, corrupted-vs-impairment is guesswork."""
    off_by_a_hair = agreement(airs={"consistency": (77.611952, 77.611953),
                                    "semantic": (100.0, 100.0)})
    assert not off_by_a_hair.realized
    assert report([off_by_a_hair]) == 1


def test_published_accuracies_are_pooled_over_pipelines_but_not_over_arms():
    """The freshness sweep shares a fault name with the main arm at other levels;
    pooling it into RQ2's cells would quietly change the published denominators."""
    main = [agreement(condition=("streaming", "freshness", "severe"),
                      flips=Counter({(False, True): 6, (True, False): 4})),
            agreement(condition=("batch", "freshness", "severe"),
                      flips=Counter({(False, True): 4, (False, False): 6}))]
    sweep = agreement(arm="freshness_sweep", condition=("streaming", "freshness", "severe"),
                      flips=Counter({(False, False): 100}))
    assert _accuracy(main + [sweep], ("freshness", "severe")) == 0.5
    assert _accuracy(main + [sweep], ("freshness", "severe"), unflipped=True) == 10 / 16


@needs_corpus
class TestAgainstTheCorpus:
    @pytest.fixture(scope="class")
    def agreements(self) -> list[RunAgreement]:
        return run(RESULTS_DIR, DATA_DIR)

    def test_every_logged_decision_is_verified_and_agrees(self, agreements):
        assert [d for a in agreements for d in a.disagreements] == []
        expected = sum(len(r["decisions"]) for r in load_runs(RESULTS_DIR))
        assert sum(a.decisions for a in agreements) == expected

    def test_every_fault_realization_regenerates_from_its_config(self, agreements):
        """REVIEW F-E7: this failed for all 32 drift/stripping runs of the main
        factorial until the injector seed rule was corrected."""
        assert [a.run_id for a in agreements if not a.realized] == []

    def test_the_published_rq2_numbers_come_back_out(self, agreements):
        baseline = _accuracy(agreements, ("none", "none"), unflipped=True)
        for key, expected in PUBLISHED_RAW.items():
            assert _accuracy(agreements, key) == pytest.approx(expected, abs=0.0015)
        for key, expected in PUBLISHED_RESIDUAL.items():
            residual = _accuracy(agreements, key, unflipped=True) - baseline
            assert residual == pytest.approx(expected, abs=0.0015)

    def test_the_four_labels_partition_the_wrong_answers(self, agreements):
        """What Fig 4.10's right panel rests on."""
        for a in agreements:
            wrong_flipped = a.flips[(True, False)]
            wrong_unflipped = a.flips[(False, False)]
            committed_wrong = (a.labels["answer_key_moved"] + a.labels["both"]
                               + a.labels["corrupted_in_transit"]
                               + a.labels["agent_impairment"])
            abstained = a.labels["abstained"] + a.labels["unparseable"]
            assert a.labels["answer_key_moved"] + a.labels["both"] <= wrong_flipped
            assert (a.labels["corrupted_in_transit"] + a.labels["agent_impairment"]
                    <= wrong_unflipped)
            assert committed_wrong + abstained == wrong_flipped + wrong_unflipped
            assert a.labels["unattributed"] == 0
