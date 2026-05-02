# Genome → Parquet Refactor (Sub-1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Plumb the existing genome-pipeline TSV outputs into the unified Parquet spine (`findings.parquet` + `cross_refs.parquet`) so future subsystems (Sub-4 social linkage, Sub-5 CI) can do cross-source SQL joins. The dashboard keeps reading `data.js` unchanged — this is a **non-breaking** refactor.

**Architecture:** A single `pipeline/parsers/genome.py` module with one generic `tsv_to_findings()` helper plus per-TSV column-mapping dicts. Each TSV type maps to canonical `(id, gene, rsid, genotype, tier, summary, meta)` rows. `cross_refs.parquet` is built by joining findings against the existing genetic-clinical correlation markdown.

**Tech Stack:** Python 3.12, `pyarrow`, `duckdb`. No new dependencies — reuses the stack from Sub-2.

---

## File structure

```
output/raw_findings/                              (existing — input to parsers)
  pgx_quick.tsv                                   (PharmCAT-derived PGx)
  clinvar_acmg.tsv, clinvar_full.tsv              (ClinVar P/LP)
  carrier_status.tsv                              (Carrier panel)
  nutrition_traits.tsv, extra_traits.tsv          (Curated SNPs)
  imputed_panels.tsv                              (Lifestyle/wellness)
  prs_scores.tsv                                  (Polygenic risk scores)

data/parquet/findings/                            (new — gitignored)
  findings-2026-05.parquet                        (one file per refresh month)
data/parquet/cross_refs/                          (new — gitignored)
  cross_refs.parquet

pipeline/parsers/genome.py                        (new — main module)
tests/parsers/test_genome.py                      (new — fixture-driven)
tests/parsers/fixtures/genome_pgx_sample.tsv      (new — 3-row fixture)
tests/parsers/fixtures/genome_clinvar_sample.tsv  (new — 2-row fixture)

pipeline/refresh.sh                               (modify — add genome step)
```

---

## Task 1 — `findings` schema + generic TSV converter (TDD)

**Files:**
- Create: `pipeline/parsers/genome.py`
- Test: `tests/parsers/test_genome.py`
- Test fixture: `tests/parsers/fixtures/genome_pgx_sample.tsv`

- [ ] **Step 1: Author a tiny PGx fixture**

Create `tests/parsers/fixtures/genome_pgx_sample.tsv`:

```
rsid	gene	drug	haplotype_role	chrom	pos	ref	alt	user_genotype	n_alt	interpretation
rs9923231	VKORC1	Warfarin	-1639G>A: A allele = lower warfarin dose required	16	31107689	C	T	T/T	2	T/T: high warfarin sensitivity, ~50% lower starting dose.
rs4244285	CYP2C19	Clopidogrel, PPIs	*2 loss-of-function	10	96541616	G	A	A/A	2	A/A: CYP2C19 *2/*2 — POOR metabolizer.
rs1057910	CYP2C9	Warfarin	*3 reduces metabolism	10	96741053	A	.	A/A	0	A/A: no *3 allele.
```

- [ ] **Step 2: Write failing test**

Create `tests/parsers/test_genome.py`:

```python
from pathlib import Path

from pipeline.parsers.genome import parse_pgx_tsv, FINDINGS_COLUMNS

PGX_FIXTURE = Path(__file__).parent / "fixtures" / "genome_pgx_sample.tsv"


def test_parse_pgx_tsv_yields_canonical_rows():
    rows = list(parse_pgx_tsv(PGX_FIXTURE))
    assert len(rows) == 3
    # Each row has every required canonical column
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
```

- [ ] **Step 3: Run test, confirm fail**

```bash
pytest tests/parsers/test_genome.py -v
```

Expected: ImportError on `parse_pgx_tsv`.

- [ ] **Step 4: Implement schema + PGx parser**

Create `pipeline/parsers/genome.py`:

