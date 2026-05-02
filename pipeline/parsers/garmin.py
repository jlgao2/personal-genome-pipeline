"""Parse Garmin Connect bulk-export JSON files into normalized sample dicts.

The bulk export is a single ZIP with hundreds of files across many subdomains.
We pull from three families:
  - DI_CONNECT/DI-Connect-Aggregator/UDSFile_*.json  (daily wellness rollups)
  - DI_CONNECT/DI-Connect-Wellness/*_sleepData.json   (per-night sleep stages)
  - DI_CONNECT/DI-Connect-Wellness/*_userBioMetrics.json (sparse biometrics)
"""
from __future__ import annotations

import json
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.parsers.garmin_types import (
    normalize_biometric, normalize_sleep, normalize_uds,
)


def _ts_from_calendar_date(d: str) -> str:
    """Garmin calendarDate is 'YYYY-MM-DD'; emit ISO 00:00:00 in UTC."""
    return f"{d}T00:00:00+00:00"


def _normalize_garmin_iso(s: str) -> str:
    """Convert Garmin '2025-10-15T04:46:23.0' → '2025-10-15T04:46:23+00:00'."""
    if not s:
        return s
    if s.endswith(".0"):
        s = s[:-2]
    if "+" not in s and "Z" not in s and not s.endswith("00:00"):
        s = s + "+00:00"
    return s


def iter_uds_samples(json_path: Path) -> Iterator[dict]:
    """Yield sample dicts from one UDSFile_*.json daily-rollup file."""
    with json_path.open() as f:
        days = json.load(f)
    for day in days:
        cal = day.get("calendarDate")
        if not cal:
            continue
        ts = _ts_from_calendar_date(cal)
        ts_end = day.get("wellnessEndTimeGmt") or ts
        ts_end = _normalize_garmin_iso(ts_end)
        for field, raw in day.items():
            mapped = normalize_uds(field)
            if mapped is None or raw is None:
                continue
            type_name, unit = mapped
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            yield {
                "ts":     ts,
                "ts_end": ts_end,
                "source": "garmin",
                "type":   type_name,
                "value":  value,
                "unit":   unit,
                "meta":   {"calendar_date": cal},
            }


def iter_sleep_samples(json_path: Path) -> Iterator[dict]:
    """Yield sample dicts from one *_sleepData.json file."""
    with json_path.open() as f:
        nights = json.load(f)
    for night in nights:
        cal = night.get("calendarDate")
        if not cal:
            continue
        ts_start = night.get("sleepStartTimestampGMT") or _ts_from_calendar_date(cal)
        ts_end   = night.get("sleepEndTimestampGMT")   or ts_start
        ts_start = _normalize_garmin_iso(ts_start)
        ts_end   = _normalize_garmin_iso(ts_end)
        score = (night.get("sleepScores") or {}).get("overallScore")
        for field, raw in night.items():
            mapped = normalize_sleep(field)
            if mapped is None or raw is None:
                continue
            type_name, unit = mapped
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            yield {
                "ts":     ts_start,
                "ts_end": ts_end,
                "source": "garmin",
                "type":   type_name,
                "value":  value,
                "unit":   unit,
                "meta":   {"calendar_date": cal, "overall_score": score},
            }


def iter_biometric_samples(json_path: Path) -> Iterator[dict]:
    """Yield sample dicts from one userBioMetrics.json file (sparse readings)."""
    with json_path.open() as f:
        readings = json.load(f)
    for r in readings:
        meta = r.get("metaData") or {}
        cal = meta.get("calendarDate", "")[:10]
        if not cal:
            continue
        ts = _ts_from_calendar_date(cal)
        for field, raw in r.items():
            mapped = normalize_biometric(field)
            if mapped is None or raw is None:
                continue
            type_name, unit = mapped
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            yield {
                "ts":     ts,
                "ts_end": ts,
                "source": "garmin",
                "type":   type_name,
                "value":  value,
                "unit":   unit,
                "meta":   {"calendar_date": cal},
            }


def _iter_from_zip_member(zf, name, parser_fn):
    """Materialize one ZIP member to a temp file, yield parsed samples."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=True) as tmp:
        tmp.write(zf.read(name))
        tmp.flush()
        yield from parser_fn(Path(tmp.name))


def parse_zip_to_parquet(zip_path: Path, outdir: Path) -> int:
    """Parse all known JSON files in a Garmin bulk-export ZIP to Parquet.

    Idempotent: clears existing garmin-*.parquet before writing.
    Returns total samples written.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("garmin-*.parquet"):
        old.unlink()

    rows_by_partition: dict[str, list[dict]] = defaultdict(list)
    n_total = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith("DI_CONNECT/DI-Connect-Aggregator/UDSFile_") and name.endswith(".json"):
                samples = list(_iter_from_zip_member(zf, name, iter_uds_samples))
            elif name.startswith("DI_CONNECT/DI-Connect-Wellness/") and name.endswith("_sleepData.json"):
                samples = list(_iter_from_zip_member(zf, name, iter_sleep_samples))
            elif name.endswith("_userBioMetrics.json") and "DI-Connect-Wellness" in name:
                samples = list(_iter_from_zip_member(zf, name, iter_biometric_samples))
            else:
                continue
            for s in samples:
                partition = s["ts"][:7]
                s = {**s, "meta": json.dumps(s["meta"])}
                rows_by_partition[partition].append(s)
                n_total += 1

    if not rows_by_partition:
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
    for partition, samples in rows_by_partition.items():
        table = pa.Table.from_pylist(samples, schema=schema)
        pq.write_table(table, outdir / f"garmin-{partition}.parquet")
    return n_total


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Parse Garmin bulk-export ZIP to Parquet.")
    ap.add_argument("zip", type=Path, help="path to garmin_export.zip")
    ap.add_argument("--outdir", type=Path, default=Path("data/parquet/samples"))
    args = ap.parse_args()
    n = parse_zip_to_parquet(args.zip, args.outdir)
    print(f"Wrote {n:,} Garmin samples to {args.outdir}/garmin-*.parquet")


if __name__ == "__main__":
    _cli()
