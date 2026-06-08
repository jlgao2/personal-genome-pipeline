# WGS SV/CNV Annotation Path (Spec B) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Annotate the 5,265 Manta SVs + ~489 Canvas CNVs with AnnotSV, tier by ACMG SV class, and fold the results into `genomic_findings.json` via the schema-v2 machinery.

**Architecture:** A new prep step cleans the SV/CNV VCFs; AnnotSV (conda env `annotsv`, GRCh38 annotations) annotates each and assigns an ACMG class 1–5; a new parser turns the ranked TSV into tiered findings rows (4–5 `actionable`, 3 `exploratory`); a registration in `parsers/genome.py` makes `export_findings` pick them up. Isolated in its own orchestrator so AnnotSV's weight never touches the core WGS run.

**Tech Stack:** bash, `bcftools`, AnnotSV 3.5.10 (conda env `annotsv`, run via `mamba run -n annotsv`), Python 3 stdlib, `pytest`.

**Design source:** `docs/superpowers/specs/2026-06-07-wgs-sv-cnv-annotsv-design.md`.

---

## File structure

| File | Responsibility | New/Modified |
|---|---|---|
| `pipeline/wgs/prep_sv_cnv.sh` | SV/CNV VCF → clean PASS, real-ALT VCFs for AnnotSV | New |
| `pipeline/15_parse_annotsv.py` | AnnotSV TSV → tiered `sv_cnv_findings.tsv` | New |
| `pipeline/parsers/genome.py` | register `parse_sv_cnv_tsv` in `TSV_PARSERS` | Modify |
| `pipeline/00_run_wgs_sv.sh` | orchestrator: prep → AnnotSV → parse → export | New |
| `tests/wgs/test_prep_sv_cnv.py` | prep transforms | New |
| `tests/wgs/test_parse_annotsv.py` | parser tiering + mapping | New |
| `tests/wgs/fixtures/sv_sample.vcf`, `cnv_sample.vcf`, `annotsv_sample.tsv` | fixtures | New |

AnnotSV itself is NOT run in unit tests (heavy external tool); it's validated in Task 5's real run. Unit tests cover our prep + parser.

---

## Task 1: `prep_sv_cnv.sh`

**Files:** Create `pipeline/wgs/prep_sv_cnv.sh`, `tests/wgs/fixtures/sv_sample.vcf`, `tests/wgs/fixtures/cnv_sample.vcf`, `tests/wgs/test_prep_sv_cnv.py`.

- [ ] **Step 1: Create `tests/wgs/fixtures/sv_sample.vcf`** (tabs between columns):
```
##fileformat=VCFv4.2
##FILTER=<ID=PASS,Description="">
##FILTER=<ID=FAIL,Description="">
##INFO=<ID=SVTYPE,Number=1,Type=String,Description="">
##INFO=<ID=END,Number=1,Type=Integer,Description="">
##INFO=<ID=SVLEN,Number=1,Type=Integer,Description="">
##contig=<ID=1>
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO	FORMAT	SQ8TH633
1	1157306	MantaDEL:1	C	<DEL>	50	PASS	SVTYPE=DEL;END=1157381;SVLEN=-75	GT	0/1
1	2000000	MantaDUP:1	C	<DUP>	40	FAIL	SVTYPE=DUP;END=2010000;SVLEN=10000	GT	0/1
```

- [ ] **Step 2: Create `tests/wgs/fixtures/cnv_sample.vcf`** (Canvas: REF segments have ALT='.'):
```
##fileformat=VCFv4.2
##FILTER=<ID=PASS,Description="">
##INFO=<ID=SVTYPE,Number=1,Type=String,Description="">
##INFO=<ID=END,Number=1,Type=Integer,Description="">
##ALT=<ID=CN0,Description="">
##contig=<ID=1>
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO	FORMAT	SQ8TH633
1	818759	Canvas:REF:1	N	.	18	PASS	END=1366066	GT	./.
1	5000000	Canvas:GAIN:1	N	<CN0>	30	PASS	SVTYPE=CNV;END=5100000	GT	./.
```

