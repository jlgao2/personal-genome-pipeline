"""Convert genome-pipeline TSV outputs to the unified findings.parquet schema.

Each TSV (PGx, ClinVar, carrier, nutrition, etc.) has a slightly different
column layout. We define one canonical findings shape and a per-TSV mapping
function that yields canonical rows. Downstream consumers query via DuckDB.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.parquet as pq

# Canonical findings.parquet column names, in stable order.
FINDINGS_COLUMNS = [
    "id",
    "source_tsv",
    "gene",
    "rsid",
    "chrom",
    "pos",
    "ref",
    "alt",
    "genotype",
    "tier",
    "summary",
    "meta",
]


def _row(source_tsv: str, **fields) -> dict:
    """Return a canonical findings row, padding missing columns with None."""
    base = {col: None for col in FINDINGS_COLUMNS}
    base.update(fields)
    base["source_tsv"] = source_tsv
    rsid = fields.get("rsid") or fields.get("pos") or ""
    base["id"] = f"{source_tsv}:{rsid}"
    if isinstance(base.get("meta"), dict):
        base["meta"] = json.dumps(base["meta"])
    return base


def _maybe_int(s: str | None) -> int | None:
    """Coerce a TSV cell to int, returning None for blanks / '.' placeholders."""
    if s is None or s == "" or s == ".":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def parse_pgx_tsv(tsv_path: Path) -> Iterator[dict]:
    """Yield canonical rows from output/raw_findings/pgx_quick.tsv."""
    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            yield _row(
                source_tsv="pgx_quick",
                gene=row.get("gene"),
                rsid=row.get("rsid"),
                chrom=row.get("chrom"),
                pos=_maybe_int(row.get("pos")),
                ref=row.get("ref"),
                alt=row.get("alt") if row.get("alt") not in (".", "") else None,
                genotype=row.get("user_genotype"),
                tier="A",
                summary=row.get("interpretation"),
                meta={
                    "drug": row.get("drug"),
                    "haplotype_role": row.get("haplotype_role"),
                    "n_alt": int(row["n_alt"]) if row.get("n_alt") else None,
                },
            )


def parse_clinvar_tsv(tsv_path: Path, source_tsv: str = "clinvar_acmg") -> Iterator[dict]:
    """Yield canonical rows from clinvar_acmg.tsv / clinvar_full.tsv / carrier_status.tsv.

    Tier mapping: ClinVar review-status stars → analyst tier:
        2+ stars → A   (multiple submitters, no conflicts)
        1 star   → B   (criteria provided, conflicting / single submitter)
        0 stars  → C   (no assertion criteria)
    """
    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            stars = int(row.get("stars") or 0)
            tier = "A" if stars >= 2 else ("B" if stars == 1 else "C")
            summary = (
                f"{row.get('clnsig')} for {row.get('clndn')} "
                f"({row.get('user_zygosity')})"
            )
            yield _row(
                source_tsv=source_tsv,
                gene=row.get("gene"),
                rsid=row.get("rsid"),
                chrom=row.get("chrom"),
                pos=_maybe_int(row.get("pos")),
                ref=row.get("ref"),
                alt=row.get("alt"),
                genotype=row.get("user_gt"),
                tier=tier,
                summary=summary,
                meta={
                    "clnsig":       row.get("clnsig"),
                    "clndn":        row.get("clndn"),
                    "clnrevstat":   row.get("clnrevstat"),
                    "stars":        stars,
                    "zygosity":     row.get("user_zygosity"),
                    "clnsig_class": row.get("clnsig_class"),
                },
            )


def parse_curated_traits_tsv(tsv_path: Path, source_tsv: str) -> Iterator[dict]:
    """Yield canonical rows from nutrition_traits.tsv / extra_traits.tsv / imputed_panels.tsv.

    Common shape: rsid, gene, trait, chrom, pos, ref, alt, user_genotype,
                  trait_allele, n_trait_alleles, interpretation, description.
    """
    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            n_trait = row.get("n_trait_alleles") or "0"
            yield _row(
                source_tsv=source_tsv,
                gene=row.get("gene"),
                rsid=row.get("rsid"),
                chrom=row.get("chrom"),
                pos=_maybe_int(row.get("pos")),
                ref=row.get("ref"),
                alt=row.get("alt") if row.get("alt") not in (".", "") else None,
                genotype=row.get("user_genotype"),
                tier="B",
                summary=row.get("interpretation"),
                meta={
                    "trait":           row.get("trait"),
                    "trait_allele":    row.get("trait_allele"),
                    "n_trait_alleles": int(n_trait),
                    "description":     row.get("description"),
                },
            )


def parse_prs_scores_tsv(tsv_path: Path) -> Iterator[dict]:
    """Yield canonical rows from prs_scores.tsv (one row per PGS Catalog score)."""
    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            pgs_id = row.get("pgs_id")
            base = _row(
                source_tsv="prs_scores",
                gene=None,
                rsid=None,
                tier="B",
                summary=row.get("description"),
                meta={
                    "pgs_id":       pgs_id,
                    "trait":        row.get("trait"),
                    "raw_score":    float(row["raw_score"]) if row.get("raw_score") else None,
                    "n_matched":    int(row["n_matched"]) if row.get("n_matched") else None,
                    "n_total":      int(row["n_total"]) if row.get("n_total") else None,
                    "pct_coverage": float(row["pct_coverage"]) if row.get("pct_coverage") else None,
                },
            )
            base["id"] = f"prs:{pgs_id}"
            yield base


# Map raw-findings filename → parser function. Missing files are skipped.
TSV_PARSERS = [
    ("pgx_quick.tsv",        lambda p: parse_pgx_tsv(p)),
    ("clinvar_acmg.tsv",     lambda p: parse_clinvar_tsv(p, "clinvar_acmg")),
    ("clinvar_full.tsv",     lambda p: parse_clinvar_tsv(p, "clinvar_full")),
    ("carrier_status.tsv",   lambda p: parse_clinvar_tsv(p, "carrier_status")),
    ("nutrition_traits.tsv", lambda p: parse_curated_traits_tsv(p, "nutrition_traits")),
    ("extra_traits.tsv",     lambda p: parse_curated_traits_tsv(p, "extra_traits")),
    ("imputed_panels.tsv",   lambda p: parse_curated_traits_tsv(p, "imputed_panels")),
    ("prs_scores.tsv",       lambda p: parse_prs_scores_tsv(p)),
]


def parse_to_parquet(raw_dir: Path, outdir: Path) -> int:
    """Parse every supported TSV under raw_dir, write one Parquet partition.

    Idempotent: existing findings-*.parquet files are deleted before writing.
    Returns total row count.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("findings-*.parquet"):
        old.unlink()

    rows: list[dict] = []
    for filename, parser_fn in TSV_PARSERS:
        path = raw_dir / filename
        if not path.exists():
            continue
        rows.extend(parser_fn(path))

    if not rows:
        return 0

    partition = _dt.date.today().strftime("%Y-%m")
    schema = pa.schema([
        ("id",         pa.string()),
        ("source_tsv", pa.string()),
        ("gene",       pa.string()),
        ("rsid",       pa.string()),
        ("chrom",      pa.string()),
        ("pos",        pa.int64()),
        ("ref",        pa.string()),
        ("alt",        pa.string()),
        ("genotype",   pa.string()),
        ("tier",       pa.string()),
        ("summary",    pa.string()),
        ("meta",       pa.string()),
    ])
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, outdir / f"findings-{partition}.parquet")
    return len(rows)


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Convert genome TSVs to findings.parquet.")
    ap.add_argument("--raw",    type=Path, default=Path("output/raw_findings"))
    ap.add_argument("--outdir", type=Path, default=Path("data/parquet/findings"))
    args = ap.parse_args()
    n = parse_to_parquet(args.raw, args.outdir)
    print(f"Wrote {n:,} findings to {args.outdir}/findings-*.parquet")


if __name__ == "__main__":
    _cli()
