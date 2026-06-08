#!/usr/bin/env bash
# One-time: derive a no-"chr"-prefix GRCh38 FASTA (contigs 1..22,X,Y) from the
# chr-prefixed PharmCAT reference, for use with `bcftools norm -f`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/refs/pharmcat/reference.fna.bgz"
OUT="$ROOT/refs/grch38_noprefix.fa"

if [[ ! -f "$SRC" ]]; then
  echo "ERROR: $SRC not found (PharmCAT reference). Run pipeline/00_setup.sh first." >&2
  exit 1
fi
if [[ -f "$OUT" && -f "$OUT.fai" ]]; then
  echo "Already built: $OUT"; exit 0
fi

# Keep only chr1..chr22,chrX,chrY; strip the 'chr' prefix in the FASTA headers.
WANT=$(printf "chr%s," {1..22} X Y | sed 's/,$//')
samtools faidx "$SRC" ${WANT//,/ } \
  | sed -E 's/^>chr([0-9XY]+).*/>\1/' > "$OUT"
samtools faidx "$OUT"
echo "Wrote $OUT and $OUT.fai"
echo "Contigs: $(cut -f1 "$OUT.fai" | tr '\n' ' ')"
