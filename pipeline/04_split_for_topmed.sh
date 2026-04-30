#!/usr/bin/env bash
# Prepare TOPMed-ready per-chromosome VCFs.
# TOPMed Imputation Server requirements (April 2026):
#   - Build: GRCh37 OR GRCh38 (server lifts over)
#   - One bgzipped VCF per autosome (chr1..chr22), and chrX as a separate file
#   - Variants must be sorted, biallelic, and have unique positions
#   - Sample IDs must be consistent across files
#   - Y and MT are NOT imputed (server skips them)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VCF=data/raw_grch37.vcf.gz
OUT=data/topmed_input
mkdir -p "$OUT"

# Note: TOPMed expects "chr1", "chr2"... prefix in some panels; r3 accepts both.
# We pass through as-is (numeric) since server auto-detects. If it rejects, we'd add chr prefix.

for CHR in {1..22} X; do
    bcftools view -r "$CHR" -Oz -o "$OUT/chr${CHR}.vcf.gz" "$VCF"
    bcftools index -t "$OUT/chr${CHR}.vcf.gz"
done

echo ""
echo "=== TOPMed input files ==="
ls -lh "$OUT/" | grep -v '^total' | awk '{print $5"\t"$9}'
echo ""
echo "Total size: $(du -sh "$OUT" | awk '{print $1}')"
