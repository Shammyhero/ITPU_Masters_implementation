"use client";

/* The readiness report: one page, printable, and traceable back to the session.
 *
 * It reports what this session actually measured and nothing else. The
 * predicted exchange rate comes from the study's runs and is labelled as such;
 * the live one is only shown once a refusal has produced evidence, because a
 * ratio with no denominator is not a number worth printing.
 *
 * Provenance is on the page for a reason: a printout that reaches a meeting
 * should say which session, which arm and which seed block produced it, so it
 * can be told apart from the experimental corpus it must never be pooled with. */

import type { SessionInfo, Tick } from "@/lib/api";

const LABELS: Record<string, string> = {
  refused: "refused by the gate, before any model call",
  abstained: "the agent declined to answer",
  unparseable: "unusable output (a failure, never retried)",
  "not verified": "not verified (no system of record)",
  correct: "correct",
  answer_key_moved: "the answer key moved (pipeline)",
  both: "both",
  corrupted_in_transit: "corrupted in transit (pipeline)",
  agent_impairment: "agent impairment (model)",
};

export default function Report({
  session, ticks, task, predicted,
}: {
  session: SessionInfo;
  ticks: Tick[];
  task: string;
  predicted: { description: string; raw: number | null; trueCost: number | null } | null;
}) {
  const meter = session.meter;
  // Every question is counted, including the ones the gate refused: a refusal
  // is an outcome — the one enforcement exists to produce — and a report that
  // dropped them would show three questions and no answers with no explanation.
  const counts = new Map<string, number>();
  for (const tick of ticks) {
    const decision = tick.decision;
    const key = decision.refused ? "refused"
      : decision.attribution ?? (decision.abstained ? "abstained"
      : decision.parse_failed ? "unparseable"
      : decision.verifiable ? "unattributed" : "not verified");
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const latest = ticks.length ? ticks[ticks.length - 1].airs : null;
  const printed = new Date().toISOString().slice(0, 16).replace("T", " ");

  return (
    <section className="report">
      <header>
        <h2>Pipeline readiness — {session.source}</h2>
        <p className="hint">
          {printed} UTC · session {session.session_id} · {task} weights ·
          answered by {session.answerer}
        </p>
      </header>

      <div className="report-grid">
        <div>
          <h3>What was measured</h3>
          <table>
            <tbody>
              {latest && (["freshness", "latency", "consistency", "semantic"] as const).map(
                (dim) => (
                  <tr key={dim}>
                    <td>{dim}</td>
                    <td className="num">
                      {latest.dimensions[dim].score === null
                        ? "UNMEASURED"
                        : latest.dimensions[dim].score.toFixed(1)}
                    </td>
                    <td className="num muted">
                      weight {(latest.dimensions[dim].weight * 100).toFixed(0)}%
                    </td>
                  </tr>
                ),
              )}
              <tr>
                <td><b>AIRS</b></td>
                <td className="num">
                  <b>{latest?.airs === null || latest === null
                    ? "no score" : latest.airs.toFixed(1)}</b>
                </td>
                <td className="num muted">
                  {latest ? `on ${(latest.weight_covered * 100).toFixed(0)}% of the weight` : ""}
                </td>
              </tr>
            </tbody>
          </table>
          <p className="src">
            Scores are from the last question of this session. A dimension that could not
            be measured is reported UNMEASURED and carries no weight — it is never scored
            as healthy.
          </p>
        </div>

        <div>
          <h3>What the gate did</h3>
          <table>
            <tbody>
              <tr><td>policy</td><td className="num">{session.policy_description}</td></tr>
              <tr><td>questions asked</td><td className="num">{meter.asked}</td></tr>
              <tr><td>answered</td><td className="num">{meter.answered}</td></tr>
              <tr><td>refused before any model call</td><td className="num">{meter.refused}</td></tr>
              <tr><td>re-read upstream first</td><td className="num">{meter.refetched}</td></tr>
              <tr><td>spend</td><td className="num">${meter.usd.toFixed(4)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <h3>Where the answers ended up</h3>
      <table>
        <tbody>
          {[...counts.entries()].map(([key, count]) => (
            <tr key={key}>
              <td>{LABELS[key] ?? key}</td>
              <td className="num">{count}</td>
              <td className="num muted">
                {ticks.length ? `${((count / ticks.length) * 100).toFixed(0)}%` : ""}
              </td>
            </tr>
          ))}
          {!counts.size && (
            <tr><td colSpan={3} className="muted">Nothing asked yet.</td></tr>
          )}
        </tbody>
      </table>
      <p className="src">
        &ldquo;Corrupted in transit&rdquo; states that a field the answer needed did not
        arrive as the system of record has it. It does not claim the change caused the
        error.
      </p>

      <h3>What enforcement is expected to cost</h3>
      {predicted ? (
        <table>
          <tbody>
            <tr>
              <td>predicted, from the study&rsquo;s runs ({predicted.description})</td>
              <td className="num">
                {predicted.raw === null ? "—" : predicted.raw.toFixed(2)} raw ·{" "}
                {predicted.trueCost === null ? "—" : predicted.trueCost.toFixed(1)} true cost
              </td>
            </tr>
            <tr>
              <td>observed in this session</td>
              <td className="num">
                {meter.exchange_rate === null
                  ? `not yet — ${meter.prevented} prevented, ${meter.forfeited} forfeited`
                  : meter.exchange_rate.toFixed(2)}
              </td>
            </tr>
          </tbody>
        </table>
      ) : (
        <p className="muted">No prediction available for this task.</p>
      )}
      <p className="src">
        Correct answers forfeited per silent failure prevented. The raw rate credits a gate
        with every silent failure inside a refused batch; the true cost credits only the
        excess over what a fault-free pipeline produces anyway. About 75% of silent failure
        is agent-intrinsic and no data gate can reach it.
      </p>

      <p className="src">
        Live session, quarantined from the study&rsquo;s corpus: arm {session.arm}, seed
        block {session.seed_block[0]}–{session.seed_block[1]}, {session.ticks} ticks in
        ~/.airs/sessions/{session.session_id}.jsonl. AIRS weights are those calibrated for
        the {task} profile; the ranking inverts across tasks, so a profile from the other
        one would describe neither.
      </p>
    </section>
  );
}
