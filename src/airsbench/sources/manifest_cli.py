"""`airs manifest` — propose, review and show what a source's fields mean.

    airs manifest propose exports > manifest.yaml
    airs manifest propose exports --model ollama/llama3.1:8b --out manifest.yaml
    airs manifest review manifest.yaml --source exports
    airs manifest show exports

Semantic readiness is UNMEASURED for a source until a person has reviewed its
manifest (`airsbench.sources.manifest`). `propose` drafts one — offline from field
names and types, or with a local model — and never marks it reviewed. `review`
walks it field by field in the terminal and stamps it with the fingerprint of the
source's schema as it is now. Point `manifest:` at the file in `sources.yaml`.

Exit status: 0 on success, 1 when a review is abandoned, 2 when a source or a
manifest cannot be read.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Callable

from agentic_faults import Record

from ..airs.calculator import semantic_completeness, semantic_score
from .base import SourceError, SourcePair, SourceSchema
from .manifest import (
    ROLES,
    Manifest,
    ManifestError,
    check_against,
    default_questions,
    dump_manifest,
    load_manifest,
    propose,
    refine_with_model,
    semantic_layer,
    stamp,
)

OLLAMA_PREFIX = "ollama/"
EDITABLE = ("role", "unit", "definition", "relationship", "tz")


def _pairs(path: Path | None) -> dict[str, SourcePair]:
    from .config import load_sources

    return load_sources(path)


def _pair(path: Path | None, pair_id: str) -> SourcePair:
    pairs = _pairs(path)
    if pair_id not in pairs:
        raise SourceError(f"no source {pair_id!r}; available: {', '.join(pairs)}")
    return pairs[pair_id]


def rendered_score(manifest: Manifest) -> float:
    """The semantic score a record carrying only this manifest's context would get."""
    return semantic_score(semantic_completeness(
        Record(payload={}, context=manifest.render_context())))


def _model_client(model: str):
    if not model.startswith(OLLAMA_PREFIX) or len(model) == len(OLLAMA_PREFIX):
        raise SourceError(f"{model!r} is not available: proposing with a hosted model needs "
                          f"per-session spend caps first. Use ollama/<name>, or no --model")
    try:
        from ..agents.llm import LLMClient
        return LLMClient(model, temperature=0.0)
    except ImportError:
        raise SourceError('proposing with a model needs the agents extra: '
                          'pip install "airs-bench[agents]"') from None


def cmd_propose(args) -> int:
    pair = _pair(args.sources, args.pair)
    schema = pair.delivered.describe()
    manifest = propose(schema, pair.id)
    if args.model:
        client = _model_client(args.model)
        try:
            manifest = refine_with_model(manifest, schema, client, args.model)
        except Exception as exc:  # transport — Ollama not running
            raise SourceError(f"{args.model} could not be reached ({type(exc).__name__}: "
                              f"{exc}); is Ollama running? start it with `ollama serve`") from None
    text = dump_manifest(manifest)
    if args.out is None:
        sys.stdout.write(text)
    else:
        if args.out.exists() and not args.force:
            raise SourceError(f"{args.out} exists; pass --force to replace it, or review it "
                              f"with `airs manifest review {args.out} --source {pair.id}`")
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} — a proposal, not yet reviewed. Next: "
              f"airs manifest review {args.out} --source {pair.id}", file=sys.stderr)
    return 0


def _show_field(schema: SourceSchema, manifest: Manifest, name: str,
                out: Callable[[str], None]) -> None:
    info = next((f for f in schema.fields if f.name == name), None)
    spec = manifest.field(name)
    kind = info.type if info else "NOT IN SOURCE"
    examples = ", ".join(json.dumps(v, ensure_ascii=False, default=str)[:24]
                         for v in (info.examples if info else ()))
    out(f"\n  {name}  ({kind}){'  e.g. ' + examples if examples else ''}")
    if spec is None:
        out("    not described")
        return
    out("    " + " · ".join(f"{key} {getattr(spec, key) or '—'}" for key in EDITABLE))


