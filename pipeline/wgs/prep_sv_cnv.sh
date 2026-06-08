#!/usr/bin/env bash
# Clean Manta SV + Canvas CNV VCFs for AnnotSV.
#   SV : restrict to 1..22,X,Y, keep FILTER=PASS, drop ALT='.'
#   CNV: restrict to 1..22,X,Y, drop Canvas REF segments (ALT='.')  [Canvas quality is per-sample FT, not site FILTER]
# Usage: prep_sv_cnv.sh <sv.vcf.gz> <cnv.vcf.gz> <out_sv.vcf.gz> <out_cnv.vcf.gz>
set -euo pipefail
SV_IN="${1:?}"; CNV_IN="${2:?}"; SV_OUT="${3:?}"; CNV_OUT="${4:?}"
REGIONS=$(printf '%s,' {1..22} X Y | sed 's/,$//')
bcftools view -r "$REGIONS" -f PASS -e 'ALT="."' "$SV_IN"  -Oz -o "$SV_OUT";  tabix -f -p vcf "$SV_OUT"
bcftools view -r "$REGIONS"         -e 'ALT="."' "$CNV_IN" -Oz -o "$CNV_OUT"; tabix -f -p vcf "$CNV_OUT"
echo "SV: $(bcftools index -n "$SV_OUT")  CNV: $(bcftools index -n "$CNV_OUT")"
