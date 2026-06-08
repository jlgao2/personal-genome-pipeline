# WGS SNV/indel Annotation Path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Annotate the 30× WGS gVCF (sample `SQ8TH633`, GRCh38) through the existing annotation layer — no imputation — producing a tiered `genomic_findings.json` (schema v2) that supersedes the imputed artifact.

**Architecture:** A new prep step normalizes the gVCF into a canonical biallelic PASS sites VCF; a new orchestrator (`00_run_wgs.sh`) feeds it to the existing annotators (`06` extended with tiered modes, `10`, `11`, PharmCAT) writing flat into `output/raw_findings/wgs/`; `export_findings --raw output/raw_findings/wgs` regenerates the JSON. Reuses ~90% of existing code; the legacy imputed path is left byte-for-byte unchanged.

**Tech Stack:** bash, `bcftools`/`bgzip`/`tabix` (already installed at `/opt/homebrew/bin`), Python 3 stdlib, `pyarrow`, `pytest`.

**Design source:** `docs/superpowers/specs/2026-06-07-wgs-snv-indel-path-design.md`.

---

## File structure

| File | Responsibility | New/Modified |
|---|---|---|
| `pipeline/wgs/make_noprefix_fasta.sh` | One-time: reheader the in-repo GRCh38 FASTA to no-`chr` contigs for `bcftools norm` | New |
| `pipeline/wgs/prep_wgs_vcf.sh` | gVCF → canonical biallelic PASS sites VCF | New |
| `pipeline/06_clinvar_acmg.py` | Add `--mode {legacy,actionable,exploratory}`, `--exclude`, `--cap` | Modify |
| `pipeline/parsers/genome.py` | Add `source` + `scan_tier` columns; register `clinvar_exploratory.tsv`; stamp `source` | Modify |
| `pipeline/export_findings.py` | `--source` arg, stamp source, bump `SCHEMA_VERSION` → 2 | Modify |
| `pipeline/00_run_wgs.sh` | WGS orchestrator | New |
| `tests/parsers/test_genome.py` | Update column-set test; add scan_tier/source + exploratory-registration tests | Modify |
| `tests/test_export_findings.py` | Add schema-v2 / source-stamp test | Modify |
| `tests/wgs/test_clinvar_modes.py` | Test `06`'s three modes | New |
| `tests/wgs/test_prep_wgs_vcf.py` | Test prep transforms (incl. the §9 normalization acceptance check) | New |
| `tests/wgs/fixtures/wgs_gvcf_sample.vcf` | Synthetic gVCF fixture | New |
| `tests/wgs/fixtures/clinvar_mini.vcf` | Tiny canonical ClinVar fixture | New |

**Convention:** WGS-specific tests live under `tests/wgs/`. Run the suite with `python3 -m pytest tests/ -v` from the repo root.

---

## Task 1: No-prefix GRCh38 FASTA for normalization

The gVCF uses contigs `1..22,X,Y` (no `chr`); the in-repo FASTA (`refs/pharmcat/reference.fna.bgz`) is `chr`-prefixed. `bcftools norm -f` requires matching names. Build a reheadered copy once. (MT/decoy contigs are excluded from the prep — see Task 4 — so we only need 1–22,X,Y.)

**Files:**
- Create: `pipeline/wgs/make_noprefix_fasta.sh`
- Output (gitignored): `refs/grch38_noprefix.fa`, `refs/grch38_noprefix.fa.fai`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# One-time: derive a no-"chr"-prefix GRCh38 FASTA (contigs 1..22,X,Y) from the
# chr-prefixed PharmCAT reference, for use with `bcftools norm -f`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/refs/pharmcat/reference.fna.bgz"
OUT="$ROOT/refs/grch38_noprefix.fa"

if [[ ! -f "$SRC" ]]; then
  echo "ERROR: $SRC not found (PharmCAT reference). Run pipeline/00_setup.sh first." >&2
  exit 1
fi
if [[ -f "$OUT" && -f "$OUT.fai" ]]; then
  echo "Already built: $OUT"; exit 0
fi

