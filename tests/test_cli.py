"""The `airs` command: dispatch, exit codes, and what a wheel must carry.

A pipeline step gates on `airs gate`'s exit status, so the entry point must be
the module's own program, not a lookalike. And a command that works from the
source tree can still be broken in the wheel — the declaration tests here are
the cheap half of that check; `make dist-check` is the expensive half.
"""

from __future__ import annotations

import json
import tomllib
from fnmatch import fnmatch
from pathlib import Path

import pytest

from airsbench import cli
from airsbench.probe import main as probe_main

ROOT = Path(__file__).parents[1]
PROBE = ROOT / "examples" / "probe"
POLICY = ROOT / "examples" / "gate" / "retrieval.json"


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_airs_probe_is_the_probe_itself(capsys):
    args = ["--records", str(PROBE / "degraded.jsonl"),
            "--source", str(PROBE / "source.jsonl"), "--task", "retrieval", "--json"]
    assert cli.main(["probe", *args]) == 0
    via_cli = capsys.readouterr().out
    assert probe_main(args) == 0
    assert capsys.readouterr().out == via_cli
    assert json.loads(via_cli)["band"] == "AT RISK"


def test_airs_gate_keeps_the_exit_codes_a_scheduler_relies_on(capsys):
    shared = ["--source", str(PROBE / "source.jsonl"), "--policy", str(POLICY)]
    assert cli.main(["gate", "--records", str(PROBE / "healthy.jsonl"), *shared]) == 0
    assert cli.main(["gate", "--records", str(PROBE / "degraded.jsonl"), *shared]) == 1
    assert cli.main(["gate", "--records", str(ROOT / "no-such-file.jsonl"), *shared]) == 2


def test_an_unknown_command_is_an_error_that_lists_the_real_ones(capsys):
    assert cli.main(["probes"]) == 2
    err = capsys.readouterr().err
    assert "unknown command 'probes'" in err
    assert all(name in err for name in cli.COMMANDS)


def test_no_command_prints_usage_and_fails_but_help_succeeds(capsys):
    assert cli.main([]) == 2
    assert "usage: airs" in capsys.readouterr().out
    assert cli.main(["--help"]) == 0


def test_version_comes_from_the_package(capsys):
    from airsbench import __version__

    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"airs {__version__}"


def test_subcommand_help_is_the_subcommand_parser(capsys):
    with pytest.raises(SystemExit) as exit_:
        cli.main(["gate", "--help"])
    assert exit_.value.code == 0
    assert "usage: airs gate" in capsys.readouterr().out


def test_the_airs_command_is_declared():
    assert _pyproject()["project"]["scripts"]["airs"] == "airsbench.cli:main"


def test_every_data_file_in_the_package_is_declared_as_package_data():
    """setuptools ships only .py files unless told otherwise. A wheel built without
    this declaration installed a probe that could not find its weights, and `make
    ci` — an editable install — could not see it."""
    patterns = _pyproject()["tool"]["setuptools"]["package-data"]["airsbench"]
    package = ROOT / "src" / "airsbench"
    data = [
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path.suffix not in (".py", ".pyc")
        and "__pycache__" not in path.parts and not path.name.startswith(".")
    ]
    assert "airs/calibrated_weights.json" in data
    undeclared = [f for f in data if not any(fnmatch(f, pattern) for pattern in patterns)]
    assert not undeclared, f"would be missing from the wheel: {undeclared}"
