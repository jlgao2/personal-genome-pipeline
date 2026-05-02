# HealthKit Longitudinal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse the user's Apple Health `export.xml` (~427 MB) into Parquet, query it with DuckDB, and add a "Vitals" section to the dashboard with genotype-driven target overlays.

**Architecture:** Streaming XML parser → partitioned Parquet under `data/parquet/samples/` → DuckDB-backed build step that emits a `data-vitals.js` module → dashboard reads it alongside existing `data.js`. Genotype-driven targets (e.g., 9p21 risk → BP <120/80) are hard-coded in code for v1; later moved to `cross_refs.parquet`.

**Tech Stack:** Python 3.12 (stdlib `xml.etree.iterparse` for streaming), `duckdb` + `pyarrow` for Parquet, vanilla JS + inline SVG sparklines on the dashboard, `pytest` for tests.

---

## File structure

```
data/raw/healthkit/export.zip                          (already on disk)
data/raw/healthkit/apple_health_export/export.xml      (extracted)
data/parquet/samples/healthkit-YYYY-MM.parquet         (output)

pipeline/parsers/__init__.py                           (new package)
pipeline/parsers/healthkit.py                          (new)
pipeline/parsers/healthkit_types.py                    (new — type-mapping table)
pipeline/build_vitals.py                               (new)
pipeline/refresh.sh                                    (new)

tests/parsers/test_healthkit.py                        (new)
tests/parsers/fixtures/healthkit_sample.xml            (new — small synthetic XML)
tests/parsers/fixtures/healthkit_sample.expected.json  (new)

docs/web/index.html                                    (modify — add Vitals section)
docs/web/css/layout.css                                (modify — add sparkline styles)
docs/web/js/main.js                                    (modify — render Vitals)
docs/web/js/data-vitals.js                             (new — generated from Parquet)

docs/superpowers/plans/2026-05-01-healthkit-longitudinal.md (this file)
```

Each parser file is small and single-purpose: `healthkit_types.py` is just the type-mapping dictionary; `healthkit.py` is the XML stream + Parquet writer; `build_vitals.py` is the DuckDB query layer.

---

## Task 1 — Install dependencies + smoke-test

**Files:**
- Modify: `pipeline/00_setup.sh:50-55` (add duckdb + pyarrow to pip install)
- Create: `tests/test_smoke_duckdb.py`

- [ ] **Step 1: Add deps to setup script**

Edit `pipeline/00_setup.sh`. Find the line beginning with `pip3 install --quiet pandas numpy pysam myvariant cyvcf2 requests` and add `duckdb pyarrow` to the package list:

```bash
pip3 install --quiet pandas numpy pysam myvariant cyvcf2 requests duckdb pyarrow 2>&1 | tail -3 || true
```

- [ ] **Step 2: Install the new deps**

```bash
pip3 install duckdb pyarrow
```

Expected: `Successfully installed duckdb-X.Y.Z pyarrow-A.B.C`.

- [ ] **Step 3: Write smoke test**

Create `tests/test_smoke_duckdb.py`:

```python
"""Verify duckdb + pyarrow round-trip a tiny dataset to Parquet."""
import tempfile
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


def test_parquet_round_trip():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "smoke.parquet"
        table = pa.table({"x": [1, 2, 3], "y": ["a", "b", "c"]})
        pq.write_table(table, out)
        rows = duckdb.query(f"select count(*) as n from '{out}'").fetchone()
        assert rows[0] == 3
```

- [ ] **Step 4: Run smoke test**

```bash
pytest tests/test_smoke_duckdb.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/00_setup.sh tests/test_smoke_duckdb.py
git commit -m "Add duckdb + pyarrow deps with smoke-test"
```

---

## Task 2 — Create `data/parquet/` directory layout

**Files:**
- Modify: `.gitignore` (already excludes `data/`)

- [ ] **Step 1: Create directories**

```bash
mkdir -p data/parquet/samples data/parquet/events
touch data/parquet/.keep data/parquet/samples/.keep data/parquet/events/.keep
```

- [ ] **Step 2: Verify .gitignore still excludes them**

```bash
git check-ignore -v data/parquet/samples/.keep
```

Expected output: line referencing the `data/` rule, confirming the path is ignored.

- [ ] **Step 3: No commit needed**

The `data/` directory is already gitignored. Skip commit; this is local-only setup.

---

## Task 3 — Type mapping table for HealthKit identifiers

**Files:**
- Create: `pipeline/parsers/__init__.py`
- Create: `pipeline/parsers/healthkit_types.py`
- Test: `tests/parsers/test_healthkit_types.py`

- [ ] **Step 1: Create empty package init**

Create `pipeline/parsers/__init__.py`:

```python
"""Parsers for converting raw external data sources into Parquet samples/events."""
```

- [ ] **Step 2: Write failing test**

Create `tests/parsers/test_healthkit_types.py`:

```python
from pipeline.parsers.healthkit_types import normalize_type, KNOWN_TYPES


def test_known_types_normalize():
    assert normalize_type("HKQuantityTypeIdentifierHeartRate") == "heart_rate"
    assert normalize_type("HKQuantityTypeIdentifierRestingHeartRate") == "heart_rate_resting"
    assert normalize_type("HKQuantityTypeIdentifierVO2Max") == "vo2max"
    assert normalize_type("HKQuantityTypeIdentifierBodyMass") == "weight"
    assert normalize_type("HKCategoryTypeIdentifierSleepAnalysis") == "sleep_stage"


def test_unknown_type_returns_none():
    assert normalize_type("HKQuantityTypeIdentifierUnknownSomething") is None


def test_known_types_set_nonempty():
    assert len(KNOWN_TYPES) > 15
```