# Keep only chr1..chr22,chrX,chrY; strip the 'chr' prefix in the FASTA headers.
WANT=$(printf "chr%s," {1..22} X Y | sed 's/,$//')
samtools faidx "$SRC" ${WANT//,/ } \
  | sed -E 's/^>chr([0-9XY]+).*/>\1/' > "$OUT"
samtools faidx "$OUT"
echo "Wrote $OUT and $OUT.fai"
echo "Contigs: $(cut -f1 "$OUT.fai" | tr '\n' ' ')"
```

- [ ] **Step 2: Make executable and run it**

Run:
```bash
chmod +x pipeline/wgs/make_noprefix_fasta.sh
bash pipeline/wgs/make_noprefix_fasta.sh
```
Expected: `Contigs: 1 2 3 ... 22 X Y`

- [ ] **Step 3: Verify it normalizes a sample record**

Run:
```bash
printf '##fileformat=VCFv4.2\n##contig=<ID=1>\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n1\t82133\t.\tCAAA\tCA,C\t.\tPASS\t.\n' \
  | bcftools norm -f refs/grch38_noprefix.fa -m- 2>/dev/null | grep -v '^#' | cut -f1-5
```
Expected: two **left-aligned/trimmed** biallelic records (a single trailing-base anchor, not `CAAA	CA`), confirming `-f` normalization works.

- [ ] **Step 4: Ensure the output is gitignored, then commit the script**

Run: `git check-ignore refs/grch38_noprefix.fa` (expected: prints the path; `refs/` large files are already ignored — if not, add `refs/grch38_noprefix.fa*` to `.gitignore`).
```bash
git add pipeline/wgs/make_noprefix_fasta.sh .gitignore
git commit -m "wgs: build no-prefix GRCh38 FASTA for bcftools norm"
```

---

## Task 2: Schema v2 — add `source` and `scan_tier` columns

**Files:**
- Modify: `pipeline/parsers/genome.py` (`FINDINGS_COLUMNS` L19-32, `_row` L35-44, `parse_to_parquet` schema L209-222 + stamping L198-203)
- Modify: `pipeline/export_findings.py` (`SCHEMA_VERSION` L26, `collect_rows` L40-52, `build_payload` L55-61, `main` L71-82)
- Modify: `tests/parsers/test_genome.py` (`test_findings_columns_complete`)

- [ ] **Step 1: Update the failing column-set test**

In `tests/parsers/test_genome.py`, replace `test_findings_columns_complete`:
```python
def test_findings_columns_complete():
    expected = {"id", "source_tsv", "gene", "rsid", "chrom", "pos",
                "ref", "alt", "genotype", "tier", "summary", "meta",
                "source", "scan_tier"}
    assert set(FINDINGS_COLUMNS) == expected


def test_row_defaults_scan_tier_actionable():
    from pipeline.parsers.genome import _row
    r = _row("clinvar_acmg", gene="BRCA1")
    assert r["scan_tier"] == "actionable"
    assert r["source"] is None  # stamped later by collect_rows / parse_to_parquet
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/parsers/test_genome.py::test_findings_columns_complete tests/parsers/test_genome.py::test_row_defaults_scan_tier_actionable -v`
Expected: FAIL (`source`/`scan_tier` not in `FINDINGS_COLUMNS`; `_row` has no scan_tier).

- [ ] **Step 3: Add the columns in `genome.py`**

Replace `FINDINGS_COLUMNS` (L19-32):
```python
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
    "source",
    "scan_tier",
]
```

Replace `_row` (L35-44) so `scan_tier` defaults to `actionable`:
```python
def _row(source_tsv: str, **fields) -> dict:
    """Return a canonical findings row, padding missing columns with None."""
    base = {col: None for col in FINDINGS_COLUMNS}
    base.update(fields)
    base["source_tsv"] = source_tsv
    base["scan_tier"] = fields.get("scan_tier", "actionable")
    rsid = fields.get("rsid") or fields.get("pos") or ""
    base["id"] = f"{source_tsv}:{rsid}"
    if isinstance(base.get("meta"), dict):
        base["meta"] = json.dumps(base["meta"])
    return base
```

Add the two fields to the parquet schema in `parse_to_parquet` (after `("meta", pa.string()),` at L221):
```python
        ("meta",       pa.string()),
        ("source",     pa.string()),
        ("scan_tier",  pa.string()),
    ])
```

Add a `source` parameter to `parse_to_parquet` and stamp it. Change the signature (L188) and the row loop (L198-203):
```python
def parse_to_parquet(raw_dir: Path, outdir: Path, source: str = "imputed") -> int:
    ...
    rows: list[dict] = []
    for filename, parser_fn in TSV_PARSERS:
        path = raw_dir / filename
        if not path.exists():
            continue
        for row in parser_fn(path):
            row["source"] = source
            rows.append(row)
```

Add `--source` to `_cli` (after the `--outdir` arg at L232):
```python
    ap.add_argument("--source", default="imputed")
    args = ap.parse_args()
    n = parse_to_parquet(args.raw, args.outdir, source=args.source)
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/parsers/test_genome.py -v`
Expected: PASS (all, including the existing clinvar/pgx tests).

- [ ] **Step 5: Stamp `source` + bump version in `export_findings.py`**

Change `SCHEMA_VERSION` (L26) to `2`. Replace `collect_rows`, `build_payload`, and `main`:
```python
SCHEMA_VERSION = 2


