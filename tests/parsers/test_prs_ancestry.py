"""Tests for parse_prs_ancestry_tsv — ancestry-calibrated (pgsc_calc) PRS rows."""
import json

from pipeline.parsers.genome import FINDINGS_COLUMNS, parse_prs_ancestry_tsv

PRS_TSV = (
    "pgs_id\ttrait\tgwas_ancestry\teas_percentile\tz_eas\tn_variants\treliability\tsummary\n"
    "PGS000018\tCoronary artery disease\tMAE\t99.9\t3.180\t1745179\tinflated\tCAD inflated\n"
    "PGS002725\tIschemic stroke\tEUR\t91.6\t1.360\t6010730\tcalibrated\tStroke calibrated\n"
    "PGS000755\tSerum uric acid\tEAS\t86.7\t1.090\t14\tsparse\tUric acid sparse\n"
)


def _write(tmp_path):
    p = tmp_path / "prs_ancestry.tsv"
    p.write_text(PRS_TSV)
    return p


def test_yields_canonical_rows(tmp_path):
    rows = list(parse_prs_ancestry_tsv(_write(tmp_path)))
    assert len(rows) == 3
    for r in rows:
        assert set(r.keys()) == set(FINDINGS_COLUMNS)
        assert r["source_tsv"] == "prs_ancestry"
        assert r["scan_tier"] == "exploratory"


def test_reliability_drives_tier_and_meta(tmp_path):
    by = {}
    for r in parse_prs_ancestry_tsv(_write(tmp_path)):
        m = json.loads(r["meta"])
        by[m["pgs_id"]] = (r, m)

    r_cad, m_cad = by["PGS000018"]
    assert m_cad["reliability"] == "inflated"
    assert m_cad["eas_percentile"] == 99.9
    assert m_cad["z_eas"] == 3.18
    assert m_cad["gwas_ancestry"] == "MAE"
    assert r_cad["tier"] == "C"   # inflated → de-emphasised

    r_str, _ = by["PGS002725"]
    assert r_str["tier"] == "B"   # calibrated → trustworthy

    r_gout, m_gout = by["PGS000755"]
    assert m_gout["reliability"] == "sparse"
    assert m_gout["n_variants"] == 14
    assert r_gout["tier"] == "C"
