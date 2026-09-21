/* Client for the API served by `airs serve`.
 *
 * The page computes no score. Every number it shows comes back from /api/score,
 * which runs the same `airsbench.probe` code as `airs probe`. A TypeScript copy of
 * the scoring rules drifted from the Python once already, and nothing would catch
 * it drifting again. The types below describe what the API returns; they are not a
 * second implementation of it. */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export type Dimension = "freshness" | "latency" | "consistency" | "semantic";
export const DIMENSIONS: Dimension[] = ["freshness", "latency", "consistency", "semantic"];

export type DimensionScore = {
  score: number | null;
  detail: string;
  weight: number;
  mean_age_seconds?: number;
};

export type Validation = { held_out_runs: number; held_out_spearman: number };

export type Meta = {
  version: string;
  dimensions: Dimension[];
  bands: { min: number; label: string; note: string }[];
  calibration: { calibrated_at: string; target: string; target_note: string; caveat: string };
  profiles: Record<string, Record<Dimension, number>>;
  validation: Record<string, Validation>;
  frontend_built: boolean;
  preloaded: boolean;
};

export type Sample = {
  id: string;
  label: string;
  description: string;
  task: string;
  delivered: string;
  source: string | null;
};

export type Preloaded = {
  label: string;
  task: string;
  delivered: string;
  source: string | null;
  records_path: string;
  source_path: string | null;
};

export type Samples = {
  samples: Sample[];
  policies: { id: string; policy: Record<string, unknown>; description: string; note: string }[];
  preloaded: Preloaded | null;
};

export type ScoreResult = {
  task: string;
  n_records: number;
  dimensions: Record<Dimension, DimensionScore>;
  airs: number | null;
  weight_covered: number;
  unmeasured: Dimension[];
  band: string | null;
  band_note: string | null;
  calibration: { calibrated_at: string; target: string };
  validation: Validation | null;
};

/** A refusal from the API — which input, which line, and how to fix it. */
export class ApiError extends Error {
  status: number;
  input: string | null;
  line: number | null;

  constructor(status: number, input: string | null, line: number | null, message: string) {
    super(message);
    this.status = status;
    this.input = input;
    this.line = line;
  }
}

const UNREACHABLE =
  "Cannot reach the AIRS server. This page is served by `airs serve` — start it and reload.";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, null, null, UNREACHABLE);
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON: reported below by status alone.
  }
  if (!response.ok) {
    const error = (body as { error?: { input?: string; line?: number; message?: string } })?.error;
    throw new ApiError(
      response.status,
      error?.input ?? null,
      error?.line ?? null,
      error?.message ?? `the server answered ${response.status}`,
    );
  }
  return body as T;
}

export const getMeta = () => request<Meta>("/api/meta");
export const getSamples = () => request<Samples>("/api/samples");

