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
