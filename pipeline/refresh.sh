#!/usr/bin/env bash
# Personal-data pipeline orchestrator.
# Detects which raw inputs changed since last run, runs only the relevant
# parsers, regenerates the dashboard. Each parser is idempotent.
#
# Usage:
#   bash pipeline/refresh.sh           # normal — uses data/ and output/
#   bash pipeline/refresh.sh --demo    # CI — uses tests/demo_data/ and /tmp
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DATA_ROOT=data
RAW_FINDINGS_DIR=output/raw_findings
CROSS_REFS_YAML=output/cross_refs.yaml
PARQUET_ROOT=data/parquet
OUTPUT_JS=output/web/js
if [[ "${1:-}" == "--demo" ]]; then
    DATA_ROOT=tests/demo_data
    RAW_FINDINGS_DIR=tests/demo_data/raw_findings
    CROSS_REFS_YAML=tests/demo_data/cross_refs.yaml
    PARQUET_ROOT=/tmp/parquet-demo
    OUTPUT_JS=/tmp/web-demo
    rm -rf "$PARQUET_ROOT" "$OUTPUT_JS"
fi
mkdir -p "$PARQUET_ROOT/samples" "$PARQUET_ROOT/findings" \
         "$PARQUET_ROOT/cross_refs" "$PARQUET_ROOT/events" "$OUTPUT_JS"
LOG="$PARQUET_ROOT/.last_refresh"

echo "═══ Personal data refresh — $(date '+%Y-%m-%d %H:%M:%S')"

# ── HealthKit ──
HK_ZIP="$DATA_ROOT/raw/healthkit/export.zip"
HK_XML="$DATA_ROOT/raw/healthkit/apple_health_export/export.xml"
if [[ -f "$HK_ZIP" ]]; then
    if [[ ! -f "$HK_XML" || "$HK_ZIP" -nt "$HK_XML" ]]; then
        echo "Extracting HealthKit zip..."
        ( cd "$DATA_ROOT/raw/healthkit" && unzip -oq export.zip )
    fi
    if [[ ! -f "$LOG" || "$HK_XML" -nt "$LOG" ]]; then
        echo "Parsing HealthKit XML → Parquet..."
        python3 -m pipeline.parsers.healthkit "$HK_XML" --outdir "$PARQUET_ROOT/samples"
    else
        echo "HealthKit Parquet up to date."
    fi
fi

# ── Garmin ──
GR_ZIP="$DATA_ROOT/raw/garmin/garmin_export.zip"
if [[ -f "$GR_ZIP" ]]; then
    if [[ ! -f "$LOG" || "$GR_ZIP" -nt "$LOG" ]]; then
        echo "Parsing Garmin bulk export → Parquet..."
        python3 -m pipeline.parsers.garmin "$GR_ZIP" --outdir "$PARQUET_ROOT/samples"
    else
        echo "Garmin Parquet up to date."
    fi
fi

# ── FHIR / MyChart bundle ──
# Drop your MyChart "Download My Record" JSON at data/raw/fhir/bundle.json
# (or any *.json in that dir — the most recent one wins).
FHIR_DIR="$DATA_ROOT/raw/fhir"
if [[ -d "$FHIR_DIR" ]]; then
    LATEST_FHIR=$(ls -t "$FHIR_DIR"/*.json 2>/dev/null | head -1 || true)
    if [[ -n "$LATEST_FHIR" ]]; then
        if [[ ! -f "$LOG" || "$LATEST_FHIR" -nt "$LOG" ]]; then
            echo "Parsing FHIR bundle → samples + events..."
            python3 -m pipeline.parsers.fhir "$LATEST_FHIR" \
                --samples-outdir "$PARQUET_ROOT/samples" \
                --events-outdir  "$PARQUET_ROOT/events"
        else
            echo "FHIR bundle up to date."
        fi
    fi
fi

# ── Genome → findings.parquet ──
if [[ -d "$RAW_FINDINGS_DIR" ]]; then
    if [[ ! -f "$LOG" || -n "$(find "$RAW_FINDINGS_DIR" -newer "$LOG" 2>/dev/null)" ]]; then
        echo "Parsing genome TSVs → findings.parquet..."
        python3 -m pipeline.parsers.genome \
            --raw "$RAW_FINDINGS_DIR" \
            --outdir "$PARQUET_ROOT/findings"
    else
        echo "Genome findings up to date."
    fi
fi

# ── Cross-refs YAML → cross_refs.parquet ──
if [[ -f "$CROSS_REFS_YAML" ]]; then
    python3 -m pipeline.parsers.cross_refs \
        --yaml "$CROSS_REFS_YAML" \
        --out  "$PARQUET_ROOT/cross_refs/cross_refs.parquet"
fi

# ── Build vitals JS ──
echo "Building data-vitals.js..."
python3 -m pipeline.build_vitals \
    --parquet "$PARQUET_ROOT/samples" \
    --out "$OUTPUT_JS/data-vitals.js"

# ── Mark refresh complete ──
date +%s > "$LOG"
echo "═══ Done. data-vitals.js → $OUTPUT_JS/data-vitals.js"
