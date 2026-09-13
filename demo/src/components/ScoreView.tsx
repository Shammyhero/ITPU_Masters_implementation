"use client";

import { DIMENSIONS, type ScoreResult } from "@/lib/api";

/* Displays what /api/score returned. Nothing here is computed from the records:
 * the composite, band, coverage and every dimension score are the API's. */

const percent = (share: number) => `${(100 * share).toFixed(1)}%`;

const bandTone = (label: string | null) =>
  label === "READY" ? "var(--good)"
    : label === "WATCH" ? "var(--warn)"
      : label ? "var(--bad)" : "var(--muted)";

const targetName = (target: string) => (target === "wrong" ? "total error" : target);

export default function ScoreView({
  result, stale, caveat,
}: { result: ScoreResult; stale: boolean; caveat?: string }) {
  return (
    <div className={`panel score-view${stale ? " is-stale" : ""}`} aria-live="polite">
      <div className="composite">
        <div>
          <div className="l">AIRS · {result.task} profile</div>
          <span className="score big" style={{ color: bandTone(result.band) }}>
            {result.airs === null ? "—" : result.airs.toFixed(1)}
          </span>
          <span className="mono muted"> /100</span>
        </div>
        <div>
          {result.band
            ? <span className={`band ${result.band.replace(" ", "-")}`}>{result.band}</span>
            : <span className="band NONE">NO SCORE</span>}
          <p className="band-note">
            {result.band_note ??
              "Not one dimension could be measured from these records. Add timestamps, " +
              "an upstream sample, or context blocks."}
          </p>
          <p className="src">
            {result.n_records.toLocaleString()} records · weights calibrated{" "}
            {result.calibration.calibrated_at} against {targetName(result.calibration.target)}
          </p>
        </div>
      </div>

      {result.unmeasured.length > 0 && (
        <div className="callout coverage">
          <b>This score rests on {percent(result.weight_covered)} of the calibrated weight.</b>{" "}
          {result.unmeasured
            .map((dim) => `${dim} (${percent(result.dimensions[dim].weight)} of the weight)`)
            .join(", ")}{" "}
          could not be measured, and {result.unmeasured.length === 1 ? "is" : "are"} left out
          of the score rather than assumed healthy. A pipeline can score well here purely
          because nobody looked.
        </div>
      )}

      <div className="dims">
        {DIMENSIONS.map((dim) => {
          const entry = result.dimensions[dim];
          const measured = entry.score !== null;
          const weightless = entry.weight === 0;
          return (
            <div
              key={dim}
              className={`dim${measured ? "" : " unmeasured"}${weightless ? " weightless" : ""}`}
            >
              <div className="dim-head">
                <span className="dim-name">{dim}</span>
                <span className="dim-weight mono">weight {percent(entry.weight)}</span>
                <span className="dim-score mono">
                  {measured ? entry.score!.toFixed(1) : "UNMEASURED"}
                </span>
              </div>
              <div className="track">
                {measured
                  ? <div className="fill" style={{ width: `${entry.score}%` }} />
                  : <div className="fill hatched" style={{ width: "100%" }} />}
              </div>
              <div className="dim-detail">
                {entry.detail}
                {weightless && ` — carries no weight in the ${result.task} profile`}
              </div>
            </div>
          );
        })}
      </div>

      <p className="src footnote">
        {result.validation &&
          `Calibration for ${result.task} held out ${result.validation.held_out_runs} runs and ` +
          `ranked them at Spearman ${result.validation.held_out_spearman.toFixed(3)}. `}
        The score ranks pipelines; it does not predict a failure rate.
        {caveat && ` ${caveat}`}
      </p>
    </div>
  );
}
