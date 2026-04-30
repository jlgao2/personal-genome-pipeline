#!/usr/bin/env bash
# QC the raw GRCh37 VCF using bcftools + a minimal plink2 missingness pass.
# Sex inference and proper het analysis aren't meaningful for a single sample with no
# allele-frequency reference, so we keep this lightweight.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VCF=data/raw_grch37.vcf.gz
PLINK=refs/plink2
QC_DIR=output/qc
mkdir -p "$QC_DIR"

# Sex inferred from chrY presence in raw 23andMe (3733 calls) + male-style hemizygous
# X calls in the source TSV. Recorded for downstream tools.
echo "George_Gao\tmale" > "$QC_DIR/inferred_sex.txt"

# Per-chromosome variant counts from bcftools
bcftools view -H "$VCF" | awk '{print $1}' | sort | uniq -c | sort -k2,2V \
    > "$QC_DIR/per_chrom_count.txt"

# Per-sample missingness on autosomes (plink2 needs no AF for this)
$PLINK --vcf "$VCF" \
       --autosome \
       --missing sample-only \
       --out "$QC_DIR/missingness" >/dev/null 2>&1

# Compute total/non-ref-only/no-alt counts directly from bcftools stats
bcftools stats "$VCF" | grep -E "^SN" > "$QC_DIR/bcftools_stats.txt"

# Compose summary
{
    echo "# Phase 1 — QC summary"
    echo ""
    echo "## Sample"
    echo "- ID: George_Gao"
    echo "- Inferred sex: male (chrY genotypes present, hemizygous X calls in source TSV)"
    echo "- Source: 23andMe v5 chip, GRCh37"
    echo ""
    echo "## bcftools stats"
    echo '```'
    cat "$QC_DIR/bcftools_stats.txt"
    echo '```'
    echo ""
    echo "## Sample missingness (autosomes)"
    if [[ -f "$QC_DIR/missingness.smiss" ]]; then
        echo '```'
        cat "$QC_DIR/missingness.smiss"
        echo '```'
    fi
    echo ""
    echo "## Per-chromosome variant counts"
    echo '```'
    cat "$QC_DIR/per_chrom_count.txt"
    echo '```'
} > "$QC_DIR/summary.md"

cat "$QC_DIR/summary.md"
