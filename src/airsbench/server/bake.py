"""Bake the tool's bundled data from the repository. Run before a release.

    python -m airsbench.server.bake

An installed wheel cannot read `examples/`, `results/runs/` or `data/`: none of
them is inside the package. What the tool needs from them is generated into the
package and committed, and the tests fail when a committed file differs from a
fresh bake — so the data is never hand-edited and never stale.

  server/data/samples.json         the worked examples: records and policies
  server/data/replay_corpus.json   every run the gate findings were replayed
                                   over, reduced to what the accounting needs
  sources/data/esci_slice.json.gz  a seeded slice of the ESCI catalog and its
                                   update stream, for the bundled demo source
  sources/data/demo_manifest.yaml  the reviewed manifest describing that slice,
                                   built from the study's own semantic context

Numbers in the prose come from the files they describe (the calibrated weights,
the policy itself, the runs), not from memory.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..gate import Policy
from ..gate.replay import load_batches
from ..probe import DEFAULT_WEIGHTS, parse_records, score
from ..sources.demo import DEMO_MANIFEST, SLICE

ROOT = Path(__file__).parents[3]
DATA = Path(__file__).parent / "data"
OUT = DATA / "samples.json"
REPLAY_OUT = DATA / "replay_corpus.json"
ESCI_DATA = ROOT / "data" / "ecommerce"
# The arms `docs/gate_findings.md` replays: the fault factorial and the freshness
# sweep, on the primary model. Other arms change the treatment (metadata shown
# to the agent, other models, composed faults) and would price a different gate.
REPLAY_ARMS = ("main", "freshness_sweep")
# 200 queries — about 1,100 products and 11,000 updates, ~0.2 MB compressed: small
# enough to ship in the wheel, large enough that demo questions rarely repeat.
SLICE_QUERIES = 200
SLICE_SEED = 20260914

# Roles of the demo payload fields. Units are kept exactly where the runner's
# record builder keeps them (price, stock), so the rendered context equals the
# context the corpus agent read — pinned by tests/test_manifest.py.
DEMO_ROLES = {"product_id": "id", "title": "label", "brand": "label",
              "price": "measure", "stock": "measure"}
DEMO_UNIT_FIELDS = ("price", "stock")
DEMO_REVIEWED_AT = (2026, 9, 17)

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


def _plain(value: Any) -> Any:
    """A pandas/numpy cell as a JSON-safe Python value; NaN becomes null."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def build_esci_slice(data_dir: Path = ESCI_DATA, n_queries: int = SLICE_QUERIES,
                     seed: int = SLICE_SEED) -> dict[str, Any]:
    """A seeded set of queries, the products they name, and those products' updates.

    Updates for other products never change these products' state, so the slice
    replays to exactly the full catalog's state for every product it holds — a
    test checks that against `data/ecommerce`.
    """
    import pandas as pd

    catalog = pd.read_parquet(data_dir / "catalog.parquet").to_dict("records")
    known = {str(row["product_id"]) for row in catalog}
    queries = sorted(
        ({"query_id": int(q["query_id"]), "query": str(q["query"]),
          "relevant_product_ids": [str(p) for p in q["relevant_product_ids"]]}
         for q in pd.read_parquet(data_dir / "queries.parquet").to_dict("records")),
        key=lambda q: q["query_id"],
    )
    usable = [q for q in queries if sum(p in known for p in q["relevant_product_ids"]) >= 2]
    chosen = sorted(random.Random(seed).sample(usable, n_queries), key=lambda q: q["query_id"])
    wanted = {pid for query in chosen for pid in query["relevant_product_ids"]}
    rows = sorted(({key: _plain(value) for key, value in row.items()}
                   for row in catalog if str(row["product_id"]) in wanted),
                  key=lambda row: row["product_id"])
    updates = [update for update in
               (json.loads(line) for line in
                (data_dir / "updates.jsonl").read_text(encoding="utf-8").splitlines() if line)
               if update["product_id"] in wanted]
    return {
        "schema": "airs-esci-slice/1",
        "seed": seed,
        "n_queries": n_queries,
        "note": "A seeded slice of the study's ESCI catalog and its synthetic update stream, "
                "for the bundled demo source.",
        "semantic_context": json.loads((data_dir / "semantic_context.json").read_text()),
        "queries": chosen,
        "catalog": rows,
        "updates": updates,
    }


def build_demo_manifest():
    """The bundled demo slice's manifest, stamped as reviewed at a fixed time."""
    from datetime import datetime, timezone

    from ..sources.demo import PAYLOAD_FIELDS, _schema, load_slice
    from ..sources.manifest import FieldSpec, Manifest, default_questions, stamp

    data = load_slice()
    context = data.context
    fields = tuple(
        FieldSpec(name, DEMO_ROLES[name],
                  unit=context["units"].get(name) if name in DEMO_UNIT_FIELDS else None,
                  definition=context["descriptions"].get(name),
                  relationship=context["relationships"].get(name))
        for name in PAYLOAD_FIELDS
    )
    manifest = Manifest("demo", context["entity_type"], fields,
                        tuple(default_questions(fields)),
                        proposed_by="bundled: the study's own semantic context")
    return stamp(manifest, _schema("demo", data),
                 now=lambda: datetime(*DEMO_REVIEWED_AT, tzinfo=timezone.utc))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=ROOT / "results" / "runs")
    parser.add_argument("--data-dir", type=Path, default=ESCI_DATA)
    args = parser.parse_args(argv)

    samples = build()
    _write(OUT, samples)
    print(f"wrote {OUT}: {len(samples['samples'])} samples, "
          f"{len(samples['policies'])} policies")

    corpus = build_replay_corpus(args.results)
    _write(REPLAY_OUT, corpus)
    print(f"wrote {REPLAY_OUT}: {corpus['runs']} runs, {corpus['decisions']:,} decisions")

    from ..sources.manifest import dump_manifest

    DEMO_MANIFEST.write_text(dump_manifest(build_demo_manifest()), encoding="utf-8")
    print(f"wrote {DEMO_MANIFEST}")

    if not (args.data_dir / "updates.jsonl").exists():
        print(f"kept {SLICE}: {args.data_dir} is not prepared (make data-ecommerce)")
        return 0
    esci = build_esci_slice(args.data_dir)
    raw = json.dumps(esci, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    SLICE.parent.mkdir(parents=True, exist_ok=True)
    SLICE.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))  # mtime=0: byte-stable
    print(f"wrote {SLICE}: {len(esci['queries'])} queries, {len(esci['catalog']):,} products, "
          f"{len(esci['updates']):,} updates, {SLICE.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