- [ ] **Step 3: Run test, confirm it fails**

```bash
pytest tests/parsers/test_healthkit_types.py -v
```

Expected: ImportError on the missing module.

- [ ] **Step 4: Implement the mapping**

Create `pipeline/parsers/healthkit_types.py`:

```python
"""Mapping from Apple HealthKit identifier strings to our normalized type vocabulary.

Only the types we want to ingest are listed. Everything else is silently dropped
by `normalize_type` returning None.
"""
from typing import Optional

# Curated subset — these are the types worth surfacing on the dashboard.
# Others (e.g., HKQuantityTypeIdentifierDietaryProtein) can be added later.
HEALTHKIT_TYPE_MAP: dict[str, str] = {
    # Cardiovascular
    "HKQuantityTypeIdentifierHeartRate":                 "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate":          "heart_rate_resting",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage":   "heart_rate_walking_avg",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":  "hrv_sdnn",
    "HKQuantityTypeIdentifierVO2Max":                    "vo2max",
    "HKQuantityTypeIdentifierBloodPressureSystolic":     "bp_systolic",
    "HKQuantityTypeIdentifierBloodPressureDiastolic":    "bp_diastolic",

    # Body composition
    "HKQuantityTypeIdentifierBodyMass":                  "weight",
    "HKQuantityTypeIdentifierBodyMassIndex":             "bmi",
    "HKQuantityTypeIdentifierBodyFatPercentage":         "body_fat_pct",
    "HKQuantityTypeIdentifierLeanBodyMass":              "lean_body_mass",

    # Activity
    "HKQuantityTypeIdentifierStepCount":                 "steps",
    "HKQuantityTypeIdentifierDistanceWalkingRunning":    "distance_walking_running",
    "HKQuantityTypeIdentifierActiveEnergyBurned":        "active_energy",
    "HKQuantityTypeIdentifierBasalEnergyBurned":         "basal_energy",
    "HKQuantityTypeIdentifierAppleExerciseTime":         "exercise_minutes",
    "HKQuantityTypeIdentifierAppleStandHour":            "stand_hours",
    "HKQuantityTypeIdentifierFlightsClimbed":            "flights_climbed",

    # Respiration / metabolic
    "HKQuantityTypeIdentifierRespiratoryRate":           "respiratory_rate",
    "HKQuantityTypeIdentifierOxygenSaturation":          "spo2",
    "HKQuantityTypeIdentifierBodyTemperature":           "body_temp",
    "HKQuantityTypeIdentifierBloodGlucose":              "blood_glucose",

    # Sleep
    "HKCategoryTypeIdentifierSleepAnalysis":             "sleep_stage",

    # Mindfulness
    "HKCategoryTypeIdentifierMindfulSession":            "mindful_minutes",
}

KNOWN_TYPES = frozenset(HEALTHKIT_TYPE_MAP.values())


def normalize_type(hk_identifier: str) -> Optional[str]:
    """Map an Apple HealthKit type identifier to our normalized name, or None."""
    return HEALTHKIT_TYPE_MAP.get(hk_identifier)
```

- [ ] **Step 5: Run tests, confirm they pass**

```bash
pytest tests/parsers/test_healthkit_types.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/parsers/ tests/parsers/test_healthkit_types.py
git commit -m "Add HealthKit type-mapping table"
```

---

## Task 4 — Synthetic test fixture

**Files:**
- Create: `tests/parsers/fixtures/healthkit_sample.xml`
- Create: `tests/parsers/fixtures/__init__.py`

- [ ] **Step 1: Create fixtures package init**

```bash
touch tests/parsers/fixtures/__init__.py
```

- [ ] **Step 2: Write a tiny synthetic Apple Health export**

Create `tests/parsers/fixtures/healthkit_sample.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [<!ELEMENT HealthData (ExportDate,Me,Record*,Workout*)>]>
<HealthData locale="en_US">
 <ExportDate value="2026-05-01 12:00:00 -0500"/>
 <Me HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale"
     HKCharacteristicTypeIdentifierDateOfBirth="1998-03-14"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch"
         unit="count/min"
         startDate="2026-04-01 08:00:00 -0500" endDate="2026-04-01 08:00:01 -0500"
         value="62"/>
 <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch"
         unit="count/min"
         startDate="2026-04-01 08:01:00 -0500" endDate="2026-04-01 08:01:01 -0500"
         value="65"/>
 <Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="Apple Watch"
         unit="count/min"
         startDate="2026-04-01 06:00:00 -0500" endDate="2026-04-01 06:00:00 -0500"
         value="58"/>
 <Record type="HKQuantityTypeIdentifierVO2Max" sourceName="Apple Watch"
         unit="mL/min·kg"
         startDate="2026-04-15 10:00:00 -0500" endDate="2026-04-15 10:00:00 -0500"
         value="42.5"/>
 <Record type="HKQuantityTypeIdentifierBodyMass" sourceName="Health"
         unit="lb"
         startDate="2026-04-20 07:00:00 -0500" endDate="2026-04-20 07:00:00 -0500"
         value="142.5"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch"
         startDate="2026-04-21 23:30:00 -0500" endDate="2026-04-22 06:45:00 -0500"
         value="HKCategoryValueSleepAnalysisAsleepCore"/>
 <Record type="HKQuantityTypeIdentifierUnknownDoNotImport" sourceName="X"
         unit="x" startDate="2026-04-01 00:00:00 -0500" endDate="2026-04-01 00:00:00 -0500"
         value="1"/>
</HealthData>
```

- [ ] **Step 3: Verify the fixture is valid XML**