def review(manifest: Manifest, schema: SourceSchema, pair_id: str,
           ask: Callable[[str], str] = input,
           out: Callable[[str], None] = print) -> Manifest | None:
    """Walk a manifest field by field; return it stamped, or None if abandoned."""
    out(f"Reviewing the manifest for {pair_id} — {len(schema.fields)} fields in the source.")
    out("  For each field: press enter to accept, or type key=value "
        f"({', '.join(EDITABLE)}), clear=<key>, drop, or q to quit without saving.")
    fields = {f.name: f for f in manifest.fields}
    names = list(dict.fromkeys([schema.id_field] + [f.name for f in schema.fields]
                               + list(fields)))
    for name in names:
        current = replace(manifest, fields=tuple(fields.values()))
        _show_field(schema, current, name, out)
        while True:
            line = ask("  > ").strip()
            if line == "":
                break
            if line.lower() == "q":
                out("Review abandoned; nothing written.")
                return None
            if line == "drop":
                fields.pop(name, None)
                out(f"    {name} dropped from the manifest")
                break
            key, sep, value = line.partition("=")
            key, value = key.strip(), value.strip()
            spec = fields.get(name)
            if key == "clear" and spec is not None and value in EDITABLE and value != "role":
                fields[name] = replace(spec, **{value: None})
            elif sep and key == "role" and value in ROLES:
                fields[name] = replace(spec, role=value) if spec else _new_field(name, value)
            elif sep and key in EDITABLE and key != "role" and value:
                if spec is None:
                    out("    set role= first — the field is not described yet")
                    continue
                fields[name] = replace(spec, **{key: value})
            else:
                out(f"    not understood: {line!r}. Roles: {', '.join(ROLES)}")
                continue
            _show_field(schema, replace(manifest, fields=tuple(fields.values())), name, out)

    entity = ask(f"\n  entity — what one record is [{manifest.entity or 'none'}]: ").strip()
    manifest = replace(manifest, entity=entity or manifest.entity,
                       fields=tuple(fields.values()),
                       checkable_questions=tuple(default_questions(tuple(fields.values()))))
    try:
        stamped = stamp(manifest, schema)
    except ManifestError as exc:
        out(f"\n  {exc}")
        return None
    undescribed = [name for name in dict.fromkeys([schema.id_field]
                                                  + [f.name for f in schema.fields])
                   if not (stamped.field(name) and stamped.field(name).definition)]
    out(f"\n  Semantic score this manifest renders: {rendered_score(stamped):.0f} "
        f"(entity, units, descriptions, relationships — each present or not)")
    if undescribed:
        out(f"  No definition for: {', '.join(undescribed)} — reported as field coverage")
    if ask("  Mark reviewed and write? [y/N] ").strip().lower() not in ("y", "yes"):
        out("Review abandoned; nothing written.")
        return None
    return stamped


def _new_field(name: str, role: str):
    from .manifest import FieldSpec

    return FieldSpec(name, role)


def cmd_review(args, ask: Callable[[str], str] = input) -> int:
    pair = _pair(args.sources, args.source)
    schema = pair.delivered.describe()
    manifest = load_manifest(args.file)
    if args.approve_as_is:
        problems = check_against(manifest, schema)
        if problems:
            raise ManifestError(f"{args.file}: {'; '.join(problems)}")
        stamped = stamp(manifest, schema)
        print(f"approved as written, without a field-by-field review: {args.file}",
              file=sys.stderr)
    else:
        stamped = review(manifest, schema, pair.id, ask=ask)
        if stamped is None:
            return 1
    args.file.write_text(dump_manifest(stamped), encoding="utf-8")
    print(f"wrote {args.file}: reviewed {stamped.reviewed_at}, fingerprint {stamped.fingerprint}")
    if pair.manifest is None or Path(pair.manifest).resolve() != args.file.resolve():
        print(f"  {pair.id} does not use this file yet: set manifest: {args.file} in "
              f"sources.yaml")
    return 0


def cmd_show(args) -> int:
    pair = _pair(args.sources, args.pair)
    layer = semantic_layer(pair)
    report = layer.to_dict()
    if layer.manifest is not None:
        report["rendered_context"] = layer.manifest.render_context()
        report["rendered_semantic_score"] = rendered_score(layer.manifest)
        report["renders_onto_records"] = layer.renders
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    print(f"{pair.id} — semantic layer {layer.state.upper()}")
    print(f"  {layer.reason}")
    if layer.manifest is None:
        return 0
    print(f"  manifest {report['manifest_path']} · id {report['manifest_id']}"
          f" · proposed by {layer.manifest.proposed_by or 'hand'}")
    coverage = layer.coverage
    print(f"  described: {', '.join(coverage['described']) or 'none'}")
    if coverage["undescribed"]:
        print(f"  no definition: {', '.join(coverage['undescribed'])}")
    source = ("rendered onto records that arrive without context" if layer.renders
              else "rendered by the pipeline itself; the manifest describes it")
    print(f"  context {source} · scores {report['rendered_semantic_score']:.0f} when present")
    return 0


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input) -> int:
    parser = argparse.ArgumentParser(prog="airs manifest", description=__doc__.splitlines()[0])
    parser.add_argument("--sources", type=Path, default=None,
                        help="a sources.yaml declaring your data sources")
    actions = parser.add_subparsers(dest="action", required=True)
    p = actions.add_parser("propose", help="draft a manifest for a source (never reviewed)")
    p.add_argument("pair")
    p.add_argument("--model", default=None, help="refine with a local model: ollama/<name>")
    p.add_argument("--out", type=Path, default=None, help="write here instead of stdout")
    p.add_argument("--force", action="store_true", help="replace an existing --out file")
    r = actions.add_parser("review", help="review a manifest field by field and stamp it")
    r.add_argument("file", type=Path)
    r.add_argument("--source", required=True, help="the source the manifest describes")
    r.add_argument("--approve-as-is", action="store_true",
                   help="stamp a hand-written manifest without the walk-through")
    s = actions.add_parser("show", help="the semantic state of a source, and why")
    s.add_argument("pair")
    s.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "propose":
            return cmd_propose(args)
        if args.action == "review":
            return cmd_review(args, ask=ask)
        return cmd_show(args)
    except (SourceError, ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nReview abandoned; nothing written.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
