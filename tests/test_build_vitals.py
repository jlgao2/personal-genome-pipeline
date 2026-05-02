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


def test_build_vitals_with_garmin_real_data():
    """If both Garmin + HealthKit are present, RHR series uses unified daily values."""
    real = Path("data/parquet/samples")
    if not (list(real.glob("garmin-*.parquet")) and list(real.glob("healthkit-*.parquet"))):
        return
    vitals = build_vitals(real)
    rhr = vitals.get("heart_rate_resting")
    assert rhr is not None
    # Garmin contributes ~2,000+ daily-rollup days vs. HealthKit's ~1,200
    assert len(rhr["series"]) >= 1500
