"""`airs probe` — score a pipeline's readiness before deploying an agent on it.

This is what makes "pre-deployment" concrete. It reads a sample of records as
your pipeline actually delivers them, scores the four AIRS dimensions, and
applies the weights calibrated in RQ4 to produce a composite and a risk band.

**No agent. No ground truth. No model calls. No API key.** That is the whole
point: the score is computable from pipeline telemetry, before an agent exists
to be harmed by the pipeline.

    airs probe --records delivered.jsonl --task retrieval
    airs probe --records delivered.jsonl --source upstream.jsonl --task retrieval --json

## Input

One JSON object per line. Every field is optional except `payload` — the probe
reports what it could and could not measure rather than assuming.

    {"id": "SKU-1", "payload": {"price": 12.99, "stock": 4},
     "context": {"entity_type": "...", "units": {...},
                 "descriptions": {...}, "relationships": {...}},
     "event_timestamp": 1772000000.0, "read_timestamp": "2026-02-25T06:13:25.050Z",
     "delivery_latency_ms": 120.0}

Timestamps are epoch seconds or ISO-8601 strings WITH a timezone. A zoneless
string is refused: the two timestamps are usually written by two different
systems, and a time without a zone cannot be compared across them. An epoch
value in milliseconds is refused too — if both timestamps were milliseconds,
every age would be a thousand times too large, and the probe would call a fresh
pipeline stale without any error at all.

`--source` takes the same shape, matched on `id` (a string or an integer): the
records as they exist upstream, before the pipeline moved them. Consistency
needs both sides, and exactly one upstream version per id.

## What it refuses to do

**A dimension it cannot measure is reported as UNMEASURED, never as 100.**

Scoring an absent measurement as perfect is the failure mode that would make
this tool actively dangerous — a pipeline with no consistency check would earn
a clean bill of health precisely because nobody looked. The composite is
computed over the measured dimensions only, and the report says which weight
was unaccounted for. A probe over a sample with no `--source` and no timestamps
reports a semantic score and an explicit warning, not a reassuring number.

Malformed input is refused the same way. Every problem is a `ProbeError` that
says where it is and how to fix it — whether the records came from a file, the
`airs` command, the admission controller or the web console — never a
traceback, and never a guess.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

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

# Read as epoch seconds, a value this large is a date after the year 5000. What
# it almost always is instead: milliseconds (or finer) since the epoch.
MILLISECOND_SUSPECT = 1e11

DUPLICATE_SOURCE_FIX = (
    "consistency needs exactly one upstream version per id; sample the latest "
    "version of each record"
)


class ProbeError(ValueError):
    """Input the probe cannot score, reported rather than guessed around."""


# ---- input: one validator for every caller ---------------------------------

def _json_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true/false"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "an array"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__


def _timestamp(value: Any, field: str, where: str) -> float:
    """Epoch seconds, from epoch seconds or a zoned ISO-8601 string."""
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            raise ProbeError(
                f"{where}: {field} {value!r} is not an ISO-8601 time; use e.g. "
                f"2026-09-13T10:00:05.050Z, or epoch seconds"
            ) from None
        if parsed.tzinfo is None:
            raise ProbeError(
                f"{where}: {field} {value!r} has no timezone, so it cannot be compared "
                f"with a time written by another system; append Z for UTC or an "
                f"offset such as +05:00"
            )
        return parsed.timestamp()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProbeError(
            f"{where}: {field} must be epoch seconds or an ISO-8601 string with a "
            f"timezone, not {_json_kind(value)}"
        )
    if not math.isfinite(value):
        raise ProbeError(f"{where}: {field} is {value}, which is not a time")
    if abs(value) >= MILLISECOND_SUSPECT:
        raise ProbeError(
            f"{where}: {field} {value} looks like milliseconds since the epoch, not "
            f"seconds; divide by 1000 (read as seconds it is a date after the year 5000)"
        )
    return float(value)


def normalise(entry: Any, where: str) -> dict[str, Any]:
    """Validate one record; return a copy with timestamps as epoch seconds.

    `where` locates the record in the message ("delivered.jsonl:14",
    "source record 3"), so the person reading the error can find it.
    """
    if not isinstance(entry, dict):
        raise ProbeError(f"{where}: each record must be a JSON object, not {_json_kind(entry)}")
    if "payload" not in entry:
        raise ProbeError(f"{where}: every record needs a 'payload' object")
    if not isinstance(entry["payload"], dict):
        raise ProbeError(
            f"{where}: 'payload' must be an object of field names to values, "
            f"not {_json_kind(entry['payload'])}"
        )
    context = entry.get("context")
    if context is not None and not isinstance(context, dict):
        raise ProbeError(
            f"{where}: 'context' must be an object (entity_type, units, descriptions, "
            f"relationships), not {_json_kind(context)}"
        )
    record_id = entry.get("id")
    if record_id is not None and (isinstance(record_id, bool)
                                  or not isinstance(record_id, (str, int))):
        raise ProbeError(
            f"{where}: 'id' must be a string or an integer, not {_json_kind(record_id)}"
        )
    opaque_map = entry.get("opaque_map")
    if opaque_map is not None and (
            not isinstance(opaque_map, dict)
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in opaque_map.items())):
        raise ProbeError(
            f"{where}: 'opaque_map' must map each opaque field name to its original name, "
            f"as semantic stripping records it"
        )

    out = dict(entry)
    for field in ("event_timestamp", "read_timestamp"):
        if entry.get(field) is not None:
            out[field] = _timestamp(entry[field], field, where)
    latency = entry.get("delivery_latency_ms")
    if latency is not None:
        if (isinstance(latency, bool) or not isinstance(latency, (int, float))
                or not math.isfinite(latency)):
            raise ProbeError(
                f"{where}: delivery_latency_ms must be a finite number of milliseconds, "
                f"not {_json_kind(latency)}"
            )
        if latency < 0:
            raise ProbeError(
                f"{where}: delivery_latency_ms is {latency}; a delivery cannot take "
                f"negative time, so check the clock or the order of the subtraction"
            )
        out["delivery_latency_ms"] = float(latency)
    return out


def _first_duplicate(ids: Iterable[tuple[int, Any]]) -> tuple[Any, int, int] | None:
    seen: dict[Any, int] = {}
    for position, record_id in ids:
        if record_id is None:
            continue
        if record_id in seen:
            return record_id, seen[record_id], position
        seen[record_id] = position
    return None


def _reject_constant(token: str) -> None:
    raise ProbeError(f"{token} is not valid JSON; write null, or leave the field out")


def parse_records(text: str, name: str = "records",
                  unique_ids: bool = False) -> list[dict[str, Any]]:
    """Parse JSONL text into validated records, naming the line of any problem.

    `unique_ids` is for an upstream sample, where two versions of one id would
    leave consistency comparing against an arbitrary one.
    """
    records: list[dict[str, Any]] = []
    lines: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line, parse_constant=_reject_constant)
        except json.JSONDecodeError as exc:
            raise ProbeError(f"{name}:{number}: not valid JSON — {exc}") from exc
        except ProbeError as exc:
            raise ProbeError(f"{name}:{number}: {exc}") from None
        records.append(normalise(entry, f"{name}:{number}"))
        lines.append(number)
    if not records:
        raise ProbeError(f"{name}: no records found")
    if unique_ids:
        duplicate = _first_duplicate(
            (line, record.get("id")) for line, record in zip(lines, records)
        )
        if duplicate:
            record_id, first, second = duplicate
            raise ProbeError(
                f"{name}: id {record_id!r} appears on lines {first} and {second}; "
                f"{DUPLICATE_SOURCE_FIX}"
            )
    return records


def load_records(path: Path, unique_ids: bool = False) -> list[dict[str, Any]]:
    return parse_records(read_jsonl(path), str(path), unique_ids=unique_ids)


def read_jsonl(path: Path) -> str:
    """The text of a JSONL file, or a ProbeError that says why it cannot be read."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ProbeError(f"{path}: no such file") from None
    except UnicodeDecodeError:
        raise ProbeError(
            f"{path}: not a UTF-8 text file; the probe reads JSONL, one JSON object "
            f"per line (export Parquet or Avro to JSONL first)"
        ) from None
    except OSError as exc:
        raise ProbeError(f"{path}: cannot be read — {exc.strerror or exc}") from None


