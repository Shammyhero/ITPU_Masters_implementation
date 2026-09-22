"""The refetch arm's grid and batch runner (docs/refetch_arm.md, build step 2).

What has to hold before the arm spends anything, and why each one is here:

- **The grid is the approved design.** 21 runs; gate never on healthy data (it
  would be the baseline, paid twice); every seed in the 90 000 block.
- **Paired (invariant 2).** Every cell and both states of a replication ask the
  same questions at the same simulated moments; cells of a state share a seed.
- **The artifact is the corpus's shape, attributed to the arm**, and records the
  question's exposure as first delivered — identical in every cell of a state.
- **The gate cell is correct by construction on this source** (§2.2): with a
  literal answerer, every re-read question is answered right. Pinned, because the
  write-up must not present it as a finding.
- **The dry-run counts what the loop actually sends** — the same prompts, the same
  tokenizer — so the estimate the cap is checked against is not a guess.
- **Spend:** refused before the campaign, stopped before a run it could not
  finish, never recorded in ~/.airs; a transport failure loses one run, not the
  campaign; a missing key costs nothing.
"""

from __future__ import annotations

import json
from argparse import Namespace
from collections import Counter
from types import SimpleNamespace

import pytest

from airsbench.analysis.campaign_state import _key
from airsbench.analyst.answerers import AnswererError, LiteralAnswerer, ModelAnswerer, Usage
from airsbench.analyst.budget import cost_of
from airsbench.analyst.verifier import AgentAnswer
from airsbench.runner import run as cli
from airsbench.runner.config import (
    REFETCH_SEED_RANGE,
    arm_of,
    build_refetch_arm,
    refetch_cell,
    run_arm,
)
from airsbench.runner.refetch import (
    PLACEHOLDER_WHY,
    ArmLedger,
    TokenCounter,
    arm_pair,
    estimate,
    execute_refetch_arm,
    question_seed,
    run_refetch,
)


def cell(configs, name, state, rep=1):
    fault = "none" if state == "healthy" else "freshness"
    return next(c for c in configs if refetch_cell(c) == name and c.fault_type == fault
                and c.replication == rep)


def args(**overrides):
    base = {"dry_run": False, "max_cost": 1.0, "offset": 0, "limit": None, "out": ""}
    return Namespace(**{**base, **overrides})


# ---- the grid ---------------------------------------------------------------------------

def test_the_grid_is_the_approved_design():
    grid = build_refetch_arm()
    assert len(grid) == 21
    cells = Counter((refetch_cell(c), "healthy" if c.fault_type == "none" else "stale")
                    for c in grid)
    assert cells == {(name, state): 3
                     for name in ("baseline", "agent_hidden", "agent_shown")
                     for state in ("healthy", "stale")} | {("gate", "stale"): 3}
    assert all(c.n_queries == 150 and c.model == "gpt-4o-mini" and c.pipeline == "streaming"
               and c.task == "retrieval" and c.dataset == "esci_demo_slice" for c in grid)
    stale = [c for c in grid if c.fault_type != "none"]
    assert all(c.severity == "severe" and c.injector_params == {"delay_seconds": 5.0}
               for c in stale)


def test_every_seed_is_the_arms_and_attributed_to_it():
    for c in build_refetch_arm():
        assert REFETCH_SEED_RANGE[0] <= c.seed < REFETCH_SEED_RANGE[1]
        assert arm_of(c.seed) == "refetch" and run_arm({"config": c.to_dict()}) == "refetch"


def test_the_order_is_replication_major():
    """A campaign stopped with --limit leaves whole replications, all cells of each."""
    assert [c.replication for c in build_refetch_arm()] == [1] * 7 + [2] * 7 + [3] * 7


def test_cells_of_a_state_share_a_seed_and_states_share_the_questions():
    grid = build_refetch_arm()
    for rep in (1, 2, 3):
        members = [c for c in grid if c.replication == rep]
        for fault in ("none", "freshness"):
            assert len({c.seed for c in members if c.fault_type == fault}) == 1
        assert len({c.seed for c in members}) == 2  # the states differ, the cells do not
        assert len({c.sample_seed for c in members}) == 1  # (task, replication) only
        assert {question_seed(c, 7) for c in members} == {members[0].sample_seed * 1_000 + 7}


