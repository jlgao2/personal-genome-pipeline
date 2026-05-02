"""Stream-parse Apple HealthKit export.xml into normalized sample dicts.

The export.xml file is large (hundreds of MB for multi-year users), so we use
xml.etree.iterparse and clear elements as we go to keep memory bounded.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.parsers.healthkit_types import normalize_type


def _parse_apple_date(s: str) -> str:
    """Convert Apple's '2026-04-01 08:00:00 -0500' format to ISO-8601."""
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")
    return dt.isoformat()


def iter_samples(xml_path: Path) -> Iterator[dict]:
    """Yield one normalized-sample dict per <Record> we recognize.

    Output dict shape:
        {
          "ts":     ISO-8601 string,
          "source": "healthkit",
          "type":   normalized type string (e.g., "heart_rate"),
          "value":  float or None (None for category records),
          "unit":   string or None,
          "meta":   dict (source app, device, category value)
        }
    """
    context = ET.iterparse(str(xml_path), events=("end",))
    for event, elem in context:
        if elem.tag != "Record":
            continue

        hk_type = elem.get("type")
        normalized = normalize_type(hk_type) if hk_type else None
        if normalized is None:
            elem.clear()
            continue

        start_date = elem.get("startDate")
        if not start_date:
            elem.clear()
            continue

        try:
            ts = _parse_apple_date(start_date)
        except ValueError:
            elem.clear()
            continue

        end_date = elem.get("endDate")
        try:
            ts_end = _parse_apple_date(end_date) if end_date else ts
        except ValueError:
            ts_end = ts

        raw_value = elem.get("value")
        unit = elem.get("unit")
        meta: dict = {
            "source_name":    elem.get("sourceName"),
            "source_version": elem.get("sourceVersion"),
            "device":         elem.get("device"),
        }

        if hk_type.startswith("HKCategoryTypeIdentifier"):
            value = None
            meta["category_value"] = raw_value
        else:
            try:
                value = float(raw_value) if raw_value is not None else None
            except ValueError:
                value = None

        yield {
            "ts":     ts,
            "ts_end": ts_end,
            "source": "healthkit",
            "type":   normalized,
            "value":  value,
            "unit":   unit,
            "meta":   {k: v for k, v in meta.items() if v is not None},
        }

        elem.clear()  # critical for memory bounds on the real 427 MB file


def parse_to_parquet(xml_path: Path, outdir: Path) -> int:
    """Parse export.xml and write samples to outdir/healthkit-YYYY-MM.parquet
    partitioned by the start month of each sample.

    Idempotent: any existing healthkit-*.parquet files in outdir are deleted
    before writing.
    Returns the total number of samples written.
    """
    outdir.mkdir(parents=True, exist_ok=True)

    # Idempotency: clear previous output for this source.
    for old in outdir.glob("healthkit-*.parquet"):
        old.unlink()

    # Group samples by year-month so we can write one file per partition.
    by_partition: dict[str, list[dict]] = defaultdict(list)
    n_total = 0
    for sample in iter_samples(xml_path):
        partition = sample["ts"][:7]  # 'YYYY-MM' from ISO timestamp
        # JSON-encode the meta dict so it sits cleanly in Parquet.
        sample = {**sample, "meta": json.dumps(sample["meta"])}
        by_partition[partition].append(sample)
        n_total += 1

    for partition, samples in by_partition.items():
        table = pa.Table.from_pylist(samples, schema=pa.schema([
            ("ts",     pa.string()),
            ("ts_end", pa.string()),
            ("source", pa.string()),
            ("type",   pa.string()),
            ("value",  pa.float64()),
            ("unit",   pa.string()),
            ("meta",   pa.string()),
        ]))
        pq.write_table(table, outdir / f"healthkit-{partition}.parquet")

    return n_total


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Parse Apple HealthKit export.xml to Parquet.")
    ap.add_argument("xml", type=Path, help="path to apple_health_export/export.xml")
    ap.add_argument("--outdir", type=Path, default=Path("data/parquet/samples"),
                    help="parquet output directory")
    args = ap.parse_args()
    n = parse_to_parquet(args.xml, args.outdir)
    print(f"Wrote {n:,} samples to {args.outdir}/healthkit-*.parquet")


if __name__ == "__main__":
    _cli()
