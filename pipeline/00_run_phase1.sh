#!/usr/bin/env bash
# Phase 1 + Phase 2 prep: 23andMe → VCF → QC → 1000G-padded TOPMed inputs
#
# At end of this script: you'll have data/topmed_input_padded_autosomes/
# ready to upload to https://imputation.biodatacatalyst.nhlbi.nih.gov/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ── Find the 23andMe zip in data/ ──
ZIP=$(ls data/*.zip 2>/dev/null | head -1 || true)
if [[ -z "$ZIP" ]]; then
    echo "ERROR: no .zip in data/" >&2
    echo "Drop your 23andMe download here, then re-run." >&2
    exit 1
fi
SAMPLE_NAME="${SAMPLE_NAME:-Subject}"
echo "Sample name: $SAMPLE_NAME"
echo "Source zip:  $ZIP"

# ── Extract ──
echo ""
echo "[1/6] Extract 23andMe TSV"
cd data && unzip -oq "$(basename "$ZIP")" && cd "$ROOT"
TSV=$(ls data/*.txt | grep -v raw_calls | head -1)
echo "  TSV: $TSV"

# ── Pre-process TSV ──
echo ""
echo "[2/6] Preprocess (drop no-calls / indels)"
python3 pipeline/01_23andme_to_tsv.py "$TSV" data/raw_calls.tsv 2>&1 | tail -8

# ── Download GRCh37 reference if needed ──
if [[ ! -f refs/human_g1k_v37.fasta.fai ]]; then
    echo ""
    echo "[3/6] Download GRCh37 reference FASTA (3 GB — first time only)"
    cd refs
    if [[ ! -f human_g1k_v37.fasta ]]; then
        echo "  fetching from 1000G EBI..."
        curl -sL --retry 3 -o human_g1k_v37.fasta.gz \
            "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/technical/reference/human_g1k_v37.fasta.gz"
        gunzip human_g1k_v37.fasta.gz
    fi
    samtools faidx human_g1k_v37.fasta
    cd "$ROOT"
else
    echo "[3/6] Reference FASTA already present"
fi

# ── Convert to VCF ──
echo ""
echo "[4/6] Convert TSV → GRCh37 VCF"
SAMPLE="$SAMPLE_NAME" bash pipeline/02_tsv_to_vcf.sh

# ── QC ──
echo ""
echo "[5/6] QC (call rate, variant counts)"
bash pipeline/03_qc.sh 2>&1 | tail -30

# ── Per-chrom split + 1000G padding ──
echo ""
echo "[6/6] Split per-chrom + pad with 1000G (~10 min download)"
bash pipeline/04_split_for_topmed.sh 2>&1 | tail -10
bash pipeline/04b_pad_with_1000g.sh 2>&1 | tail -20

# ── Make autosome-only directory for TOPMed (chrX is messy with mixed-sex padding) ──
mkdir -p data/topmed_input_padded_autosomes
cd data/topmed_input_padded_autosomes
for c in {1..22}; do
    cp -f ../topmed_input_padded/chr${c}.vcf.gz .
    cp -f ../topmed_input_padded/chr${c}.vcf.gz.tbi .
done
cd "$ROOT"

echo ""
echo "===================================="
echo " ✓ Phase 1 complete."
echo "===================================="
echo ""
echo "Files ready for TOPMed upload:"
ls -lh data/topmed_input_padded_autosomes/*.vcf.gz | awk '{print "   "$5"  "$9}'
echo ""
echo "Total: $(du -sh data/topmed_input_padded_autosomes/ | awk '{print $1}')"
echo ""
echo "Next step:"
echo "  1. Register at https://imputation.biodatacatalyst.nhlbi.nih.gov/"
echo "  2. Submit a job:"
echo "       Reference: TOPMed r3"
echo "       Build:     GRCh37/hg19"
echo "       Phasing:   Eagle v2.4"
echo "       Population: vs. TOPMed Panel"
echo "       Mode:      Quality Control & Imputation"
echo "  3. Upload all 22 chr*.vcf.gz files (NOT the .tbi files)"
echo "  4. Wait 3-12 hours; download the chr_*.zip results into data/topmed_output/"
echo "  5. When ready, run:"
echo "       TOPMED_PASS='your-decryption-password' bash pipeline/00_run_phase3.sh"