- [ ] **Step 3: Write the failing test** `tests/wgs/test_prep_sv_cnv.py`:
```python
import subprocess
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
SCRIPT = Path("pipeline/wgs/prep_sv_cnv.sh")


def _bgzip(src, dst):
    subprocess.run(f"bgzip -f -c {src} > {dst} && tabix -f -p vcf {dst}", shell=True, check=True)


def test_prep_sv_cnv(tmp_path):
    sv_in, cnv_in = tmp_path / "sv.vcf.gz", tmp_path / "cnv.vcf.gz"
    _bgzip(FIX / "sv_sample.vcf", sv_in)
    _bgzip(FIX / "cnv_sample.vcf", cnv_in)
    sv_out, cnv_out = tmp_path / "sv.clean.vcf.gz", tmp_path / "cnv.clean.vcf.gz"
    subprocess.run(["bash", str(SCRIPT), str(sv_in), str(cnv_in), str(sv_out), str(cnv_out)],
                   check=True, capture_output=True)
    sv = subprocess.run(["bcftools", "view", "-H", str(sv_out)], capture_output=True, text=True, check=True).stdout
    cnv = subprocess.run(["bcftools", "view", "-H", str(cnv_out)], capture_output=True, text=True, check=True).stdout
    # SV: PASS DEL kept, FAIL DUP dropped
    assert "MantaDEL:1" in sv and "MantaDUP:1" not in sv
    # CNV: real CN0 call kept, REF segment dropped
    assert "Canvas:GAIN:1" in cnv and "Canvas:REF:1" not in cnv
```

- [ ] **Step 4: Run → FAIL** (script missing): `python3 -m pytest tests/wgs/test_prep_sv_cnv.py -v`

- [ ] **Step 5: Write `pipeline/wgs/prep_sv_cnv.sh`:**
```bash
#!/usr/bin/env bash
# Clean Manta SV + Canvas CNV VCFs for AnnotSV.
#   SV : restrict to 1..22,X,Y, keep FILTER=PASS, drop ALT='.'
#   CNV: restrict to 1..22,X,Y, drop Canvas REF segments (ALT='.')  [Canvas quality is per-sample FT, not site FILTER]
# Usage: prep_sv_cnv.sh <sv.vcf.gz> <cnv.vcf.gz> <out_sv.vcf.gz> <out_cnv.vcf.gz>
set -euo pipefail
SV_IN="${1:?}"; CNV_IN="${2:?}"; SV_OUT="${3:?}"; CNV_OUT="${4:?}"
REGIONS=$(printf '%s,' {1..22} X Y | sed 's/,$//')
bcftools view -r "$REGIONS" -f PASS -e 'ALT="."' "$SV_IN"  -Oz -o "$SV_OUT";  tabix -f -p vcf "$SV_OUT"
bcftools view -r "$REGIONS"         -e 'ALT="."' "$CNV_IN" -Oz -o "$CNV_OUT"; tabix -f -p vcf "$CNV_OUT"
echo "SV: $(bcftools index -n "$SV_OUT")  CNV: $(bcftools index -n "$CNV_OUT")"
```

- [ ] **Step 6: `chmod +x pipeline/wgs/prep_sv_cnv.sh`; run → PASS.**

- [ ] **Step 7: Commit:**
```bash
git add pipeline/wgs/prep_sv_cnv.sh tests/wgs/test_prep_sv_cnv.py tests/wgs/fixtures/sv_sample.vcf tests/wgs/fixtures/cnv_sample.vcf
git commit -m "wgs: prep_sv_cnv.sh — clean SV/CNV VCFs for AnnotSV"
```

---

## Task 2: `15_parse_annotsv.py` — AnnotSV TSV → tiered findings

AnnotSV writes a TSV with one "full" row per SV (`Annotation_mode=full`, carrying the SV-level `ACMG_class` 1–5) plus per-gene "split" rows. We use the **full** rows.

**Files:** Create `pipeline/15_parse_annotsv.py`, `tests/wgs/fixtures/annotsv_sample.tsv`, `tests/wgs/test_parse_annotsv.py`.

- [ ] **Step 1: Create `tests/wgs/fixtures/annotsv_sample.tsv`** (minimal AnnotSV-format columns, tabs):
```
AnnotSV_ID	SV_chrom	SV_start	SV_end	SV_length	SV_type	Annotation_mode	Gene_name	ACMG_class
1_1157306_1157381_DEL	1	1157306	1157381	-75	DEL	full	BRCA1	5
1_1157306_1157381_DEL	1	1157306	1157381	-75	DEL	split	BRCA1	5
2_500_9000_DUP	2	500	9000	8500	DUP	full	XYZ	3
3_10_20_DEL	3	10	20	10	DEL	full	BENIGN1	1
```