def test_the_same_question_seed_is_the_same_question_in_both_states():
    grid = build_refetch_arm()
    healthy, stale = cell(grid, "baseline", "healthy"), cell(grid, "baseline", "stale")
    for index in range(5):
        a = arm_pair(healthy).delivered.sample(6, seed=question_seed(healthy, index))
        b = arm_pair(stale).delivered.sample(6, seed=question_seed(stale, index))
        assert (a.key, a.as_of, a.ids) == (b.key, b.as_of, b.ids)
        assert a.meta["served_as_of"] - b.meta["served_as_of"] == pytest.approx(5.0)


def test_a_cell_is_recovered_from_an_artifacts_config():
    for c in build_refetch_arm():
        assert refetch_cell(c.to_dict()) == refetch_cell(c)
    with pytest.raises(ValueError):
        refetch_cell({"refetch_mode": None})


def test_campaign_state_tells_the_cells_apart():
    """Three cells share a seed within a (state, replication); only the mode differs."""
    rep1_stale = [c for c in build_refetch_arm() if c.replication == 1 and c.fault_type != "none"]
    assert len({_key(c.to_dict()) for c in rep1_stale}) == 4


# ---- one run, at $0 -----------------------------------------------------------------------

@pytest.fixture(scope="module")
def small():
    return build_refetch_arm(replications=1, n_queries=6)


def test_an_artifact_has_the_corpus_shape_and_the_arms_seed(small, tmp_path):
    result = run_refetch(cell(small, "baseline", "stale"), LiteralAnswerer(), out_dir=tmp_path)
    artifact = json.loads((tmp_path / f"{result.run_id}.json").read_text())
    assert set(artifact) == {"run_id", "config", "started_at", "finished_at", "metrics",
                             "airs", "usage", "decisions"}
    assert run_arm(artifact) == "refetch" and artifact["config"]["refetch_mode"] == "off"
    assert len(artifact["decisions"]) == 6
    assert set(artifact["airs"]) == {"freshness", "latency", "consistency", "semantic", "total"}
    first = artifact["decisions"][0]
    # No records, as in the corpus: ids and seeds regenerate them exactly.
    assert not {"records", "delivered", "served", "upstream"} & set(first)
    assert '"price"' not in json.dumps(artifact["decisions"])
    assert first["question_seed"] == question_seed(cell(small, "baseline", "stale"), 0)


def test_the_baseline_admits_everything_and_records_what_refusal_would_have_done(small):
    stale = run_refetch(cell(small, "baseline", "stale"), LiteralAnswerer(), out_dir=None)
    healthy = run_refetch(cell(small, "baseline", "healthy"), LiteralAnswerer(), out_dir=None)
    assert all(d["gate"]["verdict"] == "admit" and d["gate"]["shadowed"]
               and d["gate"]["rules"] == ["max_record_age_seconds"] for d in stale.decisions)
    assert stale.metrics["would_refuse"] == 6 and healthy.metrics["would_refuse"] == 0
    assert stale.metrics["refetch_rate"] == 0.0


def test_the_gate_re_reads_every_stale_batch_and_is_right_by_construction(small):
    """§2.2: a re-read returns exactly the answer key, so the literal rule cannot
    miss. The arm reports the gate cell as a cost, never as this."""
    result = run_refetch(cell(small, "gate", "stale"), LiteralAnswerer(), out_dir=None)
    assert all(d["refetch"]["initiated_by"] == "gate" for d in result.decisions)
    verifiable = [d for d in result.decisions if d["verifiable"]]
    assert verifiable and all(d["correct"] for d in verifiable)
    # The first reading is kept: stale, which is why it re-read.
    assert all(d["dimensions_first"]["freshness"] < 100 for d in result.decisions)
    assert result.airs["freshness"] < 100


def test_exposure_as_first_delivered_is_the_same_in_every_cell_of_a_state(small):
    stale = [c for c in small if c.fault_type != "none"]
    exposures = {refetch_cell(c): [d["flipped_as_delivered"] for d in
                                   run_refetch(c, LiteralAnswerer(), out_dir=None).decisions]
                 for c in stale}
    assert len({tuple(v) for v in exposures.values()}) == 1


