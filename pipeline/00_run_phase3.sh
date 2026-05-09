#!/usr/bin/env bash
# Phase 3 — runs after TOPMed imputation results have been downloaded:
#   - decrypt zips
#   - concat per-chrom VCFs
#   - extract user only
#   - filter R2 >= 0.8
#   - run PharmCAT
#   - run ClinVar/ACMG annotation
#   - run nutrition / PGx panels
#   - run polygenic risk scores
#
# Requires TOPMED_PASS env var (the password TOPMed emailed you).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${TOPMED_PASS:-}" ]]; then
    echo "ERROR: TOPMED_PASS env var not set" >&2
    echo "  Usage: TOPMED_PASS='your-pass-from-email' bash pipeline/00_run_phase3.sh" >&2
    exit 2
fi

SAMPLE_NAME="${SAMPLE_NAME:-Subject}"

# ── 1. Decrypt + concat + extract + filter ──
echo "[1/6] Decrypt, concatenate, extract single sample, R²≥0.8 filter"
TOPMED_PASS="$TOPMED_PASS" SAMPLE_NAME="$SAMPLE_NAME" bash pipeline/run_post_imputation_pipeline.sh

# ── 2. Download GRCh38 ClinVar (180 MB) if needed ──
if [[ ! -f refs/clinvar_grch38.vcf.gz ]]; then
    echo ""
    echo "[2/6] Download GRCh38 ClinVar"
    curl -sL -o refs/clinvar_grch38.vcf.gz \
        "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz"
    curl -sL -o refs/clinvar_grch38.vcf.gz.tbi \
        "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz.tbi"
fi

# ── 3. PharmCAT ──
echo ""
echo "[3/6] PharmCAT (extract positions and run JAR)"
bcftools view -R refs/pharmcat/pharmcat_positions.vcf.bgz \
    data/imputed_grch38_r2_0.8.vcf.gz \
    -Oz -o data/imputed_pharmcat_positions.vcf.gz
bcftools index -t data/imputed_pharmcat_positions.vcf.gz
mkdir -p output/pharmcat
PATH="/opt/homebrew/opt/openjdk/bin:$PATH" \
java -jar refs/pharmcat/pharmcat.jar \
    -vcf data/imputed_pharmcat_positions.vcf.gz \
    -reporterHtml -reporterJson -reporterCallsOnlyTsv \
    -o output/pharmcat 2>&1 | tail -8

# ── 4. ClinVar / ACMG ──
echo ""
echo "[4/6] ClinVar annotation (P/LP variants in ACMG SF v3.2 + carrier panel)"
mkdir -p output/raw_findings/imputed_grch38
python3 pipeline/06_clinvar_acmg.py \
    --vcf data/imputed_grch38_r2_0.8.vcf.gz \
    --clinvar refs/clinvar_grch38.vcf.gz \
    --build GRCh38 \
    --outdir output/raw_findings/imputed_grch38 \
    --min-stars 2 2>&1 | tail -5

# ── 5. Nutrition / PGx / extra-traits panels ──
echo ""
echo "[5/6] Nutrition + PGx + extra-traits panels (rsID-based)"
python3 pipeline/10_imputed_panels.py \
    --vcf data/imputed_grch38_r2_0.8.vcf.gz \
    --out output/raw_findings/imputed_panels.tsv 2>&1 | tail -5

# ── 6. Polygenic Risk Scores ──
echo ""
echo "[6/7] Polygenic Risk Scores (10 PGS Catalog scores)"
python3 pipeline/11_prs.py \
    --vcf data/imputed_grch38.vcf.gz \
    --out output/raw_findings/prs_scores.tsv \
    --per-variant-out output/raw_findings/prs_per_variant.tsv 2>&1 | tail -15

# ── 7. Aggregate findings → JSON contract ──
echo ""
echo "[7/7] Aggregating findings → JSON contract for downstream consumers"
python3 -m pipeline.export_findings 2>&1 | tail -3

echo ""
echo "===================================="
echo " ✓ Phase 3 complete."
echo "===================================="
echo ""
echo "Outputs:"
echo "  output/pharmcat/imputed_pharmcat_positions.report.html  ← open in browser"
echo "  output/raw_findings/imputed_panels.tsv                  ← nutrition + PGx + traits"
echo "  output/raw_findings/imputed_grch38/clinvar_acmg.tsv     ← ACMG SF v3.2 hits"
echo "  output/raw_findings/imputed_grch38/carrier_status.tsv   ← Carrier panel hits"
echo "  output/raw_findings/prs_scores.tsv                      ← Polygenic risk scores"
echo "  output/findings/genomic_findings.json                   ← public artifact for Prefrontal Cortex"
echo ""
echo "Build the dashboard:"
echo "  python3 pipeline/13_build_report.py"
echo "  python3 -m http.server 8732 --directory output/web"
echo "  open http://localhost:8732"
