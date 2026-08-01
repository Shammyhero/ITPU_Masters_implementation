"use client";

import { useState } from "react";

export type InversionData = {
  faults: string[];
  retrieval: Record<string, number[]>;
  classification: Record<string, number[]>;
  mean_tau: number;
  masked_by_refusal: {
    model: string; fault: string; task: string; odds_ratio: number;
    accuracy: number; baseline_accuracy: number; abstained: number; note: string;
  };
};

const PRETTY: Record<string, string> = {
  freshness: "freshness",
  latency: "latency",
  schema_drift: "schema drift",
  semantic_stripping: "semantic stripping",
};

export default function Inversion({ data }: { data: InversionData }) {
  const [task, setTask] = useState<"retrieval" | "classification">("retrieval");
  const rows = data[task];
  const masked = data.masked_by_refusal;

  return (
    <section>
      <h2>The ranking transfers across models — and inverts across tasks</h2>
      <p className="sub">
        Odds ratio for silent failure against each model&rsquo;s own baseline.
        Mean Kendall&rsquo;s τ across models is {data.mean_tau.toFixed(3)}, and
        the two hosted models rank the faults identically. Switch the task and
        the ordering turns over: <b>AIRS weights transfer across models but must
        be recalibrated per task.</b>
      </p>

      <div className="tabs">
        {(["retrieval", "classification"] as const).map((t) => (
          <button
            key={t}
            className="tab"
            aria-pressed={task === t}
            onClick={() => setTask(t)}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>model</th>
              {data.faults.map((f) => (
                <th key={f}>{PRETTY[f] ?? f}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.entries(rows).map(([model, values]) => (
              <tr key={model}>
                <td>{model}</td>
                {values.map((v, i) => (
                  <td
                    key={i}
                    className={`num ${v >= 1.5 ? "hot" : "cool"}`}
                    title={v < 1 ? "below baseline" : undefined}
                  >
                    {v.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="src" style={{ marginTop: ".75rem" }}>
          Bold red = odds ratio ≥ 1.5, the threshold above which a fault
          materially raises silent failure. On retrieval that set is identical
          in all four models.
        </p>
      </div>

      {task === "classification" && (
        <div className="callout">
          <b>An odds ratio below 1 is not evidence of safety.</b>{" "}
          {masked.model} under {PRETTY[masked.fault]} scores{" "}
          {masked.odds_ratio.toFixed(2)} — lower silent failure than baseline.
          But accuracy collapsed from{" "}
          {masked.baseline_accuracy.toFixed(3)} to {masked.accuracy.toFixed(3)}{" "}
          and abstention rose to {Math.round(masked.abstained * 100)}%. The
          damage went into <em>refusal</em>, not into confident error. Ranking on
          silent failure alone would call the most destructive fault the safest —
          and this is the one fault whose corruption is legible inside the
          delivered record.
        </div>
      )}
    </section>
  );
}
