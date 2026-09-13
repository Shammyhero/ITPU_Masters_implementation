"use client";

import { useRef, useState, type DragEvent } from "react";

/* One JSONL input: paste, drop a file, or choose one. A dropped file is read in
 * the browser and sent only to `airs serve` on this machine. */

export type FieldError = { line: number | null; message: string } | null;

// The server refuses requests above this; say so before reading the file.
const MAX_FILE_BYTES = 64 * 1024 * 1024;

type Props = {
  id: "delivered" | "source";
  title: string;
  hint: string;
  value: string;
  origin: string | null;
  onChange: (text: string, origin: string | null) => void;
  error: FieldError;
  optional?: boolean;
};

export default function RecordsInput({
  id, title, hint, value, origin, onChange, error, optional,
}: Props) {
  const [dragging, setDragging] = useState(false);
  const [fileProblem, setFileProblem] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const lines = value ? value.split("\n").filter((line) => line.trim()).length : 0;

  const read = async (file: File) => {
    setFileProblem(null);
    if (file.size > MAX_FILE_BYTES) {
      setFileProblem(
        `${file.name} is ${(file.size / 1e6).toFixed(0)} MB and the limit is 64 MB — ` +
        "score a sample of the records, not the whole table.",
      );
      return;
    }
    onChange(await file.text(), file.name);
  };

  const drop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) void read(file);
  };

  return (
    <div
      className={`panel drop${dragging ? " dragging" : ""}${error ? " invalid" : ""}`}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
    >
      <div className="input-head">
        <h3>
          <label htmlFor={id}>{title}</label>
          {optional && <span className="optional">optional</span>}
        </h3>
        <div className="input-actions">
          <button type="button" className="tab" onClick={() => picker.current?.click()}>
            Choose file
          </button>
          {value && (
            <button type="button" className="tab" onClick={() => onChange("", null)}>
              Clear
            </button>
          )}
        </div>
      </div>
      <p className="hint">{hint}</p>
      <textarea
        id={id}
        value={value}
        rows={9}
        spellCheck={false}
        aria-invalid={Boolean(error)}
        placeholder={"Paste JSONL here, one record per line — or drop a .jsonl file"}
        onChange={(event) => onChange(event.target.value, null)}
      />
      <input
        ref={picker}
        type="file"
        hidden
        accept=".jsonl,.ndjson,.json,.txt,application/json"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void read(file);
          event.target.value = "";
        }}
      />
      <div className="src input-foot">
        {lines ? `${lines.toLocaleString()} ${lines === 1 ? "line" : "lines"}` : "empty"}
        {origin ? ` · from ${origin}` : ""}
      </div>
      {fileProblem && <div className="field-error">{fileProblem}</div>}
      {error && (
        <div className="field-error" role="alert">
          {error.line !== null && <b>Line {error.line}: </b>}
          {error.message}
        </div>
      )}
    </div>
  );
}
