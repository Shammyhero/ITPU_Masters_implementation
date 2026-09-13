"""`airs probe` must never turn "nobody looked" into "looks fine".

The probe scores a pipeline before an agent is deployed on it, from telemetry
alone. Its one genuinely dangerous failure mode is scoring an absent
measurement as a healthy one: a pipeline with no consistency check would then
earn a clean bill of health precisely because nothing was compared. Every test
here exists to keep an unmeasured dimension distinguishable from a good one —
and malformed input distinguishable from both.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from airsbench.probe import (
    DEFAULT_WEIGHTS,
    DIMENSIONS,
    ProbeError,
    band,
    composite,
    load_records,
    load_weights,
    main,
    measure,
    parse_records,
    score,
)

CONTEXT = {
    "entity_type": "retail_product",
    "units": {"price": "USD"},
    "descriptions": {"price": "unit price", "stock": "units available"},
    "relationships": {"product_id": "joins to queries"},
}


def _entry(pid="A", price=10.0, age=1.0, latency=50.0, context=True, **over):
    entry = {
        "id": pid,
        "payload": {"product_id": pid, "price": price, "stock": 3},
        "event_timestamp": 1_000_000.0,
        "read_timestamp": 1_000_000.0 + age,
        "delivery_latency_ms": latency,
    }
    if context:
        entry["context"] = dict(CONTEXT)
    entry.update(over)
    return entry


def _write(tmp_path: Path, name: str, entries) -> Path:
    path = tmp_path / name
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return path


# ---- the central guarantee -------------------------------------------------

def test_a_dimension_without_input_is_unmeasured_not_perfect():
    """The failure mode the whole tool hinges on."""
    measured = measure([{"payload": {"price": 1.0}, "context": dict(CONTEXT)}])
    assert measured["freshness"]["score"] is None
    assert measured["latency"]["score"] is None
    assert measured["consistency"]["score"] is None
    for dim in ("freshness", "latency", "consistency"):
        assert measured[dim]["score"] != 100.0


def test_consistency_is_unmeasured_without_a_source_sample():
    measured = measure([_entry()])
    assert measured["consistency"]["score"] is None
    assert "source" in measured["consistency"]["detail"]


def test_consistency_is_unmeasured_when_no_id_matches():
    measured = measure([_entry(pid="A")], [_entry(pid="Z")])
    assert measured["consistency"]["score"] is None
    assert "matched" in measured["consistency"]["detail"]


def test_an_absent_semantic_layer_scores_zero_rather_than_unmeasured():
    """Missing context is not a missing measurement — it IS the degradation.
    This is the one case where absence is a score, and conflating it with
    'unmeasured' would hide the fault semantic stripping models."""
    measured = measure([_entry(context=False)])
    assert measured["semantic"]["score"] == 0.0
    assert measured["semantic"]["score"] is not None


# ---- composite -------------------------------------------------------------

def test_the_composite_excludes_unmeasured_weight_rather_than_assuming_it():
    weights = {"freshness": 0.1, "latency": 0.0, "consistency": 0.7, "semantic": 0.2}
    measured = {
        "freshness": {"score": 20.0, "detail": ""},
        "latency": {"score": None, "detail": ""},
        "consistency": {"score": None, "detail": ""},
        "semantic": {"score": 40.0, "detail": ""},
    }
    score, covered = composite(measured, weights)
    assert covered == pytest.approx(0.3)
    # 0.1*20 + 0.2*40 = 10, over covered weight 0.3
    assert score == pytest.approx(10.0 / 0.3)
    assert score < 50.0, "must not be inflated by the missing 70%"


def test_a_fully_measured_composite_covers_all_the_weight():
    weights = {"freshness": 0.25, "latency": 0.25, "consistency": 0.25, "semantic": 0.25}
    measured = {d: {"score": 80.0, "detail": ""} for d in DIMENSIONS}
    score, covered = composite(measured, weights)
    assert covered == pytest.approx(1.0)
    assert score == pytest.approx(80.0)


def test_nothing_measurable_yields_no_score_rather_than_zero():
    measured = {d: {"score": None, "detail": ""} for d in DIMENSIONS}
    score, covered = composite(measured, {d: 0.25 for d in DIMENSIONS})
    assert score is None and covered == 0.0


def test_a_zero_weight_dimension_does_not_drag_the_composite():
    """Latency is calibrated to 0% — measuring it must not move the score."""
    weights = {"freshness": 0.5, "latency": 0.0, "consistency": 0.0, "semantic": 0.5}
    without = composite(
        {"freshness": {"score": 90.0, "detail": ""}, "latency": {"score": None, "detail": ""},
         "consistency": {"score": None, "detail": ""}, "semantic": {"score": 90.0, "detail": ""}},
        weights)[0]
    with_latency = composite(
        {"freshness": {"score": 90.0, "detail": ""}, "latency": {"score": 5.0, "detail": ""},
         "consistency": {"score": None, "detail": ""}, "semantic": {"score": 90.0, "detail": ""}},
        weights)[0]
    assert without == pytest.approx(with_latency)


# ---- input validation ------------------------------------------------------

def test_clock_skew_is_refused_not_scored():
    """A negative age would silently produce a flattering freshness score."""
    with pytest.raises(ProbeError, match="clock skew"):
        measure([_entry(age=-5.0)])


def test_a_record_without_a_payload_is_rejected(tmp_path):
    path = _write(tmp_path, "bad.jsonl", [{"id": "A"}])
    with pytest.raises(ProbeError, match="payload"):
        load_records(path)


def test_malformed_json_names_the_line(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"payload": {}}\nnot json\n')
    with pytest.raises(ProbeError, match=":2:"):
        load_records(path)


def test_an_empty_file_is_an_error_not_a_perfect_score(tmp_path):
    with pytest.raises(ProbeError, match="no records"):
        load_records(_write(tmp_path, "empty.jsonl", []))


def test_an_unknown_task_profile_is_refused_with_the_reason():
    """The weights invert across tasks, so silently reusing another task's
    profile would produce a confidently wrong score."""
    with pytest.raises(ProbeError, match="invert"):
        load_weights(DEFAULT_WEIGHTS, "summarisation")


BAD_LINES = [
    ('[1, 2]', "must be a JSON object"),
    ('{"payload": "price=3"}', "'payload' must be an object"),
    ('{"payload": {}, "context": ["units"]}', "'context' must be an object"),
    ('{"payload": {}, "id": 1.5}', "'id' must be a string or an integer"),
    ('{"payload": {}, "id": true}', "'id' must be a string or an integer"),
    ('{"payload": {}, "delivery_latency_ms": true}', "latency_ms must be a finite number"),
    ('{"payload": {}, "delivery_latency_ms": "120"}', "latency_ms must be a finite number"),
    ('{"payload": {}, "delivery_latency_ms": -5}', "negative time"),
    ('{"payload": {}, "delivery_latency_ms": NaN}', "NaN is not valid JSON"),
    ('{"payload": {}, "event_timestamp": Infinity}', "Infinity is not valid JSON"),
    ('{"payload": {}, "event_timestamp": true}', "epoch seconds or an ISO-8601"),
    ('{"payload": {}, "event_timestamp": "yesterday"}', "is not an ISO-8601 time"),
    ('{"payload": {}, "event_timestamp": "2026-09-13T10:00:00"}', "has no timezone"),
    ('{"payload": {}, "event_timestamp": 1772000000000}', "looks like milliseconds"),
]


@pytest.mark.parametrize("line, message", BAD_LINES)
def test_malformed_records_are_refused_saying_where_and_how_to_fix(line, message):
    with pytest.raises(ProbeError, match=re.escape(message)) as excinfo:
        parse_records('{"payload": {}}\n' + line, name="delivered.jsonl")
    assert str(excinfo.value).startswith("delivered.jsonl:2:")


@pytest.mark.parametrize("record", [
    {"payload": "x"},
    {"payload": {}, "event_timestamp": "yesterday", "read_timestamp": "now"},
    {"payload": {}, "context": ["a"]},
    {"payload": {}, "delivery_latency_ms": float("nan")},
])
def test_programmatic_callers_get_a_probe_error_not_a_crash(record):
    """The controller and the web console hand dicts straight to `measure`. A
    bare ValueError there would be a traceback and a 500, not a message."""
    with pytest.raises(ProbeError):
        measure([record])


def test_zoned_iso_timestamps_score_exactly_like_epoch_seconds():
    """Kafka, Postgres and Parquet exports mostly write ISO-8601. Two zones for
    the same instant must give the same age as the epoch numbers do."""
    from datetime import datetime, timezone

    event = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    iso = _entry(event_timestamp="2026-09-13T10:00:00Z",
                 read_timestamp="2026-09-13T15:00:05.050+05:00")
    numeric = _entry(event_timestamp=event, read_timestamp=event + 5.05)

    from_iso, from_epoch = measure([iso])["freshness"], measure([numeric])["freshness"]
    assert from_iso["score"] == pytest.approx(from_epoch["score"])
    assert from_iso["score"] == pytest.approx(100.0 / 5.05)
    assert "mean age 5.05s" in from_iso["detail"]


def test_millisecond_timestamps_are_refused_not_scored_a_thousand_times_stale():
    """Both timestamps in milliseconds keep their order, so nothing else would
    catch it: every age comes out 1000x too large and a fresh pipeline is scored
    stale with no error anywhere."""
    with pytest.raises(ProbeError, match="milliseconds"):
        measure([_entry(event_timestamp=1_772_000_000_000, read_timestamp=1_772_000_000_400)])


def test_duplicate_upstream_ids_are_refused_naming_both_lines(tmp_path):
    path = _write(tmp_path, "src.jsonl", [_entry(pid="A"), _entry(pid="B"), _entry(pid="A")])
    with pytest.raises(ProbeError, match="id 'A' appears on lines 1 and 3"):
        load_records(path, unique_ids=True)


def test_a_record_delivered_twice_is_not_an_error(tmp_path):
    """Only the upstream sample needs unique ids; redelivery is a pipeline fact."""
    path = _write(tmp_path, "d.jsonl", [_entry(pid="A"), _entry(pid="A")])
    assert len(load_records(path)) == 2


def test_measure_refuses_duplicate_source_ids_from_any_caller():
    with pytest.raises(ProbeError, match="records 1 and 2"):
        measure([_entry(pid="A")], [_entry(pid="A"), _entry(pid="A", price=12.0)])


def test_a_missing_file_is_a_probe_error(tmp_path):
    with pytest.raises(ProbeError, match="no such file"):
        load_records(tmp_path / "nope.jsonl")


def test_a_binary_file_is_refused_saying_what_the_probe_reads(tmp_path):
    path = tmp_path / "sample.parquet"
    path.write_bytes(b"PAR1\x15\x04\xff\xfe\x00")
    with pytest.raises(ProbeError, match="JSONL"):
        load_records(path)


def test_a_missing_weights_file_names_the_fix(tmp_path):
    with pytest.raises(ProbeError, match="reinstall"):
        load_weights(tmp_path / "weights.json", "retrieval")


def test_a_weights_profile_missing_a_dimension_is_refused(tmp_path):
    path = tmp_path / "weights.json"
    path.write_text(json.dumps({"profiles": {"retrieval": {"freshness": 0.5, "semantic": 0.5}}}))
    with pytest.raises(ProbeError, match="for each of"):
        load_weights(path, "retrieval")


# ---- shipped calibration ---------------------------------------------------

def test_the_shipped_weights_cover_both_calibrated_tasks():
    payload = json.loads(DEFAULT_WEIGHTS.read_text())
    assert set(payload["profiles"]) == {"retrieval", "classification"}
    for task, weights in payload["profiles"].items():
        assert sum(weights.values()) == pytest.approx(1.0, abs=0.01), task
        assert all(w >= 0 for w in weights.values()), task


def test_the_shipped_weights_are_fitted_on_total_error():
    """RQ4 §3: the silent/refusal split is an agent property, so a pipeline
    score is fitted against pipeline-caused harm."""
    assert json.loads(DEFAULT_WEIGHTS.read_text())["target"] == "wrong"


def test_the_shipped_weights_carry_their_own_validation():
    payload = json.loads(DEFAULT_WEIGHTS.read_text())
    for task in payload["profiles"]:
        assert payload["validation"][task]["held_out_spearman"] < -0.5, task


def test_the_two_task_profiles_actually_differ():
    """If they were equal, per-task calibration would be theatre."""
    profiles = json.loads(DEFAULT_WEIGHTS.read_text())["profiles"]
    assert profiles["retrieval"] != profiles["classification"]


# ---- bands and end to end --------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (100.0, "READY"), (85.0, "READY"), (84.9, "WATCH"),
    (70.0, "WATCH"), (69.9, "AT RISK"), (0.0, "AT RISK"),
])
def test_bands_are_monotone_in_the_score(score, expected):
    assert band(score)[0] == expected


def test_a_degraded_pipeline_scores_below_a_healthy_one(tmp_path, capsys):
    source = _write(tmp_path, "src.jsonl", [_entry(pid=f"P{i}") for i in range(20)])
    healthy = _write(tmp_path, "ok.jsonl",
                     [_entry(pid=f"P{i}", age=0.3) for i in range(20)])
    degraded = _write(tmp_path, "bad.jsonl",
                      [_entry(pid=f"P{i}", price=99.0, age=9.0, context=False)
                       for i in range(20)])

    scores = {}
    for name, path in (("healthy", healthy), ("degraded", degraded)):
        assert main(["--records", str(path), "--source", str(source),
                     "--task", "retrieval", "--json"]) == 0
        scores[name] = json.loads(capsys.readouterr().out)["airs"]
    assert scores["healthy"] > scores["degraded"]
    assert scores["healthy"] > 85 and scores["degraded"] < 70


def test_json_output_reports_the_covered_weight(tmp_path, capsys):
    records = _write(tmp_path, "r.jsonl", [_entry()])
    assert main(["--records", str(records), "--task", "retrieval", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dimensions"]["consistency"]["score"] is None
    assert payload["weight_covered"] < 0.5
    assert payload["band"] is not None
    assert payload["unmeasured"] == ["consistency"]


def test_json_output_is_score_and_carries_each_dimensions_weight(tmp_path, capsys):
    """The command and the web console must not be able to disagree."""
    delivered, source = [_entry(pid="A", price=12.0)], [_entry(pid="A")]
    records = _write(tmp_path, "d.jsonl", delivered)
    upstream = _write(tmp_path, "s.jsonl", source)

    assert main(["--records", str(records), "--source", str(upstream), "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(json.dumps(score(delivered, source, "retrieval")))

    weights, _ = load_weights(DEFAULT_WEIGHTS, "retrieval")
    for dim in DIMENSIONS:
        assert printed["dimensions"][dim]["weight"] == weights[dim]
    assert printed["unmeasured"] == []


def test_cli_errors_go_to_stderr_so_json_output_stays_parseable(tmp_path, capsys):
    assert main(["--records", str(tmp_path / "nope.jsonl"), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no such file" in captured.err


def test_the_probe_never_calls_a_model(tmp_path, monkeypatch, capsys):
    """Pre-deployment means pre-agent: no key, no client, no network."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    records = _write(tmp_path, "r.jsonl", [_entry()])
    assert main(["--records", str(records), "--task", "retrieval"]) == 0
    assert "AIRS" in capsys.readouterr().out
