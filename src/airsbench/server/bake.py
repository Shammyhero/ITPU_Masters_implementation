"""Bake the console's bundled data from the repository. Run before a release.

    python -m airsbench.server.bake

An installed wheel cannot read `examples/` or `results/runs/`: neither is inside
the package. What the console needs from them is generated into `server/data/`
and committed, and the tests fail when a committed file differs from a fresh
bake — so the data is never hand-edited and never stale.

  samples.json         the worked examples: sample records and example policies
  replay_corpus.json   every run the gate findings were replayed over, reduced
                       to what the accounting needs, so /api/replay prices a
                       policy on the same evidence as `docs/gate_findings.md`

Numbers in the prose come from the files they describe (the calibrated weights,
the policy itself, the runs), not from memory.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..gate import Policy
from ..gate.replay import load_batches
from ..probe import DEFAULT_WEIGHTS, parse_records, score

ROOT = Path(__file__).parents[3]
DATA = Path(__file__).parent / "data"
OUT = DATA / "samples.json"
REPLAY_OUT = DATA / "replay_corpus.json"
# The arms `docs/gate_findings.md` replays: the fault factorial and the freshness
# sweep, on the primary model. Other arms change the treatment (metadata shown
# to the agent, other models, composed faults) and would price a different gate.
REPLAY_ARMS = ("main", "freshness_sweep")

SAMPLES = {
    "healthy": ("Healthy pipeline",
                "Real ESCI catalog records, delivered fresh, fast and intact."),
    "degraded": ("Degraded pipeline",
                 "The same records delivered stale and slow, with schema drift and "
                 "semantic stripping."),
}


def _policy_note(name: str, policy: dict[str, Any], weights: dict[str, dict[str, float]]) -> str:
    if name == "retrieval":
        return (f"For retrieval-like tasks. Consistency carries "
                f"{weights['retrieval']['consistency']:.0%} of the calibrated retrieval "
                f"weight, so it is gated first.")
    if name == "staleness-budget":
        return (f"For classification-like tasks: records at most "
                f"{policy['max_record_age_seconds']} s old, the threshold the freshness "
                f"sweep located. On retrieval it prevents little and still costs "
                f"correct answers.")
    raise KeyError(f"examples/gate/{name}.json has no note in server/bake.py; write one")


def build(root: Path = ROOT) -> dict[str, Any]:
    probe_dir, gate_dir = root / "examples" / "probe", root / "examples" / "gate"
    source = (probe_dir / "source.jsonl").read_text(encoding="utf-8")

    samples = []
    for name, (label, description) in SAMPLES.items():
        delivered = (probe_dir / f"{name}.jsonl").read_text(encoding="utf-8")
        # A sample the probe cannot score must fail the bake, not the user.
        score(parse_records(delivered, name), parse_records(source, "source", unique_ids=True))
        samples.append({"id": name, "label": label, "description": description,
                        "task": "retrieval", "delivered": delivered, "source": source})

    weights = json.loads(DEFAULT_WEIGHTS.read_text(encoding="utf-8"))["profiles"]
    policies = []
    for path in sorted(gate_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        policies.append({"id": path.stem, "policy": data,
                         "description": Policy.from_dict(data).describe(),
                         "note": _policy_note(path.stem, data, weights)})
    return {"schema": "airs-samples/1", "samples": samples, "policies": policies}


def build_replay_corpus(results_dir: Path = ROOT / "results" / "runs") -> dict[str, Any]:
    """`gate.replay.load_batches` over the run artifacts, plus where they came from.

    It is that function's output, not a re-derivation, so a replay over the baked
    corpus and a replay over `results/runs/` cannot disagree.
    """
    batches = load_batches(results_dir, arms=REPLAY_ARMS)
    if not batches:
        raise SystemExit(f"no replayable runs under {results_dir}")
    tasks = sorted({b.task for b in batches})
    models = sorted({b.model for b in batches})
    return {
        "schema": "airs-replay-corpus/1",
        "arms": list(REPLAY_ARMS),
        "tasks": tasks,
        "models": models,
        "runs": len(batches),
        "decisions": sum(b.n for b in batches),
        "note": (f"Synthetic faults injected into {len(tasks)} benchmark tasks, answered "
                 f"by {', '.join(models)}. A price replayed over these runs is evidence "
                 f"of what a gate cost in this study, not a forecast for another "
                 f"pipeline or model."),
        "batches": [asdict(b) for b in batches],
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=ROOT / "results" / "runs")
    args = parser.parse_args(argv)

    samples = build()
    _write(OUT, samples)
    print(f"wrote {OUT}: {len(samples['samples'])} samples, "
          f"{len(samples['policies'])} policies")

    corpus = build_replay_corpus(args.results)
    _write(REPLAY_OUT, corpus)
    print(f"wrote {REPLAY_OUT}: {corpus['runs']} runs, {corpus['decisions']:,} decisions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