def collect_rows(raw_dir: Path, source: str = "imputed") -> list[dict]:
    rows: list[dict] = []
    for filename, parser_fn in TSV_PARSERS:
        path = raw_dir / filename
        if not path.exists():
            continue
        for row in parser_fn(path):
            row["source"] = source
            rows.append(row)
    return rows


def build_payload(raw_dir: Path, source: str = "imputed") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "source_pipeline_commit": _git_short_sha(),
        "rows": collect_rows(raw_dir, source=source),
    }


def write_findings(raw_dir: Path, out_path: Path, source: str = "imputed") -> int:
    payload = build_payload(raw_dir, source=source)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    return len(payload["rows"])
```
In `main`, add the arg and thread it:
```python
    parser.add_argument("--source", default="imputed")
    args = parser.parse_args()
    n = write_findings(args.raw, args.out, source=args.source)
```

- [ ] **Step 6: Add an export test**

Append to `tests/test_export_findings.py`:
```python
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
```

- [ ] **Step 7: Run all tests, then commit**

Run: `python3 -m pytest tests/ -v`
Expected: PASS
```bash
git add pipeline/parsers/genome.py pipeline/export_findings.py tests/parsers/test_genome.py tests/test_export_findings.py
git commit -m "findings: schema v2 — add source + scan_tier columns"
```

---

## Task 3: Register `clinvar_exploratory.tsv` and set its scan_tier

**Files:**
- Modify: `pipeline/parsers/genome.py` (`parse_clinvar_tsv` L81-117, `TSV_PARSERS` L176-185)
- Modify: `tests/parsers/test_genome.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/parsers/test_genome.py`:
```python
def test_clinvar_exploratory_registered_and_tagged(tmp_path):
    from pipeline.parsers.genome import TSV_PARSERS, parse_clinvar_tsv
    names = [n for n, _ in TSV_PARSERS]
    assert "clinvar_exploratory.tsv" in names
    f = tmp_path / "clinvar_exploratory.tsv"
    f.write_text(
        "chrom\tpos\tref\talt\trsid\tgene\tclnsig_class\tclnsig\tclndn\tclnrevstat\tstars\tuser_gt\tuser_zygosity\n"
        "7\t100\tA\tG\trs1\tXYZ\tPathogenic\tPathogenic\tcond\tcriteria_provided,_single_submitter\t1\t0/1\theterozygous\n"
    )
    rows = list(parse_clinvar_tsv(f, source_tsv="clinvar_exploratory"))
    assert rows[0]["scan_tier"] == "exploratory"
    assert rows[0]["tier"] == "B"  # 1 star → B, unchanged
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/parsers/test_genome.py::test_clinvar_exploratory_registered_and_tagged -v`
Expected: FAIL (`clinvar_exploratory.tsv` not registered; scan_tier not exploratory).

- [ ] **Step 3: Implement**

In `parse_clinvar_tsv` (L98-108), pass `scan_tier` based on `source_tsv` — add it to the `_row(...)` call:
```python
            yield _row(
                source_tsv=source_tsv,
                scan_tier="exploratory" if source_tsv == "clinvar_exploratory" else "actionable",
                gene=row.get("gene"),
                rsid=row.get("rsid"),
                chrom=row.get("chrom"),
                pos=_maybe_int(row.get("pos")),
                ref=row.get("ref"),
                alt=row.get("alt"),
                genotype=row.get("user_gt"),
                tier=tier,
                summary=summary,
                meta={ ... },  # unchanged
            )
```
Add the registry entry to `TSV_PARSERS` (after the `carrier_status.tsv` line L180):
```python
    ("clinvar_exploratory.tsv", lambda p: parse_clinvar_tsv(p, "clinvar_exploratory")),
