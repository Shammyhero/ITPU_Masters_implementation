"""`airs sources` — list, describe and sample your declared data sources.

    airs sources list
    airs sources describe demo-stale
    airs sources sample demo-stale --seed 7
    airs sources --sources sources.yaml sample exports --n 5 --json

The bundled demo pairs are always available; `--sources` adds yours. `sample`
draws records from the delivered side, reads the same ids upstream, and scores
them with `airsbench.probe` — against upstream as of the moment the delivered
values were true where the source can be read that way, and against upstream's
current state where it cannot (the output says which).

Exit status: 0 on success, 2 when a source cannot be declared or read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..probe import ProbeError, score
from .base import SourceError, SourcePair, to_probe_entry
from .manifest import semantic_layer


def _entries(records, ids) -> list[dict[str, Any]]:
    return [to_probe_entry(record, record_id) for record, record_id in zip(records, ids)]


def _upstream_entries(pair: SourcePair, sample, at: float | None) -> list[dict[str, Any]] | None:
    if pair.upstream is None:
        return None
    ids = [i for i in sample.ids if i is not None]
    return [to_probe_entry(record) for record in pair.upstream.fetch(ids, as_of=at)]


def sample_report(pair: SourcePair, n: int, key: str | None, seed: int | None,
                  task: str) -> dict[str, Any]:
    layer = semantic_layer(pair)
    sample = pair.delivered.sample(n, key=key, seed=seed)
    delivered = _entries(layer.apply(sample.records), sample.ids)
    supports_as_of = pair.upstream is not None and pair.upstream.describe().supports_as_of
    served_as_of = sample.meta.get("served_as_of") if supports_as_of else None
    now = _upstream_entries(pair, sample, sample.as_of if supports_as_of else None)
    as_served = _upstream_entries(pair, sample, served_as_of) if supports_as_of else None
    reference = as_served if supports_as_of else now
    return {
        "pair": pair.id,
        "kind": pair.kind,
        "key": sample.key,
        "as_of": sample.as_of,
        "meta": sample.meta,
        "ids": sample.ids,
        "consistency_reference": (
            "upstream as of the moment the delivered values were true" if supports_as_of
            else "upstream's current state — this source cannot be read as of a past time, "
                 "so consistency also absorbs staleness" if pair.upstream is not None
            else "none — no upstream declared, so consistency is unmeasured"
        ),
        "delivered": delivered,
        "upstream_now": now,
        "upstream_as_served": as_served,
        "semantic": layer.to_dict(),
        "airs": score(delivered, reference, task, semantic_unmeasured=layer.unmeasured_reason),
    }


def _short(payload: dict[str, Any], width: int = 44) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(", ", ": "))
    return text if len(text) <= width else text[: width - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="airs sources", description=__doc__.splitlines()[0])
    parser.add_argument("--sources", type=Path, default=None,
                        help="a sources.yaml declaring your sources (the demo pairs are "
                             "always available)")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="every available source pair")
    describe = actions.add_parser("describe", help="fields, types and examples of a pair")
    describe.add_argument("id")
    sample = actions.add_parser("sample", help="draw records, read them upstream, score them")
    sample.add_argument("id")
    sample.add_argument("--n", type=int, default=6)
    sample.add_argument("--key", default=None, help="a sampling key (a query id on the demo)")
    sample.add_argument("--seed", type=int, default=None)
    sample.add_argument("--task", default="retrieval")
    sample.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        from .config import load_sources

        pairs = load_sources(args.sources)
        if args.action == "list":
            return _list(pairs)
        pair = pairs.get(args.id)
        if pair is None:
            raise SourceError(f"no source {args.id!r}; available: {', '.join(pairs)}")
        if args.action == "describe":
            return _describe(pair)
        report = sample_report(pair, args.n, args.key, args.seed, args.task)
    except (SourceError, ProbeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    return _print_sample(report)


def _list(pairs: dict[str, SourcePair]) -> int:
    print(f"  {'source':<18}{'kind':<7}{'upstream':<10}{'as of':<7}{'manifest':<12}description")
    for pair in pairs.values():
        as_of = "yes" if pair.upstream is not None and pair.upstream.describe().supports_as_of \
            else "no"
        print(f"  {pair.id:<18}{pair.kind:<7}{'yes' if pair.upstream else 'NONE':<10}"
              f"{as_of:<7}{semantic_layer(pair).state:<12}{pair.description}")
    return 0


def _describe(pair: SourcePair) -> int:
    print(f"{pair.id} — {pair.description}")
    for side, source in (("delivered", pair.delivered), ("upstream", pair.upstream)):
        if source is None:
            print("\n  upstream: none declared — consistency and verification are unavailable")
            continue
        schema = source.describe()
        rows = "unknown" if schema.row_count is None else f"{schema.row_count:,}"
        print(f"\n  {side}: {schema.source} · {rows} records · id field {schema.id_field} · "
              f"readable as of a past time: {'yes' if schema.supports_as_of else 'no'}")
        for info in schema.fields:
            examples = ", ".join(json.dumps(v, ensure_ascii=False)[:30] for v in info.examples)
            print(f"    {info.name:<16}{info.type:<18}{examples}")
    return 0


def _print_sample(report: dict[str, Any]) -> int:
    meta = report["meta"]
    header = f"{report['pair']}"
    if meta.get("query"):
        header += f" · query {report['key']} “{meta['query']}”"
    if report["as_of"] is not None:
        header += f" · simulated time {report['as_of']:.2f}s"
    if "staleness_seconds" in meta:
        header += f" · delivered {meta['staleness_seconds']:g}s behind"
    print(header)
    upstream = {e.get("id"): e for e in report["upstream_now"] or []}
    print(f"\n  {'id':<14}{'delivered':<46}upstream now")
    for entry in report["delivered"]:
        match = upstream.get(entry.get("id"))
        print(f"  {str(entry.get('id')):<14}{_short(entry['payload']):<46}"
              f"{_short(match['payload']) if match else '—'}")
    airs = report["airs"]
    dims = " · ".join(
        f"{dim} {'UNMEASURED' if d['score'] is None else format(d['score'], '.1f')}"
        for dim, d in airs["dimensions"].items()
    )
    total = ("no score" if airs["airs"] is None else
             f"{airs['airs']:.1f} {airs['band']}, resting on "
             f"{airs['weight_covered']:.0%} of the calibrated weight")
    print(f"\n  AIRS ({airs['task']} profile): {dims} → {total}")
    print(f"  consistency compared with {report['consistency_reference']}")
    print(f"  semantic layer: {report['semantic']['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
