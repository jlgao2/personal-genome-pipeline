#!/usr/bin/env bash
# Personal-data pipeline orchestrator.
# Detects which raw inputs changed since last run, runs only the relevant
# parsers, regenerates the dashboard. Each parser is idempotent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOG=data/parquet/.last_refresh
mkdir -p data/parquet/samples data/parquet/events output/web/js

echo "═══ Personal data refresh — $(date '+%Y-%m-%d %H:%M:%S')"

# ── HealthKit ──
HK_ZIP=data/raw/healthkit/export.zip
HK_XML=data/raw/healthkit/apple_health_export/export.xml
if [[ -f "$HK_ZIP" ]]; then
    if [[ ! -f "$HK_XML" || "$HK_ZIP" -nt "$HK_XML" ]]; then
        echo "Extracting HealthKit zip..."
        cd data/raw/healthkit && unzip -oq export.zip && cd "$ROOT"
    fi
    if [[ ! -f "$LOG" || "$HK_XML" -nt "$LOG" ]]; then
        echo "Parsing HealthKit XML → Parquet..."
        python3 -m pipeline.parsers.healthkit "$HK_XML" --outdir data/parquet/samples
    else
        echo "HealthKit Parquet up to date."
    fi
fi

# ── Build vitals JS ──
echo "Building data-vitals.js..."
python3 -m pipeline.build_vitals \
    --parquet data/parquet/samples \
    --out output/web/js/data-vitals.js

# ── Mark refresh complete ──
date +%s > "$LOG"
echo "═══ Done. Open output/web/index.html or run: python3 -m http.server 8732 -d output/web"
