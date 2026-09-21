"use client";

/* The study's own decisions, played through the console's renderer.
 *
 * Every Tick here was recorded by the benchmark — gpt-4o-mini answering the
 * retrieval task under one fault at a time — and is rendered by exactly the
 * component that renders a live answer. That is the claim: a recorded silent
 * failure and a live one look identical because they are the same measurement,
 * not a demo built to resemble one.
 *
 * The feed is imported at build time, so this page needs no server. It opens
 * from a file server years from now, archived beside the data. */

import { useState } from "react";

import feed from "@/data/replay_ticks.json";
import TickView from "@/components/TickView";
import type { Tick } from "@/lib/api";

/* Cast once, deliberately. TypeScript infers the shape of an imported JSON file
 * from its current CONTENTS — so `records.served` becomes a union of the exact
 * product ids in today's bake, which is stricter than the contract and breaks
 * whenever the feed is re-baked. The real shape is produced by
 * `server/replay_bake.py` and asserted in `tests/test_replay_ticks.py`, on the
 * side that generates it. */
const FEED = feed as unknown as { ticks: Tick[]; note: string; runs: string[] };
const TICKS = FEED.ticks;
const NOTE = FEED.note;
const RUNS = FEED.runs;

function label(tick: Tick): string {
  const decision = tick.decision;
  if (decision.abstained) return "abstained";
  if (decision.parse_failed) return "unparseable";
  return (decision.attribution ?? "—").replace(/_/g, " ");
}

export default function Replay() {
  const [shown, setShown] = useState(1);
  const visible = TICKS.slice(0, shown);
  const done = shown >= TICKS.length;

  return (
    <section className="talk">
      <h1>The same instrument, on the study&rsquo;s own runs</h1>
      <p className="lede">
        Seven decisions recorded by the benchmark, played back through the console you
        would use on your own pipeline. Nothing here is staged: these are answers
        <span> </span>
        <b>gpt-4o-mini</b> gave during the experiment, with the records it was shown
        regenerated from each run&rsquo;s fault chain.
      </p>

      <div className="setup panel">
        <div className="field">
          <span className="field-label">Showing</span>
          <span className="replay-count">
            {visible.length} of {TICKS.length} decisions · {RUNS.length} runs
          </span>
        </div>
        <button className="cta" onClick={() => setShown(done ? 1 : shown + 1)}>
          {done ? "Start again" : "Next decision"}
        </button>
        {!done && (
          <button className="tab" onClick={() => setShown(TICKS.length)}>Show all</button>
        )}
      </div>

      <ol className="replay-index">
        {TICKS.map((tick, index) => (
          <li key={index} className={index < shown ? "seen" : ""}>
            <span className="replay-cond">{tick.source.condition}</span>
            <span className={`replay-label ${tick.decision.silent_failure ? "bad" : ""}`}>
              {label(tick)}
            </span>
          </li>
        ))}
      </ol>

      <div className="turns">
        {visible.map((tick, index) => (
          <TickView
            key={index}
            turn={{
              key: index,
              question: tick.question.text,
              tick,
              answer: {
                value: tick.decision.value,
                text: tick.decision.answer,
                confidence: tick.decision.confidence,
                abstained: tick.decision.abstained,
                parse_failed: tick.decision.parse_failed,
              },
              verifying: false,
            }}
          />
        ))}
      </div>

      <p className="src">{NOTE}</p>
    </section>
  );
}
