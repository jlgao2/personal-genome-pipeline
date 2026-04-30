#!/usr/bin/env bash
# End-to-end orchestration: decrypt -> concat -> extract user only -> filter R2
# -> re-run all annotation pipelines on imputed GRCh38 VCF.
#
# Reads TOPMED_PASS env var for the decryption password (never stored on disk).
#
# Usage:
#   TOPMED_PASS='...' bash pipeline/run_post_imputation_pipeline.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${TOPMED_PASS:-}" ]]; then
    echo "ERROR: TOPMED_PASS env var not set" >&2
    exit 2
fi

OUT_DIR=data/topmed_output

# ---- 1. Decrypt all chr_*.zip files ----
cd "$OUT_DIR"
shopt -s nullglob
ZIPS=(chr_*.zip)
if [[ ${#ZIPS[@]} -eq 0 ]]; then
    echo "ERROR: no chr_*.zip files in $OUT_DIR" >&2
    exit 1
fi

echo "[1/5] Decrypting ${#ZIPS[@]} TOPMed zips (4-way parallel)..."
PIDS=()
for Z in "${ZIPS[@]}"; do
    if [[ -f "${Z%.zip}.dose.vcf.gz" ]]; then
        echo "  $Z (already decrypted)"
        continue
    fi
    echo "  $Z (starting)"
    7z x -p"$TOPMED_PASS" -y -bso0 -bsp0 "$Z" >/dev/null &
    PIDS+=($!)
    # Cap parallelism at 4 — limited by disk and CPU
    if (( ${#PIDS[@]} >= 4 )); then
        wait "${PIDS[0]}"
        PIDS=("${PIDS[@]:1}")
    fi
done
# Wait for any remaining
for pid in "${PIDS[@]}"; do
    wait "$pid"
done
echo "  decryption complete"
cd "$ROOT"

# ---- 2. Concat per-chrom imputed VCFs ----
echo ""
echo "[2/5] Concatenating per-chrom imputed VCFs (autosomes 1-22)..."
ALL=data/imputed_grch38_all_samples.vcf.gz
ORDERED=$(for c in {1..22}; do echo "$OUT_DIR/chr${c}.dose.vcf.gz"; done)
bcftools concat $ORDERED -Oz -o "$ALL" 2>logs/post_imp_concat.log
bcftools index -t "$ALL"

# ---- 3. Extract George_Gao sample only ----
echo "[3/5] Extracting George_Gao sample (dropping 1000G padding)..."
USER_FULL=data/imputed_grch38.vcf.gz
USER_HQ=data/imputed_grch38_r2_0.8.vcf.gz
bcftools view -s George_Gao "$ALL" -Oz -o "$USER_FULL" 2>logs/post_imp_extract.log
bcftools index -t "$USER_FULL"

# ---- 4. R²>=0.8 high-quality filter ----
echo "[4/5] Filtering on INFO/R2 >= 0.8..."
bcftools view -e 'INFO/R2<0.8' "$USER_FULL" -Oz -o "$USER_HQ" 2>logs/post_imp_filter.log
bcftools index -t "$USER_HQ"

# ---- 5. Print summary ----
echo ""
echo "=== Imputation summary ==="
echo "All-samples imputed: $(bcftools view -H "$ALL" | wc -l | tr -d ' ') variants × $(bcftools query -l "$ALL" | wc -l | tr -d ' ') samples"
echo "George_Gao only:     $(bcftools view -H "$USER_FULL" | wc -l | tr -d ' ') variants"
echo "R² ≥ 0.8 subset:     $(bcftools view -H "$USER_HQ" | wc -l | tr -d ' ') variants"
echo ""
echo "=== Disk usage ==="
ls -lh "$ALL" "$USER_FULL" "$USER_HQ" | awk '{print $5, $9}'
echo ""
echo "Done. Imputed user-only VCFs are at:"
echo "  $USER_FULL  (full)"
echo "  $USER_HQ    (R²≥0.8, recommended for downstream)"
