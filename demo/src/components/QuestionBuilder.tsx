"use client";

/* Build a checkable question from the fields the pasted records actually have.
 *
 * A pasted source has no question of its own, and the server will not invent
 * one: an answer is verified against the QUESTION's plan, never the answerer's
 * (A3). So the question is assembled here from the six plan types the verifier
 * can execute, with the fields taken from the records themselves — no free
 * text, so every question a visitor can ask is verifiable by construction.
 *
 * The field list is read from the pasted text purely to populate these menus.
 * Nothing is scored here; the server validates the records and refuses them in
 * its own error shape if they are malformed. */

import { useMemo } from "react";

export type PlanDraft = {
  type: "min_by" | "max_by" | "top_k" | "count_where" | "sum_where" | "lookup";
  measure: string;
  where_field: string;
  where_op: ">" | ">=" | "<" | "<=" | "==" | "!=";
  where_value: string;
  filter: boolean;
  k: number;
  id: string;
};

export const EMPTY_PLAN: PlanDraft = {
  type: "min_by", measure: "", where_field: "", where_op: ">", where_value: "0",
  filter: true, k: 3, id: "",
};

const TYPES: { id: PlanDraft["type"]; label: string; needsMeasure: boolean }[] = [
  { id: "min_by", label: "the cheapest / smallest by", needsMeasure: true },
  { id: "max_by", label: "the largest by", needsMeasure: true },
  { id: "top_k", label: "the lowest few by", needsMeasure: true },
  { id: "sum_where", label: "the total of", needsMeasure: true },
  { id: "count_where", label: "how many records", needsMeasure: false },
  { id: "lookup", label: "one field of one record", needsMeasure: true },
];

/** Field names as they appear in the pasted records — for the menus only. */
export function fieldsOf(text: string): string[] {
  const names = new Set<string>();
  for (const line of text.split("\n").slice(0, 200)) {
    if (!line.trim()) continue;
    try {
      const entry = JSON.parse(line);
      const payload = entry && typeof entry === "object" && "payload" in entry
        ? (entry as { payload: unknown }).payload
        : entry;
      if (payload && typeof payload === "object") {
        for (const key of Object.keys(payload as Record<string, unknown>)) names.add(key);
      }
    } catch {
      // A malformed line is the server's to report, with its line number.
    }
  }
  return [...names];
}

/** The plan as the API takes it, or null while it is still incomplete. */
export function toPlan(draft: PlanDraft): Record<string, unknown> | null {
  const where = draft.filter && draft.where_field
    ? [{ field: draft.where_field, op: draft.where_op,
         value: numberish(draft.where_value) }]
    : [];
  if (draft.type === "count_where") return { type: "count_where", where };
  if (!draft.measure) return null;
  if (draft.type === "lookup") {
    return draft.id ? { type: "lookup", id: draft.id, measure: draft.measure } : null;
  }
  if (draft.type === "top_k") {
    return { type: "top_k", measure: draft.measure, k: draft.k, order: "asc", where };
  }
  return { type: draft.type, measure: draft.measure, where };
}

function numberish(value: string): string | number | boolean {
  const trimmed = value.trim();
  if (trimmed === "true" || trimmed === "false") return trimmed === "true";
  const asNumber = Number(trimmed);
  return trimmed !== "" && Number.isFinite(asNumber) ? asNumber : trimmed;
}

export function describe(draft: PlanDraft): string {
  const type = TYPES.find((entry) => entry.id === draft.type);
  const filter = draft.filter && draft.where_field
    ? ` where ${draft.where_field} ${draft.where_op} ${draft.where_value}`
    : "";
  if (draft.type === "count_where") return `How many records${filter || " are there"}?`;
  if (draft.type === "lookup") return `What is ${draft.measure} of ${draft.id || "…"}?`;
  if (draft.type === "top_k") return `Which ${draft.k} have the lowest ${draft.measure}${filter}?`;
  return `Which record has ${type?.id === "max_by" ? "the highest" : "the lowest"} ` +
    `${draft.measure || "…"}${filter}?`;
}

export default function QuestionBuilder({
  fields, draft, onChange,
}: {
  fields: string[];
  draft: PlanDraft;
  onChange: (draft: PlanDraft) => void;
}) {
  const type = useMemo(() => TYPES.find((entry) => entry.id === draft.type), [draft.type]);
  const set = (patch: Partial<PlanDraft>) => onChange({ ...draft, ...patch });

  return (
    <div className="builder">
      <label className="field">
        <span className="field-label">Ask for</span>
        <select value={draft.type}
                onChange={(event) => set({ type: event.target.value as PlanDraft["type"] })}>
          {TYPES.map((entry) => (
            <option key={entry.id} value={entry.id}>{entry.label}</option>
          ))}
        </select>
      </label>

      {type?.needsMeasure && (
        <label className="field">
          <span className="field-label">Field</span>
          <select value={draft.measure} onChange={(event) => set({ measure: event.target.value })}>
            <option value="">choose…</option>
            {fields.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      )}

      {draft.type === "top_k" && (
        <label className="field narrow">
          <span className="field-label">How many</span>
          <input type="number" min={1} max={20} value={draft.k}
                 onChange={(event) => set({ k: Number(event.target.value) || 1 })} />
        </label>
      )}

      {draft.type === "lookup" && (
        <label className="field">
          <span className="field-label">Record id</span>
          <input value={draft.id} placeholder="an id from your records"
                 onChange={(event) => set({ id: event.target.value })} />
        </label>
      )}

      {draft.type !== "lookup" && (
        <>
          <label className="field narrow check">
            <span className="field-label">Only some</span>
            <span className="checkline">
              <input type="checkbox" checked={draft.filter}
                     onChange={(event) => set({ filter: event.target.checked })} />
              <span>filter</span>
            </span>
          </label>
          {draft.filter && (
            <>
              <label className="field">
                <span className="field-label">Where</span>
                <select value={draft.where_field}
                        onChange={(event) => set({ where_field: event.target.value })}>
                  <option value="">choose…</option>
                  {fields.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
              <label className="field narrow">
                <span className="field-label">is</span>
                <select value={draft.where_op}
                        onChange={(event) =>
                          set({ where_op: event.target.value as PlanDraft["where_op"] })}>
                  {[">", ">=", "<", "<=", "==", "!="].map((op) => (
                    <option key={op} value={op}>{op}</option>
                  ))}
                </select>
              </label>
              <label className="field narrow">
                <span className="field-label">value</span>
                <input value={draft.where_value}
                       onChange={(event) => set({ where_value: event.target.value })} />
              </label>
            </>
          )}
        </>
      )}
    </div>
  );
}
