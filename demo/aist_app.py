"""AIST — Agentic Infrastructure Stress Tester (v0 scaffold).

Week 1 version: the fault control panel and live AIRS radar are fully
functional against synthetic records, so the injector -> AIRS loop can be
demonstrated end-to-end before the pipelines and agent exist. The agent
decision timeline and architecture comparator activate in Week 3/7 when
the harness lands.

Run:  streamlit run demo/aist_app.py
"""

from __future__ import annotations

import time

import plotly.graph_objects as go
import streamlit as st

from agentic_faults import (
    FaultChain,
    FreshnessInjector,
    LatencyInjector,
    Record,
    SchemaDriftInjector,
    SemanticStrippingInjector,
)
from airsbench.airs import (
    AIRSCalculator,
    freshness_score,
    latency_score,
    mean_semantic_completeness,
    payload_consistency,
    semantic_score,
)

N_RECORDS = 50
ZONE_COLORS = {"green": "#2e7d32", "amber": "#ff8f00", "red": "#c62828"}

st.set_page_config(page_title="AIST — Agentic Infrastructure Stress Tester", layout="wide")
st.title("AIST — Agentic Infrastructure Stress Tester")
st.caption(
    "Thesis: *Characterizing the Data Infrastructure Gap for Agentic AI Systems* — "
    "Shamsiddin Khamidov. v0 scaffold: injectors + AIRS live; agent wiring lands in Week 3."
)


def make_baseline_records() -> list[Record]:
    now = time.time()
    records = []
    for i in range(N_RECORDS):
        record = Record(
            payload={"product_id": f"P{i:04d}", "price": 10.0 + i, "stock": i % 20,
                     "brand": f"brand_{i % 7}"},
            context={
                "entity_type": "retail_product",
                "units": {"price": "USD", "stock": "units_available"},
                "descriptions": {"price": "current listed price",
                                 "stock": "units currently available"},
                "relationships": {"product_id": "joins to queries"},
            },
            event_timestamp=now,
        )
        record.read_timestamp = now
        records.append(record)
    return records


# --- Region 1: fault control panel (RQ1, RQ2) ---------------------------
st.sidebar.header("Fault control panel")
delay_s = st.sidebar.slider("Freshness delay (s)", 0.0, 10.0, 0.0, 0.1)
spike_ms = st.sidebar.slider("Latency spike (ms)", 0, 5000, 0, 50)
drift_pct = st.sidebar.slider("Schema drift (%)", 0, 50, 0, 1)
strip_pct = st.sidebar.slider("Semantic stripping (%)", 0, 100, 0, 1)
st.sidebar.caption(
    "Severity presets from the research plan — freshness: 1.5/5 s, latency: "
    "500/3000 ms, drift: 5/25 %, stripping: 30/80 %."
)

chain = FaultChain([
    FreshnessInjector(seed=1, delay_seconds=delay_s),
    LatencyInjector(seed=2, spike_ms=spike_ms, sleep=False),
    SchemaDriftInjector(seed=3, drift_probability=drift_pct / 100.0),
    SemanticStrippingInjector(seed=4, strip_rate=strip_pct / 100.0),
])

baseline = make_baseline_records()
faulted = [chain.apply(record) for record in baseline]
read_at = time.time()

mean_age = sum(record.age_seconds(at=read_at) for record in faulted) / len(faulted)
mean_latency = sum(record.meta.get("injected_latency_ms", 0) for record in faulted) / len(faulted)
mean_consistency = sum(
    payload_consistency(b, f) for b, f in zip(baseline, faulted)
) / len(baseline)

scores = {
    "freshness": freshness_score(mean_age),
    "latency": latency_score(max(mean_latency, 1.0)),
    "consistency": 100.0 * mean_consistency,
    "semantic": semantic_score(mean_semantic_completeness(faulted)),
}
calculator = AIRSCalculator()  # equal-weight placeholder until Week-6 calibration
composite = calculator.composite(scores)
zone = calculator.zone(composite)

# --- Region 2: live AIRS radar (RQ4) -------------------------------------
left, right = st.columns([2, 1])
with left:
    axes = ["Freshness", "Latency", "Consistency", "Semantic"]
    values = [scores["freshness"], scores["latency"], scores["consistency"], scores["semantic"]]
    fig = go.Figure(go.Scatterpolar(
        r=values + values[:1],
        theta=axes + axes[:1],
        fill="toself",
        line_color=ZONE_COLORS[zone],
    ))
    fig.update_layout(
        polar={"radialaxis": {"range": [0, 100], "visible": True}},
        showlegend=False,
        margin={"l": 40, "r": 40, "t": 40, "b": 40},
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.metric("AIRS composite", f"{composite:.1f} / 100")
    st.markdown(
        f"Zone: <span style='color:{ZONE_COLORS[zone]};font-weight:bold'>"
        f"{zone.upper()}</span>",
        unsafe_allow_html=True,
    )
    st.caption("green > 80 · amber 60–80 · red < 60")
    for dim, value in scores.items():
        st.progress(int(value), text=f"{dim}: {value:.0f}")

# --- Regions 3 & 4: activate with the agent harness ----------------------
st.divider()
timeline, comparator = st.columns(2)
with timeline:
    st.subheader("Agent decision timeline")
    st.info("Activates in Week 3: live agent decisions vs. ground truth, "
            "failures flagged with the AIRS score at the moment of failure (RQ1, RQ4).")
with comparator:
    st.subheader("Architecture comparator")
    st.info("Activates in Week 7: identical task on batch vs. streaming, "
            "accuracy curves overlaid (RQ3, RQ5).")