```bash
python -c "import xml.etree.ElementTree as ET; ET.parse('tests/parsers/fixtures/healthkit_sample.xml')"
```

Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add tests/parsers/fixtures/
git commit -m "Add synthetic HealthKit XML fixture for parser tests"
```

---

## Task 5 — Streaming XML parser (test-driven)

**Files:**
- Create: `pipeline/parsers/healthkit.py`
- Test: `tests/parsers/test_healthkit.py`

- [ ] **Step 1: Write failing test**

Create `tests/parsers/test_healthkit.py`:

```python
from pathlib import Path

from pipeline.parsers.healthkit import iter_samples

FIXTURE = Path(__file__).parent / "fixtures" / "healthkit_sample.xml"


def test_iter_samples_yields_known_records_only():
    samples = list(iter_samples(FIXTURE))
    types_seen = {s["type"] for s in samples}
    # Unknown identifier was filtered out
    assert "unknown_do_not_import" not in types_seen
    assert "heart_rate" in types_seen
    assert "vo2max" in types_seen
    assert "weight" in types_seen
    assert "sleep_stage" in types_seen
    assert len(samples) == 7  # 8 in fixture, 1 unknown dropped


def test_iter_samples_value_types():
    samples = list(iter_samples(FIXTURE))
    sleep = next(s for s in samples if s["type"] == "sleep_stage")
    assert sleep["value"] is None  # category records have no numeric value
    assert sleep["meta"]["category_value"] == "HKCategoryValueSleepAnalysisAsleepCore"

    hr = next(s for s in samples if s["type"] == "heart_rate")
    assert hr["value"] == 62.0
    assert hr["unit"] == "count/min"


def test_iter_samples_returns_iso_timestamps():
    samples = list(iter_samples(FIXTURE))
    s = samples[0]
    # Should be ISO-8601 string with timezone offset
    assert s["ts"].startswith("2026-")
    assert "+" in s["ts"] or "-" in s["ts"][10:]
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
pytest tests/parsers/test_healthkit.py -v
```

Expected: `ImportError: cannot import name 'iter_samples' from 'pipeline.parsers.healthkit'`.

- [ ] **Step 3: Implement the streaming parser**

Create `pipeline/parsers/healthkit.py`:

```python
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
    # Apple uses space between date and time; stdlib expects 'T' or accepts space
    # since Python 3.7 with %z. Normalize timezone "-0500" → "-05:00".
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

        # Quantity records have a numeric value; category records (sleep)
        # use the value attribute as a string identifier.
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
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
pytest tests/parsers/test_healthkit.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/healthkit.py tests/parsers/test_healthkit.py
git commit -m "Add streaming HealthKit XML parser with iterparse"
```

---

## Task 6 — Parquet writer (partitioned by year-month)

**Files:**
- Modify: `pipeline/parsers/healthkit.py` (add `parse_to_parquet` function)
- Test: `tests/parsers/test_healthkit_parquet.py`

- [ ] **Step 1: Write failing test**

Create `tests/parsers/test_healthkit_parquet.py`:

```python
import json
import tempfile
from pathlib import Path

import duckdb

from pipeline.parsers.healthkit import parse_to_parquet

FIXTURE = Path(__file__).parent / "fixtures" / "healthkit_sample.xml"


def test_parse_to_parquet_writes_partitioned_files():
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        n_written = parse_to_parquet(FIXTURE, outdir)
        # 7 known records in the fixture
        assert n_written == 7
        # All records in fixture are April 2026
        files = list(outdir.glob("healthkit-2026-04.parquet"))
        assert len(files) == 1


def test_parse_to_parquet_round_trip_via_duckdb():
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        parse_to_parquet(FIXTURE, outdir)
        rows = duckdb.query(
            f"select type, count(*) as n from '{outdir}/healthkit-*.parquet' "
            f"group by type order by type"
        ).fetchall()
        type_counts = dict(rows)
        assert type_counts["heart_rate"] == 2
        assert type_counts["heart_rate_resting"] == 1
        assert type_counts["sleep_stage"] == 1
        assert type_counts["vo2max"] == 1
        assert type_counts["weight"] == 1


def test_parse_to_parquet_idempotent():
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        parse_to_parquet(FIXTURE, outdir)
        parse_to_parquet(FIXTURE, outdir)  # second run must REPLACE not append
        n = duckdb.query(
            f"select count(*) as n from '{outdir}/healthkit-*.parquet'"
        ).fetchone()[0]
        assert n == 7  # not 14
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
pytest tests/parsers/test_healthkit_parquet.py -v
```

Expected: ImportError on `parse_to_parquet`.

- [ ] **Step 3: Implement the writer**

Append to `pipeline/parsers/healthkit.py`:

```python
import json
from collections import defaultdict

import pyarrow as pa
import pyarrow.parquet as pq


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
            ("source", pa.string()),
            ("type",   pa.string()),
            ("value",  pa.float64()),
            ("unit",   pa.string()),
            ("meta",   pa.string()),
        ]))
        pq.write_table(table, outdir / f"healthkit-{partition}.parquet")

    return n_total
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
pytest tests/parsers/test_healthkit_parquet.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/healthkit.py tests/parsers/test_healthkit_parquet.py
git commit -m "Write HealthKit samples to partitioned Parquet (idempotent)"
```

---

## Task 7 — CLI entry point

**Files:**
- Modify: `pipeline/parsers/healthkit.py` (add `if __name__ == "__main__"` block)

- [ ] **Step 1: Add CLI block to the parser**

Append to `pipeline/parsers/healthkit.py`:

```python
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
```

- [ ] **Step 2: Extract the user's real export.zip**

```bash
cd data/raw/healthkit && unzip -oq export.zip && ls apple_health_export/ | head -3
```

Expected: directory listing including `export.xml` and `workout-routes/`.

- [ ] **Step 3: Run the parser on real data**

```bash
python -m pipeline.parsers.healthkit \
    data/raw/healthkit/apple_health_export/export.xml \
    --outdir data/parquet/samples