```python
"""Convert genome-pipeline TSV outputs to the unified findings.parquet schema.

Each TSV (PGx, ClinVar, carrier, nutrition, etc.) has a slightly different
column layout. We define one canonical findings shape and a per-TSV mapping
function that yields canonical rows. Downstream consumers query via DuckDB.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterator

# Canonical findings.parquet column names, in stable order.
FINDINGS_COLUMNS = [
    "id",            # stable identifier (e.g., 'pgx_quick:rs9923231')
    "source_tsv",    # which TSV emitted this row
    "gene",
    "rsid",
    "chrom",
    "pos",
    "ref",
    "alt",
    "genotype",
    "tier",          # 'A' | 'B' | 'C' (analyst confidence)
    "summary",       # human-readable interpretation
    "meta",          # JSON string — source-specific extras
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
                pos=int(row["pos"]) if row.get("pos") else None,
                ref=row.get("ref"),
                alt=row.get("alt") if row.get("alt") not in (".", "") else None,
                genotype=row.get("user_genotype"),
                tier="A",  # PGx CPIC-graded → tier A
                summary=row.get("interpretation"),
                meta={
                    "drug": row.get("drug"),
                    "haplotype_role": row.get("haplotype_role"),
                    "n_alt": int(row["n_alt"]) if row.get("n_alt") else None,
                },
            )
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
pytest tests/parsers/test_genome.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/parsers/genome.py tests/parsers/test_genome.py tests/parsers/fixtures/genome_pgx_sample.tsv
git commit -m "Add canonical findings schema + PGx TSV parser"
```

---

## Task 2 — ClinVar + carrier parsers

**Files:**
- Modify: `pipeline/parsers/genome.py` (add `parse_clinvar_tsv`)
- Modify: `tests/parsers/test_genome.py` (add ClinVar tests)
- Test fixture: `tests/parsers/fixtures/genome_clinvar_sample.tsv`

- [ ] **Step 1: Author ClinVar fixture**

Create `tests/parsers/fixtures/genome_clinvar_sample.tsv`:

```
chrom	pos	ref	alt	rsid	gene	clnsig_class	clnsig	clndn	clnrevstat	stars	user_gt	user_zygosity
1	55504650	G	A	rs151193009	PCSK9	Pathogenic	Conflicting	Hypercholesterolemia	criteria_provided	1	1/1	homozygous_alt
19	41928081	C	T	rs78338921	BCKDHA	Pathogenic/Likely_pathogenic	Pathogenic/Likely_pathogenic	Maple syrup urine disease	multiple_submitters	2	0/1	heterozygous
```

- [ ] **Step 2: Add ClinVar test**

Append to `tests/parsers/test_genome.py`:

```python
from pipeline.parsers.genome import parse_clinvar_tsv

CLINVAR_FIXTURE = Path(__file__).parent / "fixtures" / "genome_clinvar_sample.tsv"


def test_parse_clinvar_tsv_yields_canonical_rows():
    rows = list(parse_clinvar_tsv(CLINVAR_FIXTURE, source_tsv="clinvar_acmg"))
    assert len(rows) == 2

    pcsk9 = next(r for r in rows if r["gene"] == "PCSK9")
    assert pcsk9["source_tsv"] == "clinvar_acmg"
    assert pcsk9["genotype"] == "1/1"
    # 2-star ClinVar = tier A; 1-star = tier B
    bckdha = next(r for r in rows if r["gene"] == "BCKDHA")
    assert bckdha["tier"] == "A"
    assert pcsk9["tier"] == "B"
```

- [ ] **Step 3: Implement parser**

Append to `pipeline/parsers/genome.py`:

```python
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
                pos=int(row["pos"]) if row.get("pos") else None,
                ref=row.get("ref"),
                alt=row.get("alt"),
                genotype=row.get("user_gt"),
                tier=tier,
                summary=summary,
                meta={
                    "clnsig":      row.get("clnsig"),
                    "clndn":       row.get("clndn"),
                    "clnrevstat":  row.get("clnrevstat"),
                    "stars":       stars,
                    "zygosity":    row.get("user_zygosity"),
                    "clnsig_class": row.get("clnsig_class"),
                },
            )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
pytest tests/parsers/test_genome.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/genome.py tests/parsers/test_genome.py tests/parsers/fixtures/genome_clinvar_sample.tsv
git commit -m "Add ClinVar/carrier TSV parser with star-based tier mapping"
```

---

## Task 3 — Nutrition, traits, panels, PRS parsers

**Files:**
- Modify: `pipeline/parsers/genome.py` (add 3 more parsers)
- Modify: `tests/parsers/test_genome.py`

These TSVs share a similar wide shape (rsid + gene + interpretation) so one generic parser handles all three. PRS is different (no rsid; pgs_id + trait + raw_score) — gets its own.