```

- [ ] **Step 4: Run to verify pass, then commit**

Run: `python3 -m pytest tests/parsers/test_genome.py -v`
Expected: PASS
```bash
git add pipeline/parsers/genome.py tests/parsers/test_genome.py
git commit -m "findings: register clinvar_exploratory.tsv (scan_tier=exploratory)"
```

---

## Task 4: `06_clinvar_acmg.py` — tiered `--mode`

Add `--mode {legacy,actionable,exploratory}` (default `legacy` = current 3-file behavior, so `00_run_phase3.sh` is unchanged), plus `--exclude` and `--cap` for exploratory.

**Files:**
- Modify: `pipeline/06_clinvar_acmg.py` (args L133-140; output/branch logic L142-240)
- Create: `tests/wgs/__init__.py` (empty), `tests/wgs/fixtures/clinvar_mini.vcf`, `tests/wgs/test_clinvar_modes.py`

- [ ] **Step 1: Create the ClinVar fixture**

`tests/wgs/fixtures/clinvar_mini.vcf`:
```
##fileformat=VCFv4.2
##INFO=<ID=CLNSIG,Number=.,Type=String,Description="">
##INFO=<ID=CLNDN,Number=.,Type=String,Description="">
##INFO=<ID=CLNREVSTAT,Number=.,Type=String,Description="">
##INFO=<ID=GENEINFO,Number=1,Type=String,Description="">
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
13	100	rs_brca2	A	T	.	.	CLNSIG=Pathogenic;CLNDN=Cancer;CLNREVSTAT=criteria_provided,_multiple_submitters,_no_conflicts;GENEINFO=BRCA2:675
7	200	rs_explore	G	C	.	.	CLNSIG=Likely_pathogenic;CLNDN=SomethingElse;CLNREVSTAT=criteria_provided,_single_submitter;GENEINFO=XYZ:111
1	300	rs_carrier	C	G	.	.	CLNSIG=Pathogenic;CLNDN=Recessive;CLNREVSTAT=criteria_provided,_multiple_submitters,_no_conflicts;GENEINFO=CFTR:1080
```

- [ ] **Step 2: Write the failing mode tests**

`tests/wgs/test_clinvar_modes.py`:
```python
import subprocess
import sys
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
CLINVAR = FIX / "clinvar_mini.vcf"
SCRIPT = Path("pipeline/06_clinvar_acmg.py")

