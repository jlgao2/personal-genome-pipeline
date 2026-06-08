#!/usr/bin/env bash
# gVCF -> canonical biallelic PASS variant-only GRCh38 sites VCF.
#   1. restrict to primary contigs 1..22,X,Y  (matches the no-prefix FASTA; drops MT/decoys)
#   2. drop reference blocks (ALT '.' or <NON_REF>) and keep FILTER=PASS
#   3. split multiallelics + LEFT-ALIGN + trim against the FASTA
#   4. drop any residual <NON_REF>/'.' ALT produced by the split
# Usage: prep_wgs_vcf.sh <in.gvcf.gz> <out.vcf.gz>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IN="${1:?input gVCF}"
OUT="${2:?output VCF}"
FASTA="$ROOT/refs/grch38_noprefix.fa"
[[ -f "$FASTA" ]] || { echo "ERROR: $FASTA missing — run make_noprefix_fasta.sh" >&2; exit 1; }

REGIONS=$(printf '%s,' {1..22} X Y | sed 's/,$//')

bcftools view -r "$REGIONS" -f PASS -v snps,indels "$IN" -Ou \
  | bcftools norm -f "$FASTA" -m- -Ou \
  | bcftools view -e 'ALT="<NON_REF>" || ALT="."' -Oz -o "$OUT"
tabix -p vcf "$OUT"
echo "Wrote $OUT ($(bcftools index -n "$OUT") variant records)"
