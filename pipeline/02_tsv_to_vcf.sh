#!/usr/bin/env bash
# Convert preprocessed 23andMe TSV (rsid CHROM POS A1,A2) to a sorted, indexed VCF on GRCh37.
# Inputs:  data/raw_calls.tsv, refs/human_g1k_v37.fasta
# Output:  data/raw_grch37.vcf.gz (+ .tbi)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REF=refs/human_g1k_v37.fasta
TSV=data/raw_calls.tsv
SAMPLE=George_Gao
OUT=data/raw_grch37.vcf.gz

if [[ ! -f "$REF.fai" ]]; then
    echo "Indexing reference FASTA..."
    samtools faidx "$REF"
fi

echo "Converting TSV -> VCF via bcftools convert --tsv2vcf..."
# --columns ID,CHROM,POS,AA  : column meaning per bcftools spec
# AA = alleles column ("A,T")
bcftools convert \
    --tsv2vcf "$TSV" \
    -f "$REF" \
    -s "$SAMPLE" \
    -c ID,CHROM,POS,AA \
    -Ou 2>logs/tsv2vcf.log \
| bcftools sort -Oz -o "$OUT" 2>>logs/tsv2vcf.log

bcftools index -t "$OUT"

echo ""
echo "=== Output stats ==="
bcftools stats "$OUT" | grep -E "^SN|number of (records|samples|SNPs|indels|no-ALTs|MNPs|multiallelic)" | head -15
echo ""
echo "VCF written: $OUT"