- [ ] **Step 1: Add tests for the new parsers**

Append to `tests/parsers/test_genome.py`:

```python
from pipeline.parsers.genome import (
    parse_curated_traits_tsv, parse_prs_scores_tsv,
)


def test_parse_curated_traits_runs_against_real_files():
    """Non-fixture: verify the parser handles the real shapes without fixtures."""
    real = Path("output/raw_findings/nutrition_traits.tsv")
    if not real.exists():
        return  # skip if pipeline hasn't run
    rows = list(parse_curated_traits_tsv(real, source_tsv="nutrition_traits"))
    assert len(rows) > 5
    assert all(r["source_tsv"] == "nutrition_traits" for r in rows)


def test_parse_prs_scores_handles_na_values():
    real = Path("output/raw_findings/prs_scores.tsv")
    if not real.exists():
        return
    rows = list(parse_prs_scores_tsv(real))
    assert len(rows) >= 5
    # PRS rows have no rsid; id is pgs_id-based
    assert all(r["id"].startswith("prs:") for r in rows)
```

- [ ] **Step 2: Implement the two new parsers**

Append to `pipeline/parsers/genome.py`:

```python
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
                pos=int(row["pos"]) if row.get("pos") else None,
                ref=row.get("ref"),
                alt=row.get("alt") if row.get("alt") not in (".", "") else None,
                genotype=row.get("user_genotype"),
                # Curated traits → tier B (interpretive, single-locus, sometimes weak effect)
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
                tier="B",  # PRS direction interpretable but percentile uncalibrated
                summary=row.get("description"),
                meta={
                    "pgs_id":      pgs_id,
                    "trait":       row.get("trait"),
                    "raw_score":   float(row["raw_score"]) if row.get("raw_score") else None,
                    "n_matched":   int(row["n_matched"]) if row.get("n_matched") else None,
                    "n_total":     int(row["n_total"]) if row.get("n_total") else None,
                    "pct_coverage": float(row["pct_coverage"]) if row.get("pct_coverage") else None,
                },
            )
            base["id"] = f"prs:{pgs_id}"
            yield base
```

- [ ] **Step 3: Run tests, confirm pass**

```bash
pytest tests/parsers/test_genome.py -v
```

Expected: all tests pass (real-file tests skip cleanly if files missing).

- [ ] **Step 4: Commit**

```bash
git add pipeline/parsers/genome.py tests/parsers/test_genome.py
git commit -m "Add curated-traits + PRS-scores parsers"
```

---

## Task 4 — `parse_to_parquet` orchestrator + CLI

**Files:**
- Modify: `pipeline/parsers/genome.py` (add orchestrator + CLI)
- Test: `tests/parsers/test_genome_parquet.py`

- [ ] **Step 1: Write failing test**

Create `tests/parsers/test_genome_parquet.py`:

```python
import tempfile
from pathlib import Path

import duckdb

from pipeline.parsers.genome import parse_to_parquet, FINDINGS_COLUMNS

RAW = Path("output/raw_findings")


def test_parse_to_parquet_real_data():
    if not RAW.exists():
        return  # skip if pipeline hasn't run
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

        # Schema check
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
        # Idempotent: second run replaces, doesn't append
        total = duckdb.query(
            f"select count(*) from '{outdir}/findings-*.parquet'"
        ).fetchone()[0]
        assert total == n2
        assert n1 == n2
```

- [ ] **Step 2: Implement orchestrator + CLI**

Append to `pipeline/parsers/genome.py`:

```python
import datetime as _dt

import pyarrow as pa
import pyarrow.parquet as pq

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

    # Single partition = current month (refresh writes anew each run).
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
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/parsers/test_genome_parquet.py -v
```

Expected: `2 passed`.

- [ ] **Step 4: Run on real data**

```bash
mkdir -p data/parquet/findings
python3 -m pipeline.parsers.genome
```

Expected output: `Wrote NNN findings to data/parquet/findings/findings-*.parquet` where NNN is roughly 100-200.

Spot-check via DuckDB:

```bash
python3 -c "
import duckdb
rows = duckdb.query(\"select source_tsv, tier, count(*) as n from 'data/parquet/findings/findings-*.parquet' group by source_tsv, tier order by source_tsv, tier\").fetchall()
for s, t, n in rows: print(f'  {s:24s} tier {t}  {n:>4d}')
"
```

