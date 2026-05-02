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


def test_iter_samples_includes_ts_end():
    samples = list(iter_samples(FIXTURE))
    sleep = next(s for s in samples if s["type"] == "sleep_stage")
    # Sleep record spans 23:30 → 06:45 next day
    assert sleep["ts_end"].startswith("2026-04-22")
    assert sleep["ts_end"] != sleep["ts"]
