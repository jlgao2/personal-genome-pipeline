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
# pharmcat_positions.vcf.bgz is chr-prefixed; our prep VCF is not. Rename prep
# contigs to chr-prefix so the -R slice (and PharmCAT, which expects chr-named
# GRCh38) line up. Without this the slice is empty and PharmCAT no-calls everything.
PHARMCAT_RENAME=$(mktemp)
for c in {1..22} X Y; do printf '%s\tchr%s\n' "$c" "$c"; done > "$PHARMCAT_RENAME"
bcftools annotate --rename-chrs "$PHARMCAT_RENAME" "$PREP" -Oz -o data/wgs_prep_chr.vcf.gz
bcftools index -t data/wgs_prep_chr.vcf.gz
rm -f "$PHARMCAT_RENAME"
bcftools view -R refs/pharmcat/pharmcat_positions.vcf.bgz data/wgs_prep_chr.vcf.gz \
    -Oz -o data/wgs_pharmcat_positions.vcf.gz
bcftools index -t data/wgs_pharmcat_positions.vcf.gz
NSLICE=$(bcftools index -n data/wgs_pharmcat_positions.vcf.gz)
echo "  PharmCAT positions slice: $NSLICE records"
[[ "$NSLICE" -gt 0 ]] || { echo "ERROR: PharmCAT positions slice is empty — chr-naming mismatch?" >&2; exit 1; }
mkdir -p output/pharmcat
PATH="/opt/homebrew/opt/openjdk/bin:$PATH" java -jar refs/pharmcat/pharmcat.jar \
    -vcf data/wgs_pharmcat_positions.vcf.gz -reporterHtml -reporterJson -reporterCallsOnlyTsv \
    -o output/pharmcat 2>&1 | tail -8
rm -f data/wgs_prep_chr.vcf.gz data/wgs_prep_chr.vcf.gz.tbi

echo "[6/7] Panels + PRS"
python3 pipeline/10_imputed_panels.py --vcf "$PREP" --out "$RAW/imputed_panels.tsv" 2>&1 | tail -5
python3 pipeline/11_prs.py --vcf "$PREP" --out "$RAW/prs_scores.tsv" \
    --per-variant-out "$RAW/prs_per_variant.tsv" 2>&1 | tail -10

echo "[7/7] Export findings (schema v2, source=wgs)"
python3 -m pipeline.export_findings --raw "$RAW" --source wgs

echo "✓ WGS pipeline complete → output/findings/genomic_findings.json"