export const postScore = (body: { task: string; delivered: string; source: string | null }) =>
  request<ScoreResult>("/api/score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

/* ---- the Analyst: sources, models, sessions, and one question at a time ----
 *
 * Same rule as above: the page renders what the API returns and computes
 * nothing. The Tick type below is the shape `analyst/session.py::build_tick`
 * produces — a description, not a second implementation. */

export type SemanticState = {
  state: "reviewed" | "unreviewed" | "stale" | "absent" | "invalid";
  manifest_approved: boolean;
  manifest_id: string | null;
  manifest_file: string | null;
  reason: string;
  field_coverage: { described: string[]; undescribed: string[] };
};

export type SourceSummary = {
  id: string;
  kind: string;
  description: string;
  upstream: string | null;
  supports_as_of: boolean;
  verifiable: boolean;
  semantic: SemanticState;
};

export type ModelOptions = {
  literal: { note: string };
  local: { reachable: boolean; models: string[]; note: string };
  providers: { provider: string; configured: boolean; env: string; note: string }[];
  priced: string[];
};

export type Meter = {
  asked: number; answered: number; refused: number; refetched: number;
  correct: number; silent_failures: number; prevented: number; forfeited: number;
  exchange_rate: number | null; usd: number;
};

export type SessionInfo = {
  session_id: string;
  source: string;
  answerer: string;
  policy: Record<string, unknown>;
  policy_description: string;
  refetch: "off" | "gate" | "agent";
  strip_semantics: boolean;
  task: string;
  budget: { session_cap_usd: number; day_cap_usd: number; session_spent_usd: number;
            day_spent_usd: number; calls: number; free: boolean };
  meter: Meter;
  ticks: number;
  arm: "live";
  seed_block: [number, number];
};

export type Violation = { rule: string; observed: number | null; threshold: number; detail: string };

export type GateBlock = {
  verdict: "admit" | "refetch" | "refuse";
  admitted: boolean;
  reason: string;
  violations: Violation[];
  airs: number | null;
  weight_covered: number;
  dimensions: Record<Dimension, DimensionScore>;
  n_records: number;
  shadowed: boolean;
  delegated?: boolean;
  would_have: "correct" | "silent_failure" | "wrong" | "abstained" | null;
};

export type ChangedField = {
  id: string; field: string | null; change: string;
  source?: unknown; delivered?: unknown; delivered_as?: string;
};

export type Attribution =
  | "correct" | "answer_key_moved" | "both" | "corrupted_in_transit" | "agent_impairment";

/* The AIRS block inside a Tick. `probe.score()` adds the calibration stamp and
 * the held-out validation; the router's own block (`analyst/loop.py`) and the
 * baked replay feed carry the scores without them, because they are describing
 * one question rather than answering `airs probe`. Optional here, so the
 * renderer has to handle their absence instead of assuming it. */
export type TickAirs = Omit<ScoreResult, "calibration" | "validation"> &
  Partial<Pick<ScoreResult, "calibration" | "validation">>;

/* A Tick comes from two places, and the nulls below say which: a live answer
 * carries a session, a gate verdict and the running meter; a Tick replayed from
 * the corpus carries a run_id instead, because those runs had no gate in the
 * path and no session around them. */
export type Tick = {
  t: number | null;
  mode: string;
  session_id: string | null;
  source: { pair: string; kind: string; delivered: string; upstream: string | null;
            supports_as_of: boolean; condition: string | null; semantic: SemanticState | null };
  question: { text: string; plan: Record<string, unknown>; describe: string;
              key: string | null; query: string | null };
  answerer: string;
  airs: TickAirs;
  records: {
    ids: (string | null)[];
    delivered: Record<string, unknown>[];
    served: Record<string, Record<string, unknown>> | null;
    upstream: Record<string, Record<string, unknown>> | null;
    simulated_time: number | null;
    served_as_of: number | null;
    lag_seconds: number | null;
    t0_t1_gap_seconds: number;
  };
  decision: {
    answer: string; plan: Record<string, unknown> | null; value: unknown;
    confidence: number; abstained: boolean; parse_failed: boolean; refused?: boolean;
    verifiable: boolean; reason: string | null;
    answer_upstream?: { value: unknown; computable: boolean; reason: string | null };
    answer_served?: { value: unknown; computable: boolean; reason: string | null };
    correct: boolean | null; silent_failure: boolean | null; flipped?: boolean | null;
    attribution: Attribution | null; changed_fields?: ChangedField[];
    plan_matches_question?: boolean | null; agent_plan_agrees?: boolean | null;
  };
  gate: GateBlock | null;
  refetch: { attempted: boolean; initiated_by: "gate" | "agent" | null; n_records: number;
             verdict_after: string | null; airs_after: number | null; reason: string | null };
  cost: { model: string; input_tokens: number; output_tokens: number; usd: number;
          provider: string; hosted: boolean };
  running: Meter | null;
  notes: string[];
  provenance: { arm: string; seed_block: number[] | null; seed: number | null;
                run_id?: string; session_id: string | null };
};

/** What `/api/ask` streams, in the order the work actually happened. */
export type AskEvent =
  | { stage: "gate"; verdict: string; question: string; gate: GateBlock; source: string;
      n_records: number }
  | { stage: "refetch"; refetch: Tick["refetch"] }
  | { stage: "answer"; answer: { value: unknown; text: string; confidence: number;
        abstained: boolean; parse_failed: boolean; plan: Record<string, unknown> | null };
      cost: Tick["cost"] }
  | { stage: "tick"; tick: Tick }
  | { stage: "error"; error: { input: string | null; line: number | null; message: string } };

export const getSources = () => request<{ sources: SourceSummary[] }>("/api/sources");
export const getModels = () => request<ModelOptions>("/api/models");
export const getSession = (id: string) => request<SessionInfo>(`/api/session/${id}`);

export const testSource = (id: string) =>
  request<SourceSummary & { schema: { source: string; id_field: string; row_count: number | null;
                                      fields: { name: string; type: string; examples: unknown[] }[] };
                            sample: Record<string, unknown>[] }>(
    `/api/sources/${encodeURIComponent(id)}/test`, { method: "POST" });

export const openSession = (body: {
  source: string; answerer: string; policy?: Record<string, unknown> | null;
  refetch?: string; task?: string; max_cost?: number | null;
  records?: string | null; upstream?: string | null; strip_semantics?: boolean;
}) =>
  request<SessionInfo>("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

/** Ask one question, calling `onEvent` as each stage arrives.
 *
 * Server-Sent Events over fetch rather than EventSource, because the question
 * is a POST. The stages are the point: the gate's verdict, then the answer,
 * then — after a real pause, while the verifier works — the Tick. Rendering
 * them as they arrive is what makes the verification legible; batching them
 * would throw away the only thing this stream is for. */
export async function ask(
  body: { session_id: string; question?: string; plan?: Record<string, unknown>; n?: number },
  onEvent: (event: AskEvent) => void,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, null, null, UNREACHABLE);
  }
  if (!response.ok || !response.body) {
    let payload: { error?: { input?: string; line?: number; message?: string } } | null = null;
    try {
      payload = await response.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, payload?.error?.input ?? null,
                       payload?.error?.line ?? null,
                       payload?.error?.message ?? `the server answered ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line; anything after the last one is
    // an incomplete frame and stays in the buffer.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const lines = frame.split("\n");
      // The event NAME carries the stage. `event: tick` sends the Tick itself as
      // data — one documented shape, with no stage field of its own — so the
      // name is the only way to know what arrived.
      const name = lines.find((line) => line.startsWith("event: "))?.slice(7).trim();
      const data = lines
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (!name || !data) continue;
      const payload = JSON.parse(data);
      onEvent(name === "tick" ? { stage: "tick", tick: payload as Tick }
                              : ({ ...payload, stage: name } as AskEvent));
    }
  }
}
