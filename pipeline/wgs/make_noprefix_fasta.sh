#!/usr/bin/env bash
# One-time: fetch a no-"chr"-prefix GRCh38 FASTA (contigs 1..22,X,Y,MT,scaffolds)
# for `bcftools norm -f`. Ensembl's primary assembly is natively no-prefix, which
# matches the WGS gVCF's contig naming (1..22,X,Y,MT). We use it instead of the
# PharmCAT reference (refs/pharmcat/reference.fna.bgz), which is chr-prefixed AND
# truncated on disk.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/refs/grch38_noprefix.fa"
URL="https://ftp.ensembl.org/pub/release-110/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"

if [[ -f "$OUT" && -f "$OUT.fai" ]]; then
  echo "Already built: $OUT"; exit 0
fi

echo "Downloading GRCh38 primary assembly (~900 MB) from Ensembl ..."
curl -fL --retry 3 --retry-delay 5 -o "$OUT.gz" "$URL"
echo "Decompressing (~3 GB) ..."
gunzip -f "$OUT.gz"
samtools faidx "$OUT"
echo "Wrote $OUT and $OUT.fai"
echo "Primary contigs: $(cut -f1 "$OUT.fai" | grep -E '^([0-9]+|X|Y|MT)$' | tr '\n' ' ')"
