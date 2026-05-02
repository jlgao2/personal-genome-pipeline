from pathlib import Path

from pipeline.parsers.genome import (
    FINDINGS_COLUMNS,
    parse_pgx_tsv,
    parse_clinvar_tsv,
    parse_curated_traits_tsv,
    parse_prs_scores_tsv,
)

PGX_FIXTURE = Path(__file__).parent / "fixtures" / "genome_pgx_sample.tsv"
CLINVAR_FIXTURE = Path(__file__).parent / "fixtures" / "genome_clinvar_sample.tsv"


def test_parse_pgx_tsv_yields_canonical_rows():
    rows = list(parse_pgx_tsv(PGX_FIXTURE))
    assert len(rows) == 3
    for r in rows:
        assert set(FINDINGS_COLUMNS).issubset(r.keys())

    vkorc1 = next(r for r in rows if r["rsid"] == "rs9923231")
    assert vkorc1["gene"] == "VKORC1"
    assert vkorc1["genotype"] == "T/T"
    assert vkorc1["source_tsv"] == "pgx_quick"
    assert "warfarin" in vkorc1["summary"].lower()


def test_findings_columns_complete():
    expected = {"id", "source_tsv", "gene", "rsid", "chrom", "pos",
                "ref", "alt", "genotype", "tier", "summary", "meta"}
    assert set(FINDINGS_COLUMNS) == expected


def test_parse_clinvar_tsv_yields_canonical_rows():
    rows = list(parse_clinvar_tsv(CLINVAR_FIXTURE, source_tsv="clinvar_acmg"))
    assert len(rows) == 2

    pcsk9 = next(r for r in rows if r["gene"] == "PCSK9")
    assert pcsk9["source_tsv"] == "clinvar_acmg"
    assert pcsk9["genotype"] == "1/1"
    bckdha = next(r for r in rows if r["gene"] == "BCKDHA")
    # 2-star → tier A; 1-star → tier B
    assert bckdha["tier"] == "A"
    assert pcsk9["tier"] == "B"


def test_parse_curated_traits_runs_against_real_files():
    real = Path("output/raw_findings/nutrition_traits.tsv")
    if not real.exists():
        return
    rows = list(parse_curated_traits_tsv(real, source_tsv="nutrition_traits"))
    assert len(rows) > 5
    assert all(r["source_tsv"] == "nutrition_traits" for r in rows)


def test_parse_prs_scores_handles_na_values():
    real = Path("output/raw_findings/prs_scores.tsv")
    if not real.exists():
        return
    rows = list(parse_prs_scores_tsv(real))
    assert len(rows) >= 5
    assert all(r["id"].startswith("prs:") for r in rows)
