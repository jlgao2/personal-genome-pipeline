#!/usr/bin/env bash
# Pad the user's single-sample VCF with public 1000G phase 3 samples
# (mixed populations) so we hit the TOPMed Imputation Server minimum of 20 samples.
#
# Inputs:  data/raw_grch37.vcf.gz, data/topmed_input/chr*.vcf.gz
# Outputs: data/topmed_input_padded/chr*.vcf.gz   (>= 20 samples each)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUTDIR=data/topmed_input_padded
mkdir -p "$OUTDIR" data/1000g_pad logs

# 30 verified 1000G phase 3 sample IDs (from chr1 v5b header). Mix of populations.
# All confirmed present in both autosomes + chrX in v5b/v1c releases.
SAMPLES="HG00096,HG00097,HG00099,HG00100,HG00101,\
HG00102,HG00103,HG00105,HG00106,HG00107,\
HG00108,HG00109,HG00110,HG00111,HG00112,\
HG00113,HG00114,HG00115,HG00116,HG00117,\
HG00118,HG00119,HG00120,HG00121,HG00122,\
HG00123,HG00125,HG00126,HG00127,HG00128"

# Build chip-positions tsv (CHROM\tPOS) once
POS_TSV=data/chip_positions.tsv
if [[ ! -f "$POS_TSV" ]]; then
    echo "Building chip-positions TSV..."
    bcftools view -H data/raw_grch37.vcf.gz \
        | awk -v OFS='\t' '{print $1, $2}' \
        > "$POS_TSV"
    echo "  $(wc -l <"$POS_TSV") positions"
fi

# Per-chromosome work — pull 1000G subset and merge with user's chr VCF
process_chrom() {
    local CHR="$1"
    local URL_FILE="$2"

    echo "  [chr$CHR] starting"
    local PAD_LOCAL="data/1000g_pad/chr${CHR}.vcf.gz"
    local USR="data/topmed_input/chr${CHR}.vcf.gz"
    local OUT="$OUTDIR/chr${CHR}.vcf.gz"

    if [[ ! -f "$PAD_LOCAL" ]]; then
        # Per-chr position list
        awk -v c="$CHR" '$1==c {print $1"\t"$2}' "$POS_TSV" \
            > "data/1000g_pad/chr${CHR}.tsv"

        bcftools view -r "$CHR" \
                      -T "data/1000g_pad/chr${CHR}.tsv" \
                      -s "$SAMPLES" \
                      --force-samples \
                      "$URL_FILE" 2>"logs/1000g_chr${CHR}.log" \
        | bcftools annotate -x INFO 2>>"logs/1000g_chr${CHR}.log" \
        | bcftools view -Oz -o "$PAD_LOCAL" 2>>"logs/1000g_chr${CHR}.log"

        bcftools index -t "$PAD_LOCAL"
    fi

    bcftools merge "$USR" "$PAD_LOCAL" -Oz -o "$OUT" 2>"logs/merge_chr${CHR}.log"
    bcftools index -t "$OUT"

    local NSAMP=$(bcftools query -l "$OUT" | wc -l | tr -d ' ')
    local NVAR=$(bcftools view -H "$OUT" | wc -l | tr -d ' ')
    local NPAD=$(bcftools view -H "$PAD_LOCAL" | wc -l | tr -d ' ')
    echo "  [chr$CHR] DONE  (1000G pad: $NPAD vars × ?; merged: $NVAR vars × $NSAMP samples)"
}

# Run autosomes 1-22 with 3 in parallel (1000G FTP can handle this)
PIDS=()
for CHR in {1..22}; do
    URL="https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/ALL.chr${CHR}.phase3_shapeit2_mvncall_integrated_v5b.20130502.genotypes.vcf.gz"
    process_chrom "$CHR" "$URL" &
    PIDS+=($!)

    # Cap concurrency at 3 active downloads
    if (( ${#PIDS[@]} >= 3 )); then
        wait "${PIDS[0]}"
        PIDS=("${PIDS[@]:1}")
    fi
done

# chrX (different URL pattern, single)
URL="https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/ALL.chrX.phase3_shapeit2_mvncall_integrated_v1c.20130502.genotypes.vcf.gz"
process_chrom "X" "$URL" &
PIDS+=($!)

# Wait for all remaining
for pid in "${PIDS[@]}"; do
    wait "$pid"
done

echo ""
echo "=== Done. New TOPMed input directory: $OUTDIR/ ==="
ls -lh "$OUTDIR/"*.vcf.gz | awk '{print $5, $9}'
echo ""
echo "Sample list (first chr1 file):"
bcftools query -l "$OUTDIR/chr1.vcf.gz"
echo ""
echo "Total: $(bcftools query -l "$OUTDIR/chr1.vcf.gz" | wc -l | tr -d ' ') samples"
