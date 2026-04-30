#!/usr/bin/env bash
# After TOPMed imputation: concat per-chrom VCFs, filter R2>=0.8, index.
# Inputs:  data/topmed_output/chr*.dose.vcf.gz
# Outputs: data/imputed_grch38.vcf.gz, data/imputed_grch38_r2_0.8.vcf.gz
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IN_DIR=data/topmed_output
OUT_FULL=data/imputed_grch38.vcf.gz
OUT_HQ=data/imputed_grch38_r2_0.8.vcf.gz

if ! ls "$IN_DIR"/chr*.dose.vcf.gz >/dev/null 2>&1; then
    echo "ERROR: no imputed VCFs in $IN_DIR. See pipeline/TOPMED_SUBMIT_GUIDE.md" >&2
    exit 1
fi

echo "Concatenating per-chrom imputed VCFs (will contain 24 samples — 1000G pad + George_Gao)..."
bcftools concat $(ls "$IN_DIR"/chr{1..22}.dose.vcf.gz "$IN_DIR"/chrX.dose.vcf.gz 2>/dev/null) \
    -Oz -o data/imputed_grch38_all_samples.vcf.gz
bcftools index -t data/imputed_grch38_all_samples.vcf.gz

echo ""
echo "Extracting George_Gao only (drop 1000G padding samples)..."
bcftools view -s George_Gao data/imputed_grch38_all_samples.vcf.gz \
    -Oz -o "$OUT_FULL"
bcftools index -t "$OUT_FULL"

echo ""
echo "Filtering on INFO/R2 >= 0.8..."
bcftools view -e 'INFO/R2<0.8' "$OUT_FULL" -Oz -o "$OUT_HQ"
bcftools index -t "$OUT_HQ"

echo ""
echo "=== Variant counts ==="
echo "Full imputed (George_Gao only):  $(bcftools view -H "$OUT_FULL" | wc -l | tr -d ' ')"
echo "High-quality (R²≥0.8):           $(bcftools view -H "$OUT_HQ" | wc -l | tr -d ' ')"
