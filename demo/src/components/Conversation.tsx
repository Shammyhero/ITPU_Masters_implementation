"use client";

/* The conversation: ask a question of a pipeline, and find out who was wrong.
 *
 * Every number here arrives from the API. The page computes nothing — not the
 * score, not the verdict, not the attribution — because a second implementation
 * of a scoring rule drifts from the first, and this one would drift from the
 * thesis.
 *
 * The stages are rendered as they arrive and never batched. The gate decides,
 * the agent answers, and only THEN the verifier resolves; the pause in between
 * is where a viewer forms an expectation that the verdict can break. Collapsing
 * that into one update would throw away the only thing the stream is for. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  type AskEvent,
  type GateBlock,
  type ModelOptions,
  type SessionInfo,
  type SourceSummary,
  type Tick,
  ask,
  getModels,
  getSources,
  openSession,
} from "@/lib/api";
import QuestionBuilder, {
  EMPTY_PLAN, type PlanDraft, describe, fieldsOf, toPlan,
} from "@/components/QuestionBuilder";
import RecordsInput, { type FieldError } from "@/components/RecordsInput";
import TickView from "@/components/TickView";

// The paste box as a source: the records travel in the request body, so the
// server still opens no file or connection because a request asked it to.
const INLINE = "inline";

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

const POLICIES: { id: string; label: string; note: string; policy: Record<string, unknown> | null }[] = [
  { id: "open", label: "No policy", note: "every question is answered", policy: null },
  { id: "fresh", label: "Freshness budget · 2 s", policy: { name: "fresh", max_record_age_seconds: 2 },
    note: "stale batches are re-read from the system of record before answering" },
  { id: "intact", label: "Records must arrive intact",
    policy: { name: "intact", min_dimension: { consistency: 95 } },
    note: "a batch whose fields changed in transit is refused — no model call, no cost" },
  { id: "ready", label: "AIRS ≥ 80", policy: { name: "ready", min_airs: 80 },
    note: "the composite floor, using the weights calibrated for this task" },
];

export default function Conversation() {
  const [sources, setSources] = useState<SourceSummary[] | null>(null);
  const [models, setModels] = useState<ModelOptions | null>(null);
  const [sourceId, setSourceId] = useState("demo-stale");
  const [answerer, setAnswerer] = useState("literal");
  const [policyId, setPolicyId] = useState("fresh");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [delivered, setDelivered] = useState("");
  const [upstream, setUpstream] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, FieldError>>({});
  const [draft, setDraft] = useState<PlanDraft>(EMPTY_PLAN);
  const [stripped, setStripped] = useState(false);
  const nextKey = useRef(0);

  useEffect(() => {
    getSources().then((body) => setSources(body.sources)).catch((exc: ApiError) =>
      setError(exc.message));
    getModels().then(setModels).catch(() => setModels(null));
  }, []);

  const source = sources?.find((entry) => entry.id === sourceId) ?? null;
  const policy = POLICIES.find((entry) => entry.id === policyId) ?? POLICIES[0];
  // Changing any of these makes a new session: the meter below counts one
  // configuration, and mixing two would make its exchange rate meaningless.
  useEffect(() => {
    setSession(null);
    setTurns([]);
  }, [sourceId, answerer, policyId, delivered, upstream, stripped]);

  const pasting = sourceId === INLINE;
  // A pasted sample rarely carries timestamps, and a freshness budget then
  // refuses every batch — correctly ("we did not look" is not "it is fine"),
  // but it is a poor first minute. Start pasted sessions with no policy; the
  // user can add one and will be told what it needs.
  useEffect(() => {
    if (sourceId === INLINE) setPolicyId("open");
  }, [sourceId]);
  const fields = useMemo(() => (pasting ? fieldsOf(delivered) : []), [delivered, pasting]);
  const plan = pasting ? toPlan(draft) : null;
  const ready = !pasting || (delivered.trim().length > 0 && plan !== null);

  const askOne = useCallback(async () => {
    setBusy(true);
    setError(null);
    const turn: Turn = { key: nextKey.current++, question: "", verifying: false };
    setTurns((previous) => [...previous, turn]);
    const update = (patch: Partial<Turn>) =>
      setTurns((previous) =>
        previous.map((entry) => (entry.key === turn.key ? { ...entry, ...patch } : entry)));

    try {
      let current = session;
      if (!current) {
        current = await openSession({
          source: sourceId, answerer, policy: policy.policy, refetch: "gate",
          strip_semantics: stripped,
          ...(pasting ? { records: delivered, upstream: upstream || null } : {}),
        });
        setSession(current);
        setFieldErrors({});
      }
      const question = pasting && plan
        ? { plan, question: describe(draft) }
        : {};
      await ask({ session_id: current.session_id, ...question }, (event: AskEvent) => {
        if (event.stage === "gate") {
          update({ gate: event.gate, question: event.question });
        } else if (event.stage === "refetch") {
          update({ refetch: event.refetch });
        } else if (event.stage === "answer") {
          // The answer stands alone for a moment: this is the claim, before
          // anything has checked it.
          update({ answer: event.answer, verifying: true });
        } else if (event.stage === "tick") {
          update({ tick: event.tick, verifying: false });
          const running = event.tick.running;
          setSession((previous) =>
            previous && running
              ? { ...previous, meter: running, ticks: previous.ticks + 1 }
              : previous);
        } else if (event.stage === "error") {
          update({ error: event.error.message, verifying: false });
        }
      });
    } catch (exc) {
      const message = exc instanceof ApiError ? exc.message : String(exc);
      // A refusal about the records belongs beside the box they were typed in,
      // with the line the server named.
      if (exc instanceof ApiError && (exc.input === "records" || exc.input === "upstream")) {
        setFieldErrors({ [exc.input]: { line: exc.line, message: exc.message } });
      }
      update({ error: message, verifying: false });
      setError(message);
    } finally {
      setBusy(false);
    }
    // Every value the request is built from belongs here. Without `delivered`
    // the callback kept the empty initial text, sent no records, and the server
    // rightly refused `inline` as a source nobody declared.
  }, [answerer, delivered, draft, pasting, plan, policy, session, sourceId, stripped,
      upstream]);

  const answerers = [
    { id: "literal", label: "No model", note: models?.literal.note ?? "the question executed over the delivered records, $0" },
    ...(models?.local.models ?? []).map((name) => ({
      id: name, label: name.replace("ollama/", ""), note: "local, free, nothing leaves this machine",
    })),
    ...(models?.providers ?? []).filter((provider) => provider.configured).map((provider) => ({
      id: `${provider.provider}/${provider.provider === "openai" ? "gpt-4o-mini"
            : provider.provider === "anthropic" ? "claude-haiku-4-5" : "gemini-2.5-flash"}`,
      label: provider.provider, note: provider.note,
    })),
  ];

  return (
    <section className="talk">
      <h1>Ask your pipeline a question</h1>
      <p className="lede">
        The answer is checked against the system of record as it was at the moment it was
        given. When it is wrong, this says whether your pipeline moved the answer, damaged
        the record, or the model simply got it wrong.
      </p>

      <div className="setup panel">
        <label className="field">
          <span className="field-label">Source</span>
          <select value={sourceId} onChange={(event) => setSourceId(event.target.value)}
                  disabled={!sources}>
            {(sources ?? []).map((entry) => (
              <option key={entry.id} value={entry.id}>{entry.id}</option>
            ))}
            <option value={INLINE}>paste my own records</option>
          </select>
        </label>
        <label className="field">
          <span className="field-label">Answered by</span>
          <select value={answerer} onChange={(event) => setAnswerer(event.target.value)}>
            {answerers.map((entry) => (
              <option key={entry.id} value={entry.id}>{entry.label}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Policy</span>
          <select value={policyId} onChange={(event) => setPolicyId(event.target.value)}>
            {POLICIES.map((entry) => (
              <option key={entry.id} value={entry.id}>{entry.label}</option>
            ))}
          </select>
        </label>
        <label className="field narrow check">
          <span className="field-label">Semantic layer</span>
          <span className="checkline">
            <input type="checkbox" checked={stripped}
                   onChange={(event) => setStripped(event.target.checked)} />
            <span>strip it</span>
          </span>
        </label>
        <button className="cta" onClick={askOne} disabled={busy || !sources || !ready}>
          {busy ? "asking…" : turns.length ? "Ask another" : "Ask a question"}
        </button>
      </div>

      {pasting && (
        <div className="paste panel">
          <RecordsInput
            id="delivered" title="Records as your pipeline delivers them"
            hint="One JSON object per line. Each needs an id and a payload."
            value={delivered} origin={null}
            onChange={(text) => setDelivered(text)}
            error={fieldErrors.records ?? null}
          />
          <RecordsInput
            id="source" title="The same records from your system of record"
            hint="Optional. Without it an answer cannot be verified, and the session says so."
            value={upstream} origin={null}
            onChange={(text) => setUpstream(text)}
            error={fieldErrors.upstream ?? null}
            optional
          />
          {fields.length > 0 && (
            <>
              <QuestionBuilder fields={fields} draft={draft} onChange={setDraft} />
              <p className="hint">
                Your question: <b>{describe(draft)}</b>{" "}
                {plan === null && <span className="warn-text">— choose a field to finish it.</span>}
              </p>
            </>
          )}
          {delivered.trim() && fields.length === 0 && (
            <p className="hint warn-text">
              No fields found yet. Each line is one JSON object with a payload.
            </p>
          )}
        </div>
      )}

      <div className="setup-notes">
        {stripped && (
          <p className="hint warn-text">
            This runs the study&rsquo;s own semantic-stripping injector over the records
            <span> </span><b>this console</b> reads — the context block is removed and field
            names become opaque tokens. Nothing about your pipeline is changed. Dropping
            the descriptions alone would move nothing, because <b>price</b> and
            <span> </span><b>stock</b> describe themselves; whether it changes the
            answer on your data is an observation, not a promise.
          </p>
        )}
        {pasting && policy.policy?.max_record_age_seconds !== undefined &&
          !delivered.includes("event_timestamp") && (
          <p className="hint warn-text">
            This policy checks how old the records are, and pasted records carry no
            <span> </span><b>event_timestamp</b> — so the budget cannot be shown to hold and
            every batch is refused. Add timestamps, or choose <b>No policy</b>.
          </p>
        )}
        {pasting && (
          <p className="hint">
            Your records are sent to <b>airs serve</b> on this machine and held in memory
            for this session only. Nothing is written, and a pasted source has no history,
            so pipeline lag shows up as values changed in transit rather than as the answer
            key moving.
          </p>
        )}
        {source && (
          <p className="hint">
            <b>{source.id}</b> — {source.description}{" "}
            {!source.verifiable && (
              <span className="warn-text">No system of record is declared, so answers
              cannot be verified.</span>
            )}
          </p>
        )}
        <p className="hint">{policy.note}</p>
        {source && source.semantic.state !== "reviewed" && (
          <p className="hint warn-text">
            Semantic readiness is UNMEASURED: {source.semantic.reason}
          </p>
        )}
        {answerers.find((entry) => entry.id === answerer)?.note && (
          <p className="hint">{answerers.find((entry) => entry.id === answerer)?.note}</p>
        )}
      </div>

      {error && <div className="callout error"><b>Refused.</b> {error}</div>}

      {session && <Meter session={session} />}

      <div className="turns">
        {turns.map((turn) => (
          <TickView key={turn.key} turn={turn} />
        ))}
      </div>

      {!turns.length && (
        <p className="src">
          Nothing is written anywhere you did not choose: questions run on this machine,
          and the session is kept in ~/.airs/sessions, never in the study&rsquo;s results.
        </p>
      )}
    </section>
  );
}

function Meter({ session }: { session: SessionInfo }) {
  const meter = session.meter;
  if (!meter.asked) return null;
  const cells: [string, string, string][] = [
    ["asked", String(meter.asked), "questions this session"],
    ["answered", String(meter.answered), "reached the answerer"],
    ["refused", String(meter.refused), "stopped before any model call"],
    ["re-read", String(meter.refetched), "upstream read again first"],
    ["silent failures", String(meter.silent_failures), "confident, committed, wrong"],
    ["spent", `$${meter.usd.toFixed(4)}`, session.budget.free ? "free by construction" :
      `cap $${session.budget.session_cap_usd.toFixed(2)}`],
  ];
  return (
    <div className="meter panel">
      {cells.map(([label, value, note]) => (
        <div className="meter-cell" key={label}>
          <div className="meter-v">{value}</div>
          <div className="meter-l">{label}</div>
          <div className="meter-n">{note}</div>
        </div>
      ))}
      {meter.prevented > 0 || meter.forfeited > 0 ? (
        <div className="meter-cell wide">
          <div className="meter-v">
            {meter.exchange_rate === null ? "—" : meter.exchange_rate.toFixed(1)}
          </div>
          <div className="meter-l">correct answers forfeited per silent failure prevented</div>
          <div className="meter-n">
            {meter.prevented} prevented · {meter.forfeited} forfeited. The study measured
            7–21 across its own runs.
          </div>
        </div>
      ) : null}
    </div>
  );
}
