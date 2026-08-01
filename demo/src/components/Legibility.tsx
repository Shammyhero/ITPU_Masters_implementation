"use client";

import { useState } from "react";

type Fault = {
  id: string; name: string; record: Record<string, unknown>;
  spot_it: boolean; why: string; abstained: number;
};
export type LegibilityData = {
  healthy: Record<string, unknown>;
  faults: Fault[];
  punchline: string;
};

function Rec({ data, highlight }: { data: Record<string, unknown>; highlight?: boolean }) {
  return (
    <pre className={`rec${highlight ? " odd" : ""}`}>
      {"{\n"}
      {Object.entries(data).map(([k, v], i, a) => (
        <span key={k}>
          {`  "${k}": ${typeof v === "string" ? `"${v}"` : v}`}
          {i < a.length - 1 ? ",\n" : "\n"}
        </span>
      ))}
      {"}"}
    </pre>
  );
}

export default function Legibility({ data }: { data: LegibilityData }) {
  const [guesses, setGuesses] = useState<Record<string, boolean>>({});
  const answered = Object.keys(guesses).length;
  const done = answered === data.faults.length;
  const correct = data.faults.filter((f) => guesses[f.id] === f.spot_it).length;

  return (
    <section>
      <span className="act">Act 2</span>
      <h2>Could you have known?</h2>
      <p className="sub">
        Four different things go wrong in a data pipeline. Here is the same
        product record under each. Judge each one by eye:{" "}
        <b>can you tell something is wrong?</b> Then compare your instinct with
        how often the agent refused to answer.
      </p>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <div className="l">The record when everything is healthy</div>
        <Rec data={data.healthy} />
      </div>

      <div className="grid legi">
        {data.faults.map((f) => {
          const guess = guesses[f.id];
          const shown = guess !== undefined;
          return (
            <div key={f.id} className="panel col">
              <h3>{f.name}</h3>
              <Rec data={f.record} highlight={shown && f.spot_it} />
              {!shown ? (
                <div className="ask">
                  <span>Can you tell?</span>
                  <button className="tab" onClick={() => setGuesses((g) => ({ ...g, [f.id]: true }))}>
                    Yes
                  </button>
                  <button className="tab" onClick={() => setGuesses((g) => ({ ...g, [f.id]: false }))}>
                    No
                  </button>
                </div>
              ) : (
                <>
                  <div className={`judge ${guess === f.spot_it ? "hit" : "miss"}`}>
                    {guess === f.spot_it ? "Matches the data" : "The data disagrees"}
                    {" — "}
                    {f.spot_it ? "this one is spottable" : "this one is not"}
                  </div>
                  <p className="why">{f.why}</p>
                  <div className="abst">
                    <div className="track">
                      <div className="fill" style={{
                        width: `${Math.min(100, f.abstained * 100 * 4)}%`,
                        background: f.spot_it ? "var(--good)" : "var(--bad)",
                      }} />
                    </div>
                    <div className="abst-l">
                      agent declined on <b>{(f.abstained * 100).toFixed(0)}%</b> of queries
                    </div>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {done && (
        <div className="callout big">
          <b>You matched the agent on {correct} of {data.faults.length}.</b>{" "}
          {data.punchline} It declines on the one fault you can see and commits
          on the three you cannot — which is why the dangerous faults are not the
          severe ones, but the <em>quiet</em> ones.
        </div>
      )}
    </section>
  );
}