- [ ] **Step 2: Write the failing test** `tests/wgs/test_parse_annotsv.py`:
```python
import subprocess, sys
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "annotsv_sample.tsv"
SCRIPT = Path("pipeline/15_parse_annotsv.py")


def test_parse_annotsv_tiers(tmp_path):
    out = tmp_path / "sv_cnv_findings.tsv"
    subprocess.run([sys.executable, str(SCRIPT), "--annotsv", str(FIX),
                    "--caller", "manta", "--out", str(out)], check=True, capture_output=True)
    rows = [l.split("\t") for l in out.read_text().splitlines()]
    header, data = rows[0], rows[1:]
    col = {c: i for i, c in enumerate(header)}
    # class 5 + class 3 kept (full rows only → 2 rows); class 1 dropped; split row not double-counted
    genes = {r[col["gene"]] for r in data}
    assert genes == {"BRCA1", "XYZ"}
    by_gene = {r[col["gene"]]: r for r in data}
    assert by_gene["BRCA1"][col["scan_tier"]] == "actionable"   # class 5
    assert by_gene["XYZ"][col["scan_tier"]] == "exploratory"    # class 3
    assert by_gene["BRCA1"][col["svtype"]] == "DEL"
    assert by_gene["BRCA1"][col["caller"]] == "manta"
```

- [ ] **Step 3: Run → FAIL** (script missing).

- [ ] **Step 4: Write `pipeline/15_parse_annotsv.py`:**
```python
#!/usr/bin/env python3
"""Parse an AnnotSV output TSV into tiered SV/CNV findings.

Uses AnnotSV "full" rows (one per SV, carrying the SV-level ACMG_class 1-5).
Keeps class >= 3; tiers 4-5 -> actionable, 3 -> exploratory; sorts exploratory by
class desc and caps. Emits output/raw_findings/wgs/sv_cnv_findings.tsv.
"""
import argparse
import csv
import sys

COLS = ["chrom", "start", "end", "svtype", "svlen", "gene", "acmg_class",
        "scan_tier", "caller", "summary"]


def parse(annotsv_path, caller, cap):
    rows = []
    with open(annotsv_path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            if r.get("Annotation_mode") != "full":
                continue
            try:
                cls = int(r.get("ACMG_class", ""))
            except ValueError:
                continue
            if cls < 3:
                continue
            svtype = r.get("SV_type", "")
            gene = r.get("Gene_name", "")
            scan_tier = "actionable" if cls >= 4 else "exploratory"
            label = {5: "pathogenic", 4: "likely pathogenic", 3: "uncertain"}.get(cls, str(cls))
            summary = f"{svtype} overlapping {gene} — AnnotSV class {cls} ({label})"
            rows.append({
                "chrom": r.get("SV_chrom", ""), "start": r.get("SV_start", ""),
                "end": r.get("SV_end", ""), "svtype": svtype, "svlen": r.get("SV_length", ""),
                "gene": gene, "acmg_class": cls, "scan_tier": scan_tier,
                "caller": caller, "summary": summary,
            })
    # actionable kept whole; exploratory sorted by class desc then capped
    actionable = [r for r in rows if r["scan_tier"] == "actionable"]
    exploratory = sorted([r for r in rows if r["scan_tier"] == "exploratory"],
                         key=lambda r: -r["acmg_class"])[:cap]
    return actionable + exploratory


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotsv", required=True)
    ap.add_argument("--caller", required=True, choices=["manta", "canvas"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--cap", type=int, default=200)
    args = ap.parse_args()
    rows = parse(args.annotsv, args.caller, args.cap)
    with open(args.out, "a" if args.out.endswith(".append") else "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    sys.stderr.write(f"{args.caller}: wrote {len(rows)} SV/CNV findings to {args.out}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run → PASS.** **Step 6: Commit:**
```bash
git add pipeline/15_parse_annotsv.py tests/wgs/test_parse_annotsv.py tests/wgs/fixtures/annotsv_sample.tsv
git commit -m "wgs: 15_parse_annotsv.py — AnnotSV TSV to tiered SV/CNV findings"
```

> **Validation note for Task 5:** AnnotSV's real column names must be confirmed against actual output (`SV_chrom/SV_start/SV_end/SV_length/SV_type/Annotation_mode/Gene_name/ACMG_class` are the AnnotSV 3.x defaults). If the real header differs, adjust the `r.get(...)` keys and re-run the test.

---

## Task 3: Register `parse_sv_cnv_tsv` in `genome.py`

**Files:** Modify `pipeline/parsers/genome.py`; modify `tests/parsers/test_genome.py`.

- [ ] **Step 1: Append failing test** to `tests/parsers/test_genome.py`:
```python
def test_parse_sv_cnv_tsv(tmp_path):
    from pipeline.parsers.genome import TSV_PARSERS, parse_sv_cnv_tsv
    assert "sv_cnv_findings.tsv" in [n for n, _ in TSV_PARSERS]
    f = tmp_path / "sv_cnv_findings.tsv"
    f.write_text(
        "chrom\tstart\tend\tsvtype\tsvlen\tgene\tacmg_class\tscan_tier\tcaller\tsummary\n"
        "1\t1157306\t1157381\tDEL\t-75\tBRCA1\t5\tactionable\tmanta\tDEL overlapping BRCA1 — AnnotSV class 5 (pathogenic)\n"
    )
    rows = list(parse_sv_cnv_tsv(f))
    r = rows[0]
    assert r["source_tsv"] == "sv_cnv" and r["gene"] == "BRCA1"
    assert r["alt"] == "<DEL>" and r["tier"] == "A" and r["scan_tier"] == "actionable"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add to `pipeline/parsers/genome.py`** (after `parse_prs_scores_tsv`):