USER_VCF = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSQ8TH633
13\t100\trs_brca2\tA\tT\t.\tPASS\t.\tGT\t0/1
7\t200\trs_explore\tG\tC\t.\tPASS\t.\tGT\t0/1
1\t300\trs_carrier\tC\tG\t.\tPASS\t.\tGT\t0/1
"""


def _run(mode, outdir, extra=None):
    vcf = outdir / "user.vcf"
    vcf.write_text(USER_VCF)
    cmd = [sys.executable, str(SCRIPT), "--vcf", str(vcf), "--clinvar", str(CLINVAR),
           "--build", "GRCh38", "--outdir", str(outdir), "--mode", mode, "--min-stars", "1"]
    if extra:
        cmd += extra
    subprocess.run(cmd, check=True, capture_output=True)


def test_actionable_writes_acmg_and_carrier_not_full(tmp_path):
    _run("actionable", tmp_path)
    assert (tmp_path / "clinvar_acmg.tsv").exists()
    assert (tmp_path / "carrier_status.tsv").exists()
    assert not (tmp_path / "clinvar_full.tsv").exists()
    acmg = (tmp_path / "clinvar_acmg.tsv").read_text()
    assert "BRCA2" in acmg            # ACMG SF gene
    assert "XYZ" not in acmg          # non-ACMG gene excluded
    carrier = (tmp_path / "carrier_status.tsv").read_text()
    assert "CFTR" in carrier


def test_exploratory_genomewide_excludes_actionable(tmp_path):
    _run("actionable", tmp_path)
    _run("exploratory", tmp_path,
         extra=["--exclude", str(tmp_path / "clinvar_acmg.tsv"), "--cap", "200"])
    expl = (tmp_path / "clinvar_exploratory.tsv").read_text()
    assert "XYZ" in expl              # genome-wide P/LP not in ACMG
    assert "BRCA2" not in expl        # excluded: already in actionable


def test_legacy_default_writes_full(tmp_path):
    vcf = tmp_path / "user.vcf"
    vcf.write_text(USER_VCF)
    subprocess.run([sys.executable, str(SCRIPT), "--vcf", str(vcf),
                    "--clinvar", str(CLINVAR), "--build", "GRCh38",
                    "--outdir", str(tmp_path), "--min-stars", "1"], check=True, capture_output=True)
    assert (tmp_path / "clinvar_full.tsv").exists()  # legacy default unchanged
```

- [ ] **Step 3: Run to verify failure**

Run: `python3 -m pytest tests/wgs/test_clinvar_modes.py -v`
Expected: FAIL (no `--mode`/`--exclude`/`--cap`; actionable still writes full).

- [ ] **Step 4: Add the args**

In `main()` (after L139 `--min-stars`):
```python
    ap.add_argument("--mode", choices=["legacy", "actionable", "exploratory"],
                    default="legacy")
    ap.add_argument("--exclude", default=None,
                    help="exploratory mode: TSV whose chrom:pos:ref:alt rows to skip")
    ap.add_argument("--cap", type=int, default=200,
                    help="exploratory mode: max rows after sorting by (stars, sig)")
    args = ap.parse_args()
```

- [ ] **Step 5: Refactor the writer/branch logic**

Replace the body from L148 (`full_path = ...`) through the end of `main()` with a mode-aware version. Keep a single matching loop that yields candidate rows, then route by mode:

```python
    full_path = os.path.join(args.outdir, "clinvar_full.tsv")
    acmg_path = os.path.join(args.outdir, "clinvar_acmg.tsv")
    carrier_path = os.path.join(args.outdir, "carrier_status.tsv")
    explore_path = os.path.join(args.outdir, "clinvar_exploratory.tsv")

    header = "chrom\tpos\tref\talt\trsid\tgene\tclnsig_class\tclnsig\tclndn\tclnrevstat\tstars\tuser_gt\tuser_zygosity\n"

    # exploratory: keys to skip (already reported as actionable)
    exclude_keys = set()
    if args.exclude and os.path.exists(args.exclude):
        with open(args.exclude) as ex:
            next(ex, None)  # header
            for ln in ex:
                c = ln.rstrip("\n").split("\t")
                if len(c) >= 4:
                    exclude_keys.add((c[0], c[1], c[2], c[3]))

    def iter_matches():
        """Yield (gene, stars, cls, row_str, key) for every P/LP, >=min-stars,
        non-ref/ref match — the shared engine for all modes."""
        open_fn = gzip.open if args.clinvar.endswith(".gz") else open
        with open_fn(args.clinvar, "rt") as cv:
            for line in cv:
                if line.startswith("#"):
                    continue
                cols = line.rstrip().split("\t")
                if len(cols) < 8:
                    continue
                chrom, pos, rsid, ref, alt = cols[0], cols[1], cols[2], cols[3], cols[4]
                chrom = chrom.replace("chr", "")
                info = parse_clinvar_info(cols[7])
                key = (chrom, int(pos))
                if key not in user_vars:
                    continue
                for u_ref, u_alt, u_gt in user_vars[key]:
                    if u_ref != ref or u_alt != alt:
                        continue
                    cls = is_pathogenic(info["CLNSIG"])
                    if not cls:
                        continue
                    stars = review_status_stars(info["CLNREVSTAT"])
                    if stars < args.min_stars:
                        continue
                    zyg = "unknown"
                    if u_gt:
                        a = u_gt.replace("|", "/").split("/")
                        if len(a) == 2:
                            zyg = ("ref/ref" if a[0] == a[1] == "0"
                                   else "homozygous_alt" if a[0] == a[1]
                                   else "heterozygous")
                    if zyg == "ref/ref":
                        continue
                    row_str = (
                        f"{chrom}\t{pos}\t{ref}\t{alt}\t{rsid}\t{info['GENEINFO']}\t"
                        f"{cls}\t{info['CLNSIG']}\t{info['CLNDN']}\t{info['CLNREVSTAT']}\t"
                        f"{stars}\t{u_gt}\t{zyg}\n"
                    )
                    yield info["GENEINFO"], stars, cls, row_str, (chrom, pos, ref, alt)

    if args.mode == "exploratory":
        # genome-wide P/LP, exclude actionable dupes, sort by stars desc then sig, cap
        sig_rank = {"Pathogenic": 0, "Pathogenic/Likely_pathogenic": 1, "Likely_pathogenic": 2}
        matches = [m for m in iter_matches() if m[4] not in exclude_keys]
        matches.sort(key=lambda m: (-m[1], sig_rank.get(m[2], 9)))
        with open(explore_path, "w") as f_ex:
            f_ex.write(header)
            for gene, stars, cls, row_str, key in matches[: args.cap]:
                f_ex.write(row_str)
        sys.stderr.write(f"exploratory: {len(matches)} matched, wrote {min(len(matches), args.cap)} → {explore_path}\n")
        return

    # legacy + actionable share the acmg/carrier writes; legacy also writes full
    write_full = args.mode == "legacy"
    files = {"acmg": open(acmg_path, "w"), "carrier": open(carrier_path, "w")}
    if write_full:
        files["full"] = open(full_path, "w")
    for fh in files.values():
        fh.write(header)
    n_acmg = n_carrier = 0
    for gene, stars, cls, row_str, key in iter_matches():
        if write_full:
            files["full"].write(row_str)
        if gene in ACMG_SF_V32:
            files["acmg"].write(row_str); n_acmg += 1
        if gene in ACMG_CARRIER_PANEL:
            files["carrier"].write(row_str); n_carrier += 1
    for fh in files.values():
        fh.close()
    sys.stderr.write(f"mode={args.mode}: ACMG {n_acmg}, carrier {n_carrier}\n")
```

(Note: the old `parse_vcf_positions` call at L144-146 stays above this block; `user_vars` is in scope.)

- [ ] **Step 6: Run mode tests to verify pass**

Run: `python3 -m pytest tests/wgs/test_clinvar_modes.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Verify the legacy imputed path is unbroken**

Run: `python3 -m pytest tests/ -v`
Expected: PASS. (Legacy default writes full+acmg+carrier; `00_run_phase3.sh` passes no `--mode`.)

- [ ] **Step 8: Commit**

```bash
git add pipeline/06_clinvar_acmg.py tests/wgs/
git commit -m "clinvar: add tiered --mode (legacy/actionable/exploratory)"
```

---

## Task 5: `prep_wgs_vcf.sh` — gVCF → canonical biallelic PASS VCF

**Files:**
- Create: `pipeline/wgs/prep_wgs_vcf.sh`
- Create: `tests/wgs/fixtures/wgs_gvcf_sample.vcf`, `tests/wgs/test_prep_wgs_vcf.py`

- [ ] **Step 1: Create the synthetic gVCF fixture**

`tests/wgs/fixtures/wgs_gvcf_sample.vcf`:
```
##fileformat=VCFv4.2
##FILTER=<ID=PASS,Description="">
##FILTER=<ID=FAIL,Description="">
##contig=<ID=1>
##INFO=<ID=END,Number=1,Type=Integer,Description="">
##FORMAT=<ID=GT,Number=1,Type=String,Description="">
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO	FORMAT	SQ8TH633
1	10001	.	T	.	.	PASS	END=10100	GT	0/0
1	20000	.	A	<NON_REF>	.	PASS	.	GT	0/0
1	30000	rs_mixed	A	T,<NON_REF>	50	PASS	.	GT	1/0
1	40000	rs_fail	G	C	5	FAIL	.	GT	1/1
1	50000	.	G	A	50	PASS	.	GT	0/1
1	82133	rs_indel	CAAA	CA,C	50	PASS	.	GT	1/2
```
This exercises: ref-block (`.`), `<NON_REF>` block, mixed `T,<NON_REF>`, a FAIL record, a PASS variant without rsID, and the non-parsimonious multiallelic indel.

- [ ] **Step 2: Write the failing prep test**

`tests/wgs/test_prep_wgs_vcf.py`:
```python
import subprocess
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "wgs_gvcf_sample.vcf"
SCRIPT = Path("pipeline/wgs/prep_wgs_vcf.sh")
FASTA = Path("refs/grch38_noprefix.fa")


def _prep(tmp_path):
    inp = tmp_path / "in.vcf.gz"
    subprocess.run(f"bgzip -c {FIX} > {inp} && tabix -p vcf {inp}", shell=True, check=True)
    out = tmp_path / "out.vcf.gz"
    subprocess.run(["bash", str(SCRIPT), str(inp), str(out)], check=True, capture_output=True)
    recs = subprocess.run(["bcftools", "view", "-H", str(out)],
                          capture_output=True, text=True, check=True).stdout.strip().splitlines()
    return [r.split("\t") for r in recs if r]


def test_prep_transforms(tmp_path):
    if not FASTA.exists():
        import pytest; pytest.skip("run pipeline/wgs/make_noprefix_fasta.sh first")
    rows = _prep(tmp_path)
    sites = {(r[0], r[1], r[3], r[4]) for r in rows}
    # ref-blocks dropped
    assert not any(r[4] in (".", "<NON_REF>") for r in rows)
    # FAIL dropped
    assert not any(r[1] == "40000" for r in rows)
    # PASS variant without rsID kept
    assert ("1", "50000", "G", "A") in sites
    # rsID retained
    assert any(r[1] == "50000" for r in rows)
    # mixed record: real ALT kept, NON_REF gone
    assert ("1", "30000", "A", "T") in sites
    # multiallelic indel left-aligned/trimmed to canonical biallelic (anchor-trimmed)
    indel = [r for r in rows if r[1] == "82133"]
    assert len(indel) == 2
    for r in indel:
        assert len(r[3]) <= 4 and r[3][0] == "C"   # trimmed, not the raw CAAA for both
        assert "," not in r[4]                       # biallelic
```

- [ ] **Step 3: Run to verify failure**

Run: `python3 -m pytest tests/wgs/test_prep_wgs_vcf.py -v`
Expected: FAIL (script does not exist).

- [ ] **Step 4: Write `prep_wgs_vcf.sh`**

```bash
#!/usr/bin/env bash
# gVCF -> canonical biallelic PASS variant-only GRCh38 sites VCF.
#   1. restrict to primary contigs 1..22,X,Y  (matches the no-prefix FASTA; drops MT/decoys)
#   2. drop reference blocks (ALT '.' or <NON_REF>) and keep FILTER=PASS
#   3. split multiallelics + LEFT-ALIGN + trim against the FASTA
#   4. drop any residual <NON_REF>/'.' ALT produced by the split
# Usage: prep_wgs_vcf.sh <in.gvcf.gz> <out.vcf.gz>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IN="${1:?input gVCF}"
OUT="${2:?output VCF}"
FASTA="$ROOT/refs/grch38_noprefix.fa"
[[ -f "$FASTA" ]] || { echo "ERROR: $FASTA missing — run make_noprefix_fasta.sh" >&2; exit 1; }

REGIONS=$(printf '%s,' {1..22} X Y | sed 's/,$//')

bcftools view -r "$REGIONS" -f PASS -e 'ALT="." || ALT="<NON_REF>"' "$IN" -Ou \
  | bcftools norm -f "$FASTA" -m- -Ou \
  | bcftools view -e 'ALT="<NON_REF>" || ALT="."' -Oz -o "$OUT"
tabix -p vcf "$OUT"
echo "Wrote $OUT ($(bcftools index -n "$OUT") variant records)"
```

- [ ] **Step 5: Make executable, run test to verify pass**

Run:
```bash
chmod +x pipeline/wgs/prep_wgs_vcf.sh
python3 -m pytest tests/wgs/test_prep_wgs_vcf.py -v
```
Expected: PASS (or SKIP if the FASTA from Task 1 isn't built — build it first).

- [ ] **Step 6: Commit**

```bash
git add pipeline/wgs/prep_wgs_vcf.sh tests/wgs/test_prep_wgs_vcf.py tests/wgs/fixtures/wgs_gvcf_sample.vcf
git commit -m "wgs: prep_wgs_vcf.sh — gVCF to canonical biallelic PASS VCF"
```

---

## Task 6: `00_run_wgs.sh` — WGS orchestrator

**Files:**
- Create: `pipeline/00_run_wgs.sh`

- [ ] **Step 1: Write the orchestrator**

```bash
#!/usr/bin/env bash
# WGS annotation pipeline (no imputation). Runs prep + tiered annotation on the
# 30x WGS gVCF, writing flat into output/raw_findings/wgs/, then exports findings.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

GVCF="${GVCF:-data/wgs/SQ8TH633.30x.snp-indel.genome.vcf.gz}"
PREP=data/wgs/SQ8TH633.wgs.pass.vcf.gz
RAW=output/raw_findings/wgs
mkdir -p "$RAW" logs

echo "[1/7] Build no-prefix FASTA (idempotent)"
bash pipeline/wgs/make_noprefix_fasta.sh

echo "[2/7] Prep gVCF → canonical biallelic PASS VCF"
bash pipeline/wgs/prep_wgs_vcf.sh "$GVCF" "$PREP"

echo "[3/7] ClinVar GRCh38 (download if needed)"
if [[ ! -f refs/clinvar_grch38.vcf.gz ]]; then
  curl -sL -o refs/clinvar_grch38.vcf.gz     https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz
  curl -sL -o refs/clinvar_grch38.vcf.gz.tbi https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.tbi
fi

echo "[4/7] ClinVar/ACMG — actionable then exploratory"
python3 pipeline/06_clinvar_acmg.py --vcf "$PREP" --clinvar refs/clinvar_grch38.vcf.gz \
    --build GRCh38 --outdir "$RAW" --mode actionable --min-stars 2
python3 pipeline/06_clinvar_acmg.py --vcf "$PREP" --clinvar refs/clinvar_grch38.vcf.gz \
    --build GRCh38 --outdir "$RAW" --mode exploratory --min-stars 1 \
    --exclude "$RAW/clinvar_acmg.tsv" --cap 200

echo "[5/7] PharmCAT"
bcftools view -R refs/pharmcat/pharmcat_positions.vcf.bgz "$PREP" -Oz -o data/wgs_pharmcat_positions.vcf.gz
bcftools index -t data/wgs_pharmcat_positions.vcf.gz
mkdir -p output/pharmcat
PATH="/opt/homebrew/opt/openjdk/bin:$PATH" java -jar refs/pharmcat/pharmcat.jar \
    -vcf data/wgs_pharmcat_positions.vcf.gz -reporterHtml -reporterJson -reporterCallsOnlyTsv \
    -o output/pharmcat 2>&1 | tail -8

echo "[6/7] Panels + PRS"
python3 pipeline/10_imputed_panels.py --vcf "$PREP" --out "$RAW/imputed_panels.tsv" 2>&1 | tail -5
python3 pipeline/11_prs.py --vcf "$PREP" --out "$RAW/prs_scores.tsv" \
    --per-variant-out "$RAW/prs_per_variant.tsv" 2>&1 | tail -10

echo "[7/7] Export findings (schema v2, source=wgs)"
python3 -m pipeline.export_findings --raw "$RAW" --source wgs

echo "✓ WGS pipeline complete → output/findings/genomic_findings.json"
```

- [ ] **Step 2: Write a smoke test**

Append to `tests/wgs/test_prep_wgs_vcf.py`:
```python
def test_orchestrator_omits_topmed_steps():
    text = Path("pipeline/00_run_wgs.sh").read_text()
    assert "TOPMED_PASS" not in text
    assert "decrypt" not in text.lower()
    assert "--source wgs" in text
    assert "output/raw_findings/wgs" in text
```

- [ ] **Step 3: Make executable, run test, commit**

Run:
```bash
chmod +x pipeline/00_run_wgs.sh
python3 -m pytest tests/wgs/ -v
```
Expected: PASS
```bash
git add pipeline/00_run_wgs.sh tests/wgs/test_prep_wgs_vcf.py
git commit -m "wgs: 00_run_wgs.sh orchestrator"
```

---

## Task 7: End-to-end run on the real gVCF (manual validation)

Not a unit test — a one-time real-data validation. **Long-running** (ClinVar download ~180 MB; full scan of 5 M sites; PharmCAT JVM; PRS downloads).

- [ ] **Step 1: Run the full pipeline**

Run: `bash pipeline/00_run_wgs.sh 2>&1 | tee logs/wgs_run_$(date +%Y%m%d).log`
Expected: completes through `[7/7]`, writes `output/findings/genomic_findings.json`.

- [ ] **Step 2: Sanity-check the findings**

Run:
```bash
python3 - <<'PY'
import json
d = json.load(open("output/findings/genomic_findings.json"))
print("schema", d["schema_version"], "rows", len(d["rows"]))
print("sources", set(r["source"] for r in d["rows"]))
print("scan_tiers", {r["scan_tier"] for r in d["rows"]})
expl = [r for r in d["rows"] if r["scan_tier"]=="exploratory"]
print("exploratory rows", len(expl), "(<=200 cap)")
PY
```
Expected: `schema 2`, `sources {'wgs'}`, both scan tiers present, exploratory ≤ 200.

- [ ] **Step 3: Spot-check a known indel normalized correctly**

Run: `bcftools view -H data/wgs/SQ8TH633.wgs.pass.vcf.gz 1:82133 | cut -f1-5`
Expected: left-aligned/trimmed biallelic records (the §9 acceptance check on real data).

- [ ] **Step 4: Commit any config/doc adjustments surfaced by the run** (no code expected if tasks 1–6 are correct).

---

## Task 8: Document the WGS entrypoint

**Files:**
- Modify: `README.md` (add a short "WGS path" section near the architecture diagram)

- [ ] **Step 1: Add a README section**

Under the Architecture section, add:
```markdown
### Alternative input: 30× WGS (no imputation)

If you have whole-genome sequencing instead of (or in addition to) the chip,
skip phases 1–2 entirely and run:

    GVCF=data/wgs/<sample>.snp-indel.genome.vcf.gz bash pipeline/00_run_wgs.sh

This normalizes the gVCF, runs tiered ClinVar/ACMG (actionable + exploratory),
panels, PRS, and PharmCAT, and writes a schema-v2 `genomic_findings.json`
(`source=wgs`). See `docs/superpowers/specs/2026-06-07-wgs-snv-indel-path-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README — WGS (no-imputation) entrypoint"
```

---

## Self-review checklist (run before execution)

- **Spec coverage:** prep (T5) ✓, mandatory left-align + FASTA (T1, T5) ✓, tiered ClinVar actionable+exploratory with dedupe+cap (T4) ✓, scan_tier/source schema v2 in both FINDINGS_COLUMNS and parquet schema (T2) ✓, clinvar_exploratory registration (T3) ✓, keep imputed_panels.tsv filename (T6) ✓, flat wgs/ dir + `--raw`/`--source` supersede (T2, T6) ✓, reuse 10/11/PharmCAT (T6) ✓, tests incl. orchestrator + carrier + panels/PRS-on-WGS (T4–T6) ✓, prs_per_variant report-only (T6 — not registered) ✓.
- **clinvar_full duplication** avoided: actionable mode does NOT write full; exploratory excludes actionable keys (T4). ✓
- **Legacy imputed path** unchanged: `--mode` defaults to `legacy` = current 3-file behavior; `00_run_phase3.sh` passes no `--mode` (T4). ✓
- **Pre-existing bug** (export flat-dir vs `imputed_grch38/`): out of scope, flagged in spec §11 — not touched here. ✓
```
