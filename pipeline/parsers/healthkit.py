"""Stream-parse Apple HealthKit export.xml into normalized sample dicts.

The export.xml file is large (hundreds of MB for multi-year users), so we use
xml.etree.iterparse and clear elements as we go to keep memory bounded.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterator

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
            "source": "healthkit",
            "type":   normalized,
            "value":  value,
            "unit":   unit,
            "meta":   {k: v for k, v in meta.items() if v is not None},
        }

        elem.clear()  # critical for memory bounds on the real 427 MB file