```python
def parse_sv_cnv_tsv(tsv_path: Path) -> Iterator[dict]:
    """Yield canonical rows from sv_cnv_findings.tsv (AnnotSV-derived)."""
    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            cls = _maybe_int(row.get("acmg_class"))
            tier = "A" if cls == 5 else ("B" if cls == 4 else "C")
            yield _row(
                source_tsv="sv_cnv",
                scan_tier=row.get("scan_tier") or "actionable",
                gene=row.get("gene"),
                chrom=row.get("chrom"),
                pos=_maybe_int(row.get("start")),
                ref="N",
                alt=f"<{row.get('svtype')}>",
                tier=tier,
                summary=row.get("summary"),
                meta={
                    "end": _maybe_int(row.get("end")), "svlen": row.get("svlen"),
                    "svtype": row.get("svtype"), "acmg_class": cls, "caller": row.get("caller"),
                },
            )
```
Register in `TSV_PARSERS` (after the `clinvar_exploratory.tsv` line):
```python
    ("sv_cnv_findings.tsv", lambda p: parse_sv_cnv_tsv(p)),
```

- [ ] **Step 4: Run `python3 -m pytest tests/ -q` → PASS.** **Step 5: Commit:**
```bash
git add pipeline/parsers/genome.py tests/parsers/test_genome.py
git commit -m "findings: register sv_cnv_findings.tsv (AnnotSV-derived rows)"
```

---

## Task 4: `00_run_wgs_sv.sh` orchestrator

**Files:** Create `pipeline/00_run_wgs_sv.sh`; append a smoke test to `tests/wgs/test_prep_sv_cnv.py`.

