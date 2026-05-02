import json
import zipfile
from pathlib import Path

import duckdb

from pipeline.parsers.garmin import parse_zip_to_parquet

UDS = json.loads((Path(__file__).parent / "fixtures" / "garmin_uds_sample.json").read_text())
SLEEP = json.loads((Path(__file__).parent / "fixtures" / "garmin_sleep_sample.json").read_text())
BIO = json.loads((Path(__file__).parent / "fixtures" / "garmin_biometrics_sample.json").read_text())


def _make_test_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("DI_CONNECT/DI-Connect-Aggregator/UDSFile_test.json", json.dumps(UDS))
        zf.writestr("DI_CONNECT/DI-Connect-Wellness/test_86394354_sleepData.json", json.dumps(SLEEP))
        zf.writestr("DI_CONNECT/DI-Connect-Wellness/86394354_userBioMetrics.json", json.dumps(BIO))
        zf.writestr("DI_GARMIN_TRAILS/something.json", json.dumps({"x": 1}))


def test_parse_zip_round_trip(tmp_path):
    zip_path = tmp_path / "g.zip"
    outdir = tmp_path / "out"
    _make_test_zip(zip_path)
    n = parse_zip_to_parquet(zip_path, outdir)
    assert n > 0
    rows = duckdb.query(
        f"select type, count(*) from '{outdir}/garmin-*.parquet' group by type"
    ).fetchall()
    types = {t for t, _ in rows}
    assert "heart_rate_resting" in types
    assert "sleep_deep" in types
    assert "vo2max" in types or "weight" in types


def test_parse_zip_idempotent(tmp_path):
    zip_path = tmp_path / "g.zip"
    outdir = tmp_path / "out"
    _make_test_zip(zip_path)
    n1 = parse_zip_to_parquet(zip_path, outdir)
    n2 = parse_zip_to_parquet(zip_path, outdir)
    total = duckdb.query(
        f"select count(*) from '{outdir}/garmin-*.parquet'"
    ).fetchone()[0]
    assert total == n2
    assert n1 == n2


ACT = json.loads((Path(__file__).parent / "fixtures" / "garmin_activities_sample.json").read_text())


def test_parse_zip_writes_events_partitions(tmp_path):
    zip_path = tmp_path / "g.zip"
    samples_out = tmp_path / "samples"
    events_out  = tmp_path / "events"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("DI_CONNECT/DI-Connect-Aggregator/UDSFile_t.json", json.dumps(UDS))
        zf.writestr("DI_CONNECT/DI-Connect-Fitness/test_summarizedActivities.json",
                    json.dumps(ACT))
    n = parse_zip_to_parquet(zip_path, samples_out, events_out)
    assert n > 0
    assert list(events_out.glob("garmin-*.parquet")), "events partition was not written"

    rows = duckdb.query(
        f"select label, count(*) from '{events_out}/garmin-*.parquet' group by label"
    ).fetchall()
    labels = {r[0] for r in rows}
    assert "Chicago Tennis" in labels
