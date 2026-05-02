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
