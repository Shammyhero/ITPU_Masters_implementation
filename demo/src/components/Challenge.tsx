"use client";

import { useState } from "react";

type Candidate = {
  id: string; title: string;
  served_price: number; served_stock: number;
  true_price: number; true_stock: number; changed: boolean;
};
export type Case = {
  query: string; candidates: Candidate[];
  agent_answer: string; agent_confidence: number; true_answer: string;
  staleness_seconds: number; run_id: string;
};

const money = (n: number) => `$${n.toFixed(2)}`;

export default function Challenge({ cases }: { cases: Case[] }) {
  const [caseIndex, setCaseIndex] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const c = cases[caseIndex];
  if (!c) return null;

  const agreedWithAgent = picked === c.agent_answer;
  const readerWasRight = picked === c.true_answer;

  const next = () => {
    setCaseIndex((i) => (i + 1) % cases.length);
    setPicked(null);
    setRevealed(false);
  };

  return (
    <section>
      <span className="act">Act 1</span>
      <h2>You be the agent</h2>
      <p className="sub">
        Here is a real customer query and the catalog records an agent was
        actually given. Your job is the agent&rsquo;s job: pick the{" "}
        <b>cheapest product that is in stock</b>.
      </p>

      <div className="panel">
        <div className="q">&ldquo;{c.query}&rdquo;</div>

        <div className="cands">
          {c.candidates.map((p) => {
            const out = p.served_stock === 0;
            const isPick = picked === p.id;
            const isTruth = revealed && p.id === c.true_answer;
            const isAgent = revealed && p.id === c.agent_answer;
            return (
              <button
                key={p.id}
                className={`cand${isPick ? " picked" : ""}${isTruth ? " truth" : ""}`}
                disabled={revealed}
                onClick={() => setPicked(p.id)}
              >
                <div className="cand-main">
                  <span className="cand-title">{p.title}</span>
                  <span className="cand-id mono">{p.id}</span>
                </div>
                <div className="cand-nums">
                  <span className={`mono price${revealed && p.changed ? " was" : ""}`}>
                    {money(p.served_price)}
                  </span>
                  {revealed && p.changed && (
                    <span className="mono price now">{money(p.true_price)}</span>
                  )}
                  <span className={`stock${out ? " out" : ""}`}>
                    {out ? "out of stock" : `${p.served_stock} in stock`}
                  </span>
                </div>
                {revealed && (isTruth || isAgent) && (
                  <div className="cand-tags">
                    {isAgent && <span className="tag agent">agent picked this</span>}
                    {isTruth && <span className="tag truth">actually cheapest</span>}
                  </div>
                )}
              </button>
            );
          })}
        </div>

        {!revealed && (
          <button className="cta" disabled={!picked} onClick={() => setRevealed(true)}>
            {picked ? "Lock it in" : "Pick a product first"}
          </button>
        )}

        {revealed && (
          <div className={`reveal ${readerWasRight ? "ok" : "bad"}`}>
            <div className="reveal-t">
              {readerWasRight
                ? "You got it — but only by not doing the task."
                : agreedWithAgent
                ? "You chose exactly what the agent chose. You were both wrong."
                : "Wrong — and so was the agent."}
            </div>
            <p>
              The records you were shown were{" "}
              <b>{c.staleness_seconds} seconds out of date</b>. In that window
              the prices moved, so the cheapest in-stock product was no longer
              the one the catalog implied. Both of you answered correctly for the
              data in front of you, and wrongly for the world.
            </p>
            <p>
              The agent answered <span className="mono">{c.agent_answer}</span> at{" "}
              <b>confidence {c.agent_confidence.toFixed(2)}</b> — the top of its
              scale. It did not hedge, and it did not decline.
            </p>
            <p className="key">
              Look back at the records. There was no timestamp, no age, nothing
              about when any of it was true. <b>You could not have known — and
              neither could the agent.</b> That is the whole thesis.
            </p>
            <button className="cta ghost-btn" onClick={next}>
              Try another real query →
            </button>
          </div>
        )}
      </div>
      <p className="src">
        Reconstructed exactly from run {c.run_id.slice(0, 8)} — same query, same
        timestamps, same catalog state the agent was served.
      </p>
    </section>
  );
}
