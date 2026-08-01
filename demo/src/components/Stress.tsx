"use client";

import { useState } from "react";

type Stop = {
  label: string; fault: string; severity: string; n: number;
  dims: Record<string, number>;
  accuracy: number; abstained: number; silent: number;
};
export type StressData = {
  note: string;
  tasks: Record<string, Record<string, Stop[]>>;
};

const FAULTS = ["freshness", "latency", "schema_drift", "semantic_stripping"];
const PRETTY: Record<string, string> = {
  freshness: "Freshness", latency: "Latency",
  schema_drift: "Schema drift", semantic_stripping: "Semantic stripping",
};
const DIMS = ["freshness", "latency", "consistency", "semantic"];

function Bar({ label, value, tone, baseline }: {
  label: string; value: number; tone: string; baseline?: number;
}) {
  const pct = Math.max(0, Math.min(100, value * 100));
  const basePct = baseline === undefined ? null : Math.max(0, Math.min(100, baseline * 100));
  return (
    <div className="bar">
      <div className="bar-head">
        <span>{label}</span>
        <span className="mono" style={{ color: tone }}>{pct.toFixed(0)}%</span>
      </div>
      <div className="track">
        <div className="fill" style={{ width: `${pct}%`, background: tone }} />
        {basePct !== null && (
          <div className="ghost" style={{ left: `${basePct}%` }}
               title={`healthy baseline ${basePct.toFixed(0)}%`} />
        )}
      </div>
    </div>
  );
}

export default function Stress({ data, weights }: {
  data: StressData; weights: Record<string, number>;
}) {
  const [task, setTask] = useState("retrieval");
  const [fault, setFault] = useState("freshness");
  const [index, setIndex] = useState(4);

  const stops = data.tasks[task]?.[fault] ?? [];
  const i = Math.min(index, stops.length - 1);
  const stop = stops[i];
  const base = stops[0];
  if (!stop) return null;

  // AIRS composite over the calibrated weights — the same arithmetic the
  // probe does, recomputed live as the dial moves.
  const airs = DIMS.reduce((sum, d) => sum + (weights[d] ?? 0) * stop.dims[d], 0);
  const band = airs >= 85 ? "READY" : airs >= 70 ? "WATCH" : "AT RISK";
  const tone = airs >= 85 ? "var(--good)" : airs >= 70 ? "var(--warn)" : "var(--bad)";

  return (
    <section>
      <h2>Stress the pipeline</h2>
      <p className="sub">
        Choose a fault, drag the severity, and watch the agent&rsquo;s behaviour
        move. <b>Every stop is a real measured condition</b> — {stop.n} logged
        decisions at this one — so nothing between two stops is claimed and
        nothing is interpolated. AIRS is recomputed live from the dimension
        scores using the calibrated weights.
      </p>

      <div className="tabs">
        {Object.keys(data.tasks).map((t) => (
          <button key={t} className="tab" aria-pressed={task === t}
                  onClick={() => { setTask(t); setIndex(Math.min(index, 1)); }}>
            {t}
          </button>
        ))}
      </div>
      <div className="tabs">
        {FAULTS.map((f) => (
          <button key={f} className="tab" aria-pressed={fault === f}
                  onClick={() => { setFault(f); setIndex(1); }}>
            {PRETTY[f]}
          </button>
        ))}
      </div>

      <div className="panel">
        <div className="dial">
          <input type="range" min={0} max={stops.length - 1} step={1} value={i}
                 onChange={(e) => setIndex(Number(e.target.value))}
                 aria-label={`${PRETTY[fault]} severity`} />
          <div className="ticks">
            {stops.map((s, k) => (
              <button key={s.label} className="tick" aria-pressed={k === i}
                      onClick={() => setIndex(k)}>{s.label}</button>
            ))}
          </div>
        </div>

        <div className="readout">
          <div>
            <div className="score" style={{ color: tone }}>{airs.toFixed(1)}</div>
            <div className="l">AIRS <span className={`band ${band.replace(" ", ".")}`}>{band}</span></div>
            <div className="src" style={{ marginTop: ".6rem" }}>
              {DIMS.map((d) => `${d.slice(0, 4)} ${stop.dims[d].toFixed(0)}`).join(" · ")}
            </div>
          </div>
          <div className="bars">
            <Bar label="Accuracy" value={stop.accuracy} tone="var(--accent)"
                 baseline={base.accuracy} />
            <Bar label="Silent failure — wrong AND confident" value={stop.silent}
                 tone="var(--bad)" baseline={base.silent} />
            <Bar label="Abstained — the safe failure" value={stop.abstained}
                 tone="var(--good)" baseline={base.abstained} />
            <div className="src">
              Ghost marker = the healthy baseline for this task. n = {stop.n} decisions.
            </div>
          </div>
        </div>

        {fault === "semantic_stripping" && task === "classification" && i === stops.length - 1 && (
          <div className="callout">
            <b>Watch which bar moved.</b> Accuracy collapsed, but silent failure
            barely rose — the damage went into <em>abstention</em>. This is the
            one fault whose corruption is legible inside the record, so the agent
            refuses instead of guessing. Ranking faults on silent failure alone
            would call this the safest one.
          </div>
        )}
        {fault === "latency" && i > 0 && (
          <div className="callout">
            <b>Nothing moved, and that is the finding.</b> A synchronous agent
            with no deadline waits and reads identical data, so latency cannot
            change what it concludes. Latency earns a calibrated weight of
            exactly 0%.
          </div>
        )}
        {fault === "freshness" && task === "retrieval" && i >= 4 && (
          <div className="callout">
            <b>Accuracy falls, but the agent is not impaired.</b> Staleness moved
            the answer key — on the queries it left answerable, accuracy is
            unchanged (residual −0.003). What rises is <em>exposure</em>, not
            error rate.
          </div>
        )}
      </div>
    </section>
  );
}
