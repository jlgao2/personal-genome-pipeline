"""Parse FHIR Bundle JSON (MyChart, Apple Health Records, etc.) into samples + events.

MyChart's "Download My Record" produces a FHIR R4 Bundle. We extract:
  - Observation resources (labs, vitals)         → samples.parquet
  - Condition resources (diagnoses)              → events.parquet (type='condition')
  - MedicationStatement resources                → events.parquet (type='medication')
  - Procedure resources                          → events.parquet (type='procedure')
  - Immunization resources                       → events.parquet (type='immunization')

Sample type normalization uses LOINC codes when present, falling back to display strings.
The fhir_types module maps the most common ones to our normalized vocab.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.parsers.fhir_types import LOINC_TO_TYPE, normalize_loinc


def _bundle_entries(bundle_path: Path) -> Iterator[dict]:
    """Yield each resource from a FHIR Bundle (or directly from a list of resources)."""
    with bundle_path.open() as f:
        doc = json.load(f)
    if isinstance(doc, list):
        for r in doc:
            yield r
        return
    if doc.get("resourceType") == "Bundle":
        for entry in doc.get("entry", []):
            res = entry.get("resource")
            if res:
                yield res
    else:
        # Single resource document
        yield doc


def _normalize_fhir_dt(s: Optional[str]) -> Optional[str]:
    """Best-effort FHIR datetime → ISO-8601 with timezone."""
    if not s:
        return None
    if len(s) == 10:                 # date only — pad to noon UTC
        return f"{s}T12:00:00+00:00"
    if s.endswith("Z"):
        return s.replace("Z", "+00:00")
    if "+" in s[10:] or "-" in s[10:]:
        return s
    return s + "+00:00"


def _observation_value(obs: dict) -> tuple[Optional[float], Optional[str]]:
    """Pull (value, unit) from a FHIR Observation, handling Quantity / valueString."""
    q = obs.get("valueQuantity")
    if q is not None:
        try:
            return float(q.get("value")), q.get("unit")
        except (TypeError, ValueError):
            return None, q.get("unit")
    v = obs.get("valueString")
    if v is not None:
        try:
            return float(v), None
        except (TypeError, ValueError):
            return None, None
    return None, None


def iter_observation_samples(bundle_path: Path) -> Iterator[dict]:
    """Yield sample dicts from FHIR Observation resources (labs + vitals)."""
    for res in _bundle_entries(bundle_path):
        if res.get("resourceType") != "Observation":
            continue
        ts = _normalize_fhir_dt(
            res.get("effectiveDateTime")
            or (res.get("effectivePeriod") or {}).get("start")
            or res.get("issued")
        )
        if not ts:
            continue
        value, unit = _observation_value(res)
        if value is None:
            continue
        # Find a LOINC code (preferred) or fall back to the display text.
        loinc_code = None
        display = None
        for c in (res.get("code") or {}).get("coding", []):
            if c.get("system", "").endswith("loinc.org"):
                loinc_code = c.get("code")
            display = display or c.get("display")
        if not display:
            display = (res.get("code") or {}).get("text")
        normalized = normalize_loinc(loinc_code) if loinc_code else None
        if normalized is None:
            # Skip unknown LOINC codes for now — extending the vocab = adding rows
            # to LOINC_TO_TYPE in fhir_types.py.
            continue
        yield {
            "ts":     ts,
            "ts_end": ts,
            "source": "fhir",
            "type":   normalized,
            "value":  value,
            "unit":   unit,
            "meta":   {
                "loinc_code": loinc_code,
                "display":    display,
                "subject_ref": (res.get("subject") or {}).get("reference"),
            },
        }


def iter_condition_events(bundle_path: Path) -> Iterator[dict]:
    """Yield event dicts (type='condition') from FHIR Condition resources."""
    for res in _bundle_entries(bundle_path):
        if res.get("resourceType") != "Condition":
            continue
        ts_start = _normalize_fhir_dt(
            res.get("onsetDateTime") or res.get("recordedDate")
        )
        if not ts_start:
            continue
        code = res.get("code") or {}
        display = code.get("text") or next(
            (c.get("display") for c in code.get("coding", [])), None
        )
        clinical_status = (res.get("clinicalStatus") or {}).get("text") or \
                          next((c.get("code") for c in (res.get("clinicalStatus") or {}).get("coding", [])), None)
        yield {
            "ts_start": ts_start,
            "ts_end":   ts_start,
            "source":   "fhir",
            "type":     "condition",
            "label":    display or "Condition",
            "meta":     {
                "clinical_status": clinical_status,
                "category":        (res.get("category") or [{}])[0].get("text"),
                "icd_codes":       [c.get("code") for c in code.get("coding", [])
                                    if "icd" in (c.get("system") or "").lower()],
            },
        }


def iter_medication_events(bundle_path: Path) -> Iterator[dict]:
    """Yield event dicts (type='medication') from FHIR MedicationStatement / Request."""
    for res in _bundle_entries(bundle_path):
        rt = res.get("resourceType")
        if rt not in ("MedicationStatement", "MedicationRequest"):
            continue
        ts_start = _normalize_fhir_dt(
            (res.get("effectivePeriod") or {}).get("start")
            or res.get("effectiveDateTime")
            or res.get("dateAsserted")
            or res.get("authoredOn")
        )
        if not ts_start:
            continue
        ts_end = _normalize_fhir_dt(
            (res.get("effectivePeriod") or {}).get("end")
        ) or ts_start
        med = res.get("medicationCodeableConcept") or {}
        label = med.get("text") or next(
            (c.get("display") for c in med.get("coding", [])), "Medication"
        )
        yield {
            "ts_start": ts_start,
            "ts_end":   ts_end,
            "source":   "fhir",
            "type":     "medication",
            "label":    label,
            "meta":     {
                "fhir_type": rt,
                "status":    res.get("status"),
                "rxnorm":    next((c.get("code") for c in med.get("coding", [])
                                   if "rxnorm" in (c.get("system") or "").lower()), None),
            },
        }


def parse_bundle_to_parquet(bundle_path: Path,
                            samples_outdir: Path,
                            events_outdir: Path) -> tuple[int, int]:
    """Parse a FHIR Bundle JSON into samples + events Parquet partitions.

    Idempotent: clears existing fhir-*.parquet in both outdirs before writing.
    Returns (n_samples, n_events).
    """
    samples_outdir.mkdir(parents=True, exist_ok=True)
    events_outdir.mkdir(parents=True, exist_ok=True)
    for old in samples_outdir.glob("fhir-*.parquet"):
        old.unlink()
    for old in events_outdir.glob("fhir-*.parquet"):
        old.unlink()

    samples_by_partition: dict[str, list[dict]] = defaultdict(list)
    events_by_partition:  dict[str, list[dict]] = defaultdict(list)
    n_samples = 0
    n_events  = 0

    for s in iter_observation_samples(bundle_path):
        s = {**s, "meta": json.dumps(s["meta"])}
        samples_by_partition[s["ts"][:7]].append(s)
        n_samples += 1
    for e in iter_condition_events(bundle_path):
        e = {**e, "meta": json.dumps(e["meta"])}
        events_by_partition[e["ts_start"][:7]].append(e)
        n_events += 1
    for e in iter_medication_events(bundle_path):
        e = {**e, "meta": json.dumps(e["meta"])}
        events_by_partition[e["ts_start"][:7]].append(e)
        n_events += 1

    sample_schema = pa.schema([
        ("ts",     pa.string()),
        ("ts_end", pa.string()),
        ("source", pa.string()),
        ("type",   pa.string()),
        ("value",  pa.float64()),
        ("unit",   pa.string()),
        ("meta",   pa.string()),
    ])
    for partition, samples in samples_by_partition.items():
        table = pa.Table.from_pylist(samples, schema=sample_schema)
        pq.write_table(table, samples_outdir / f"fhir-{partition}.parquet")

    event_schema = pa.schema([
        ("ts_start", pa.string()),
        ("ts_end",   pa.string()),
        ("source",   pa.string()),
        ("type",     pa.string()),
        ("label",    pa.string()),
        ("meta",     pa.string()),
    ])
    for partition, events in events_by_partition.items():
        table = pa.Table.from_pylist(events, schema=event_schema)
        pq.write_table(table, events_outdir / f"fhir-{partition}.parquet")

    return n_samples, n_events


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Parse a FHIR Bundle JSON to Parquet.")
    ap.add_argument("bundle", type=Path, help="path to FHIR Bundle JSON (MyChart export)")
    ap.add_argument("--samples-outdir", type=Path, default=Path("data/parquet/samples"))
    ap.add_argument("--events-outdir",  type=Path, default=Path("data/parquet/events"))
    args = ap.parse_args()
    n_s, n_e = parse_bundle_to_parquet(args.bundle, args.samples_outdir, args.events_outdir)
    print(f"Wrote {n_s:,} observations + {n_e:,} events from {args.bundle.name}")


if __name__ == "__main__":
    _cli()
