#!/usr/bin/env bash
# One-shot environment setup for the genome pipeline.
#
# Installs:
#   - bcftools, samtools, p7zip (via Homebrew)
#   - openjdk (for PharmCAT)
#   - poppler (PDF text extraction, optional)
#   - plink2 binary (downloaded directly)
#   - PharmCAT JAR + its Python deps in a venv
#   - Python 3 packages: pandas, pysam, myvariant, cyvcf2
#
# Idempotent — safe to re-run.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "===================================="
echo " GENOME PIPELINE — environment setup"
echo "===================================="

# 1. Brew formulas
need_brew() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "  -> brew install $2"
        brew install "$2" >/dev/null 2>&1 || true
    else
        echo "  ✓ $1 already installed"
    fi
}

if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew not installed. Install from https://brew.sh first." >&2
    exit 1
fi

echo ""
echo "[1/5] CLI tools (Homebrew)"
need_brew bcftools  bcftools
need_brew samtools  samtools
need_brew 7z        p7zip
need_brew java      openjdk
need_brew pdftotext poppler
need_brew nextflow  nextflow   # optional, for pgsc_calc

# 2. plink2
echo ""
echo "[2/5] plink2 binary"
mkdir -p refs
if [[ ! -x refs/plink2 ]]; then
    OS_ARCH=""
    case "$(uname -sm)" in
        "Darwin arm64")  OS_ARCH="mac_arm64" ;;
        "Darwin x86_64") OS_ARCH="mac_x86_64" ;;
        "Linux x86_64")  OS_ARCH="linux_x86_64_intel" ;;
        *) echo "Unsupported platform: $(uname -sm)" >&2 ;;
    esac
    if [[ -n "$OS_ARCH" ]]; then
        # Pinned alpha7 build that's stable as of 2026-04
        URL="https://s3.amazonaws.com/plink2-assets/alpha7/plink2_${OS_ARCH}_20260425.zip"
        echo "  -> downloading $URL"
        curl -sL -o /tmp/plink2.zip "$URL" || true
        cd refs && unzip -oq /tmp/plink2.zip && cd "$ROOT"
        rm -f /tmp/plink2.zip
    fi
fi
[[ -x refs/plink2 ]] && echo "  ✓ refs/plink2 ready"

# 3. Python deps for the pipeline scripts
echo ""
echo "[3/5] Python packages"
pip3 install --quiet pandas numpy pysam myvariant cyvcf2 requests duckdb pyarrow 2>&1 | tail -3 || true
echo "  ✓ Python deps installed"

# 4. PharmCAT
echo ""
echo "[4/5] PharmCAT (3.2.0)"
mkdir -p refs/pharmcat
if [[ ! -f refs/pharmcat/pharmcat.jar ]]; then
    cd refs/pharmcat
    LATEST_URL=$(curl -sL https://api.github.com/repos/PharmGKB/PharmCAT/releases/latest | grep "browser_download_url" | grep "pharmcat-.*-all.jar" | head -1 | cut -d'"' -f4)
    PIPE_URL=$(curl -sL https://api.github.com/repos/PharmGKB/PharmCAT/releases/latest | grep "browser_download_url" | grep "pharmcat-pipeline-.*tar.gz" | head -1 | cut -d'"' -f4)
    PREP_URL=$(curl -sL https://api.github.com/repos/PharmGKB/PharmCAT/releases/latest | grep "browser_download_url" | grep "pharmcat-preprocessor-.*tar.gz" | head -1 | cut -d'"' -f4)
    curl -sL -o pharmcat.jar "$LATEST_URL"
    [[ -n "$PIPE_URL" ]] && curl -sL -o pipeline.tar.gz "$PIPE_URL" && tar xzf pipeline.tar.gz
    [[ -n "$PREP_URL" ]] && curl -sL -o preprocessor.tar.gz "$PREP_URL" && tar xzf preprocessor.tar.gz
    cd "$ROOT"
fi
[[ -f refs/pharmcat/pharmcat.jar ]] && echo "  ✓ PharmCAT JAR ready ($(ls -lh refs/pharmcat/pharmcat.jar | awk '{print $5}'))"

# Python venv for pharmcat_pipeline (needs python 3.10+)
if command -v python3.12 >/dev/null 2>&1; then
    PY=python3.12
elif command -v python3.11 >/dev/null 2>&1; then
    PY=python3.11
elif command -v python3.10 >/dev/null 2>&1; then
    PY=python3.10
else
    echo "  ⚠ Python 3.10+ not found — installing 3.12 via Homebrew"
    brew install python@3.12 >/dev/null 2>&1
    PY=python3.12
fi
if [[ ! -d refs/pharmcat/venv ]]; then
    "$PY" -m venv refs/pharmcat/venv
    source refs/pharmcat/venv/bin/activate
    pip install --quiet pandas colorama "packaging~=24.1" 2>&1 | tail -2
    deactivate
fi
echo "  ✓ PharmCAT Python venv ready"

# 5. Reference downloads (lazy — only when 02_tsv_to_vcf actually runs)
echo ""
echo "[5/5] Reference data"
echo "  ⓘ GRCh37 FASTA (3 GB) and ClinVar VCFs are downloaded on demand by"
echo "    later phases. Skipping for now."

# ── Project directory structure ──
mkdir -p data logs output/{qc,raw_findings,pharmcat,web/{css,js}}

echo ""
echo "===================================="
echo " ✓ Setup complete."
echo "===================================="
echo ""
echo "Next: drop your 23andMe .zip into ./data/ and run:"
echo "  bash pipeline/00_run_phase1.sh"
