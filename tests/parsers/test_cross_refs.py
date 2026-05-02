import duckdb

from pipeline.parsers.cross_refs import parse_cross_refs_yaml


def test_parse_cross_refs_yaml(tmp_path):
    fixture = tmp_path / "cross_refs.yaml"
    fixture.write_text(
        "- finding_id: pgx_quick:rs1\n"
        "  sample_type: x\n"
        "  expected_direction: increase\n"
        "  target_value: 100.0\n"
        "  takeaway: example\n"
    )
    out = tmp_path / "cross_refs.parquet"
    n = parse_cross_refs_yaml(fixture, out)
    assert n == 1
    rows = duckdb.query(f"select * from '{out}'").fetchall()
    assert rows[0][0] == "pgx_quick:rs1"
    assert rows[0][3] == 100.0


def test_parse_cross_refs_empty_file(tmp_path):
    fixture = tmp_path / "empty.yaml"
    fixture.write_text("")
    out = tmp_path / "out.parquet"
    n = parse_cross_refs_yaml(fixture, out)
    assert n == 0
