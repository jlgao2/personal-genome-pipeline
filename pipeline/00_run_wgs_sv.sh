#!/usr/bin/env bash
# SV/CNV annotation pipeline (AnnotSV). Isolated from the core WGS run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
SV=data/wgs/SQ8TH633.30x.sv.vcf.gz
CNV=data/wgs/SQ8TH633.30x.cnv.vcf.gz
RAW=output/raw_findings/wgs
TMP=data/wgs/sv_cnv; mkdir -p "$TMP" "$RAW" output/annotsv

echo "[1/4] prep SV/CNV"
bash pipeline/wgs/prep_sv_cnv.sh "$SV" "$CNV" "$TMP/sv.clean.vcf.gz" "$TMP/cnv.clean.vcf.gz"

echo "[2/4] AnnotSV (GRCh38)"
for kind in sv cnv; do
  mamba run -n annotsv AnnotSV -SVinputFile "$TMP/$kind.clean.vcf.gz" \
     -genomeBuild GRCh38 -outputDir output/annotsv -outputFile "$kind.annotated"
done

echo "[3/4] parse → tiered findings (sv first, then append cnv)"
python3 pipeline/15_parse_annotsv.py --annotsv output/annotsv/sv.annotated.tsv  --caller manta  --out "$RAW/sv_cnv_findings.tsv"
python3 pipeline/15_parse_annotsv.py --annotsv output/annotsv/cnv.annotated.tsv --caller canvas --out "$RAW/sv_cnv_findings.tsv.append"
tail -n +2 "$RAW/sv_cnv_findings.tsv.append" >> "$RAW/sv_cnv_findings.tsv" && rm -f "$RAW/sv_cnv_findings.tsv.append"

echo "[4/4] export findings (schema v2, source=wgs)"
python3 -m pipeline.export_findings --raw "$RAW" --source wgs
echo "✓ SV/CNV findings folded into output/findings/genomic_findings.json"
