"""Parse JSON sample drops uploaded by the iOS companion app.

The iOS app writes one `samples_YYYY-MM-DD.json` file per day to iCloud Drive
(Documents/ios_export/) — a flat list of normalized sample dicts that match
the {ts, ts_end, source, type, value, unit, meta} schema. We read all such
files in a directory (typically a symlink into iCloud) and emit a single
ios-YYYY-MM.parquet partition for downstream Vitals queries.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def parse_drops_to_parquet(drops_dir: Path, outdir: Path) -> int:
    """Read every samples_YYYY-MM-DD.json in drops_dir; emit partitioned Parquet.

    Idempotent: clears existing ios-*.parquet before writing.
    Returns total samples written.
    """
    if not drops_dir.exists():
        return 0
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("ios-*.parquet"):
        old.unlink()

    by_partition: dict[str, list[dict]] = defaultdict(list)
    n_total = 0
    for drop in sorted(drops_dir.glob("samples_*.json")):
        try:
            rows = json.loads(drop.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(rows, list):
            continue
        for r in rows:
            ts = r.get("ts")
            if not ts:
                continue
            partition = ts[:7]
            # The meta field can come as a dict or a stringified JSON; normalize.
            meta = r.get("meta")
            if isinstance(meta, dict):
                meta = json.dumps(meta)
            r = {**r, "meta": meta or "{}"}
            by_partition[partition].append(r)
            n_total += 1

    if not by_partition:
        return 0

    schema = pa.schema([
        ("ts",     pa.string()),
        ("ts_end", pa.string()),
        ("source", pa.string()),
        ("type",   pa.string()),
        ("value",  pa.float64()),
        ("unit",   pa.string()),
        ("meta",   pa.string()),
    ])
    for partition, rows in by_partition.items():
        # Cast value to float defensively
        for r in rows:
            try:
                r["value"] = float(r.get("value")) if r.get("value") is not None else None
            except (TypeError, ValueError):
                r["value"] = None
        table = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(table, outdir / f"ios-{partition}.parquet")
    return n_total


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Ingest iOS sample drops to Parquet.")
    ap.add_argument("--drops",  type=Path, default=Path("data/raw/ios"))
    ap.add_argument("--outdir", type=Path, default=Path("data/parquet/samples"))
    args = ap.parse_args()
    n = parse_drops_to_parquet(args.drops, args.outdir)
    print(f"Wrote {n:,} iOS samples to {args.outdir}/ios-*.parquet")


if __name__ == "__main__":
    _cli()
