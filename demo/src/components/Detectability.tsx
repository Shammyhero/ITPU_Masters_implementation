"use client";

type Column = {
  id: string;
  label: string;
  shown: string;
  answer: string | null;
  confidence: number | null;
  abstained: boolean;
  correct: boolean | null;
  run_id: string | null;
  note?: string;
};

export type DetectabilityData = {
  case: {
    query: string;
    true_answer: string;
    served_answer: string;
    record_age_seconds: number;
    columns: Column[];
  };
  summary: {
    n_flipped: number;
    without: { abstained: number; silent: number; confidence_wrong: number };
    with_age: { abstained: number; silent: number; confidence_wrong: number };
    mcnemar_p: number;
    discordant: number[];
  };
};

/** The record as the agent saw it, per column. */
function RecordView({ column, age }: { column: Column; age: number }) {
  if (column.id === "budget_enforced") {
    return (
      <div className="record">
        {`{ "policy": "max_record_age_seconds: 1.0" }`}
        <br />
        <br />
        <span className="hl">→ record is 5.05s old — REJECTED at the gate</span>
        <br />
        the agent is never asked
      </div>
    );
  }
  return (
    <div className="record">
      {`{\n  "product_id": "…",\n  "price": 24.99,\n  "stock": 3`}
      {column.id === "age_delivered" && (
        <>
          {`,\n  `}
          <span className="hl">{`"_record_age_seconds": ${age}`}</span>
        </>
      )}
      {`\n}`}
    </div>
  );
}

function Verdict({ column }: { column: Column }) {
  const blocked = column.id === "budget_enforced";
  if (blocked) {
    return (
      <div className="verdict safe">
        <div className="t">No wrong answer reaches the user</div>
        <div className="d">
          The staleness budget is enforced outside the model, so the decision is
          never made on data that cannot support it.
        </div>
      </div>
    );
  }
  return (
    <div className="verdict lie">
      <div className="t">
        Confidently wrong — {(column.confidence ?? 0).toFixed(2)} confidence
      </div>
      <div className="d">
        Answered <span className="mono">{column.answer}</span>, which was correct
        for the data it was shown and wrong for the world at query time. It did
        not abstain.
      </div>
    </div>
  );
}

export default function Detectability({ data }: { data: DetectabilityData }) {
  const { case: c, summary: s } = data;
  const pct = (x: number) => `${Math.round(x * 100)}%`;

  return (
    <section>
      <h2>Delivering the record&rsquo;s age does not fix it</h2>
      <p className="sub">
        A real query from the detectability arm. Staleness moved the correct
        answer, so the agent cannot be right — the only question is whether it
        says so. Columns 1 and 2 are actual logged decisions on the{" "}
        <em>same query, same fault realisation, same prompt</em>; the only
        difference is the highlighted field.
      </p>

      <div className="panel" style={{ marginBottom: "1rem" }}>
        <div className="mono" style={{ color: "var(--muted)", fontSize: ".8rem" }}>
          customer query
        </div>
        <div style={{ fontSize: "1.05rem" }}>&ldquo;{c.query}&rdquo;</div>
        <div className="src">
          truth at query time: {c.true_answer} · what the stale catalog implied:{" "}
          {c.served_answer}
        </div>
      </div>

      <div className="grid three">
        {c.columns.map((column, i) => (
          <div key={column.id} className="panel col">
            <div className="step">STEP {i + 1}</div>
            <h3>{column.label}</h3>
            <RecordView column={column} age={c.record_age_seconds} />
            <Verdict column={column} />
            {column.run_id && (
              <div className="src">run {column.run_id.slice(0, 8)}</div>
            )}
            {column.note && <div className="src">{column.note}</div>}
          </div>
        ))}
      </div>

      <div className="callout">
        <b>This is a null result, and it is the useful one.</b> Across all{" "}
        {s.n_flipped} unanswerable queries in the arm, abstention moved{" "}
        {pct(s.without.abstained)} → {pct(s.with_age.abstained)} and silent
        failure {pct(s.without.silent)} → {pct(s.with_age.silent)} — McNemar
        exact p = {s.mcnemar_p.toFixed(2)}, on {s.discordant[0] + s.discordant[1]}{" "}
        discordant pairs where 6 are needed for significance. Mean confidence
        when wrong stayed at {s.with_age.confidence_wrong.toFixed(2)}. An age is
        not actionable without a policy: the agent is told the record is{" "}
        {c.record_age_seconds}s old and never told what age is acceptable.{" "}
        <b>Ship the age and the budget, and enforce the budget outside the model.</b>
      </div>
    </section>
  );
}
