from pathlib import Path

import duckdb

from pipeline.parsers.fhir import (
    iter_observation_samples,
    iter_condition_events,
    iter_medication_events,
    parse_bundle_to_parquet,
)
from pipeline.parsers.fhir_types import normalize_loinc

FIXTURE = Path(__file__).parent / "fixtures" / "fhir_bundle_sample.json"


def test_normalize_loinc_known_codes():
    assert normalize_loinc("13457-7") == "ldl_cholesterol"
    assert normalize_loinc("8480-6") == "bp_systolic"
    assert normalize_loinc("13965-9") == "homocysteine"
    assert normalize_loinc("9999-0") is None
    assert normalize_loinc(None) is None


def test_iter_observation_samples_filters_unknown_loinc():
    rows = list(iter_observation_samples(FIXTURE))
    types = {r["type"] for r in rows}
    assert "ldl_cholesterol" in types
    assert "homocysteine" in types
    assert "bp_systolic" in types
    # Made-up LOINC was dropped
    assert len(rows) == 3


def test_iter_observation_value_extracted():
    rows = list(iter_observation_samples(FIXTURE))
    ldl = next(r for r in rows if r["type"] == "ldl_cholesterol")
    assert ldl["value"] == 83.0
    assert ldl["unit"] == "mg/dL"
    assert ldl["source"] == "fhir"


def test_iter_observation_date_only_padded():
    rows = list(iter_observation_samples(FIXTURE))
    bp = next(r for r in rows if r["type"] == "bp_systolic")
    # date-only "2026-03-02" → "2026-03-02T12:00:00+00:00"
    assert bp["ts"].startswith("2026-03-02T")
    assert "+" in bp["ts"][10:]


def test_condition_events_parsed():
    events = list(iter_condition_events(FIXTURE))
    assert len(events) == 1
    htn = events[0]
    assert htn["type"] == "condition"
    assert "hypertension" in htn["label"].lower()
    assert htn["meta"]["icd_codes"] == ["I10"]
    assert htn["meta"]["clinical_status"] == "active"


def test_medication_events_parsed():
    events = list(iter_medication_events(FIXTURE))
    assert len(events) == 1
    med = events[0]
    assert med["type"] == "medication"
    assert "Lisinopril" in med["label"]
    assert med["meta"]["rxnorm"] == "29046"


def test_parse_bundle_to_parquet_round_trip(tmp_path):
    samples_out = tmp_path / "samples"
    events_out  = tmp_path / "events"
    n_s, n_e = parse_bundle_to_parquet(FIXTURE, samples_out, events_out)
    assert n_s == 3   # 3 observations with known LOINC
    assert n_e == 2   # 1 condition + 1 medication

    rows = duckdb.query(
        f"select type, count(*) from '{samples_out}/fhir-*.parquet' group by type"
    ).fetchall()
    types = {r[0] for r in rows}
    assert "ldl_cholesterol" in types

    rows = duckdb.query(
        f"select type, count(*) from '{events_out}/fhir-*.parquet' group by type"
    ).fetchall()
    event_types = {r[0] for r in rows}
    assert "condition" in event_types
    assert "medication" in event_types


def test_parse_bundle_idempotent(tmp_path):
    samples_out = tmp_path / "samples"
    events_out  = tmp_path / "events"
    parse_bundle_to_parquet(FIXTURE, samples_out, events_out)
    parse_bundle_to_parquet(FIXTURE, samples_out, events_out)
    n_samples = duckdb.query(
        f"select count(*) from '{samples_out}/fhir-*.parquet'"
    ).fetchone()[0]
    assert n_samples == 3   # not 6 — idempotent
