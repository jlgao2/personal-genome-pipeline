import tempfile
from pathlib import Path

import duckdb

from pipeline.parsers.genome import parse_to_parquet, FINDINGS_COLUMNS

RAW = Path("output/raw_findings")


def test_parse_to_parquet_real_data():
    if not RAW.exists():
        return
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        n = parse_to_parquet(RAW, outdir)
        assert n > 0
        files = list(outdir.glob("findings-*.parquet"))
        assert len(files) >= 1

        rows = duckdb.query(
            f"select source_tsv, count(*) as n from '{outdir}/findings-*.parquet' "
            f"group by source_tsv order by source_tsv"
        ).fetchall()
        sources = {s for s, _ in rows}
        assert "pgx_quick" in sources
        assert "clinvar_acmg" in sources or "clinvar_full" in sources

        schema = duckdb.query(
            f"describe select * from '{outdir}/findings-*.parquet'"
        ).fetchall()
        col_names = {row[0] for row in schema}
        assert set(FINDINGS_COLUMNS).issubset(col_names)


def test_parse_to_parquet_idempotent():
    if not RAW.exists():
        return
    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td)
        n1 = parse_to_parquet(RAW, outdir)
        n2 = parse_to_parquet(RAW, outdir)
        total = duckdb.query(
            f"select count(*) from '{outdir}/findings-*.parquet'"
        ).fetchone()[0]
        assert total == n2
        assert n1 == n2