Expected: rows for pgx_quick (tier A), clinvar_acmg (tier B/C), nutrition_traits (tier B), prs_scores (tier B), etc.

- [ ] **Step 5: Commit**

```bash
git add pipeline/parsers/genome.py tests/parsers/test_genome_parquet.py
git commit -m "Add genome.parse_to_parquet orchestrator + CLI"
```

---

## Task 5 — `cross_refs.parquet` from clinical correlation markdown

**Files:**
- Create: `pipeline/parsers/cross_refs.py`
- Test: `tests/parsers/test_cross_refs.py`

The existing `output/genetic_clinical_correlation.md` documents convergences (e.g., "9p21 G/G + measured LDL=83 + family hx of CAD → tier A"). Each convergence is a `cross_refs` row pairing a `finding_id` with a `sample_type` and a takeaway.

For v1: the cross-refs table is hand-authored from a small YAML alongside the markdown. Auto-extraction from prose is overkill at this scale (~12 convergences).

- [ ] **Step 1: Author `output/cross_refs.yaml`**

Create `output/cross_refs.yaml` (NOT gitignored — it's a hand-curated mapping, no PHI):

```yaml
- finding_id: pgx_quick:rs9923231
  sample_type: warfarin_dose_response
  expected_direction: decrease
  target_value: null
  takeaway: VKORC1 -1639 A/A predicts ~50% lower warfarin starting dose. Confirmed by clinician note from cardiology consult 2024-08.

- finding_id: pgx_quick:rs4244285
  sample_type: clopidogrel_response
  expected_direction: decrease
  target_value: null
  takeaway: CYP2C19 *2/*2 = poor metabolizer. Clopidogrel ineffective; alternate antiplatelet recommended if cardiac event.

- finding_id: prs:PGS000018
  sample_type: ldl_cholesterol
  expected_direction: increase
  target_value: 100.0
  takeaway: CAD PRS slightly elevated. Measured LDL 77-83 mg/dL is well-controlled — keep statin discussion open if trending up.
```

(User adds more entries as analysis grows. This is a small, slowly-changing file.)

- [ ] **Step 2: Write the parser + test**

Create `tests/parsers/test_cross_refs.py`:

```python
import tempfile
from pathlib import Path

import duckdb

from pipeline.parsers.cross_refs import parse_cross_refs_yaml

YAML_FIXTURE = Path(__file__).parent / "fixtures" / "cross_refs_sample.yaml"


def test_parse_cross_refs_yaml(tmp_path):
    fixture = tmp_path / "cross_refs.yaml"
    fixture.write_text("""
- finding_id: pgx_quick:rs1
  sample_type: x
  expected_direction: increase
  target_value: 100.0
  takeaway: example
""".lstrip())
    out = tmp_path / "cross_refs.parquet"
    n = parse_cross_refs_yaml(fixture, out)
    assert n == 1
    rows = duckdb.query(f"select * from '{out}'").fetchall()
    assert rows[0][0] == "pgx_quick:rs1"
```

Create `pipeline/parsers/cross_refs.py`:

```python
"""Build cross_refs.parquet from a hand-curated YAML mapping.

Each entry pairs a finding_id (matches findings.parquet.id) with a sample
type from samples.parquet and a clinical takeaway. The YAML lives at
output/cross_refs.yaml and is hand-edited as analysis grows.
"""
from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import yaml


def parse_cross_refs_yaml(yaml_path: Path, out_path: Path) -> int:
    """Read a YAML list of cross-ref dicts; write to a single Parquet file."""
    with yaml_path.open() as f:
        entries = yaml.safe_load(f) or []
    schema = pa.schema([
        ("finding_id",         pa.string()),
        ("sample_type",        pa.string()),
        ("expected_direction", pa.string()),
        ("target_value",       pa.float64()),
        ("takeaway",           pa.string()),
    ])
    rows = [
        {
            "finding_id":         e["finding_id"],
            "sample_type":        e["sample_type"],
            "expected_direction": e.get("expected_direction"),
            "target_value":       e.get("target_value"),
            "takeaway":           e.get("takeaway"),
        }
        for e in entries
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, out_path)
    return len(rows)


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Build cross_refs.parquet from YAML.")
    ap.add_argument("--yaml", type=Path, default=Path("output/cross_refs.yaml"))
    ap.add_argument("--out",  type=Path, default=Path("data/parquet/cross_refs/cross_refs.parquet"))
    args = ap.parse_args()
    n = parse_cross_refs_yaml(args.yaml, args.out)
    print(f"Wrote {n} cross-refs to {args.out}")


if __name__ == "__main__":
    _cli()
```

- [ ] **Step 3: Install pyyaml + run tests**

```bash
pip3 install pyyaml --quiet
pytest tests/parsers/test_cross_refs.py -v
```

Expected: `1 passed`.

- [ ] **Step 4: Run against the real YAML**

```bash
python3 -m pipeline.parsers.cross_refs
```

Expected: `Wrote 3 cross-refs to data/parquet/cross_refs/cross_refs.parquet`.

- [ ] **Step 5: Commit**

```bash
git add output/cross_refs.yaml pipeline/parsers/cross_refs.py tests/parsers/test_cross_refs.py
git commit -m "Add cross_refs.parquet parser from YAML curation"
```

---

## Task 6 — Wire into `refresh.sh` + final smoke

**Files:**
- Modify: `pipeline/refresh.sh`

- [ ] **Step 1: Add genome step to refresh.sh**

Edit `pipeline/refresh.sh`. After the HealthKit block (before the `# ── Build vitals JS ──` line), insert:

```bash
# ── Genome → findings.parquet ──
if [[ -d output/raw_findings ]]; then
    if [[ ! -f "$LOG" || -n "$(find output/raw_findings -newer "$LOG" 2>/dev/null)" ]]; then
        echo "Parsing genome TSVs → findings.parquet..."
        python3 -m pipeline.parsers.genome \
            --raw output/raw_findings \
            --outdir data/parquet/findings
    else
        echo "Genome findings up to date."
    fi
fi

# ── Cross-refs YAML → cross_refs.parquet ──
if [[ -f output/cross_refs.yaml ]]; then
    python3 -m pipeline.parsers.cross_refs \
        --yaml output/cross_refs.yaml \
        --out  data/parquet/cross_refs/cross_refs.parquet
fi
```

- [ ] **Step 2: Run end-to-end**

```bash
rm -f data/parquet/.last_refresh
bash pipeline/refresh.sh
```

Expected output ends with both new lines: "Parsing genome TSVs..." and a write count, plus the cross_refs write.

- [ ] **Step 3: SQL sanity — verify cross-source join works**

```bash
python3 <<'PY'
import duckdb
# The whole point of the spine: join findings ↔ cross_refs ↔ healthkit samples.
rows = duckdb.query("""
SELECT f.gene, f.summary, c.sample_type, c.takeaway
FROM   'data/parquet/findings/findings-*.parquet' f
JOIN   'data/parquet/cross_refs/cross_refs.parquet' c
ON     f.id = c.finding_id
""").fetchall()
for r in rows:
    print(r)
PY
```

Expected: 3 rows joining VKORC1/CYP2C19/CAD-PRS findings to their respective sample types.

- [ ] **Step 4: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests still pass (HealthKit + genome).

- [ ] **Step 5: Commit**

```bash
git add pipeline/refresh.sh
git commit -m "Wire genome + cross_refs parsers into refresh.sh"
```

---

## Acceptance criteria

- [ ] `bash pipeline/refresh.sh` regenerates `findings.parquet` + `cross_refs.parquet` in <5 seconds.
- [ ] DuckDB join `findings ⨝ cross_refs` returns at least 3 rows linking genotype to sample-type.
- [ ] Dashboard (`output/web/index.html`) still renders identically — no behavioral change to the live UI.
- [ ] All TSVs in `output/raw_findings/` are represented in `findings.parquet`.
- [ ] Tier mapping: PGx → A, ClinVar 2★ → A, ClinVar 1★ → B, curated SNPs → B, PRS → B.
- [ ] Re-running is idempotent (Parquet replaced, not appended).

## What this plan does NOT do

- **No data.js changes.** Dashboard reads the existing hand-curated file. Migrating curation lives in a follow-up plan if/when desired.
- **No live SQL queries from the browser.** DuckDB-Wasm or similar is a future consideration.
- **No GPX/workout-route parsing.** Exists in HealthKit zip but rendered in a later subsystem.
- **No automatic clinical-correlation extraction from `genetic_clinical_correlation.md`.** Cross-refs are hand-authored YAML for v1.
