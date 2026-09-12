"""Tests for the AIRS curve sensitivity analysis.

Two of these protect the analysis's claim rather than its code:

- `test_physical_quantities_distinguish_baseline_from_mild_latency` pins the
  reason the module reads the run configuration instead of inverting the
  recorded score. `latency_score` saturates at 100 for everything at or below
  target, so inversion maps a fault-free run and a mild-latency run to the same
  500 ms. An earlier draft did exactly that and treated every clean pipeline as
  degraded.
- `test_shipped_variant_reproduces_the_published_weights` pins that the refit
  path here agrees with `airs_calibration`. If it drifted, this analysis would be
  reporting sensitivity of something other than the published metric.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from airsbench.airs import DIMENSIONS, freshness_score, latency_score
from airsbench.analysis.curve_sensitivity import (
    ANCHOR_RATIO,
    CURVES,
    SHIPPED_FRESHNESS_TARGET_S,
    SHIPPED_LATENCY_TARGET_MS,
    SHIPPED_SHAPE,
    build_variants,
    physical_quantities,
)

TARGETS = (0.25, 1.0, 500.0)


def run_stub(fault: str, severity: str, pipeline: str = "streaming", **params):
    return {"run_id": "r", "config": {
        "pipeline": pipeline, "fault_type": fault, "severity": severity,
        "task": "retrieval", "replication": 1, "injector_params": params,
        "seed": 1, "model": "gpt-4o-mini"}}


# ---- the curve family -----------------------------------------------------

@pytest.mark.parametrize("name", sorted(CURVES))
@pytest.mark.parametrize("target", TARGETS)
def test_every_curve_hits_both_anchors(name, target):
    """The comparison isolates SHAPE only if every curve shares its endpoints.

    Without a common anchor a reviewer could fairly object that the alternatives
    were chosen steeper or shallower than the shipped one, and that the spread in
    fitted weights reflects that choice rather than the functional form.
    """
    curve = CURVES[name]
    assert curve(target, target) == pytest.approx(100.0)
    assert curve(ANCHOR_RATIO * target, target) == pytest.approx(10.0, abs=1e-6)


@pytest.mark.parametrize("name", sorted(CURVES))
def test_every_curve_is_monotone_and_bounded(name):
    curve = CURVES[name]
    target = 1.0
    xs = [target * r for r in (0.1, 0.5, 1.0, 1.5, 2, 3, 5, 8, 10, 15, 30, 100)]
    scores = [curve(x, target) for x in xs]
    assert all(0.0 <= s <= 100.0 for s in scores)
    assert all(a >= b - 1e-9 for a, b in zip(scores, scores[1:])), scores
    assert all(curve(x, target) == 100.0 for x in (1e-9, 0.5 * target, target))


def test_the_shipped_shape_is_the_calculators_own_function():
    """The 'shipped' variant must be the real thing, not a re-derivation."""
    curve = CURVES[SHIPPED_SHAPE]
    for age in (0.05, 0.5, 1.0, 3.0, 5.05, 12.0):
        assert curve(age, SHIPPED_FRESHNESS_TARGET_S) == pytest.approx(
            freshness_score(age))
    for ms in (1.0, 250.0, 500.0, 3000.0):
        assert curve(ms, SHIPPED_LATENCY_TARGET_MS) == pytest.approx(
            latency_score(ms))


def test_variants_include_the_shipped_one_exactly_once():
    variants = build_variants()
    shipped = [v for v in variants if v.shipped]
    assert len(shipped) == 1
    assert shipped[0].shape == SHIPPED_SHAPE
    assert shipped[0].freshness_target_s == SHIPPED_FRESHNESS_TARGET_S
    assert shipped[0].latency_target_ms == SHIPPED_LATENCY_TARGET_MS
    assert {v.family for v in variants} == {"shipped", "shape", "target"}


# ---- physical quantities --------------------------------------------------

def test_physical_quantities_distinguish_baseline_from_mild_latency():
    """The trap that inverting the recorded score would fall into.

    latency_score(0 ms) and latency_score(500 ms) are both exactly 100, so the
    recorded dimension cannot separate a clean pipeline from the mild-latency
    condition. Reading spike_ms from the config can, and must.
    """
    _, clean_ms = physical_quantities(run_stub("none", "none"))
    _, mild_ms = physical_quantities(run_stub("latency", "mild", spike_ms=500))
    _, severe_ms = physical_quantities(run_stub("latency", "severe", spike_ms=3000))

    assert (clean_ms, mild_ms, severe_ms) == (0.0, 500.0, 3000.0)
    assert latency_score(max(clean_ms, 1.0)) == latency_score(mild_ms) == 100.0


def test_freshness_quantity_matches_the_true_value_staleness():
    age, _ = physical_quantities(run_stub("freshness", "severe", delay_seconds=5.0))
    assert age == pytest.approx(0.05 + 5.0)  # streaming inherent + injected
    batch, _ = physical_quantities(run_stub("none", "none", pipeline="batch"))
    assert batch == pytest.approx(3.0)


def test_compound_faults_read_their_own_parameter_block():
    """A compound condition nests injector_params by fault name."""
    age, ms = physical_quantities({
        "run_id": "r",
        "config": {"pipeline": "streaming", "fault_type": "latency+schema_drift",
                   "severity": "severe", "task": "retrieval", "replication": 1,
                   "seed": 80_001, "model": "gpt-4o-mini",
                   "injector_params": {"latency": {"spike_ms": 3000},
                                       "schema_drift": {"drift_probability": 0.25}}},
    })
    assert ms == 3000.0
    assert age == pytest.approx(0.05)


# ---- agreement with the published calibration -----------------------------

WEIGHTS_PATH = Path("src/airsbench/airs/calibrated_weights.json")
DATA_DIR = Path("data/ecommerce")

needs_data = pytest.mark.skipif(
    not (DATA_DIR / "updates.jsonl").exists(),
    reason="prepared ESCI dataset not present",
)


@needs_data
@pytest.mark.parametrize("task", ["retrieval", "classification"])
def test_shipped_variant_reproduces_the_published_weights(task):
    """Refitting under the shipped curve must return the exported weights.

    This module's whole claim is that it measures the sensitivity of the
    PUBLISHED metric. If its refit path diverged from `airs_calibration` — a
    different split, target or estimator — it would be measuring something else
    and the tornado plot would be about a metric nobody ships.
    """
    from airsbench.analysis.airs_calibration import build_frame
    from airsbench.analysis.curve_sensitivity import attach_physical, refit

    frame = attach_physical(build_frame(Path("results/runs"), DATA_DIR),
                            Path("results/runs"))
    shipped = next(v for v in build_variants() if v.shipped)
    got = refit(frame, shipped, task)["weights"]
    expected = json.loads(WEIGHTS_PATH.read_text())["profiles"][task]

    for dim in DIMENSIONS:
        assert got[dim] == pytest.approx(expected[dim], abs=0.005), dim
