"use client";

import { useMemo, useState } from "react";

/* Client-side port of `airsbench.probe`. The scoring formulas are arithmetic —
 * porting them keeps the demo dependency-free while preserving the property
 * that matters: an unmeasurable dimension is UNMEASURED, never 100. */

const REQUIRED_CONTEXT = ["entity_type", "units", "descriptions", "relationships"];
const DIMS = ["freshness", "latency", "consistency", "semantic"] as const;

type Dim = { score: number | null; detail: string };
type Rec = Record<string, any>;

const freshnessScore = (age: number) => (age <= 1 ? 100 : (100 * 1) / age);
const latencyScore = (ms: number) => (ms <= 500 ? 100 : (100 * 500) / ms);

function semanticCompleteness(r: Rec): number {
  const ctx = r.context ?? {};
  const present = REQUIRED_CONTEXT.filter((k) => {
    const v = ctx[k];
    return v !== undefined && v !== null &&
      (typeof v === "object" ? Object.keys(v).length > 0 : String(v).length > 0);
  });
  return present.length / REQUIRED_CONTEXT.length;
}

function consistency(src: Rec, dst: Rec): number {
  const a = src.payload ?? {}, b = dst.payload ?? {};
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  if (!keys.size) return 1;
  let match = 0;
  keys.forEach((k) => { if (JSON.stringify(a[k]) === JSON.stringify(b[k])) match++; });
  return match / keys.size;
}

export function scoreRecords(delivered: Rec[], source: Rec[] | null) {
  const out: Record<string, Dim> = {};

  const ages = delivered
    .filter((r) => r.read_timestamp != null && r.event_timestamp != null)
    .map((r) => Number(r.read_timestamp) - Number(r.event_timestamp));
  if (!ages.length) {
    out.freshness = { score: null, detail: "no record carries both event_timestamp and read_timestamp" };
  } else if (Math.min(...ages) < 0) {
    out.freshness = { score: null, detail: "a record was read before its event timestamp — clock skew, refusing to score" };
  } else {
    const mean = ages.reduce((s, x) => s + x, 0) / ages.length;
    out.freshness = { score: freshnessScore(Math.max(mean, 1e-6)),
      detail: `mean age ${mean.toFixed(2)}s over ${ages.length} of ${delivered.length} records` };
  }

  const lat = delivered.filter((r) => r.delivery_latency_ms != null)
    .map((r) => Number(r.delivery_latency_ms));
  out.latency = lat.length
    ? { score: latencyScore(Math.max(lat.reduce((s, x) => s + x, 0) / lat.length, 1)),
        detail: `mean ${(lat.reduce((s, x) => s + x, 0) / lat.length).toFixed(0)}ms over ${lat.length} of ${delivered.length} records` }
    : { score: null, detail: "no record carries delivery_latency_ms" };

  if (!source) {
    out.consistency = { score: null, detail: "no upstream sample given; nothing to compare against" };
  } else {
    const byId = new Map(source.filter((r) => r.id != null).map((r) => [r.id, r]));
    const pairs = delivered.filter((r) => r.id != null && byId.has(r.id));
    out.consistency = pairs.length
      ? { score: 100 * pairs.reduce((s, r) => s + consistency(byId.get(r.id)!, r), 0) / pairs.length,
          detail: `${pairs.length} of ${delivered.length} records matched by id` }
      : { score: null, detail: "no record id matched between the two samples" };
  }

  const withCtx = delivered.filter((r) => r.context && Object.keys(r.context).length);
  out.semantic = withCtx.length
    ? { score: 100 * delivered.reduce((s, r) => s + semanticCompleteness(r), 0) / delivered.length,
        detail: `context present on ${withCtx.length} of ${delivered.length} records` }
    : { score: 0, detail: "no record carries a context block — the semantic layer is absent, which is a score of 0, not an absent measurement" };

  return out;
}

function parse(text: string): { records: Rec[]; error: string | null } {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const records: Rec[] = [];
  for (let i = 0; i < lines.length; i++) {
    try {
      const entry = JSON.parse(lines[i]);
      if (typeof entry !== "object" || entry === null || !("payload" in entry)) {
        return { records: [], error: `line ${i + 1}: every record needs a "payload" object` };
      }
      records.push(entry);
    } catch {
      return { records: [], error: `line ${i + 1}: not valid JSON` };
    }
  }
  return { records, error: records.length ? null : "no records" };
}

