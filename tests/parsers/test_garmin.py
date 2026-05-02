from pathlib import Path

from pipeline.parsers.garmin import (
    iter_uds_samples, iter_sleep_samples, iter_biometric_samples,
)
from pipeline.parsers.garmin_types import normalize_uds

UDS_FIXTURE   = Path(__file__).parent / "fixtures" / "garmin_uds_sample.json"
SLEEP_FIXTURE = Path(__file__).parent / "fixtures" / "garmin_sleep_sample.json"
BIO_FIXTURE   = Path(__file__).parent / "fixtures" / "garmin_biometrics_sample.json"


def test_normalize_uds_known_fields():
    assert normalize_uds("minAvgHeartRate") == ("heart_rate_resting", "bpm")
    assert normalize_uds("vigorousIntensityMinutes") == ("vigorous_minutes", "min")
    assert normalize_uds("madeUpField") is None


def test_iter_uds_samples_yields_one_per_known_field_per_day():
    rows = list(iter_uds_samples(UDS_FIXTURE))
    types = {r["type"] for r in rows}
    assert "heart_rate_resting" in types
    assert "heart_rate_min_daily" in types
    assert "vigorous_minutes" in types
    # 2 days × 7 mapped fields = 14 rows
    assert len(rows) == 14
    rhr = [r for r in rows if r["type"] == "heart_rate_resting"]
    assert {r["value"] for r in rhr} == {51.0, 50.0}
    assert all(r["source"] == "garmin" for r in rows)


def test_sleep_parser_emits_stage_seconds():
    rows = list(iter_sleep_samples(SLEEP_FIXTURE))
    types = {r["type"] for r in rows}
    assert "sleep_deep" in types
    assert "sleep_light" in types
    assert "sleep_rem" in types
    deep = next(r for r in rows if r["type"] == "sleep_deep")
    assert deep["value"] == 6900.0
    assert deep["unit"] == "s"
    # Score is in meta, not its own row
    assert deep["meta"]["overall_score"] == 68


def test_biometrics_parser_skips_null_entries():
    rows = list(iter_biometric_samples(BIO_FIXTURE))
    # Two real readings (vo2max, weight). The 'userSetNullForWeight' entry has
    # no actual value field and is dropped.
    types = [r["type"] for r in rows]
    assert types.count("vo2max") == 1
    assert types.count("weight") == 1
    assert len(rows) == 2