# ---- measurement ------------------------------------------------------------

def _as_record(entry: dict[str, Any]) -> Record:
    record = Record(
        payload=dict(entry["payload"]),
        context=dict(entry.get("context") or {}),
        event_timestamp=float(entry.get("event_timestamp") or 0.0),
    )
    if entry.get("read_timestamp") is not None:
        record.read_timestamp = float(entry["read_timestamp"])
    if entry.get("opaque_map"):
        # The names semantic stripping made opaque, so consistency can reverse
        # them: opacity belongs to the semantic dimension alone (invariant 5).
        record.meta["opaque_map"] = dict(entry["opaque_map"])
    return record


def measure(
    delivered: list[dict[str, Any]], source: list[dict[str, Any]] | None = None
) -> dict[str, dict[str, Any]]:
    """Score each dimension, or mark it unmeasured and say why.

    Every dimension returns {"score": float|None, "detail": str}. A None score
    is the honest answer when the input does not carry what the dimension needs
    — see the module docstring on why that must never become 100. Freshness also
    carries `mean_age_seconds` when measured, so the admission controller holds
    an age budget against the same number the probe scored.
    """
    delivered = [normalise(e, f"delivered record {i}") for i, e in enumerate(delivered, 1)]
    if source is not None:
        source = [normalise(e, f"source record {i}") for i, e in enumerate(source, 1)]
        duplicate = _first_duplicate(enumerate((e.get("id") for e in source), start=1))
        if duplicate:
            record_id, first, second = duplicate
            raise ProbeError(
                f"source: id {record_id!r} appears in records {first} and {second}; "
                f"{DUPLICATE_SOURCE_FIX}"
            )

    out: dict[str, dict[str, Any]] = {}
    records = [_as_record(e) for e in delivered]

    # ---- freshness: read_timestamp - event_timestamp ---------------------
    ages = [
        e["read_timestamp"] - e["event_timestamp"]
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
            "mean_age_seconds": mean_age,
        }

    # ---- latency: observed delivery time ---------------------------------
    latencies = [
        e["delivery_latency_ms"] for e in delivered
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


# ---- weights and composite --------------------------------------------------

def load_weights(path: Path, task: str) -> tuple[dict[str, float], dict[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProbeError(
            f"weights file {path} not found; the calibrated weights ship with "
            f"airs-bench, so reinstall it, or pass --weights"
        ) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"weights file {path} is not readable calibration JSON — {exc}") from None
    profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
    if task not in profiles:
        raise ProbeError(
            f"no calibrated profile for task {task!r}. Available: "
            f"{', '.join(sorted(profiles)) or '(none)'}. The weights invert "
            f"across tasks, so a profile from another task must not be reused — "
            f"recalibrate for this one."
        )
    weights = profiles[task]
    if (not isinstance(weights, dict) or set(weights) != set(DIMENSIONS)
            or any(isinstance(w, bool) or not isinstance(w, (int, float))
                   or not math.isfinite(w) or w < 0 for w in weights.values())):
        raise ProbeError(
            f"weights profile {task!r} in {path} must give one non-negative number "
            f"for each of {', '.join(DIMENSIONS)}"
        )
    return weights, payload


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


def score(
    delivered: list[dict[str, Any]],
    source: list[dict[str, Any]] | None = None,
    task: str = "retrieval",
    weights_path: Path = DEFAULT_WEIGHTS,
) -> dict[str, Any]:
    """Everything `airs probe --json` reports, as data.

    The command prints it and the web console returns it, so the two cannot
    disagree. Each dimension carries its own weight, beside its score and
    evidence, so a consumer never pairs a score with the wrong task's weight.
    """
    weights, meta = load_weights(weights_path, task)
    measured = measure(delivered, source)
    airs, covered = composite(measured, weights)
    label, note = band(airs) if airs is not None else (None, None)
    return {
        "task": task,
        "n_records": len(delivered),
        "dimensions": {dim: {**measured[dim], "weight": weights[dim]} for dim in DIMENSIONS},
        "weights": weights,
        "airs": airs,
        "weight_covered": covered,
        "unmeasured": [dim for dim in DIMENSIONS if measured[dim]["score"] is None],
        "band": label,
        "band_note": note,
        "calibration": {k: meta.get(k) for k in ("calibrated_at", "target")},
        "validation": meta.get("validation", {}).get(task),
    }


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

    # Errors go to stderr, so `--json` output piped into another tool is either
    # a complete document or nothing.
    try:
        delivered = load_records(args.records)
        source = load_records(args.source, unique_ids=True) if args.source else None
        if args.json:
            result = score(delivered, source, args.task, args.weights)
        else:
            weights, meta = load_weights(args.weights, args.task)
            measured = measure(delivered, source)
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result["airs"] is not None else 1

    return report(measured, weights, meta, args.task, len(delivered))


if __name__ == "__main__":
    raise SystemExit(main())
