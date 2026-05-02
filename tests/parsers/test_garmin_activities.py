from pathlib import Path

from pipeline.parsers.garmin import iter_activities

FIXTURE = Path(__file__).parent / "fixtures" / "garmin_activities_sample.json"


def test_iter_activities_yields_one_event_per_activity():
    events = list(iter_activities(FIXTURE))
    assert len(events) == 2
    for e in events:
        assert e["source"] == "garmin"
        assert e["type"] == "workout"
        assert "ts_start" in e and "ts_end" in e

    tennis = next(e for e in events if e["label"] == "Chicago Tennis")
    assert tennis["meta"]["sport"] == "TENNIS"
    assert tennis["meta"]["avg_hr"] == 140
    assert tennis["meta"]["calories"] == 2229
    assert tennis["meta"]["hr_time_in_zone"]["zone_3"] == 1392968


def test_iter_activities_handles_missing_optional_fields():
    events = list(iter_activities(FIXTURE))
    run = next(e for e in events if e["label"] == "Morning Run")
    assert run["meta"]["sport"] == "RUNNING"
    assert "hr_time_in_zone" not in run["meta"]
    assert run["meta"].get("training_load") is None
