#!/usr/bin/env bash
# Decrypt the password-protected TOPMed result zips.
# TOPMed wraps each chr's results in an AES-256 encrypted zip; the password
# was emailed to you when imputation finished.
#
# Usage:  bash pipeline/04c_decrypt_topmed.sh '<password>'
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/data/topmed_output"

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 '<topmed-password-from-email>'" >&2
    exit 2
fi
PASS="$1"

shopt -s nullglob
ZIPS=(chr_*.zip)
if [[ ${#ZIPS[@]} -eq 0 ]]; then
    echo "ERROR: no chr_*.zip files in $(pwd)" >&2
    exit 1
fi

echo "Decrypting ${#ZIPS[@]} zip files..."
for Z in "${ZIPS[@]}"; do
    echo "  $Z"
    7z x -p"$PASS" -y -bso0 -bsp0 "$Z"
done

echo ""
echo "=== Decrypted contents ==="
ls -lh *.dose.vcf.gz *.info.gz 2>/dev/null | head
echo ""
echo "Total dose VCFs: $(ls *.dose.vcf.gz 2>/dev/null | wc -l | tr -d ' ')"