```

Expected output (single line): `Wrote NNN,NNN samples to data/parquet/samples/healthkit-*.parquet`.
Run time: ~30-90 seconds for a 427 MB file.

- [ ] **Step 4: Spot-check the output**

```bash
duckdb -c "select type, count(*) as n
           from 'data/parquet/samples/healthkit-*.parquet'
           group by type order by n desc limit 12"
```

Expected: rows showing `heart_rate` with the largest count, then `steps`, `active_energy`, etc.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/healthkit.py
git commit -m "Add CLI entry point for healthkit parser"
```

---

## Task 8 — Vitals query layer (DuckDB)

**Files:**
- Create: `pipeline/build_vitals.py`
- Test: `tests/test_build_vitals.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_build_vitals.py`:

```python
import json
import tempfile
from pathlib import Path

from pipeline.parsers.healthkit import parse_to_parquet
from pipeline.build_vitals import build_vitals

FIXTURE = Path(__file__).parent / "parsers" / "fixtures" / "healthkit_sample.xml"


def test_build_vitals_returns_expected_keys():
    with tempfile.TemporaryDirectory() as td:
        parquet_dir = Path(td)
        parse_to_parquet(FIXTURE, parquet_dir)
        vitals = build_vitals(parquet_dir)

        # Each known type should have a section
        assert "heart_rate_resting" in vitals
        assert "vo2max" in vitals
        assert "weight" in vitals

        # Each section has a series of (date, value) tuples
        rhr = vitals["heart_rate_resting"]
        assert "series" in rhr
        assert "latest" in rhr
        assert "trend" in rhr  # "up" | "down" | "flat" | None
        assert rhr["latest"] == 58.0


def test_build_vitals_handles_missing_type():
    with tempfile.TemporaryDirectory() as td:
        parquet_dir = Path(td)
        parse_to_parquet(FIXTURE, parquet_dir)
        vitals = build_vitals(parquet_dir)
        # Fixture has no blood pressure
        assert "bp_systolic" not in vitals or vitals.get("bp_systolic") is None
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
pytest tests/test_build_vitals.py -v
```

Expected: ImportError on `build_vitals`.

- [ ] **Step 3: Implement the builder**

Create `pipeline/build_vitals.py`:

```python
"""Query the Parquet store for dashboard-ready Vitals data.

Each Vital is a small dict with:
  - series:  list of [iso-date-string, value] pairs
  - latest:  most recent value
  - trend:   'up' | 'down' | 'flat' | None  (last 30d slope direction)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb

# Vitals we surface on the dashboard. Each entry is a query that reduces the
# raw samples to one daily value (avg/min/max/sum depending on the metric).
VITAL_QUERIES: dict[str, str] = {
    "heart_rate_resting": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, avg(value) AS v
        FROM   read_parquet('{parquet}/healthkit-*.parquet', union_by_name=true)
        WHERE  type = 'heart_rate_resting' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
    "vo2max": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, max(value) AS v
        FROM   read_parquet('{parquet}/healthkit-*.parquet', union_by_name=true)
        WHERE  type = 'vo2max' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
    "weight": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, avg(value) AS v
        FROM   read_parquet('{parquet}/healthkit-*.parquet', union_by_name=true)
        WHERE  type = 'weight' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
    "bp_systolic": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, avg(value) AS v
        FROM   read_parquet('{parquet}/healthkit-*.parquet', union_by_name=true)
        WHERE  type = 'bp_systolic' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
    "bp_diastolic": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, avg(value) AS v
        FROM   read_parquet('{parquet}/healthkit-*.parquet', union_by_name=true)
        WHERE  type = 'bp_diastolic' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
    "sleep_minutes": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d,
               sum(epoch(ts_end::TIMESTAMP - ts::TIMESTAMP) / 60.0) AS v
        FROM   read_parquet('{parquet}/healthkit-*.parquet', union_by_name=true)
        WHERE  type = 'sleep_stage' AND value IS NULL
        GROUP BY d ORDER BY d
    """,
    "exercise_minutes": """
        SELECT date_trunc('day', ts::TIMESTAMP)::DATE AS d, sum(value) AS v
        FROM   read_parquet('{parquet}/healthkit-*.parquet', union_by_name=true)
        WHERE  type = 'exercise_minutes' AND value IS NOT NULL
        GROUP BY d ORDER BY d
    """,
}


def _trend_of(series: list[tuple]) -> Optional[str]:
    """Return 'up'|'down'|'flat'|None based on simple linear slope of last 30 points."""
    if len(series) < 5:
        return None
    tail = series[-30:]
    n = len(tail)
    xs = list(range(n))
    ys = [v for _, v in tail]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return "flat"
    slope = num / den
    range_y = max(ys) - min(ys) or 1
    rel = slope / range_y
    if rel > 0.01:
        return "up"
    if rel < -0.01:
        return "down"
    return "flat"


def build_vitals(parquet_dir: Path) -> dict:
    """Return a dict keyed by vital name, each entry shaped for the dashboard."""
    out: dict = {}
    parquet_str = str(parquet_dir).rstrip("/")
    # Include only vital queries whose Parquet has matching rows
    for name, query in VITAL_QUERIES.items():
        try:
            rows = duckdb.query(query.format(parquet=parquet_str)).fetchall()
        except duckdb.Error:
            continue
        if not rows:
            continue
        series = [[d.isoformat() if hasattr(d, "isoformat") else str(d), float(v)] for d, v in rows]
        out[name] = {
            "series": series,
            "latest": series[-1][1] if series else None,
            "trend":  _trend_of([(d, v) for d, v in series]),
        }
    return out
```

