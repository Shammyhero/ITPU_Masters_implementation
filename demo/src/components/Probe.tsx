"use client";

import { useState } from "react";

type Dim = { score: number | null; detail: string };
export type ProbeData = {
  weights: Record<string, number>;
  calibrated_at: string;
  target: string;
  samples: {
    id: string; label: string; n_records: number;
    dimensions: Record<string, Dim>;
    airs: number | null; weight_covered: number; band: string | null;
  }[];
};

const ORDER = ["freshness", "latency", "consistency", "semantic"];

export default function Probe({ data }: { data: ProbeData }) {
  const [id, setId] = useState(data.samples[0]?.id);
  const sample = data.samples.find((s) => s.id === id) ?? data.samples[0];
  if (!sample) return null;
  const partial = sample.weight_covered < 0.999;

  return (
    <section>
      <h2>Score the pipeline before you deploy the agent</h2>
      <p className="sub">
        <span className="mono">airs probe</span> reads a sample of records as
        your pipeline delivers them and scores four dimensions — no agent, no
        ground truth, no model call, no API key. Weights calibrated{" "}
        {data.calibrated_at} against total error, held out by run.
      </p>

      <div className="tabs">
        {data.samples.map((s) => (
          <button key={s.id} className="tab" aria-pressed={s.id === id}
                  onClick={() => setId(s.id)}>
            {s.label}
          </button>
        ))}
      </div>

      <div className="panel">
        <div style={{ display: "flex", alignItems: "baseline", gap: ".75rem",
                      flexWrap: "wrap", marginBottom: "1rem" }}>
          <span className="score">
            {sample.airs === null ? "—" : sample.airs.toFixed(1)}
          </span>
          <span className="mono" style={{ color: "var(--muted)" }}>/100</span>
          {sample.band && (
            <span className={`band ${sample.band.replace(" ", ".")}`}>
              {sample.band}
            </span>
          )}
          <span className="src" style={{ marginLeft: "auto" }}>
            {sample.n_records} records
          </span>
        </div>

        <table>
          <thead>
            <tr><th>dimension</th><th>score</th><th>weight</th>
                <th style={{ textAlign: "left" }}>evidence</th></tr>
          </thead>
          <tbody>
            {ORDER.map((dim) => {
              const d = sample.dimensions[dim];
              const w = data.weights[dim] ?? 0;
              const unmeasured = d?.score === null;
              return (
                <tr key={dim}>
                  <td>{dim}</td>
                  <td className={`num ${unmeasured ? "hot" : ""}`}>
                    {unmeasured ? "UNMEASURED" : d.score!.toFixed(1)}
                  </td>
                  <td className="num cool">{(w * 100).toFixed(1)}%</td>
                  <td style={{ textAlign: "left", color: "var(--muted)",
                               fontSize: ".82rem" }}>
                    {d?.detail}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {partial && (
          <div className="callout">
            <b>This composite rests on {Math.round(sample.weight_covered * 100)}%
            of the calibrated weight.</b> Unmeasured dimensions are excluded, never
            assumed healthy — a pipeline can score well here purely because nobody
            looked. Supplying an upstream sample is what makes consistency
            measurable.
          </div>
        )}
      </div>
    </section>
  );
}
