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
