import json
from pathlib import Path

import duckdb

from pipeline.parsers.ios_samples import parse_drops_to_parquet


def _drop(rows: list, path: Path) -> None:
    path.write_text(json.dumps(rows))


def test_parse_drops_round_trip(tmp_path):
    drops = tmp_path / "drops"
    out = tmp_path / "out"
    drops.mkdir()
    _drop([
        {"ts": "2026-05-01T08:00:00+00:00", "ts_end": "2026-05-01T08:00:00+00:00",
         "source": "healthkit", "type": "heart_rate_resting",
         "value": 52.0, "unit": "bpm", "meta": "{\"via\":\"ios_app\"}"},
        {"ts": "2026-05-01T09:00:00+00:00", "ts_end": "2026-05-01T09:00:00+00:00",
         "source": "healthkit", "type": "weight",
         "value": 213.5, "unit": "lb", "meta": {"via": "ios_app"}},
    ], drops / "samples_2026-05-01.json")
    _drop([
        {"ts": "2026-05-02T08:00:00+00:00", "ts_end": "2026-05-02T08:00:00+00:00",
         "source": "healthkit", "type": "heart_rate_resting",
         "value": 50.0, "unit": "bpm", "meta": "{}"},
    ], drops / "samples_2026-05-02.json")

    n = parse_drops_to_parquet(drops, out)
    assert n == 3

    rows = duckdb.query(
        f"select type, count(*) from '{out}/ios-*.parquet' group by type"
    ).fetchall()
    types = {r[0] for r in rows}
    assert "heart_rate_resting" in types
    assert "weight" in types


def test_parse_drops_idempotent(tmp_path):
    drops = tmp_path / "drops"; drops.mkdir()
    out = tmp_path / "out"
    _drop([{"ts": "2026-05-01T00:00:00+00:00", "ts_end": "2026-05-01T00:00:00+00:00",
            "source": "healthkit", "type": "x", "value": 1.0, "unit": "u", "meta": "{}"}],
          drops / "samples_2026-05-01.json")
    parse_drops_to_parquet(drops, out)
    parse_drops_to_parquet(drops, out)
    total = duckdb.query(f"select count(*) from '{out}/ios-*.parquet'").fetchone()[0]
    assert total == 1


def test_parse_drops_empty_dir(tmp_path):
    out = tmp_path / "out"
    n = parse_drops_to_parquet(tmp_path / "nonexistent", out)
    assert n == 0