const SAMPLE_DELIVERED = `{"id":"SKU-1","payload":{"price":24.99,"stock":3},"context":{"entity_type":"retail_product","units":{"price":"USD"},"descriptions":{"price":"unit price"},"relationships":{}},"event_timestamp":1772000000,"read_timestamp":1772000005.05,"delivery_latency_ms":120}
{"id":"SKU-2","payload":{"price":8.50,"stock":0},"context":{"entity_type":"retail_product","units":{"price":"USD"},"descriptions":{"price":"unit price"},"relationships":{}},"event_timestamp":1772000000,"read_timestamp":1772000004.10,"delivery_latency_ms":140}`;
const SAMPLE_SOURCE = `{"id":"SKU-1","payload":{"price":19.99,"stock":3}}
{"id":"SKU-2","payload":{"price":8.50,"stock":2}}`;

export default function ProbeLive({ weights }: { weights: Record<string, number> }) {
  const [delivered, setDelivered] = useState(SAMPLE_DELIVERED);
  const [source, setSource] = useState(SAMPLE_SOURCE);

  const result = useMemo(() => {
    const d = parse(delivered);
    if (d.error) return { error: d.error };
    const s = source.trim() ? parse(source) : { records: [], error: null };
    if (s.error) return { error: `upstream sample — ${s.error}` };
    const dims = scoreRecords(d.records, s.records.length ? s.records : null);
    const usable = DIMS.filter((k) => dims[k].score !== null);
    const covered = usable.reduce((sum, k) => sum + (weights[k] ?? 0), 0);
    const airs = covered
      ? usable.reduce((sum, k) => sum + (weights[k] ?? 0) * dims[k].score!, 0) / covered
      : null;
    return { dims, airs, covered, n: d.records.length };
  }, [delivered, source, weights]);

  if ("error" in result && result.error) {
    return (
      <section>
        <h2>Probe your own pipeline</h2>
        <ProbeInputs {...{ delivered, setDelivered, source, setSource }} />
        <div className="panel" style={{ borderColor: "var(--bad)" }}>
          <b style={{ color: "var(--bad)" }}>error:</b> {result.error}
        </div>
      </section>
    );
  }

  const { dims, airs, covered, n } = result as any;
  const band = airs === null ? null : airs >= 85 ? "READY" : airs >= 70 ? "WATCH" : "AT RISK";
  const tone = airs === null ? "var(--muted)"
    : airs >= 85 ? "var(--good)" : airs >= 70 ? "var(--warn)" : "var(--bad)";

  return (
    <section>
      <h2>Probe your own pipeline</h2>
      <p className="sub">
        Paste records as your pipeline delivers them. Scored in your browser —
        nothing is uploaded, no model is called. Edit either box and the score
        moves. <b>Clear the upstream sample</b> to see the guard that matters:
        consistency becomes UNMEASURED, not 100.
      </p>
      <ProbeInputs {...{ delivered, setDelivered, source, setSource }} />

      <div className="panel">
        <div style={{ display: "flex", alignItems: "baseline", gap: ".75rem",
                      flexWrap: "wrap", marginBottom: "1rem" }}>
          <span className="score" style={{ color: tone }}>
            {airs === null ? "—" : airs.toFixed(1)}
          </span>
          <span className="mono" style={{ color: "var(--muted)" }}>/100</span>
          {band && <span className={`band ${band.replace(" ", ".")}`}>{band}</span>}
          <span className="src" style={{ marginLeft: "auto" }}>{n} records</span>
        </div>
        <table>
          <thead><tr><th>dimension</th><th>score</th><th>weight</th>
                     <th style={{ textAlign: "left" }}>evidence</th></tr></thead>
          <tbody>
            {DIMS.map((d) => (
              <tr key={d}>
                <td>{d}</td>
                <td className={`num ${dims[d].score === null ? "hot" : ""}`}>
                  {dims[d].score === null ? "UNMEASURED" : dims[d].score.toFixed(1)}
                </td>
                <td className="num cool">{((weights[d] ?? 0) * 100).toFixed(1)}%</td>
                <td style={{ textAlign: "left", color: "var(--muted)", fontSize: ".82rem" }}>
                  {dims[d].detail}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {covered < 0.999 && (
          <div className="callout">
            <b>This composite rests on {Math.round(covered * 100)}% of the
            calibrated weight.</b> Unmeasured dimensions are excluded, never
            assumed healthy — a pipeline can score well here purely because
            nobody looked.
          </div>
        )}
      </div>
    </section>
  );
}

function ProbeInputs({ delivered, setDelivered, source, setSource }: any) {
  return (
    <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", marginBottom: "1rem" }}>
      <div className="panel">
        <h3>Delivered records <span className="src">(JSONL)</span></h3>
        <textarea value={delivered} onChange={(e) => setDelivered(e.target.value)}
                  spellCheck={false} rows={7} />
      </div>
      <div className="panel">
        <h3>Upstream sample <span className="src">(optional — enables consistency)</span></h3>
        <textarea value={source} onChange={(e) => setSource(e.target.value)}
                  spellCheck={false} rows={7} />
      </div>
    </div>
  );
}