- [ ] **Step 1: Write `pipeline/00_run_wgs_sv.sh`:**
```bash
#!/usr/bin/env bash
# SV/CNV annotation pipeline (AnnotSV). Isolated from the core WGS run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
SV=data/wgs/SQ8TH633.30x.sv.vcf.gz
CNV=data/wgs/SQ8TH633.30x.cnv.vcf.gz
RAW=output/raw_findings/wgs
TMP=data/wgs/sv_cnv; mkdir -p "$TMP" "$RAW" output/annotsv

echo "[1/4] prep SV/CNV"
bash pipeline/wgs/prep_sv_cnv.sh "$SV" "$CNV" "$TMP/sv.clean.vcf.gz" "$TMP/cnv.clean.vcf.gz"

echo "[2/4] AnnotSV (GRCh38)"
for kind in sv cnv; do
  mamba run -n annotsv AnnotSV -SVinputFile "$TMP/$kind.clean.vcf.gz" \
     -genomeBuild GRCh38 -outputDir output/annotsv -outputFile "$kind.annotated"
done

echo "[3/4] parse → tiered findings (sv first, then append cnv)"
python3 pipeline/15_parse_annotsv.py --annotsv output/annotsv/sv.annotated.tsv  --caller manta  --out "$RAW/sv_cnv_findings.tsv"
python3 pipeline/15_parse_annotsv.py --annotsv output/annotsv/cnv.annotated.tsv --caller canvas --out "$RAW/sv_cnv_findings.tsv.append"
tail -n +2 "$RAW/sv_cnv_findings.tsv.append" >> "$RAW/sv_cnv_findings.tsv" && rm -f "$RAW/sv_cnv_findings.tsv.append"

echo "[4/4] export findings (schema v2, source=wgs)"
python3 -m pipeline.export_findings --raw "$RAW" --source wgs
echo "✓ SV/CNV findings folded into output/findings/genomic_findings.json"
```

- [ ] **Step 2: Append smoke test** to `tests/wgs/test_prep_sv_cnv.py`:
```python
def test_sv_orchestrator_shape():
    from pathlib import Path
    text = Path("pipeline/00_run_wgs_sv.sh").read_text()
    assert "mamba run -n annotsv AnnotSV" in text
    assert "15_parse_annotsv.py" in text
    assert "output/raw_findings/wgs" in text
```

- [ ] **Step 3: `chmod +x`; `bash -n pipeline/00_run_wgs_sv.sh`; run tests → PASS. Commit:**
```bash
git add pipeline/00_run_wgs_sv.sh tests/wgs/test_prep_sv_cnv.py
git commit -m "wgs: 00_run_wgs_sv.sh — SV/CNV AnnotSV orchestrator"
```

---

## Task 5: End-to-end real run (validation)

Requires the AnnotSV GRCh38 annotation databases installed (`INSTALL_annotations.sh`).

- [ ] **Step 1: Confirm annotations:** `mamba run -n annotsv bash -lc 'ls $(dirname $(which AnnotSV))/../share/AnnotSV/Annotations_Human' | head`
- [ ] **Step 2: Run:** `bash pipeline/00_run_wgs_sv.sh 2>&1 | tee logs/wgs_sv_run.log`
- [ ] **Step 3: Confirm AnnotSV column names** match the parser (`head -1 output/annotsv/sv.annotated.tsv`); if not, fix `15_parse_annotsv.py` keys + re-run Task 2 test.
- [ ] **Step 4: Sanity-check findings:**
```bash
python3 - <<'PY'
import json, collections
d = json.load(open("output/findings/genomic_findings.json"))
sv = [r for r in d["rows"] if r["source_tsv"]=="sv_cnv"]
print("sv/cnv findings:", len(sv), "tiers:", collections.Counter(r["scan_tier"] for r in sv))
PY
```
Expected: a handful of class-3+ SV/CNV findings with `source=wgs`, both scan tiers represented.

---

## Task 6: Document

- [ ] **Step 1: Add a README note** under the WGS section: SV/CNV via `bash pipeline/00_run_wgs_sv.sh` (needs the `annotsv` conda env + GRCh38 annotations); folds AnnotSV class-3+ structural findings into `genomic_findings.json`. Commit `docs: README — WGS SV/CNV (AnnotSV) entrypoint`.

---

## Self-review

- **Spec coverage:** install/annotations (Task 5 prereq) ✓, prep drop-REF-segments + PASS (T1) ✓, AnnotSV per-file (T4) ✓, tiered parse class≥3 with 4–5 actionable / 3 exploratory + cap (T2) ✓, schema reuse `parse_sv_cnv_tsv` registered (T3) ✓, isolated orchestrator (T4) ✓, tests for prep + parser + registration (T1–T3) ✓, real validation (T5) ✓.
- **No schema change** — reuses schema-v2 `source`/`scan_tier`/`tier` from Spec A. ✓
- **Risk carried to T5:** AnnotSV real column names + chr-naming (no-prefix input vs AnnotSV GRCh38 annotation naming) — explicitly validated in Task 5 Step 3.