- [ ] **Step 4: Sleep-stage edge case — fix the SQL**

Sleep records have no numeric `value` column; the test will fail because `sleep_minutes` query references `ts_end` which the Parquet schema doesn't have. Re-write the parser to ALSO emit `ts_end` for category records.

Edit `pipeline/parsers/healthkit.py` — modify the schema in `parse_to_parquet`:

```python
        table = pa.Table.from_pylist(samples, schema=pa.schema([
            ("ts",     pa.string()),
            ("ts_end", pa.string()),
            ("source", pa.string()),
            ("type",   pa.string()),
            ("value",  pa.float64()),
            ("unit",   pa.string()),
            ("meta",   pa.string()),
        ]))
```

And modify `iter_samples` to capture `endDate`:

```python
        end_date = elem.get("endDate")
        try:
            ts_end = _parse_apple_date(end_date) if end_date else ts
        except ValueError:
            ts_end = ts
        ...
        yield {
            "ts":     ts,
            "ts_end": ts_end,
            "source": "healthkit",
            ...
        }
```

Update the existing `iter_samples` test to assert `ts_end` is present.

- [ ] **Step 5: Run tests, confirm all pass**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pipeline/build_vitals.py pipeline/parsers/healthkit.py tests/test_build_vitals.py tests/parsers/test_healthkit.py
git commit -m "Add Vitals DuckDB query layer with trend detection"
```

---

## Task 9 — Generate `data-vitals.js` from query results

**Files:**
- Modify: `pipeline/build_vitals.py` (add JS-emit function + CLI)
- Test: `tests/test_build_vitals_js.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_build_vitals_js.py`:

```python
import json
import re
import tempfile
from pathlib import Path

from pipeline.parsers.healthkit import parse_to_parquet
from pipeline.build_vitals import write_vitals_js

FIXTURE = Path(__file__).parent / "parsers" / "fixtures" / "healthkit_sample.xml"


def test_write_vitals_js_emits_valid_es_module():
    with tempfile.TemporaryDirectory() as td:
        parquet_dir = Path(td) / "parquet"
        out_js = Path(td) / "data-vitals.js"
        parse_to_parquet(FIXTURE, parquet_dir)
        write_vitals_js(parquet_dir, out_js)

        content = out_js.read_text()
        assert content.startswith("/* AUTO-GENERATED")
        assert "export const VITALS" in content

        # Extract the JSON literal after `=` and verify it parses.
        match = re.search(r"export const VITALS\s*=\s*(\{.*\});", content, re.S)
        assert match
        data = json.loads(match.group(1))
        assert "heart_rate_resting" in data
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
pytest tests/test_build_vitals_js.py -v
```

Expected: ImportError on `write_vitals_js`.

- [ ] **Step 3: Implement the JS emitter**

Append to `pipeline/build_vitals.py`:

```python
import json as _json


def write_vitals_js(parquet_dir: Path, out_path: Path) -> None:
    """Build vitals dict and emit as an ES module the dashboard imports."""
    vitals = build_vitals(parquet_dir)
    payload = _json.dumps(vitals, indent=2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "/* AUTO-GENERATED by pipeline/build_vitals.py — do not edit by hand. */\n"
        f"export const VITALS = {payload};\n"
    )


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Build data-vitals.js from Parquet samples.")
    ap.add_argument("--parquet", type=Path, default=Path("data/parquet/samples"))
    ap.add_argument("--out",     type=Path, default=Path("output/web/js/data-vitals.js"))
    args = ap.parse_args()
    write_vitals_js(args.parquet, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    _cli()
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
pytest tests/test_build_vitals_js.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Generate against real data**

```bash
mkdir -p output/web/js
python -m pipeline.build_vitals \
    --parquet data/parquet/samples \
    --out output/web/js/data-vitals.js
head -5 output/web/js/data-vitals.js
```

Expected: file with `/* AUTO-GENERATED ...` comment then `export const VITALS = { "heart_rate_resting": ...`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/build_vitals.py tests/test_build_vitals_js.py
git commit -m "Emit data-vitals.js from Parquet via DuckDB"
```

---

## Task 10 — Vitals section in dashboard HTML

**Files:**
- Modify: `output/web/index.html` (add `<section id="vitals">` + sidebar nav entry)

> Note: `output/web/` is the **private** dashboard, not `docs/web/`. Public demo gets its own synthetic vitals later.

- [ ] **Step 1: Make sure output/web/ exists**

```bash
[ -d output/web ] || cp -r docs output/web && rm -rf output/web/superpowers
ls output/web/
```

Expected: `index.html  css/  js/`.

- [ ] **Step 2: Add nav entry**

Edit `output/web/index.html`. In the `<aside class="rail">` section, find the "Findings" `<ul class="nav-sections">` block (near the top of the rail). Insert a new `<li>` for vitals immediately after the PRS button:

```html
        <li><button class="nav-btn" data-section="vitals" data-num="07a">Vitals</button></li>
```

Renumber the subsequent `data-num` attributes if needed (keep the numbers monotonic).

- [ ] **Step 3: Add the Vitals section markup**

In `output/web/index.html`, immediately after the `</section>` that ends the existing PRS section, insert:

```html
  <!-- Vitals (HealthKit) -->
  <section class="section" id="vitals">
    <p class="section-kicker">Longitudinal · HealthKit</p>
    <h2 class="section-title">Vitals</h2>
    <p class="section-lead">
      Live time-series from your Apple Health export. Each chart is annotated
      with the genotype-driven target where one applies. Hover any chart for the
      most recent value and trend.
    </p>
    <div class="vitals-grid" id="vitals-grid"></div>
  </section>
```

- [ ] **Step 4: Bump cache version**

In the `<head>`, increment all `?v=20260430l` occurrences to `?v=20260501a`.

- [ ] **Step 5: Verify HTML still parses**

```bash
python -c "from html.parser import HTMLParser; \
           p=HTMLParser(); p.feed(open('output/web/index.html').read())"
```

Expected: no error.

- [ ] **Step 6: Commit**

```bash
git add output/web/index.html
git commit -m "Add Vitals section markup + nav entry to private dashboard"
```

---

## Task 11 — Vitals CSS (sparkline + card grid)

**Files:**
- Modify: `output/web/css/layout.css`

- [ ] **Step 1: Add Vitals styles**

Append to `output/web/css/layout.css`:

```css
/* ── Vitals (HealthKit time-series cards) ── */
.vitals-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  margin-bottom: 1.5rem;
}
.vital-card {
  background: var(--bg-card);
  padding: 1rem 1.1rem 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  position: relative;
}
.vital-card-name {
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--fg-dim);
}
.vital-card-value {
  font-family: var(--font-display);
  font-size: 2.2rem;
  font-weight: 500;
  font-style: italic;
  letter-spacing: 0;
  color: var(--fg);
  line-height: 1;
}
.vital-card-unit {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--fg-dim);
  margin-left: 0.4em;
}
.vital-card-trend {
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}
.vital-card-trend[data-trend="up"]   { color: var(--rune); }
.vital-card-trend[data-trend="down"] { color: var(--accent); }
.vital-card-trend[data-trend="flat"] { color: var(--fg-dim); }

