"""Offline sensitivity check — free, no LLM calls.

Answers the question the freshness research question depends on: how
often does staleness change the CORRECT ANSWER? If a stale catalog yields
the same answer as the fresh one, no agent, however bad, can show
degradation, and RQ1 has no threshold to find.

This is the cheapest possible pilot pre-check and should be re-run
whenever the update-stream parameters change.

    python -m airsbench.dataprep.check_sensitivity --n 400
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from ..agents.retrieval import RetrievalAgent
from ..pipelines.loader import CatalogTimeMachine
from ..runner.execute import BATCH_INHERENT_STALENESS_S, N_CANDIDATES

STALENESS_LEVELS = {
    "streaming baseline (0.05s)": 0.05,
    "mild fault (1.5s)": 1.5,
    "severe fault (5s)": 5.0,
    f"batch inherent ({BATCH_INHERENT_STALENESS_S:.0f}s)": BATCH_INHERENT_STALENESS_S,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path("data/ecommerce"))
    parser.add_argument("--n", type=int, default=400, help="queries to sample")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    import pandas as pd

    rng = random.Random(args.seed)
    machine = CatalogTimeMachine.load(args.data_dir)
    queries = pd.read_parquet(args.data_dir / "queries.parquet").to_dict("records")
    usable = [q for q in queries if len(q["relevant_product_ids"]) >= 2]

    per_product_interval = len(machine.base) / max(len(machine.updates) / machine.max_ts, 1e-9)
    print(f"catalog: {len(machine.base)} products | updates: {len(machine.updates)} "
          f"over {machine.max_ts:.1f}s")
    print(f"mean interval between updates to one product: {per_product_interval:.1f}s\n")

    counts = {label: 0 for label in STALENESS_LEVELS}
    evaluated = 0

    for _ in range(args.n):
        query = rng.choice(usable)
        t_query = rng.uniform(machine.max_ts * 0.5, machine.max_ts)
        truth_state = machine.state_at(t_query)
        ids = [str(p) for p in query["relevant_product_ids"]][:N_CANDIDATES]
        ids = [pid for pid in ids if pid in truth_state]
        if len(ids) < 2:
            continue
        truth = RetrievalAgent.ground_truth([truth_state[pid] for pid in ids])
        if truth is None:
            continue
        evaluated += 1

        for label, staleness in STALENESS_LEVELS.items():
            served_state = machine.state_at(max(0.0, t_query - staleness))
            served = RetrievalAgent.ground_truth([served_state[pid] for pid in ids])
            if served is None or served["product_id"] != truth["product_id"]:
                counts[label] += 1

    print(f"Answer-flip rate over {evaluated} evaluated queries")
    print("(share of queries where the stale catalog implies a DIFFERENT correct answer)\n")
    for label, count in counts.items():
        rate = count / evaluated if evaluated else 0.0
        bar = "#" * int(rate * 40)
        print(f"  {label:<28} {rate:6.1%}  {bar}")

    severe = counts["severe fault (5s)"] / evaluated if evaluated else 0.0
    print()
    if severe < 0.10:
        print("VERDICT: too insensitive — a perfect agent would lose <10% under a severe "
              "fault. Increase --update-rate in prepare_ecommerce.")
    else:
        print(f"VERDICT: sensitive. A severe freshness fault can cost up to {severe:.0%} "
              "accuracy, which is a measurable degradation for RQ1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
