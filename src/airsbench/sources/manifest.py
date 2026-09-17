"""The semantic manifest: what a source's fields mean, reviewed by a person.

AIRS's semantic dimension scores the context an agent reads beside the values —
entity, units, descriptions, relationships. A generic source carries none of it,
and the tool cannot invent it: `price` could be list or net, cents or dollars.
So the Analyst measures semantics in two states (brief correction 2):

    no reviewed manifest   semantic is UNMEASURED — the tool does not know what the
                           fields mean, and an unknown field is not a healthy one
    reviewed manifest      its context is rendered into the delivered records, and
                           `airsbench.probe`'s own rule scores it: the four context
                           categories present, and 0 where records carry none

The score is the calibrated one, unchanged: it counts the four categories, not the
fields described (author decision, 17 Sep). Which fields a manifest leaves without a
definition is reported beside it as *field coverage* — an observation, not a score,
because the RQ4 weights were calibrated on the category rule.

A manifest counts as reviewed only while it carries a review stamp whose schema
fingerprint matches the source as it is now. A pipeline that renames or retypes a
column makes its manifest stale, and semantic returns to UNMEASURED until someone
looks again — which is the drift a manifest exists to catch.

    source: exports
    entity: retail_product
    fields:
      product_id: {role: id, definition: Catalog identifier}
      price:      {role: measure, unit: USD, definition: Listed price, excl. tax}
      stock:      {role: measure, unit: units, definition: Units on hand}
      brand:      {role: label, definition: Maker, relationship: groups products by maker}
    checkable_questions: [min_by, max_by, top_k, count_where, sum_where, lookup]
    reviewed: {at: '2026-09-17T09:12:00Z', fields_fingerprint: 'sha256:…'}

Where the context comes from depends on the source. A pipeline that renders its
own semantic layer — the demo, built by the runner's record builders — is
*described* by its manifest, and the manifest is never re-rendered on top of it:
doing so would undo semantic stripping. A source whose records arrive bare (files)
gets the reviewed manifest rendered in, and only onto records without context of
their own.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from agentic_faults import Record

from .base import SourceError, SourcePair, SourceSchema

ROLES = ("id", "measure", "label", "updated_at")
TOP_KEYS = {"source", "entity", "fields", "checkable_questions", "proposed_by", "reviewed"}
FIELD_KEYS = {"role", "unit", "definition", "relationship", "tz"}
REVIEW_KEYS = {"at", "fields_fingerprint"}
NUMERIC = {"integer", "number"}
_TIME_NAME = re.compile(r"(updated|modified|timestamp|(^|_)(at|ts|time|date)$)", re.I)

STATES = ("reviewed", "unreviewed", "stale", "absent", "invalid")


class ManifestError(SourceError):
    """A manifest that cannot be read or does not validate — says where and why."""


@dataclass(frozen=True)
class FieldSpec:
    name: str
    role: str
    unit: str | None = None
    definition: str | None = None
    relationship: str | None = None
    tz: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in (("role", self.role), ("unit", self.unit),
                                  ("definition", self.definition),
                                  ("relationship", self.relationship), ("tz", self.tz))
                if v is not None}


@dataclass(frozen=True)
class Manifest:
    source: str
    entity: str | None
    fields: tuple[FieldSpec, ...]
    checkable_questions: tuple[str, ...]
    proposed_by: str | None = None
    reviewed_at: str | None = None
    fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"source": self.source}
        if self.entity is not None:
            out["entity"] = self.entity
        out["fields"] = {f.name: f.to_dict() for f in self.fields}
        out["checkable_questions"] = list(self.checkable_questions)
        if self.proposed_by is not None:
            out["proposed_by"] = self.proposed_by
        if self.reviewed_at is not None:
            out["reviewed"] = {"at": self.reviewed_at, "fields_fingerprint": self.fingerprint}
        return out

    @property
    def manifest_id(self) -> str:
        """Content hash: the same manifest has the same id wherever it is loaded."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    def field(self, name: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.name == name), None)

    def render_context(self) -> dict[str, Any]:
        """The semantic layer this manifest declares, in the shape the probe scores.

        A category nothing in the manifest fills is rendered empty, and the probe
        counts it as absent — a manifest without units scores lower, as it should.
        """
        return {
            "entity_type": self.entity or "",
            "units": {f.name: f.unit for f in self.fields if f.unit},
            "descriptions": {f.name: f.definition for f in self.fields if f.definition},
            "relationships": {f.name: f.relationship for f in self.fields if f.relationship},
        }


