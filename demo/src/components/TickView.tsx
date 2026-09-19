"use client";

/* One question, rendered in the order it happened.
 *
 * This component is fed by the live stream and — later — by the replay corpus,
 * because both produce the same Tick. One renderer, two feeds: a walkthrough
 * built from recorded runs and a live answer look identical, which is the point
 * the thesis is making.
 *
 * Confidence is shown greyed, with the measured AUC beside it, because the
 * study found the agent's own confidence separates its silent failures from its
 * correct answers at 0.501 — a coin flip. Rendering it as a reassuring number
 * would contradict the result on the same screen. */

import type { Attribution, ChangedField, GateBlock, Tick } from "@/lib/api";

type Turn = {
  key: number;
  question: string;
  gate?: GateBlock;
  refetch?: Tick["refetch"];
  answer?: { value: unknown; text: string; confidence: number; abstained: boolean;
             parse_failed: boolean };
  tick?: Tick;
  error?: string;
  verifying: boolean;
};

const VERDICT: Record<Attribution, { label: string; tone: string; detail: string }> = {
  correct: { label: "Correct", tone: "safe", detail: "the answer matches the system of record" },
  answer_key_moved: {
    label: "Silent failure · the answer key moved", tone: "lie",
    detail: "the pipeline served values that had since changed, and the answer followed them",
  },
  both: {
    label: "Silent failure · both", tone: "lie",
    detail: "the answer key moved, and the answer did not follow the served values either",
  },
  corrupted_in_transit: {
    label: "Silent failure · corrupted in transit", tone: "lie",
    detail: "fields this answer needs did not arrive as the system of record has them",
  },
  agent_impairment: {
    label: "Silent failure · agent impairment", tone: "lie",
    detail: "the records arrived intact and supported the right answer; the model still missed it",
  },
};

const CHANGE_WORDS: Record<string, string> = {
  renamed: "renamed", retyped: "changed type", "value changed": "different value",
  missing: "missing", "name made opaque": "name replaced",
  "record not delivered": "never arrived",
};

