"""Prepare the e-commerce retrieval dataset (Amazon ESCI subset).

Industry scenario #1 (supervisor requirement): product QA over a live
catalog. Downloads the ESCI shopping-queries dataset, filters to
US-English / small_version, samples a catalog and query set, then
SYNTHESIZES the dynamic commerce fields (price, stock, last_updated)
plus an update stream that mutates them over time.

Why synthesize: ESCI provides real products, queries, and relevance
labels but is static. Freshness faults only degrade agent accuracy when
ground truth changes over time — the update stream creates exactly that,
with the generator fully documented and seeded (methodology chapter).

Outputs (under --out):
  catalog.parquet          product_id, title, brand, color, price, stock, last_updated
  queries.parquet          query_id, query, relevant_product_ids (ESCI label 'E')
  updates.jsonl            timestamped price/stock mutations (replayable)
  semantic_context.json    the semantic layer attached to records at runtime

Usage:
  python -m airsbench.dataprep.prepare_ecommerce --out data/ecommerce \
      --n-products 20000 --n-queries 1500 --n-updates 50000 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ESCI_HF_REPO = "tasksource/esci"

SEMANTIC_CONTEXT = {
    "entity_type": "retail_product",
    "units": {"price": "USD", "stock": "units_available", "last_updated": "epoch_seconds"},
    "descriptions": {
        "product_id": "Unique catalog identifier (ESCI product_id)",
        "title": "Customer-facing product title",
        "brand": "Manufacturer brand name",
        "color": "Primary product color",
        "price": "Current listed price in US dollars; changes over time",
        "stock": "Units currently available; 0 means out of stock",
        "last_updated": "Timestamp of the most recent price/stock change",
    },
    "relationships": {
        "product_id": "joins to queries.relevant_product_ids",
        "brand": "groups products from the same manufacturer",
    },
}


def synthesize_dynamics(products, query_groups, rng: random.Random):
    """Attach price/stock to each product.

    Prices are CLUSTERED per query: products relevant to the same query
    are substitutes and therefore priced within a common band (+/- 25 % of
    a per-query base). Global random pricing would make the cheapest
    candidate obvious and unshakeable, so a price change could never flip
    the correct answer — the task would be insensitive to staleness by
    construction. Clustering restores the sensitivity a real "cheapest
    in-stock option" decision has.

    Stock starts low (0-6 units) because stock-outs are the sharpest
    mechanism by which the correct answer changes over time.
    """
    by_id = {p["product_id"]: p for p in products}
    for product_ids in query_groups:
        base = rng.lognormvariate(3.0, 0.8)
        for pid in product_ids:
            product = by_id.get(pid)
            if product is None or "price" in product:
                continue
            product["price"] = round(max(0.5, base * rng.uniform(0.75, 1.25)), 2)

    for product in products:
        product.setdefault("price", round(rng.lognormvariate(3.0, 0.8), 2))
        product["stock"] = rng.randint(0, 6)
        product["last_updated"] = 0.0
    return products


def generate_update_stream(products, n_updates: int, update_rate: float, rng: random.Random):
    """Timestamped mutations of price and stock.

    ``update_rate`` (updates per second, across the whole catalog) sets
    the catalog's velocity, and it is an experimentally load-bearing
    parameter: the mean interval between updates to any ONE product is
    ``len(products) / update_rate`` seconds. That interval must be
    comparable to the staleness levels under test (1.5 s mild, 5 s
    severe), or "stale" data is identical to fresh data and the freshness
    fault cannot degrade anything. At the defaults (20 000 products,
    1000 updates/s) a product changes every ~20 s, so a 5 s staleness
    covers ~25 % of an update interval.

    Replaying updates up to time t yields the ground-truth catalog state
    at t — the reference the agent is scored against.
    """
    updates = []
    ts = 0.0
    for _ in range(n_updates):
        ts += rng.expovariate(update_rate)
        product = rng.choice(products)
        if rng.random() < 0.5:
            delta = 1.0 + rng.uniform(0.05, 0.35) * rng.choice([-1, 1])
            product["price"] = max(0.5, round(product["price"] * delta, 2))
            field, value = "price", product["price"]
        else:
            # Stock walks around zero so products cross in and out of
            # availability, flipping the correct answer.
            product["stock"] = max(0, product["stock"] + rng.choice([-3, -2, -1, 1, 2, 3]))
            field, value = "stock", product["stock"]
        product["last_updated"] = ts
        updates.append(
            {"ts": round(ts, 3), "product_id": product["product_id"], field: value}
        )
    return updates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/ecommerce"))
    parser.add_argument("--n-products", type=int, default=20000)
    parser.add_argument("--n-queries", type=int, default=1500)
    parser.add_argument("--n-updates", type=int, default=200000)
    parser.add_argument("--update-rate", type=float, default=2000.0,
                        help="catalog updates per second (sets catalog velocity; "
                             "2000/s over 20k products = one update per product per ~10s, "
                             "modelling a high-velocity dynamic-pricing catalog)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    import pandas as pd

    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pip install -e '.[data]' first") from exc

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"Loading ESCI from HuggingFace ({ESCI_HF_REPO}) ...")
    try:
        ds = load_dataset(ESCI_HF_REPO, split="train")
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            f"Could not load '{ESCI_HF_REPO}' ({exc}).\n"
            "Fallback: download shopping_queries_dataset_*.parquet from "
            "https://github.com/amazon-science/esci-data and re-run with a local path."
        ) from exc

    df = ds.to_pandas()
    df = df[(df["product_locale"] == "us") & (df["small_version"] == 1)]

    # --- catalog ---------------------------------------------------------
    products_df = (
        df.drop_duplicates("product_id")[
            ["product_id", "product_title", "product_brand", "product_color"]
        ]
        .rename(columns={"product_title": "title", "product_brand": "brand",
                         "product_color": "color"})
        .head(args.n_products)
    )
    products = products_df.to_dict("records")
    product_ids = {p["product_id"] for p in products}

    # --- queries (exact-match relevance only) ----------------------------
    exact = df[df["esci_label"] == "Exact"]
    exact = exact[exact["product_id"].isin(product_ids)]
    grouped = (
        exact.groupby(["query_id", "query"])["product_id"]
        .apply(lambda ids: list(dict.fromkeys(ids)))  # dedupe, keep first-seen order
        .reset_index()
    )
    grouped = grouped[grouped["product_id"].str.len() >= 2]
    queries = grouped.sample(n=min(args.n_queries, len(grouped)), random_state=args.seed)
    queries = queries.rename(columns={"product_id": "relevant_product_ids"})

    # Prices are clustered within each query's candidate set, so pricing
    # must happen after the query groups are known.
    products = synthesize_dynamics(products, list(queries["relevant_product_ids"]), rng)

    # --- update stream (generated on a copy; catalog keeps t=0 state) ----
    updates = generate_update_stream(
        [dict(p) for p in products], args.n_updates, args.update_rate, rng
    )

    pd.DataFrame(products).to_parquet(args.out / "catalog.parquet", index=False)
    queries.to_parquet(args.out / "queries.parquet", index=False)
    with open(args.out / "updates.jsonl", "w") as fh:
        for update in updates:
            fh.write(json.dumps(update) + "\n")
    (args.out / "semantic_context.json").write_text(json.dumps(SEMANTIC_CONTEXT, indent=2))

    print(f"catalog: {len(products)} products | queries: {len(queries)} "
          f"| updates: {len(updates)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