# ---- reading and writing ----------------------------------------------------

def parse_manifest(data: Any, where: str) -> Manifest:
    if not isinstance(data, dict):
        raise ManifestError(f"{where}: a manifest is a mapping with source:, entity: and fields:")
    _only(data, TOP_KEYS, where)
    source = data.get("source")
    if not isinstance(source, str) or not source:
        raise ManifestError(f"{where}: source: must name the source this manifest describes")
    entity = data.get("entity")
    if entity is not None and not isinstance(entity, str):
        raise ManifestError(f"{where}: entity: must be text, e.g. retail_product")
    raw_fields = data.get("fields")
    if not isinstance(raw_fields, dict) or not raw_fields:
        raise ManifestError(f"{where}: fields: must map at least one field name to its role")

    fields = []
    for name, spec in raw_fields.items():
        label = f"{where}: fields.{name}"
        if not isinstance(spec, dict):
            raise ManifestError(f"{label}: give a mapping, e.g. {{role: measure, unit: USD}}")
        _only(spec, FIELD_KEYS, label)
        role = spec.get("role")
        if role not in ROLES:
            raise ManifestError(f"{label}.role: one of {list(ROLES)}, got {role!r}")
        text = {}
        for key in ("unit", "definition", "relationship", "tz"):
            value = spec.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ManifestError(f"{label}.{key}: must be non-empty text")
            text[key] = value.strip() if isinstance(value, str) else None
        fields.append(FieldSpec(str(name), role, **text))

    ids = [f.name for f in fields if f.role == "id"]
    if len(ids) != 1:
        raise ManifestError(f"{where}: exactly one field needs role: id, found "
                            f"{len(ids)}{' (' + ', '.join(ids) + ')' if ids else ''}")

    from ..analyst.plan import TYPES as PLAN_TYPES  # here: analyst imports sources

    questions = data.get("checkable_questions")
    if questions is None:
        questions = default_questions(fields)
    if not isinstance(questions, list) or any(q not in PLAN_TYPES for q in questions):
        raise ManifestError(f"{where}: checkable_questions: a list drawn from {list(PLAN_TYPES)}")
    if any(q != "count_where" and q != "lookup" for q in questions) and \
            not any(f.role == "measure" for f in fields):
        needing = ", ".join(q for q in questions if q not in ("count_where", "lookup"))
        raise ManifestError(f"{where}: {needing} need a field with role: measure")

    reviewed = data.get("reviewed")
    reviewed_at = fingerprint_value = None
    if reviewed is not None:
        if not isinstance(reviewed, dict):
            raise ManifestError(f"{where}: reviewed: is written by `airs manifest review`")
        _only(reviewed, REVIEW_KEYS, f"{where}: reviewed")
        reviewed_at, fingerprint_value = reviewed.get("at"), reviewed.get("fields_fingerprint")
        if not isinstance(reviewed_at, str) or not isinstance(fingerprint_value, str):
            raise ManifestError(f"{where}: reviewed: needs at: and fields_fingerprint: — "
                                f"stamp it with `airs manifest review`")
    proposed_by = data.get("proposed_by")
    if proposed_by is not None and not isinstance(proposed_by, str):
        raise ManifestError(f"{where}: proposed_by: must be text")
    return Manifest(source, entity, tuple(fields), tuple(questions), proposed_by,
                    reviewed_at, fingerprint_value)


def load_manifest(path: Path | str) -> Manifest:
    from .config import _read_yaml  # the loader that refuses duplicate keys

    path = Path(path)
    return parse_manifest(_read_yaml(path), str(path))


def dump_manifest(manifest: Manifest) -> str:
    import yaml

    header = ("# Semantic manifest — what each field means. Reviewed with `airs manifest "
              "review`;\n# a change to the source's fields makes it stale until reviewed "
              "again.\n")
    return header + yaml.safe_dump(manifest.to_dict(), sort_keys=False, allow_unicode=True,
                                   width=100)