.vital-spark {
  width: 100%;
  height: 56px;
  display: block;
  margin-top: 0.4rem;
}
.vital-spark-line {
  fill: none;
  stroke: var(--accent);
  stroke-width: 1.2;
  filter: drop-shadow(0 0 4px var(--accent-glow));
}
.vital-spark-target {
  stroke: var(--rune);
  stroke-width: 0.8;
  stroke-dasharray: 3 3;
  opacity: 0.7;
}
.vital-spark-target-label {
  font-family: var(--font-mono);
  font-size: 7px;
  fill: var(--rune);
  letter-spacing: 0.1em;
}

.vital-card-target {
  font-family: var(--font-mono);
  font-size: 0.55rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--rune);
  border-top: 1px solid var(--border);
  padding-top: 0.55rem;
  margin-top: 0.3rem;
}
```

- [ ] **Step 2: Spot-check no syntax error**

```bash
python -c "import re; \
           s=open('output/web/css/layout.css').read(); \
           assert s.count('{') == s.count('}'), 'unbalanced braces'"
```

Expected: no output (success).

- [ ] **Step 3: Commit**

```bash
git add output/web/css/layout.css
git commit -m "Add Vitals card + sparkline styles"
```

---

## Task 12 — Vitals render function in JS

**Files:**
- Modify: `output/web/js/main.js` (add `renderVitals` + import + call)

- [ ] **Step 1: Add import for VITALS at top of main.js**

Edit `output/web/js/main.js`. Below the existing `import { ... } from './data.js?v=...'`, add:

```js
import { VITALS } from './data-vitals.js?v=20260501a';
import { VITAL_TARGETS } from './vitals-targets.js?v=20260501a';
```

- [ ] **Step 2: Add renderVitals function**

Find the `renderProtocol` function. Immediately above it, insert:

```js
/* ── Render Vitals (HealthKit time-series cards) ── */
const VITAL_DISPLAY = {
  heart_rate_resting: { label: "Resting HR",    unit: "bpm",        decimals: 0 },
  vo2max:             { label: "VO₂ Max",       unit: "mL/min·kg",  decimals: 1 },
  weight:             { label: "Weight",        unit: "kg",         decimals: 1 },
  bp_systolic:        { label: "BP Systolic",   unit: "mmHg",       decimals: 0 },
  bp_diastolic:       { label: "BP Diastolic",  unit: "mmHg",       decimals: 0 },
  sleep_minutes:      { label: "Sleep",         unit: "min/night",  decimals: 0 },
  exercise_minutes:   { label: "Exercise",      unit: "min/day",    decimals: 0 },
};

function vitalSpark(series, target) {
  if (!series || series.length < 2) return "";
  const W = 320, H = 56, PAD = 4;
  const xs = series.map((_, i) => i);
  const ys = series.map(([, v]) => v);
  const minY = Math.min(...ys, target ?? Infinity);
  const maxY = Math.max(...ys, target ?? -Infinity);
  const rangeY = (maxY - minY) || 1;
  const xToPx = i => PAD + (i / (xs.length - 1)) * (W - 2 * PAD);
  const yToPx = v => H - PAD - ((v - minY) / rangeY) * (H - 2 * PAD);

  const pathD = series
    .map(([, v], i) => `${i === 0 ? "M" : "L"} ${xToPx(i).toFixed(1)} ${yToPx(v).toFixed(1)}`)
    .join(" ");

  const targetLine = target != null
    ? `<line class="vital-spark-target" x1="${PAD}" y1="${yToPx(target).toFixed(1)}"
                                         x2="${W - PAD}" y2="${yToPx(target).toFixed(1)}"/>
       <text class="vital-spark-target-label" x="${W - PAD}" y="${yToPx(target).toFixed(1) - 2}"
             text-anchor="end">target ${target}</text>`
    : "";

  return `
    <svg class="vital-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      ${targetLine}
      <path class="vital-spark-line" d="${pathD}"/>
    </svg>
  `;
}

