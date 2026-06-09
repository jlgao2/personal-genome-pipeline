#!/usr/bin/env bash
# Align the 30x WGS FASTQ -> coordinate-sorted, duplicate-marked BAM on the GRCh38
# *no-alt analysis set* (chr-prefixed) — the build the downstream specialist callers
# (Cyrius/CYP2D6, SMNCopyNumberCaller, HLA typers, mitochondrial calling) are
# calibrated on. This unlocks the analyses the DRAGEN VCF can't provide.
#
# Tools come from the `align` conda env (bwa + samtools), built by logs/align_setup.sh.
# Parallelism (Apple Silicon, 18 cores / 48 GB):
#   - bwa mem -t spreads alignment across ALL cores (the real multiprocessing; sharding
#     the FASTQ would not help on a single host — it only duplicates the 6 GB index).
#   - FASTQ is plain gzip, whose single-threaded inflate can starve a many-core bwa, so
#     reads are fed through pigz (parallel) via process substitution.
#   - the coordinate sort gets its own thread pool + a healthy memory budget.
#   - bwa (original mem) is used over bwa-mem2 because Rosetta lacks AVX; bwa has a native
#     arm64 build and produces caller-compatible alignments.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"

# This Mac (mac.lan) is also the always-on homelab server (cloudflared/caddy + the
# prefrontal-cortex health dashboard, CRM, portrait/health-refresh launchd jobs).
# Run as a polite neighbor: lower scheduling priority so the live services keep CPU
# under contention, while still soaking up all cores when the box is idle (overnight).
# Children (bwa/samtools/pigz) inherit this niceness. Override with NICE= for full throttle.
renice "${NICE:-10}" $$ >/dev/null 2>&1 || true

SAMPLE="${SAMPLE:-SQ8TH633}"
R1="${R1:-data/wgs/${SAMPLE}.30x.R1.fq.gz}"
R2="${R2:-data/wgs/${SAMPLE}.30x.R2.fq.gz}"
REF="${REF:-refs/align/GRCh38_no_alt_analysis_set.fna}"
OUT="${OUT:-data/wgs/bam/${SAMPLE}.grch38.markdup.bam}"
NCPU="$(sysctl -n hw.ncpu 2>/dev/null || nproc)"
BWA_T="${BWA_T:-$((NCPU - 2))}"     # leave ~2 cores for pigz + the sort pipe
SORT_T="${SORT_T:-8}"
RG="@RG\tID:${SAMPLE}\tSM:${SAMPLE}\tPL:ILLUMINA\tLB:${SAMPLE}"

# put the align env's bwa/samtools on PATH (cleaner than wrapping <(...) in `mamba run`)
ENVBIN="$( (conda env list 2>/dev/null || mamba env list 2>/dev/null) | awk '/\/envs\/align$/{print $NF}')/bin"
[ -x "$ENVBIN/bwa" ] || { echo "[align] bwa not found in align env ($ENVBIN)" >&2; exit 1; }
export PATH="$ENVBIN:$PATH"
DECOMP="gzip -dc"; command -v pigz >/dev/null 2>&1 && DECOMP="pigz -dc -p 4"

for f in "$R1" "$R2" "$REF" "$REF.bwt"; do
  [ -s "$f" ] || { echo "[align] missing required input: $f" >&2; exit 1; }
done
mkdir -p "$(dirname "$OUT")"
echo "[align] $(date) sample=$SAMPLE  bwa_threads=$BWA_T sort_threads=$SORT_T  decomp='$DECOMP'"
echo "[align] $R1 + $R2  ->  $OUT"

bwa mem -t "$BWA_T" -R "$RG" "$REF" <($DECOMP "$R1") <($DECOMP "$R2") \
 | samtools fixmate -m -@ 4 - - \
 | samtools sort -@ "$SORT_T" -m 1536M -T "data/wgs/bam/${SAMPLE}.sorttmp" - \
 | samtools markdup -@ 4 - "$OUT"
samtools index -@ 4 "$OUT"
samtools flagstat -@ 4 "$OUT" > "${OUT%.bam}.flagstat.txt"
samtools coverage "$OUT" | awk 'NR==1 || $1 ~ /^chr([0-9]+|X|Y|M)$/' > "${OUT%.bam}.coverage.txt"

echo "[align] $(date) DONE -> $OUT"
sed -n '1,6p' "${OUT%.bam}.flagstat.txt"