def _only(mapping: dict[Any, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(str(key) for key in mapping if key not in allowed)
    if unknown:
        raise ManifestError(f"{label}: unknown key(s) {unknown}; allowed: {sorted(allowed)}")


def default_questions(fields: Sequence[FieldSpec]) -> list[str]:
    from ..analyst.plan import TYPES as PLAN_TYPES

    has_measure = any(f.role == "measure" for f in fields)
    return [q for q in PLAN_TYPES if has_measure or q in ("count_where", "lookup")]


# ---- the review stamp -------------------------------------------------------

def fingerprint(schema: SourceSchema) -> str:
    """Field names and kinds, order-free. Integer and float count as one kind, so
    a column that gains a decimal value is not a schema change; a renamed or
    retyped column is."""
    def kind(type_text: str) -> str:
        parts = {("number" if p in NUMERIC else p) for p in type_text.split("|")}
        return "|".join(sorted(parts))

    canonical = json.dumps(sorted((f.name, kind(f.type)) for f in schema.fields))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def check_against(manifest: Manifest, schema: SourceSchema) -> list[str]:
    """Problems that make this manifest wrong for this source, in plain words."""
    names = {f.name: f.type for f in schema.fields}
    # File sources lift the id column out of the payload; it still exists.
    names.setdefault(schema.id_field, "string")
    problems = [f"describes {f.name!r}, which the source does not have"
                for f in manifest.fields if f.name not in names]
    for f in manifest.fields:
        if f.role == "measure" and f.name in names and \
                not set(names[f.name].split("|")) & NUMERIC:
            problems.append(f"{f.name!r} has role measure but holds {names[f.name]}")
    return problems


def stamp(manifest: Manifest, schema: SourceSchema,
          now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Manifest:
    problems = check_against(manifest, schema)
    if problems:
        raise ManifestError(f"cannot mark reviewed: the manifest {'; '.join(problems)}")
    at = now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return replace(manifest, reviewed_at=at, fingerprint=fingerprint(schema))


# ---- the two states ---------------------------------------------------------

@dataclass
class SemanticLayer:
    """What the semantic dimension may claim for one source pair, and why."""

    state: str
    reason: str
    manifest: Manifest | None = None
    path: str | None = None
    renders: bool = False
    coverage: dict[str, list[str]] = field(default_factory=dict)

    @property
    def measured(self) -> bool:
        return self.state == "reviewed"

    @property
    def unmeasured_reason(self) -> str | None:
        return None if self.measured else self.reason

    def apply(self, records: Sequence[Record]) -> list[Record]:
        """Records as the agent and the probe should see them.

        Only a reviewed manifest renders, only for a source that does not render
        its own semantic layer, and only onto records that arrived without context.
        """
        if not (self.measured and self.renders):
            return list(records)
        context = self.manifest.render_context()
        out = []
        for record in records:
            if record.context:
                out.append(record)
                continue
            copy = record.clone()
            copy.context = json.loads(json.dumps(context))
            out.append(copy)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "manifest_approved": self.measured,
            "manifest_id": self.manifest.manifest_id if self.manifest else None,
            "manifest_path": self.path,
            "reason": self.reason,
            "field_coverage": self.coverage,
        }


def semantic_layer(pair: SourcePair) -> SemanticLayer:
    """Resolve a pair's manifest into one of the two measurement states.

    reviewed    stamped, fingerprint matches the source now, fields all exist
    unreviewed  a valid manifest nobody has approved
    stale       approved against a schema the source no longer has
    absent      no manifest declared
    invalid     a manifest file that does not parse or validate
    """
    renders = not getattr(pair.delivered, "renders_context", False)
    if pair.manifest is None:
        return SemanticLayer("absent", (
            f"semantic UNMEASURED: no manifest declared for {pair.id}, so the tool does not "
            f"know what its fields mean. Propose one with `airs manifest propose {pair.id}`"),
            renders=renders)
    if not Path(pair.manifest).exists():
        return SemanticLayer("absent", (
            f"semantic UNMEASURED: {pair.id} declares manifest {pair.manifest}, which does not "
            f"exist yet. Propose it with `airs manifest propose {pair.id} --out "
            f"{pair.manifest}`"), path=pair.manifest, renders=renders)
    try:
        manifest = load_manifest(pair.manifest)
    except SourceError as exc:
        return SemanticLayer("invalid", f"semantic UNMEASURED: {exc}", path=pair.manifest,
                             renders=renders)

    schema = pair.delivered.describe()
    coverage = _coverage(manifest, schema)
    common = dict(manifest=manifest, path=pair.manifest, renders=renders, coverage=coverage)
    if manifest.reviewed_at is None:
        return SemanticLayer("unreviewed", (
            f"semantic UNMEASURED: the manifest for {pair.id} has not been reviewed. "
            f"Approve it with `airs manifest review {pair.manifest} --source {pair.id}`"),
            **common)
    problems = check_against(manifest, schema)
    if manifest.fingerprint != fingerprint(schema) or problems:
        detail = "; ".join(problems) if problems else "the source's fields or types changed"
        return SemanticLayer("stale", (
            f"semantic UNMEASURED: the manifest for {pair.id} was reviewed against a "
            f"different schema ({detail}). Review it again with "
            f"`airs manifest review {pair.manifest} --source {pair.id}`"), **common)
    undescribed = coverage["undescribed"]
    return SemanticLayer("reviewed", (
        f"manifest reviewed {manifest.reviewed_at}"
        + (f"; no definition for {', '.join(undescribed)}" if undescribed else
           "; every field has a definition")), **common)


def _coverage(manifest: Manifest, schema: SourceSchema) -> dict[str, list[str]]:
    described = {f.name for f in manifest.fields if f.definition}
    names = [f.name for f in schema.fields]
    if schema.id_field not in names:
        names.insert(0, schema.id_field)
    return {"described": [n for n in names if n in described],
            "undescribed": [n for n in names if n not in described]}


# ---- proposing one ----------------------------------------------------------

def propose(schema: SourceSchema, source_id: str) -> Manifest:
    """A first draft from names and types alone — offline, no model, $0.

    It guesses roles and nothing else. Units, definitions and relationships are
    left empty on purpose: a guessed unit is worse than an absent one, and the
    reviewer, not the tool, knows whether `price` includes tax.
    """
    fields = []
    for info in schema.fields:
        kinds = set(info.type.split("|")) - {"null"}
        if info.name == schema.id_field:
            role = "id"
        elif _TIME_NAME.search(info.name) and kinds <= NUMERIC | {"string"}:
            role = "updated_at"
        elif kinds and kinds <= NUMERIC:
            role = "measure"
        else:
            role = "label"
        fields.append(FieldSpec(info.name, role))
    if not any(f.role == "id" for f in fields):
        # File sources lift the id column out of the payload into the record's id.
        fields.insert(0, FieldSpec(schema.id_field, "id"))
    return Manifest(source=source_id, entity=None, fields=tuple(fields),
                    checkable_questions=tuple(default_questions(fields)),
                    proposed_by="heuristic")


MANIFEST_SYSTEM = """You document datasets. Given a table's field names, types and example
values, describe each field. Respond with JSON only:
{"entity": "<what one record is, snake_case>",
 "fields": {"<field>": {"role": "id" | "measure" | "label" | "updated_at",
                        "unit": "<unit or null>", "definition": "<one short sentence>"}}}
Use role "measure" only for numeric fields. Give a unit only when the examples make it
clear; otherwise null."""


def refine_with_model(draft: Manifest, schema: SourceSchema, client: Any,
                      model: str) -> Manifest:
    """One local model call proposing an entity, units and definitions.

    Every suggestion is validated field by field; anything malformed keeps the
    heuristic draft's value. The result is still a proposal: nothing a model
    writes counts until a person reviews it.
    """
    listing = json.dumps({"fields": [{"name": f.name, "type": f.type,
                                      "examples": list(f.examples)} for f in schema.fields]},
                         default=str, ensure_ascii=False)
    result = client.call_json([("system", MANIFEST_SYSTEM), ("user", listing)])
    if not isinstance(result, dict):
        return replace(draft, proposed_by=f"heuristic ({model} returned no usable JSON)")
    suggested = result.get("fields") if isinstance(result.get("fields"), dict) else {}
    kinds = {f.name: set(f.type.split("|")) - {"null"} for f in schema.fields}
    fields = []
    for spec in draft.fields:
        s = suggested.get(spec.name) if isinstance(suggested.get(spec.name), dict) else {}
        role = spec.role
        if spec.role != "id" and s.get("role") in ROLES and s.get("role") != "id":
            if s["role"] != "measure" or (kinds[spec.name] and kinds[spec.name] <= NUMERIC):
                role = s["role"]
        fields.append(replace(spec, role=role, unit=_text(s.get("unit")),
                              definition=_text(s.get("definition"))))
    entity = _text(result.get("entity"))
    return replace(draft, entity=entity, fields=tuple(fields),
                   checkable_questions=tuple(default_questions(fields)), proposed_by=model)


def _text(value: Any, limit: int = 200) -> str | None:
    if not isinstance(value, str) or not value.strip() or value.strip().lower() == "null":
        return None
    return value.strip()[:limit]