function renderVitals() {
  const root = document.getElementById("vitals-grid");
  if (!root) return;
  if (!VITALS || Object.keys(VITALS).length === 0) {
    root.innerHTML =
      `<p style="padding:1rem; font-family: var(--font-mono); font-size: 0.65rem;
                 color: var(--fg-dim);">
         No HealthKit data yet — drop your export.zip in <code>data/raw/healthkit/</code>
         and run <code>refresh.sh</code>.
       </p>`;
    return;
  }
  const cards = Object.entries(VITALS).map(([key, data]) => {
    const display = VITAL_DISPLAY[key] || { label: key, unit: "", decimals: 1 };
    const target = VITAL_TARGETS[key] || null;
    const fixed = data.latest != null ? data.latest.toFixed(display.decimals) : "—";
    const trendArrow = { up: "↑", down: "↓", flat: "→" }[data.trend] || "";
    return `
      <article class="vital-card">
        <div class="vital-card-name">${display.label}</div>
        <div>
          <span class="vital-card-value">${fixed}</span>
          <span class="vital-card-unit">${display.unit}</span>
        </div>
        ${vitalSpark(data.series, target ? target.value : null)}
        <div class="vital-card-trend" data-trend="${data.trend || 'flat'}">
          ${trendArrow} ${data.trend || "flat"} · last 30d
        </div>
        ${target ? `<div class="vital-card-target">Target: ${target.label}</div>` : ""}
      </article>
    `;
  }).join("");
  root.innerHTML = cards;
}
```

- [ ] **Step 3: Wire renderVitals into the boot sequence**

Find the `DOMContentLoaded` handler (search for `renderProtocol();`). Add `renderVitals();` directly after it:

```js
  renderPRSOverview();
  renderProtocol();
  renderVitals();           // NEW
  renderCrossRef();
```

- [ ] **Step 4: Manually verify the page loads**

```bash
cd output/web && python3 -m http.server 8732 &
sleep 1
curl -sI http://localhost:8732/ | head -1
```

Expected: `HTTP/1.0 200 OK`.

Visit `http://localhost:8732/`, scroll to the new **Vitals** section, confirm cards render and sparklines draw.

Stop the server: `kill %1`.

- [ ] **Step 5: Commit**

```bash
git add output/web/js/main.js
git commit -m "Render Vitals cards with inline-SVG sparklines"
```

---

## Task 13 — Genotype-driven target overlays

**Files:**
- Create: `output/web/js/vitals-targets.js`

> v1: hard-coded targets in JS. A later subsystem (`cross_refs.parquet` builder) will derive these from the user's actual findings.

- [ ] **Step 1: Author the targets module**

Create `output/web/js/vitals-targets.js`:

```js
/* Genotype-driven target overlays for Vitals charts.
 * Eunjung Kim's demo: APOE ε3/ε4 + CAD PRS slightly elevated + HFE compound het.
 * Each target is plotted as a dashed amber line on the corresponding sparkline.
 */
export const VITAL_TARGETS = {
  bp_systolic: {
    value: 120,
    label: "<120 mmHg (CAD PRS + APOE ε4)",
  },
  bp_diastolic: {
    value: 80,
    label: "<80 mmHg (CAD PRS + APOE ε4)",
  },
  heart_rate_resting: {
    value: 60,
    label: "<60 bpm (cardiovascular fitness)",
  },
  vo2max: {
    value: 35,
    label: "≥35 mL/min·kg (CAD PRS — fitness floor)",
  },
  sleep_minutes: {
    value: 420,
    label: "≥7 h (APOE ε4 — amyloid clearance)",
  },
  exercise_minutes: {
    value: 30,
    label: "≥30 min/day (CAD PRS prevention)",
  },
};
```

- [ ] **Step 2: Verify the JS imports cleanly**

Reload `http://localhost:8732/` (start the server again per Task 12 step 4). Check the browser console — there should be no import errors. The Vitals cards should now show a dashed amber line on the sparklines that have a target defined, with a small target label at the right edge.

- [ ] **Step 3: Commit**

```bash
git add output/web/js/vitals-targets.js
git commit -m "Add genotype-driven target overlays for Vitals sparklines"
```

---

## Task 14 — Refresh orchestrator

**Files:**
- Create: `pipeline/refresh.sh`

- [ ] **Step 1: Author refresh.sh**

Create `pipeline/refresh.sh`:

```bash
#!/usr/bin/env bash
# Personal-data pipeline orchestrator.
# Detects which raw inputs changed since last run, runs only the relevant
# parsers, regenerates the dashboard. Each parser is idempotent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG=data/parquet/.last_refresh
mkdir -p data/parquet/samples data/parquet/events output/web/js

echo "═══ Personal data refresh — $(date '+%Y-%m-%d %H:%M:%S')"

# ── HealthKit ──
HK_ZIP=data/raw/healthkit/export.zip
HK_XML=data/raw/healthkit/apple_health_export/export.xml
if [[ -f "$HK_ZIP" ]]; then
    if [[ ! -f "$HK_XML" || "$HK_ZIP" -nt "$HK_XML" ]]; then
        echo "Extracting HealthKit zip..."
        cd data/raw/healthkit && unzip -oq export.zip && cd "$ROOT"
    fi
    if [[ ! -f "$LOG" || "$HK_XML" -nt "$LOG" ]]; then
        echo "Parsing HealthKit XML → Parquet..."
        python3 -m pipeline.parsers.healthkit "$HK_XML" --outdir data/parquet/samples
    else
        echo "HealthKit Parquet up to date."
    fi
fi

# ── Build vitals JS ──
echo "Building data-vitals.js..."
python3 -m pipeline.build_vitals \
    --parquet data/parquet/samples \
    --out output/web/js/data-vitals.js

# ── Mark refresh complete ──
date +%s > "$LOG"
echo "═══ Done. Open output/web/index.html or run: python3 -m http.server 8732 -d output/web"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x pipeline/refresh.sh
```

