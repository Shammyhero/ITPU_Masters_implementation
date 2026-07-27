"""Resuming must not be able to skip runs or pay for them twice.

`--offset` indexes into a builder's grid, not into the results directory. Once
more than one arm writes there, counting files over-reports the offset and
silently skips conditions. This resolves the offset by matching artifacts to
grid entries, and refuses to emit a resume command when the assumptions
`--offset` depends on do not hold.
"""

from __future__ import annotations

from airsbench.analysis.campaign_state import report
from airsbench.runner.config import build_detectability_arm, build_grid


def _artifact(cfg, cost=0.01):
    return {"config": cfg.to_dict(), "usage": {"cost_usd": cost}}


def _main_prefix(n):
    return [_artifact(cfg) for cfg in build_grid(replications=4)[:n]]


def test_clean_partial_campaign_reports_the_right_offset(capsys):
    assert report(_main_prefix(66)) == 0
    out = capsys.readouterr().out
    assert "66/144 done" in out
    assert "--offset 66 --limit 78" in out


def test_other_arms_do_not_shift_the_main_offset(capsys):
    """The bug this module exists to prevent: 80 files, offset still 66."""
    runs = _main_prefix(66) + [_artifact(c) for c in build_detectability_arm()]
    assert report(runs) == 0
    out = capsys.readouterr().out
    assert "80 run artifacts" in out
    assert "--offset 66 --limit 78" in out, "file count leaked into the offset"
    assert "detectability (14 runs)            14/14 done" in out


def test_a_complete_arm_is_reported_complete_not_resumable(capsys):
    report([_artifact(c) for c in build_detectability_arm()])
    out = capsys.readouterr().out
    assert "complete" in out
    assert "--detectability --n-queries 80 --offset" not in out


def test_duplicates_are_flagged(capsys):
    runs = _main_prefix(66)
    runs.append(runs[3])
    assert report(runs) == 1
    assert "run more than once" in capsys.readouterr().out


def test_a_gap_blocks_the_resume_command(capsys):
    """A hole in the middle cannot be expressed as an offset."""
    runs = _main_prefix(66)
    del runs[10]
    assert report(runs) == 1
    out = capsys.readouterr().out
    assert "not a contiguous prefix" in out
    assert "re-run the gaps individually" in out
    assert "resume:" not in out, "must not offer an offset it cannot honour"


def test_an_unrecognised_seed_is_flagged_not_ignored(capsys):
    runs = _main_prefix(66)
    stray = dict(runs[0])
    stray["config"] = dict(stray["config"], seed=10_000_000)
    runs.append(stray)
    assert report(runs) == 1
    assert "outside every arm block" in capsys.readouterr().out


def test_an_empty_campaign_is_not_an_error(capsys):
    assert report([]) == 0
    assert "not started" in capsys.readouterr().out


def test_cost_is_totalled_across_arms(capsys):
    runs = [_artifact(cfg, cost=0.02) for cfg in build_grid(replications=4)[:10]]
    report(runs)
    assert "$0.200" in capsys.readouterr().out
