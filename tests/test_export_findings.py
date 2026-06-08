"""Tests for pipeline.export_findings — emits the public artifact JSON
that downstream consumers (Prefrontal Cortex health pipeline) ingest."""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.export_findings import (
    SCHEMA_VERSION,
    build_payload,
    collect_rows,
    write_findings,
)
from pipeline.parsers.genome import FINDINGS_COLUMNS

DEMO = Path(__file__).parent / "demo_data" / "raw_findings"


def test_collect_rows_returns_canonical_shape():
    rows = collect_rows(DEMO)
    assert rows, "demo TSVs should yield at least one row"
    for r in rows:
        assert set(r.keys()) == set(FINDINGS_COLUMNS), (
            f"row missing columns: {set(FINDINGS_COLUMNS) - set(r.keys())}"
        )
        # id is the parser's natural key — never empty
        assert r["id"]
        # source_tsv is one of the demo files we shipped
        assert r["source_tsv"] in {"pgx_quick", "clinvar_acmg"}


def test_collect_rows_skips_missing_tsvs(tmp_path):
    # No TSVs at all → empty list, no exception.
    rows = collect_rows(tmp_path)
    assert rows == []


def test_build_payload_has_envelope():
    p = build_payload(DEMO)
    assert p["schema_version"] == SCHEMA_VERSION
    assert isinstance(p["exported_at"], str) and "T" in p["exported_at"]
    # source_pipeline_commit is a short-sha or "unknown"
    assert isinstance(p["source_pipeline_commit"], str)
    assert isinstance(p["rows"], list) and len(p["rows"]) > 0


def test_write_findings_round_trip(tmp_path):
    out = tmp_path / "subdir" / "genomic_findings.json"
    n = write_findings(DEMO, out)
    assert n > 0
    assert out.exists()

    payload = json.loads(out.read_text())
    assert payload["schema_version"] == SCHEMA_VERSION
    assert len(payload["rows"]) == n
    # JSON is human-pretty, not minified — diff-friendly.
    assert "\n  " in out.read_text()


def test_write_findings_creates_parent_dir(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "out.json"
    write_findings(DEMO, deep)
    assert deep.exists()


def test_schema_v2_and_source_stamp(tmp_path):
    from pipeline.export_findings import SCHEMA_VERSION, build_payload
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "clinvar_acmg.tsv").write_text(
        "chrom\tpos\tref\talt\trsid\tgene\tclnsig_class\tclnsig\tclndn\tclnrevstat\tstars\tuser_gt\tuser_zygosity\n"
        "13\t32339000\tA\tT\trs80357000\tBRCA2\tPathogenic\tPathogenic\tcancer\tcriteria_provided,_multiple_submitters,_no_conflicts\t2\t0/1\theterozygous\n"
    )
    assert SCHEMA_VERSION == 2
    payload = build_payload(raw, source="wgs")
    assert payload["schema_version"] == 2
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["source"] == "wgs"
    assert row["scan_tier"] == "actionable"
    assert row["tier"] == "A"  # 2 stars → unchanged A/B/C semantics