function show(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export default function TickView({ turn }: { turn: Turn }) {
  const tick = turn.tick;
  const gate = tick?.gate ?? turn.gate;
  const decision = tick?.decision;
  const attribution = decision?.attribution ?? null;
  const verdict = attribution ? VERDICT[attribution] : null;

  return (
    <article className="turn panel">
      <header className="turn-head">
        <p className="turn-q">{turn.question || tick?.question.text}</p>
        {tick && <p className="turn-plan">checked as: {tick.question.describe}</p>}
      </header>

      {gate && <GateLine gate={gate} refetch={turn.refetch ?? tick?.refetch} />}

      {turn.answer && !turn.answer.abstained && !turn.answer.parse_failed && (
        <div className="answer">
          <div className="answer-v">{show(turn.answer.value)}</div>
          <div className="answer-c">
            confidence {turn.answer.confidence.toFixed(2)}
            <span className="auc"> · the agent&rsquo;s confidence predicts its own silent
              failures at AUC 0.501 — a coin flip</span>
          </div>
        </div>
      )}
      {turn.answer?.abstained && (
        <div className="answer abstained">
          <div className="answer-v">abstained</div>
          <div className="answer-c">{turn.answer.text}</div>
        </div>
      )}
      {turn.answer?.parse_failed && (
        <div className="answer abstained">
          <div className="answer-v">unparseable</div>
          <div className="answer-c">the model&rsquo;s output could not be read as an answer —
            counted as a failure, never retried</div>
        </div>
      )}

      {turn.verifying && (
        <p className="verifying">checking it against the system of record…</p>
      )}

      {verdict && (
        <div className={`verdict ${verdict.tone}`}>
          <div className="t">{verdict.label}</div>
          <div className="d">{verdict.detail}</div>
        </div>
      )}
      {tick && !decision?.verifiable && !decision?.refused && (
        <div className="verdict">
          <div className="t">Not verified</div>
          <div className="d">{decision?.reason}</div>
        </div>
      )}

      {tick && <Trace tick={tick} />}
      {turn.error && <div className="callout error"><b>Refused.</b> {turn.error}</div>}
    </article>
  );
}

function GateLine({ gate, refetch }: { gate: GateBlock; refetch?: Tick["refetch"] }) {
  const tone = gate.verdict === "refuse" ? "lie" : gate.verdict === "refetch" ? "warn" : "safe";
  return (
    <div className={`gate-line ${tone}`}>
      <span className={`gate-badge ${tone}`}>{gate.verdict.toUpperCase()}</span>
      <span className="gate-reason">{gate.reason}</span>
      {refetch?.attempted && (
        <span className="gate-refetch">
          {refetch.n_records} record{refetch.n_records === 1 ? "" : "s"} read again
          ({refetch.initiated_by}-initiated) → {refetch.verdict_after}
        </span>
      )}
      {gate.verdict === "refuse" && (
        <>
          <span className="gate-cost">no model was called, so this cost nothing</span>
          {/* What the refusal bought or cost, in its own tone: a forfeited
              correct answer is not good news and must not be coloured as if
              it were. */}
          {gate.would_have === "silent_failure" && (
            <span className="gate-bought">and it prevented a silent failure</span>
          )}
          {gate.would_have === "correct" && (
            <span className="gate-forfeit">but it forfeited a correct answer</span>
          )}
          {gate.would_have === "abstained" && (
            <span className="gate-reason">the records did not support an answer anyway</span>
          )}
        </>
      )}
    </div>
  );
}

function Trace({ tick }: { tick: Tick }) {
  const { records, decision, airs } = tick;
  const changed = new Map<string, ChangedField>();
  for (const change of decision.changed_fields ?? []) {
    if (change.field) changed.set(`${change.id}:${change.field}`, change);
  }
  const fields = Array.from(
    new Set([
      tick.question.plan.measure as string | undefined,
      ...((tick.question.plan.where as { field: string }[] | undefined) ?? []).map((c) => c.field),
    ].filter(Boolean) as string[]),
  );
  const moved = Boolean(decision.flipped);

  return (
    <details className="trace">
      <summary>What the agent was shown, and what was true</summary>
      <table className="trace-table">
        <thead>
          <tr>
            <th>record</th>
            <th>delivered</th>
            {moved && <th>served then</th>}
            <th>system of record</th>
          </tr>
        </thead>
        <tbody>
          {records.ids.map((id, index) => {
            const delivered = records.delivered[index] ?? {};
            const served = id ? records.served?.[id] : undefined;
            const upstream = id ? records.upstream?.[id] : undefined;
            const marks = fields
              .map((field) => changed.get(`${id}:${field}`))
              .filter(Boolean) as ChangedField[];
            return (
              <tr key={id ?? index}>
                <td>{id ?? "—"}</td>
                <td className="num">
                  <Fields payload={delivered} fields={fields} />
                  {marks.map((change) => (
                    <span className="mark" key={change.field}>
                      {change.field} {CHANGE_WORDS[change.change] ?? change.change}
                    </span>
                  ))}
                </td>
                {moved && <td className="num"><Fields payload={served} fields={fields} /></td>}
                <td className="num"><Fields payload={upstream} fields={fields} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="trace-foot">
        <span>
          AIRS at that moment:{" "}
          {airs.airs === null ? "no score" : `${airs.airs.toFixed(1)} ${airs.band ?? ""}`}
          {" · "}
          {(["freshness", "latency", "consistency", "semantic"] as const).map((dim) => (
            <span key={dim} className="dim-chip">
              {dim} {airs.dimensions[dim].score === null
                ? "UNMEASURED"
                : airs.dimensions[dim].score.toFixed(0)}
            </span>
          ))}
        </span>
        {records.lag_seconds !== null && (
          <span>delivered {records.lag_seconds}s behind the system of record</span>
        )}
        {decision.answer_served !== undefined && decision.flipped && (
          <span>
            the served values implied {show(decision.answer_served.value)}; the truth was{" "}
            {show(decision.answer_upstream?.value)}
          </span>
        )}
      </div>
      {tick.notes.map((note, index) => (
        <p className="src" key={index}>{note}</p>
      ))}
    </details>
  );
}

function Fields({ payload, fields }: { payload?: Record<string, unknown>; fields: string[] }) {
  if (!payload) return <>—</>;
  return (
    <>
      {fields.map((field, index) => (
        <span key={field}>
          {index > 0 && " · "}
          <span className="field-name">{field}</span>{" "}
          {field in payload ? show(payload[field]) : <span className="absent">absent</span>}
        </span>
      ))}
    </>
  );
}
