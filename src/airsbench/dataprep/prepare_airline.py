"""Prepare the airline delay classification dataset (BTS On-Time).

Industry scenario #2: aviation. Downloads monthly On-Time Performance
archives from the U.S. Bureau of Transportation Statistics (public
domain), extracts flight features, labels each flight with ArrDel15
(arrival delayed >= 15 min), and writes a class-balanced sample.

Outputs (under --out):
  flights.parquet          features + label per flight
  semantic_context.json    the semantic layer attached to records at runtime

Usage:
  python -m airsbench.dataprep.prepare_airline --out data/airline \
      --year 2024 --months 1 2 3 --n-per-class 15000 --seed 42

Note: transtats.bts.gov occasionally has TLS certificate hiccups; if the
download fails, fetch the PREZIP files manually and pass --local-dir.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

BTS_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)

FEATURES = [
    "Month", "DayOfWeek", "Reporting_Airline", "Origin", "Dest",
    "CRSDepTime", "CRSArrTime", "Distance", "DepDelay",
]
LABEL = "ArrDel15"

SEMANTIC_CONTEXT = {
    "entity_type": "scheduled_flight",
    "units": {
        "CRSDepTime": "local time, hhmm",
        "CRSArrTime": "local time, hhmm",
        "Distance": "statute miles",
        "DepDelay": "minutes (negative = early departure)",
    },
    "descriptions": {
        "Month": "Calendar month of the flight (1-12)",
        "DayOfWeek": "Day of week (1=Monday ... 7=Sunday)",
        "Reporting_Airline": "IATA carrier code of the operating airline",
        "Origin": "IATA code of the departure airport",
        "Dest": "IATA code of the arrival airport",
        "CRSDepTime": "Scheduled departure time",
        "CRSArrTime": "Scheduled arrival time",
        "Distance": "Great-circle distance between airports",
        "DepDelay": "Actual departure delay at gate pushback",
        "ArrDel15": "Ground truth: 1 if arrival delay >= 15 minutes",
    },
    "relationships": {
        "Origin/Dest": "IATA airport codes; join to airport reference data",
        "Reporting_Airline": "IATA carrier code; join to carrier reference data",
    },
}


def load_month(year: int, month: int, local_dir: Path | None):
    import pandas as pd
    import requests

    name = f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}"
    if local_dir is not None:
        raw = (local_dir / f"{name}.zip").read_bytes()
    else:
        url = BTS_URL.format(year=year, month=month)
        print(f"Downloading {url} ...")
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        raw = response.content

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        with zf.open(csv_name) as fh:
            return pd.read_csv(fh, usecols=FEATURES + [LABEL], low_memory=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/airline"))
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--months", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--n-per-class", type=int, default=15000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--local-dir", type=Path, default=None,
                        help="directory with manually downloaded PREZIP files")
    args = parser.parse_args(argv)

    import pandas as pd

    args.out.mkdir(parents=True, exist_ok=True)
    frames = [load_month(args.year, month, args.local_dir) for month in args.months]
    df = pd.concat(frames, ignore_index=True).dropna(subset=[LABEL])

    # Class-balanced sample: delayed flights are the minority class (~20%),
    # balancing keeps per-run accuracy interpretable across conditions.
    delayed = df[df[LABEL] == 1.0]
    ontime = df[df[LABEL] == 0.0]
    n = min(args.n_per_class, len(delayed), len(ontime))
    sample = pd.concat([
        delayed.sample(n=n, random_state=args.seed),
        ontime.sample(n=n, random_state=args.seed),
    ]).sample(frac=1.0, random_state=args.seed)  # shuffle

    sample.to_parquet(args.out / "flights.parquet", index=False)
    (args.out / "semantic_context.json").write_text(json.dumps(SEMANTIC_CONTEXT, indent=2))
    print(f"flights: {len(sample)} rows ({n} per class) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