- [ ] **Step 3: End-to-end smoke**

```bash
bash pipeline/refresh.sh
```

Expected output: lines for each step, ending in "Done." — total runtime under 90 seconds for the 427 MB Apple Health export.

- [ ] **Step 4: Verify the dashboard updated**

```bash
head -3 output/web/js/data-vitals.js
```

Expected: `/* AUTO-GENERATED ...` then `export const VITALS = {...}`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/refresh.sh
git commit -m "Add refresh.sh orchestrator (HealthKit only for now)"
```

---

## Task 15 — README "Bring Your Own Data" section

**Files:**
- Modify: `README.md` (append BYOD section)

- [ ] **Step 1: Append to README**

Add to `README.md` (at the end, before the License/credits section):

```markdown
## Bring Your Own Data (BYOD)

Beyond 23andMe, this pipeline also ingests longitudinal health data. Drop any of
the supported source files into `data/raw/<source>/` and run
`bash pipeline/refresh.sh` — the dashboard will pick up new charts automatically.

### Supported sources

| Source | Where to put it | Status |
|---|---|---|
| **23andMe v5 raw** | `data/raw/genome/genome_*.zip` | ✅ implemented (Phase 1) |
| **Apple HealthKit** | `data/raw/healthkit/export.zip` (the ZIP from Health.app → Profile → "Export All Health Data") | ✅ implemented (Vitals section) |
| **Garmin Connect bulk** | `data/raw/garmin/` (the unzipped bulk export from Garmin Connect → Profile → Account → Export Your Data) | ⏳ planned |
| **Social aggregates** | `data/raw/social/aggregates.parquet` (produced by the separate `social-media-graph` repo, derived signals only — no raw contacts) | ⏳ planned |
| **Clinical labs** | `data/raw/labs/*.csv` (LabCorp/Quest CSV exports) | ⏳ planned |

### What gets parsed

For Apple HealthKit specifically: the parser pulls these record types into the
Vitals section: heart rate (resting, walking-avg, HRV), VO₂ max, blood
pressure, weight, BMI, body fat %, steps, distance, active/basal energy,
exercise minutes, sleep stages, respiratory rate, SpO₂, blood glucose.

Other Apple HealthKit types (e.g., dietary records, mindfulness sessions) are
silently skipped — extending coverage = adding rows to
`pipeline/parsers/healthkit_types.py:HEALTHKIT_TYPE_MAP`.

### Privacy

Real data lives only on your machine — `data/`, `output/`, and the
auto-generated `output/web/js/data-vitals.js` are gitignored. The public
`docs/` site keeps the synthetic Eunjung Kim demo. Nothing personal touches
GitHub unless you explicitly commit it.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Document Bring-Your-Own-Data convention + HealthKit usage"
```

---

## Task 16 — Final sanity check

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass. No deprecation warnings on `pyarrow`/`duckdb`.

- [ ] **Step 2: Re-run refresh end-to-end**

```bash
rm -f data/parquet/.last_refresh
bash pipeline/refresh.sh
```

Expected: full pipeline runs, ends with "Done." in <90 seconds.

- [ ] **Step 3: Visual verification**

```bash
python3 -m http.server 8732 -d output/web &
open http://localhost:8732/
sleep 5
kill %1
```

Verify visually:
- Vitals section renders below PRS
- Sparklines have data
- Trends show up/down/flat with arrow + color
- BP/sleep/HR/VO2max have dashed amber target lines + labels
- Cards animate on scroll-in (existing CSS)

- [ ] **Step 4: Commit any final tweaks**

```bash
git status
# If diff is clean: nothing to commit, plan complete.
# If you found issues during visual check, fix and commit.
```

---

## What's deferred to follow-up plans

- **Sub-1 genome refactor** (move existing `data.js` content into `findings.parquet` + auto-build) — separate plan.
- **Sub-3 Garmin** — separate plan, gated on user receiving the Garmin bulk-export email.
- **Sub-4 social linkage** — separate plan, gated on the `social-media-graph` repo exposing per-day aggregates.
- **Sub-5 CI on synthetic demo** — separate plan; will build `parquet-demo/` files with synthetic Eunjung Kim time-series and run the parser nightly.
- **GPX route visualization** — workout map overlays on Vitals. Code stub already extracts route geometry into Parquet; rendering deferred.
- **fswatch live-refresh** — user opted to defer until after a few weeks of manual `refresh.sh`.
- **Public dashboard demo data** — synthetic vitals-vitals.js for `docs/web/` so the public demo also has Vitals cards.

## Acceptance criteria for this plan

- [ ] User runs `bash pipeline/refresh.sh` once — dashboard's Vitals section populates from real HealthKit data.
- [ ] All 16 tasks committed.
- [ ] `pytest tests/` passes with at least 8 test functions.
- [ ] Re-running `refresh.sh` is idempotent (Parquet files are replaced, not appended).
- [ ] Sparklines show genotype-driven amber target lines for BP, RHR, VO₂max, sleep, exercise.
- [ ] No personal data is in any git commit (verify: `git log --all --full-history -- data/` returns empty).
