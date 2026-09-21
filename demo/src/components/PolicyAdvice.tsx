"use client";

/* A policy to start from, and what it is predicted to cost.
 *
 * Nothing here is a heuristic. Every policy offered was replayed over the
 * study's own runs — the same accounting behind `docs/gate_findings.md` — and
 * the one recommended is the cheapest by exchange rate among those that refuse
 * something and still answer. What the live session has measured only removes
 * policies its pipeline could never clear; the floors themselves always come
 * from the corpus.
 *
 * Two costs are shown, never blended, because they answer different questions:
 * the sweep's raw rate credits a gate with every silent failure inside a
 * refused batch, while the attribution rate credits only the excess over what a
 * fault-free pipeline produces anyway. On retrieval those are 2.26 and 7.0, and
 * a reader who saw only the first would think enforcement four times cheaper
 * than the study found. */

import { useEffect, useState } from "react";

import {
  ApiError,
  type PolicyOutcome,
  type Recommendation,
  recommendPolicy,
} from "@/lib/api";

// docs/gate_findings.md: the attribution "true cost" for retrieval, and the
// share of silent failure no gate can reach.
const TRUE_COST = { retrieval: 7.0, classification: null } as Record<string, number | null>;

export default function PolicyAdvice({
  task, sessionId, onApply, onPredicted,
}: {
  task: string;
  sessionId: string | null;
  onApply: (policy: Record<string, unknown>, description: string) => void;
  onPredicted?: (predicted: { description: string; raw: number | null;
                              trueCost: number | null } | null) => void;
}) {
  const [advice, setAdvice] = useState<Recommendation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let live = true;
    recommendPolicy({ task, session_id: sessionId })
      .then((body) => {
        if (!live) return;
        setAdvice(body);
        // The report prints the prediction beside the session's own rate.
        onPredicted?.(body.recommended
          ? { description: body.recommended.policy_name,
              raw: body.recommended.exchange_rate, trueCost: TRUE_COST[task] ?? null }
          : null);
      })
      .catch((exc: ApiError) => live && setError(exc.message));
    return () => { live = false; };
    // `onPredicted` is a setter from the parent and is deliberately not a
    // dependency: including it would refetch on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task, sessionId]);

  if (error) return <p className="hint warn-text">No recommendation: {error}</p>;
  if (!advice?.recommended) return null;
  const best = advice.recommended;
  const trueCost = TRUE_COST[task];

  return (
    <div className="advice panel">
      <div className="advice-head">
        <div>
          <h3>Suggested policy: {best.policy_name}</h3>
          {/* `describe()` prefixes the name, which the heading already carries. */}
          <p className="advice-rule">
            {best.description.startsWith(`${best.policy_name}: `)
              ? best.description.slice(best.policy_name.length + 2)
              : best.description}
          </p>
          <p className="hint">
            Priced on {advice.corpus.runs} of the study&rsquo;s runs
            {advice.filtered_by_session && ", filtered to what this pipeline could clear"}.
            It is not a measurement of your data.
          </p>
        </div>
        <button className="cta"
                onClick={() => onApply(best.policy, best.description)}>
          Apply to the router
        </button>
      </div>

      <div className="advice-grid">
        <Cell value={`${(best.coverage * 100).toFixed(0)}%`} label="still answered"
              note="coverage after refusals" />
        <Cell value={`${(best.prevented_share * 100).toFixed(0)}%`}
              label="silent failures prevented" note="of those in the corpus" />
        <Cell value={`${(best.forfeited_share * 100).toFixed(0)}%`}
              label="correct answers forfeited" note="the price of the refusals" />
        <Cell value={best.exchange_rate === null ? "—" : best.exchange_rate.toFixed(2)}
              label="raw exchange rate"
              note="forfeited per prevented, crediting every silent failure in a refused batch" />
        <Cell value={trueCost === null ? "—" : trueCost.toFixed(1)}
              label="attribution true cost"
              note="crediting only the excess over a fault-free pipeline" em />
      </div>

      {advice.fault_free && (
        <p className="hint">
          About <b>{(advice.fault_free.rate * 100).toFixed(0)}%</b> of silent failure is
          present on a fault-free pipeline ({advice.fault_free.pipelines} clean pipelines,
          {" "}{(advice.fault_free.min * 100).toFixed(0)}–
          {(advice.fault_free.max * 100).toFixed(0)}%). No data gate can reach it, which is
          why the two costs above differ: a gate can only be credited with the failures a
          fault actually caused.
        </p>
      )}

      <button className="tab" onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Show"} the {advice.considered.length} policies considered
      </button>
      {open && (
        <table className="advice-table">
          <thead>
            <tr>
              <th>policy</th><th>coverage</th><th>prevented</th>
              <th>forfeited</th><th>raw rate</th><th>usable here</th>
            </tr>
          </thead>
          <tbody>
            {advice.considered.map((row) => (
              <Row key={row.policy_name} row={row} best={best.policy_name} />
            ))}
          </tbody>
        </table>
      )}
      <p className="src">{advice.note}</p>
    </div>
  );
}

function Cell({ value, label, note, em }: {
  value: string; label: string; note: string; em?: boolean;
}) {
  return (
    <div className={`advice-cell${em ? " em" : ""}`}>
      <div className="advice-v">{value}</div>
      <div className="advice-l">{label}</div>
      <div className="advice-n">{note}</div>
    </div>
  );
}

function Row({ row, best }: { row: PolicyOutcome; best: string }) {
  return (
    <tr className={row.policy_name === best ? "best" : ""}>
      <td>{row.description}</td>
      <td className="num">{(row.coverage * 100).toFixed(0)}%</td>
      <td className="num">{(row.prevented_share * 100).toFixed(0)}%</td>
      <td className="num">{(row.forfeited_share * 100).toFixed(0)}%</td>
      <td className="num">{row.exchange_rate === null ? "—" : row.exchange_rate.toFixed(2)}</td>
      <td className="num">{row.feasible_here ? "yes" : "no"}</td>
    </tr>
  );
}