class AsksThenAnswers:
    """Asks to re-read the first record, then answers literally. No model."""

    name = "asks-then-answers"

    def __init__(self):
        self.calls = 0

    def answer(self, question, plan, records):
        self.calls += 1
        if self.calls % 2:
            return AgentAnswer(refetch_ids=(records[0].meta["record_id"],), text="why"), \
                Usage(self.name)
        return LiteralAnswerer().answer(question, plan, records)


def test_the_agents_requests_are_counted_and_attributed(small):
    result = run_refetch(cell(small, "agent_shown", "stale"), AsksThenAnswers(), out_dir=None)
    assert result.metrics["agent_requests"] == 6 and result.metrics["refetch_rate"] == 1.0
    assert all(d["refetch"]["initiated_by"] == "agent" and len(d["refetch"]["asked_ids"]) == 1
               for d in result.decisions)


# ---- the dry-run counts what the loop sends -------------------------------------------------

def _ids_in(user_message: str) -> list[str]:
    block = user_message.split('fields are under "data"):\n', 1)[1].split("\n\nAnswer the", 1)[0]
    return [record["id"] for record in json.loads(block)]


class Recording:
    """A stand-in for LLMClient that asks to re-read everything (the worst case),
    then answers — and keeps every message list it was sent."""

    def __init__(self, asks: bool):
        self.asks, self.sent = asks, []
        self.usage = SimpleNamespace(input_tokens=0, output_tokens=0)

    def call_json(self, messages):
        self.sent.append(messages)
        if self.asks and len(messages) == 2:
            return {"action": "refetch", "ids": _ids_in(messages[1][1]), "why": PLACEHOLDER_WHY}
        return {"answer": "a", "plan": None, "value": "x", "confidence": 0.5, "abstain": False}


@pytest.mark.parametrize("name,state", [("baseline", "stale"), ("gate", "stale"),
                                        ("agent_shown", "stale"), ("agent_hidden", "healthy")])
def test_the_dry_run_counts_exactly_what_the_loop_sends(small, name, state):
    config = cell(small, name, state)
    agent = config.refetch_mode == "agent"
    client = Recording(asks=agent)
    run_refetch(config, ModelAnswerer("ollama/x", client=client, offer_refetch=agent),
                out_dir=None)
    counter = TokenCounter(config.model, offer_refetch=agent)
    sent = sum(counter.count(messages) for messages in client.sent)
    est = estimate(config)
    assert est.first_input + est.second_input == sent
    assert est.first_calls == 6 and est.second_calls == (6 if agent else 0)
    assert est.worst_usd >= est.expected_usd > 0


# ---- the campaign: spend and failure --------------------------------------------------------

def test_the_campaign_is_refused_when_its_worst_case_exceeds_the_cap(small, tmp_path, capsys):
    assert execute_refetch_arm(small, args(max_cost=0.001, out=str(tmp_path))) == 1
    assert "REFUSED" in capsys.readouterr().out and not list(tmp_path.glob("*.json"))


def test_a_dry_run_spends_nothing_and_writes_nothing(small, tmp_path, capsys):
    never = lambda *a: pytest.fail("a dry run built an answerer")  # noqa: E731
    assert execute_refetch_arm(small, args(dry_run=True, out=str(tmp_path)), make=never) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "worst case" in out and not list(tmp_path.glob("*.json"))


def test_offset_and_limit_select_a_stage(small, capsys):
    execute_refetch_arm(small, args(dry_run=True, offset=2, limit=3))
    assert "Staged: runs 3-5 of 7" in capsys.readouterr().out


def test_a_campaign_runs_every_cell_and_keeps_its_spend_out_of_home(small, tmp_path):
    budgets = []

    def make(spec, budget, offer):
        budgets.append(budget)
        return AsksThenAnswers() if offer else LiteralAnswerer()

    assert execute_refetch_arm(small, args(out=str(tmp_path)), make=make) == 0
    artifacts = [json.loads(p.read_text()) for p in tmp_path.glob("*.json")]
    assert len(artifacts) == 7 and {run_arm(a) for a in artifacts} == {"refetch"}
    assert all(isinstance(b.ledger, ArmLedger) for b in budgets)
    assert len({id(b) for b in budgets}) == 1  # one cap across the whole invocation


