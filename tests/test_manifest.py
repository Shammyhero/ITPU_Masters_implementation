"""The semantic manifest and the two-state semantic rule (plan A2, brief correction 2).

Three guarantees carry the weight:

- **Nobody said what the fields mean → UNMEASURED, never 100 and never 0.** The
  probe's own rule (no context = 0) is for records a pipeline delivered; a tool
  that has not been told what a column means has not measured anything.
- **A reviewed manifest is scored by the calibrated rule, unchanged.** Four
  categories present or not (author decision, 17 Sep); which fields lack a
  definition is reported beside it, never folded into the score.
- **Reviewed means reviewed against this schema.** Renaming or retyping a column
  makes the manifest stale, and semantic returns to UNMEASURED.

And one the demo depends on: the bundled manifest renders exactly the context the
corpus agent read, and is never re-rendered on top of a pipeline that renders its
own — which would undo semantic stripping.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from airsbench.analyst.answerers import LiteralAnswerer
from airsbench.analyst.plan import Plan
from airsbench.analyst.session import Question, ask
from airsbench.pipelines.loader import build_product_record
from airsbench.sources.__main__ import sample_report
from airsbench.sources.config import load_sources
from airsbench.sources.demo import DEMO_MANIFEST, load_slice
from airsbench.sources.manifest import (
    FieldSpec,
    Manifest,
    ManifestError,
    dump_manifest,
    fingerprint,
    load_manifest,
    parse_manifest,
    propose,
    refine_with_model,
    semantic_layer,
    stamp,
)
from airsbench.sources.manifest_cli import main as manifest_main
from airsbench.sources.manifest_cli import rendered_score

ROWS = [{"product_id": "A", "price": 10.0, "stock": 3, "title": "kettle",
         "updated_at": "2026-09-13T10:00:00Z"},
        {"product_id": "B", "price": 7.5, "stock": 0, "title": "mug",
         "updated_at": "2026-09-13T10:00:00Z"},
        {"product_id": "C", "price": 3.0, "stock": 9, "title": "spoon",
         "updated_at": "2026-09-13T10:00:00Z"}]

FULL = {"source": "shop", "entity": "retail_product", "fields": {
    "product_id": {"role": "id", "definition": "Catalog id"},
    "price": {"role": "measure", "unit": "USD", "definition": "Listed price"},
    "stock": {"role": "measure", "unit": "units", "definition": "Units on hand"},
    "title": {"role": "label", "definition": "Name", "relationship": "shown to customers"},
    "updated_at": {"role": "updated_at", "tz": "UTC"},
}}


def _csv(path: Path, rows) -> Path:
    header = list(rows[0])
    path.write_text(",".join(header) + "\n" +
                    "".join(",".join(str(r[h]) for h in header) + "\n" for r in rows))
    return path


def _pair(tmp_path: Path, manifest: dict | str | None = None, rows=ROWS):
    delivered = _csv(tmp_path / "delivered.csv", rows)
    lines = ["sources:", "  shop:", "    type: files", f"    delivered: {delivered.name}",
             f"    upstream: {delivered.name}", "    id_field: product_id"]
    if manifest is not None:
        path = tmp_path / "manifest.yaml"
        path.write_text(manifest if isinstance(manifest, str) else json.dumps(manifest))
        lines.append("    manifest: manifest.yaml")
    (tmp_path / "sources.yaml").write_text("\n".join(lines) + "\n")
    return load_sources(tmp_path / "sources.yaml")["shop"]


def _reviewed(tmp_path: Path, spec: dict = FULL, rows=ROWS):
    pair = _pair(tmp_path, spec, rows)
    stamped = stamp(parse_manifest(spec, "test"), pair.delivered.describe())
    Path(pair.manifest).write_text(dump_manifest(stamped))
    return load_sources(tmp_path / "sources.yaml")["shop"]


def _semantic(pair):
    return sample_report(pair, 3, None, 1, "retrieval")["airs"]["dimensions"]["semantic"]


# ---- the two states ---------------------------------------------------------

def test_no_manifest_is_unmeasured_not_zero(tmp_path):
    pair = _pair(tmp_path)
    report = sample_report(pair, 3, None, 1, "retrieval")
    semantic = report["airs"]["dimensions"]["semantic"]
    assert semantic["score"] is None and "UNMEASURED" in semantic["detail"]
    assert "semantic" in report["airs"]["unmeasured"]
    assert report["airs"]["airs"] is not None  # the composite rests on what was measured
    assert report["semantic"]["state"] == "absent"


def test_a_declared_manifest_not_written_yet_is_absent_and_names_the_command(tmp_path):
    """Declaring manifest: before proposing it must not make sources.yaml unloadable,
    or `airs manifest propose --out` could never create the file (found live, 17 Sep)."""
    pair = _pair(tmp_path, FULL)
    Path(pair.manifest).unlink()
    pair = load_sources(tmp_path / "sources.yaml")["shop"]
    layer = semantic_layer(pair)
    assert layer.state == "absent" and "airs manifest propose shop --out" in layer.reason


def test_an_unreviewed_manifest_is_still_unmeasured(tmp_path):
    pair = _pair(tmp_path, FULL)
    assert semantic_layer(pair).state == "unreviewed"
    assert _semantic(pair)["score"] is None


def test_a_reviewed_manifest_is_rendered_and_scored_by_the_probes_rule(tmp_path):
    pair = _reviewed(tmp_path)
    layer = semantic_layer(pair)
    assert layer.state == "reviewed" and layer.renders
    assert _semantic(pair)["score"] == 100.0
    assert layer.coverage["undescribed"] == ["updated_at"]


def test_a_partial_manifest_scores_the_categories_it_fills_not_its_fields(tmp_path):
    """Entity + descriptions, no units, no relationships: 2 of 4 categories = 50.
    One definition or five makes no difference to the score — only to coverage."""
    one_definition = {"source": "shop", "entity": "retail_product", "fields": {
        "product_id": {"role": "id"}, "price": {"role": "measure", "definition": "Price"},
        "stock": {"role": "measure"}, "title": {"role": "label"},
        "updated_at": {"role": "updated_at"}}}
    pair = _reviewed(tmp_path, one_definition)
    assert _semantic(pair)["score"] == 50.0
    assert semantic_layer(pair).coverage["described"] == ["price"]


def test_renaming_a_column_after_review_makes_the_manifest_stale(tmp_path):
    _reviewed(tmp_path)
    renamed = [{("cost" if k == "price" else k): v for k, v in r.items()} for r in ROWS]
    _csv(tmp_path / "delivered.csv", renamed)
    pair = load_sources(tmp_path / "sources.yaml")["shop"]
    layer = semantic_layer(pair)
    assert layer.state == "stale" and "'price'" in layer.reason
    assert _semantic(pair)["score"] is None


def test_retyping_a_column_is_stale_but_gaining_a_decimal_is_not(tmp_path):
    whole = [dict(r, stock=int(r["stock"])) for r in ROWS]
    _reviewed(tmp_path, rows=whole)
    _csv(tmp_path / "delivered.csv", [dict(r, stock=r["stock"] + 0.5) for r in whole])
    assert semantic_layer(load_sources(tmp_path / "sources.yaml")["shop"]).state == "reviewed"
    _csv(tmp_path / "delivered.csv", [dict(r, stock="many") for r in whole])
    assert semantic_layer(load_sources(tmp_path / "sources.yaml")["shop"]).state == "stale"


def test_an_invalid_manifest_is_unmeasured_with_the_reason(tmp_path):
    pair = _pair(tmp_path, "source: shop\nfields: {price: {role: price}}\n")
    layer = semantic_layer(pair)
    assert layer.state == "invalid" and "role" in layer.reason


def test_context_the_pipeline_delivered_is_never_overwritten(tmp_path):
    from agentic_faults import Record

    layer = semantic_layer(_reviewed(tmp_path))
    own = Record(payload={"price": 1.0}, context={"entity_type": "theirs"})
    bare = Record(payload={"price": 1.0})
    kept, rendered = layer.apply([own, bare])
    assert kept.context == {"entity_type": "theirs"}
    assert rendered.context["entity_type"] == "retail_product" and bare.context == {}


# ---- the demo ---------------------------------------------------------------

def test_the_bundled_manifest_renders_exactly_the_context_the_corpus_agent_read():
    data = load_slice()
    product = next(iter(data.machine.base.values()))
    corpus_context = build_product_record(product, data.context, event_ts=0.0).context
    assert load_manifest(DEMO_MANIFEST).render_context() == corpus_context


def test_the_committed_demo_manifest_is_a_fresh_bake():
    from airsbench.server.bake import build_demo_manifest

    assert DEMO_MANIFEST.read_text() == dump_manifest(build_demo_manifest())


def test_every_demo_pair_is_reviewed_and_never_re_rendered():
    """Re-rendering onto demo-stripped would undo the fault, so nothing is rendered."""
    pairs = load_sources()
    for pair in pairs.values():
        layer = semantic_layer(pair)
        assert (layer.state, layer.renders) == ("reviewed", False), pair.id
    assert _semantic(pairs["demo-healthy"])["score"] == 100.0
    stripped = pairs["demo-stripped"]
    sample = stripped.delivered.sample(6, seed=3)
    assert semantic_layer(stripped).apply(sample.records) == sample.records
    # Severe stripping hits each record with a probability, so a few keep context:
    # the score is what A1 already scored (test_demo_source), well below healthy.
    assert _semantic(stripped)["score"] < 50.0


# ---- the Tick ---------------------------------------------------------------

def test_the_tick_records_the_semantic_state_and_says_why_it_is_unmeasured(tmp_path):
    pair = _pair(tmp_path)
    question = Question("Which product is cheapest in stock?", Plan.from_dict(
        {"type": "min_by", "measure": "price",
         "where": [{"field": "stock", "op": ">", "value": 0}]}), n=3)
    tick = ask(pair, question, LiteralAnswerer(), seed=1)
    assert tick["source"]["semantic"]["manifest_approved"] is False
    assert tick["airs"]["dimensions"]["semantic"]["score"] is None
    assert any("UNMEASURED" in note for note in tick["notes"])


# ---- validation -------------------------------------------------------------

@pytest.mark.parametrize("change, message", [
    ({"fields": {"a": {"role": "id"}, "b": {"role": "id"}}}, "exactly one field"),
    ({"colour": "blue"}, "unknown key"),
    ({"fields": {"a": {"role": "id", "unit": 5}}}, "non-empty text"),
    ({"fields": {"a": {"role": "id"}}, "checkable_questions": ["min_by"]}, "role: measure"),
    ({"checkable_questions": ["guess"]}, "checkable_questions"),
])
def test_a_malformed_manifest_is_refused_with_the_fix(change, message):
    with pytest.raises(ManifestError, match=message):
        parse_manifest({**FULL, **change}, "m.yaml")


def test_a_measure_over_text_cannot_be_marked_reviewed(tmp_path):
    pair = _pair(tmp_path)
    spec = {**FULL, "fields": {**FULL["fields"], "title": {"role": "measure"}}}
    with pytest.raises(ManifestError, match="'title' has role measure"):
        stamp(parse_manifest(spec, "m"), pair.delivered.describe())


def test_a_manifest_round_trips_through_yaml_with_the_same_id(tmp_path):
    manifest = parse_manifest(FULL, "m")
    path = tmp_path / "m.yaml"
    path.write_text(dump_manifest(manifest))
    assert load_manifest(path).manifest_id == manifest.manifest_id


# ---- proposing --------------------------------------------------------------

def test_the_offline_proposal_guesses_roles_and_never_units_or_meanings(tmp_path):
    schema = _pair(tmp_path).delivered.describe()
    draft = propose(schema, "shop")
    roles = {f.name: f.role for f in draft.fields}
    assert roles == {"product_id": "id", "price": "measure", "stock": "measure",
                     "title": "label", "updated_at": "updated_at"}
    assert all(f.unit is None and f.definition is None for f in draft.fields)
    assert draft.reviewed_at is None and draft.proposed_by == "heuristic"


class FakeClient:
    def __init__(self, result):
        self.result = result

    def call_json(self, messages):
        return self.result


def test_a_model_proposal_is_validated_field_by_field(tmp_path):
    schema = _pair(tmp_path).delivered.describe()
    draft = propose(schema, "shop")
    refined = refine_with_model(draft, schema, FakeClient({"entity": "product", "fields": {
        "product_id": {"role": "measure"},                 # the id is never reassigned
        "title": {"role": "measure", "definition": "x"},   # measure over text: refused
        "price": {"role": "measure", "unit": "USD", "definition": "Price"},
        "stock": {"role": "label", "unit": "null"},
    }}), "ollama/test")
    by_name = {f.name: f for f in refined.fields}
    assert by_name["product_id"].role == "id"
    assert by_name["title"].role == "label" and by_name["title"].definition == "x"
    assert (by_name["price"].unit, by_name["price"].definition) == ("USD", "Price")
    assert by_name["stock"].unit is None
    assert refined.entity == "product" and refined.reviewed_at is None
    garbage = refine_with_model(draft, schema, FakeClient("not json"), "ollama/test")
    assert [f.role for f in garbage.fields] == [f.role for f in draft.fields]


# ---- the command ------------------------------------------------------------

def test_review_walks_the_fields_and_stamps_the_file(tmp_path, capsys):
    pair = _pair(tmp_path, {"source": "shop", "fields": {"product_id": {"role": "id"}}})
    answers = iter(["definition=Catalog id", "",          # product_id
                    "role=measure", "unit=USD", "",       # price
                    "role=measure", "",                   # stock
                    "role=label", "",                     # title
                    "drop",                               # updated_at
                    "retail_product", "y"])
    status = manifest_main(["--sources", str(tmp_path / "sources.yaml"), "review",
                            pair.manifest, "--source", "shop"], ask=lambda _: next(answers))
    assert status == 0
    written = load_manifest(pair.manifest)
    schema = load_sources(tmp_path / "sources.yaml")["shop"].delivered.describe()
    assert written.fingerprint == fingerprint(schema)
    assert written.field("price").unit == "USD" and written.field("updated_at") is None
    assert semantic_layer(load_sources(tmp_path / "sources.yaml")["shop"]).state == "reviewed"


def test_quitting_a_review_writes_nothing(tmp_path):
    pair = _pair(tmp_path, FULL)
    before = Path(pair.manifest).read_text()
    status = manifest_main(["--sources", str(tmp_path / "sources.yaml"), "review",
                            pair.manifest, "--source", "shop"], ask=lambda _: "q")
    assert status == 1 and Path(pair.manifest).read_text() == before


def test_propose_never_overwrites_without_force(tmp_path, capsys):
    _pair(tmp_path)
    out = tmp_path / "manifest.yaml"
    out.write_text("keep me")
    args = ["--sources", str(tmp_path / "sources.yaml"), "propose", "shop", "--out", str(out)]
    assert manifest_main(args) == 2 and out.read_text() == "keep me"
    assert manifest_main(args + ["--force"]) == 0
    assert load_manifest(out).reviewed_at is None


def test_rendered_score_counts_categories():
    fields = (FieldSpec("id", "id"), FieldSpec("p", "measure", unit="USD"))
    assert rendered_score(Manifest("s", "thing", fields, ("lookup",))) == 50.0
