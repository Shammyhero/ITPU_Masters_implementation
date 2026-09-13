"""Bake the console's bundled data from the repository. Run before a release.

    python -m airsbench.server.bake

An installed wheel cannot read `examples/` or `results/runs/`: neither is inside
the package. What the console needs from them is generated into `server/data/`
and committed, and `tests/test_server.py` fails when the committed file differs
from a fresh bake — so the data is never hand-edited and never stale.

Numbers in the prose come from the files they describe (the calibrated weights,
the policy itself), not from memory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..gate import Policy
from ..probe import DEFAULT_WEIGHTS, parse_records, score

ROOT = Path(__file__).parents[3]
OUT = Path(__file__).parent / "data" / "samples.json"

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    payload = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(payload['samples'])} samples, "
          f"{len(payload['policies'])} policies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