def test_a_missing_key_stops_the_campaign_before_anything_runs(small, tmp_path, capsys):
    def make(spec, budget, offer):
        raise AnswererError("OPENAI_API_KEY not set")

    assert execute_refetch_arm(small, args(out=str(tmp_path)), make=make) == 1
    assert "Cannot start" in capsys.readouterr().out and not list(tmp_path.glob("*.json"))


class Unreachable:
    name = "unreachable"

    def answer(self, *a):
        raise AnswererError("openai/gpt-4o-mini could not be reached (timeout)")


def test_a_transport_failure_loses_one_run_not_the_campaign(small, tmp_path, capsys):
    built = []

    def make(spec, budget, offer):
        built.append(offer)
        # The key check, then the first run fails; every other run is fine.
        return Unreachable() if len(built) == 2 else LiteralAnswerer()

    assert execute_refetch_arm(small, args(out=str(tmp_path)), make=make) == 1
    assert len(list(tmp_path.glob("*.json"))) == 6
    assert "1 run(s) FAILED" in capsys.readouterr().out


def charging(tokens_per_call: int):
    """A model client that bills `tokens_per_call` input tokens for every answer."""
    usage = SimpleNamespace(input_tokens=0, output_tokens=0)

    class Billed:
        def __init__(self):
            self.usage = usage

        def call_json(self, messages):
            usage.input_tokens += tokens_per_call
            return {"answer": "a", "plan": None, "value": "x", "confidence": 0.5,
                    "abstain": False}

    return lambda spec, budget, offer: ModelAnswerer(spec, client=Billed(), budget=budget,
                                                     offer_refetch=offer)


def test_a_campaign_stops_before_a_run_it_cannot_afford(small, tmp_path, capsys):
    """Billed more than estimated, the cap stops the campaign BETWEEN runs: the first
    run completes, and the second is not started because its worst case no longer fits."""
    baseline_only = [c for c in small if c.refetch_mode == "off"]  # one call per question
    cap = sum(estimate(c).worst_usd for c in baseline_only) * 1.05 + 0.02
    second_worst = estimate(baseline_only[1]).worst_usd
    per_call_usd = (cap - second_worst / 2) / 6  # run 1 leaves half of run 2's worst case
    tokens = int(per_call_usd / cost_of("gpt-4o-mini", 1, 0))
    assert execute_refetch_arm(baseline_only, args(max_cost=cap, out=str(tmp_path)),
                               make=charging(tokens)) == 1
    out = capsys.readouterr().out
    assert "STOPPED before run 2" in out and "--offset 1" in out
    artifacts = list(tmp_path.glob("*.json"))
    assert len(artifacts) == 1
    assert len(json.loads(artifacts[0].read_text())["decisions"]) == 6


def test_a_call_that_would_cross_the_cap_stops_the_campaign_and_writes_nothing(
        small, tmp_path, capsys):
    """The analyst Budget's check before every call: a run cut short is not saved."""
    cap = sum(estimate(c).worst_usd for c in small) * 1.05
    assert execute_refetch_arm(small, args(max_cost=cap, out=str(tmp_path)),
                               make=charging(5_000_000)) == 1
    out = capsys.readouterr().out
    assert "STOPPED: refused before calling" in out and "wrote nothing" in out
    assert not list(tmp_path.glob("*.json"))


# ---- the command line -------------------------------------------------------------------------

def test_the_cli_dry_runs_the_arm(capsys):
    assert cli.main(["--refetch-arm", "--dry-run", "--replications", "1",
                     "--n-queries", "2", "--max-cost", "5"]) == 0
    assert "7 runs x 2 questions" in capsys.readouterr().out


def test_other_modes_keep_their_default_of_twelve(capsys):
    cli.main(["--smoke", "--dry-run", "--max-cost", "5"])
    assert "x 12 queries" in capsys.readouterr().out
