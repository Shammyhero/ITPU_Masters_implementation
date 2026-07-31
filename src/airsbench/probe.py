"""`airs probe` — score a pipeline's readiness before deploying an agent on it.

This is what makes "pre-deployment" concrete. It reads a sample of records as
your pipeline actually delivers them, scores the four AIRS dimensions, and
applies the weights calibrated in RQ4 to produce a composite and a risk band.

**No agent. No ground truth. No model calls. No API key.** That is the whole
point: the score is computable from pipeline telemetry, before an agent exists
to be harmed by the pipeline.

    python -m airsbench.probe --records delivered.jsonl --task retrieval
    python -m airsbench.probe --records delivered.jsonl --source upstream.jsonl \\
        --task retrieval --json

## Input

One JSON object per line. Every field is optional except `payload` — the probe
reports what it could and could not measure rather than assuming.

    {"id": "SKU-1", "payload": {"price": 12.99, "stock": 4},
     "context": {"entity_type": "...", "units": {...},
                 "descriptions": {...}, "relationships": {...}},
     "event_timestamp": 1772000000.0, "read_timestamp": 1772000005.05,
     "delivery_latency_ms": 120.0}

`--source` takes the same shape, matched on `id`: the records as they exist
upstream, before the pipeline moved them. Consistency needs both sides.

## What it refuses to do

**A dimension it cannot measure is reported as UNMEASURED, never as 100.**

Scoring an absent measurement as perfect is the failure mode that would make
this tool actively dangerous — a pipeline with no consistency check would earn
a clean bill of health precisely because nobody looked. The composite is
computed over the measured dimensions only, and the report says which weight
was unaccounted for. A probe over a sample with no `--source` and no timestamps
reports a semantic score and an explicit warning, not a reassuring number.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from agentic_faults import Record

from .airs import (
    freshness_score,
    latency_score,
    mean_semantic_completeness,
    payload_consistency,
    semantic_score,
)

DIMENSIONS = ("freshness", "latency", "consistency", "semantic")
DEFAULT_WEIGHTS = Path(__file__).parent / "airs" / "calibrated_weights.json"

# Risk bands over the composite. Deliberately coarse: the calibration ranks
# pipelines well (held-out Spearman -0.75 to -0.88) but does not support a
# precise failure-rate prediction, so the output is an ordering aid, not a
# forecast.
BANDS = (
    (85.0, "READY", "no dimension materially degraded"),
    (70.0, "WATCH", "a dimension is degraded enough to matter"),
    (0.0, "AT RISK", "expect elevated silent failure on this pipeline"),
)


class ProbeError(ValueError):
    """Input the probe cannot score, reported rather than guessed around."""


def load_records(path: Path) -> list[dict[str, Any]]:
    records = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProbeError(f"{path}:{number}: not valid JSON — {exc}") from exc
        if not isinstance(entry, dict) or "payload" not in entry:
            raise ProbeError(f"{path}:{number}: every record needs a 'payload' object")
        records.append(entry)
    if not records:
        raise ProbeError(f"{path}: no records found")
    return records


def _as_record(entry: dict[str, Any]) -> Record:
    record = Record(
        payload=dict(entry["payload"]),
        context=dict(entry.get("context") or {}),
        event_timestamp=float(entry.get("event_timestamp") or 0.0),
    )
    if entry.get("read_timestamp") is not None:
        record.read_timestamp = float(entry["read_timestamp"])
    return record


def measure(
    delivered: list[dict[str, Any]], source: list[dict[str, Any]] | None = None
) -> dict[str, dict[str, Any]]:
    """Score each dimension, or mark it unmeasured and say why.

    Every dimension returns {"score": float|None, "detail": str}. A None score
    is the honest answer when the input does not carry what the dimension needs
    — see the module docstring on why that must never become 100.
    """
    out: dict[str, dict[str, Any]] = {}
    records = [_as_record(e) for e in delivered]

    # ---- freshness: read_timestamp - event_timestamp ---------------------
    ages = [
        float(e["read_timestamp"]) - float(e["event_timestamp"])
        for e in delivered
        if e.get("read_timestamp") is not None and e.get("event_timestamp") is not None
    ]
    if not ages:
        out["freshness"] = {"score": None, "detail":
                            "no record carries both event_timestamp and read_timestamp"}
    elif min(ages) < 0:
        raise ProbeError(
            "a record was read before its event timestamp — check clock skew or "
            "a swapped field; refusing to score freshness from it"
        )
    else:
        mean_age = statistics.fmean(ages)
        out["freshness"] = {
            "score": freshness_score(max(mean_age, 1e-6)),
            "detail": f"mean age {mean_age:.2f}s over {len(ages)} of "
                      f"{len(delivered)} records",
        }

    # ---- latency: observed delivery time ---------------------------------
    latencies = [
        float(e["delivery_latency_ms"]) for e in delivered
        if e.get("delivery_latency_ms") is not None
    ]
    if not latencies:
        out["latency"] = {"score": None,
                          "detail": "no record carries delivery_latency_ms"}
    else:
        mean_latency = statistics.fmean(latencies)
        out["latency"] = {
            "score": latency_score(max(mean_latency, 1.0)),
            "detail": f"mean {mean_latency:.0f}ms over {len(latencies)} of "
                      f"{len(delivered)} records",
        }

    # ---- consistency: delivered payload vs upstream ----------------------
    if source is None:
        out["consistency"] = {"score": None, "detail":
                              "no --source sample given; nothing to compare against"}
    else:
        by_id = {e.get("id"): e for e in source if e.get("id") is not None}
        pairs = [
            (by_id[e["id"]], e)
            for e in delivered
            if e.get("id") is not None and e.get("id") in by_id
        ]
        if not pairs:
            out["consistency"] = {"score": None, "detail":
                                  "no record id matched between source and delivered"}
        else:
            agreement = statistics.fmean(
                payload_consistency(_as_record(src), _as_record(dst))
                for src, dst in pairs
            )
            out["consistency"] = {
                "score": 100.0 * agreement,
                "detail": f"{len(pairs)} of {len(delivered)} records matched by id",
            }

    # ---- semantic completeness -------------------------------------------
    if not any(e.get("context") for e in delivered):
        out["semantic"] = {"score": 0.0, "detail":
                           "no record carries a context block — the semantic layer "
                           "is absent, which is a score of 0, not an absent measurement"}
    else:
        out["semantic"] = {
            "score": semantic_score(mean_semantic_completeness(records)),
            "detail": f"context present on "
                      f"{sum(1 for e in delivered if e.get('context'))} of "
                      f"{len(delivered)} records",
        }
    return out


def load_weights(path: Path, task: str) -> tuple[dict[str, float], dict[str, Any]]:
    payload = json.loads(path.read_text())
    profiles = payload.get("profiles", {})
    if task not in profiles:
        raise ProbeError(
            f"no calibrated profile for task {task!r}. Available: "
            f"{', '.join(sorted(profiles)) or '(none)'}. The weights invert "
            f"across tasks, so a profile from another task must not be reused — "
            f"recalibrate for this one."
        )
    return profiles[task], payload


def composite(measured: dict[str, dict[str, Any]], weights: dict[str, float]):
    """Weighted composite over MEASURED dimensions only.

    Returns (score, covered_weight). `covered_weight` is the share of the
    calibrated weight the composite actually rests on — the caller must show
    it, because a composite covering 30% of the weight is a different claim
    from one covering 100%.
    """
    usable = {
        dim: measured[dim]["score"]
        for dim in DIMENSIONS
        if measured.get(dim, {}).get("score") is not None
    }
    covered = sum(weights.get(dim, 0.0) for dim in usable)
    if covered == 0:
        return None, 0.0
    score = sum(weights[dim] * usable[dim] for dim in usable) / covered
    return score, covered


def band(score: float) -> tuple[str, str]:
    for threshold, label, note in BANDS:
        if score >= threshold:
            return label, note
    return BANDS[-1][1], BANDS[-1][2]


def report(measured, weights, meta, task: str, n_records: int) -> int:
    score, covered = composite(measured, weights)

    print(f"AIRS probe — {n_records} records, task profile '{task}'")
    print(f"weights calibrated {meta.get('calibrated_at', '?')} "
          f"against target '{meta.get('target', '?')}'\n")

    print(f"  {'dimension':<14}{'score':>11}{'weight':>9}   evidence")
    print("  " + "-" * 78)
    unmeasured = []
    for dim in DIMENSIONS:
        entry = measured.get(dim, {"score": None, "detail": "not evaluated"})
        weight = weights.get(dim, 0.0)
        if entry["score"] is None:
            unmeasured.append((dim, weight))
            print(f"  {dim:<14}{'UNMEASURED':>11}{weight:>9.1%}   {entry['detail']}")
        else:
            print(f"  {dim:<14}{entry['score']:>11.1f}{weight:>9.1%}   {entry['detail']}")

    print()
    if score is None:
        print("  NO SCORE — not one dimension could be measured from this input.")
        print("  Supply timestamps, a --source sample, or context blocks.")
        return 1

    label, note = band(score)
    print(f"  AIRS {score:.1f}/100   {label}   ({note})")

    if covered < 0.999:
        print(f"\n  ⚠ This composite rests on {covered:.0%} of the calibrated weight.")
        print("    Unmeasured dimensions are EXCLUDED, not assumed healthy:")
        for dim, weight in unmeasured:
            print(f"      {dim} ({weight:.1%} of the weight) was not measured")
        print("    A pipeline can score well here purely because nobody looked.")

    validation = meta.get("validation", {}).get(task, {})
    if validation:
        print(f"\n  Calibration for this task held out "
              f"{validation.get('held_out_runs', '?')} runs and ranked them at "
              f"Spearman {validation.get('held_out_spearman', float('nan')):+.3f}.")
    print("  The score ranks pipelines; it does not predict a failure rate.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="airs probe", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--records", type=Path, required=True,
                        help="JSONL of records as the pipeline delivers them")
    parser.add_argument("--source", type=Path, default=None,
                        help="JSONL of the same records upstream, matched on 'id' "
                             "(required to score consistency)")
    parser.add_argument("--task", default="retrieval",
                        help="which calibrated weight profile to apply")
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable output instead of a report")
    args = parser.parse_args(argv)

    try:
        delivered = load_records(args.records)
        source = load_records(args.source) if args.source else None
        weights, meta = load_weights(args.weights, args.task)
        measured = measure(delivered, source)
    except ProbeError as exc:
        print(f"error: {exc}")
        return 2

    if args.json:
        score, covered = composite(measured, weights)
        print(json.dumps({
            "task": args.task,
            "n_records": len(delivered),
            "dimensions": measured,
            "weights": weights,
            "airs": score,
            "weight_covered": covered,
            "band": band(score)[0] if score is not None else None,
            "calibration": {k: meta.get(k) for k in ("calibrated_at", "target")},
        }, indent=2))
        return 0 if score is not None else 1

    return report(measured, weights, meta, args.task, len(delivered))


if __name__ == "__main__":
    raise SystemExit(main())
