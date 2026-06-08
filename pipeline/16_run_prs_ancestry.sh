#!/usr/bin/env bash
# Ancestry-calibrated PRS via nf-core/pgsc_calc (the trustworthy path — replaces the
# normal-approximation in 11_prs.py / 12_eas_bmi_percentile.py, which give NA or invalid
# percentiles). Computes per-PGS scores AND a genetic-ancestry-adjusted percentile by
# projecting the sample onto the HGDP+1kGP reference (so percentiles are read against the
# matched population, e.g. East Asian — not a European distribution).
#
# Prereqs (one-time):
#   - nextflow + a conda/mamba install; Java on PATH (Homebrew openjdk).
#   - Reference: curl the FULL ~15 GB tarball, verify with `zstd -t`:
#       curl -fL --retry 15 -o refs/pgsc_calc/pgsc_HGDP+1kGP_v1.tar.zst \
#         https://ftp.ebi.ac.uk/pub/databases/spot/pgs/resources/pgsc_HGDP+1kGP_v1.tar.zst
#
# macOS Apple-Silicon notes baked in below:
#   - CONDA_SUBDIR=osx-64 (bioconda plink2 etc. have no osx-arm64 build → Rosetta).
#   - a zcat→`gzip -dc` shim, injected at the FRONT of PATH via the laptop.config
#     beforeScript (macOS zcat can't read .gz; MATCH_COMBINE/ancestry steps use zcat and
#     fail silently otherwise — see the beforeScript comment below).
#   - --min_overlap 0.0: WGS vs GRCh37-lifted scorefiles match at 33–70%, below the strict
#     0.75 default; the ancestry adjustment scores sample+reference over the SAME variants
#     so the percentile stays a fair rank.
#   - input must be AUTOSOMES-ONLY (plink2 rejects chrX without sex info).
#
# CAVEAT on output: genome-wide PRS computed from WGS and standardised against a reference
# panel are technically inflated (extreme Z) — trust moderate-Z, adequately-covered scores.
# See docs/prs/EUR_vs_EAS_PRS_interpretation.md.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

PREP="${PREP:-data/wgs/SQ8TH633.wgs.pass.vcf.gz}"   # from pipeline/wgs/prep_wgs_vcf.sh
SAMPLE="${SAMPLE:-SQ8TH633}"
REF="${REF:-refs/pgsc_calc/pgsc_HGDP+1kGP_v1.tar.zst}"
OUTDIR=output/pgsc_calc
# Score set: 10 European (baseline) + EAS-validated panel (see docs/prs/eas_panel.md).
SCORES="${SCORES:-PGS000018,PGS000014,PGS000016,PGS000039,PGS000334,PGS000049,PGS000338,PGS000041,PGS000302,PGS000061,PGS005365,PGS004941,PGS005143,PGS002725,PGS004942,PGS002814,PGS005161,PGS005402,PGS005162,PGS005163,PGS005169,PGS005167,PGS005144,PGS005153,PGS002290,PGS000755,PGS012555,PGS005128,PGS003865,PGS002745,PGS005146,PGS001796,PGS000660}"

mkdir -p "$OUTDIR/shims"

echo "[1/4] autosomes-only input (drop X/Y — plink2 needs sex for chrX; PRS are autosomal)"
AUTO=data/wgs/${SAMPLE}.wgs.pass.auto.vcf.gz
bcftools view -r "$(seq -s, 1 22)" "$PREP" -Oz -o "$AUTO"; tabix -f -p vcf "$AUTO"

echo "[2/4] samplesheet + laptop config + zcat shim"
printf 'sampleset,path_prefix,chrom,format,vcf_genotype_field\n%s,%s/%s,,vcf,GT\n' \
  "$SAMPLE" "$ROOT" "${AUTO%.vcf.gz}" > "$OUTDIR/samplesheet.csv"
NCPU=$(sysctl -n hw.ncpu 2>/dev/null || nproc)
cat > "$OUTDIR/laptop.config" <<EOF
executor { name='local'; cpus=${NCPU}; queueSize=${NCPU} }
process {
  resourceLimits = [ cpus: ${NCPU}, memory: '40.GB', time: '720.h' ]
  // macOS: force the zcat->gzip shim to win even after '-profile conda' prepends the
  // env bin to PATH. MATCH_COMBINE builds filter_ids via 'zcat <(...)' in a process
  // substitution; macOS /usr/bin/zcat fails silently there (wants a .Z suffix) -> empty
  // filter -> every score "matches" 0 variants -> ValueError. beforeScript runs AFTER
  // conda activation, so prepending the shim dir here guarantees it resolves first.
  beforeScript   = 'export PATH="$ROOT/$OUTDIR/shims:\$PATH"'
}
params  { max_cpus=${NCPU}; max_memory='40.GB' }
EOF
printf '#!/usr/bin/env bash\nexec gzip -dc "$@"\n' > "$OUTDIR/shims/zcat"; chmod +x "$OUTDIR/shims/zcat"

echo "[3/4] run pgsc_calc with ancestry"
export PATH="$OUTDIR/shims:/opt/homebrew/opt/openjdk/bin:$PATH"
export NXF_DISABLE_CHECK_LATEST=1 CONDA_SUBDIR=osx-64
nextflow run pgscatalog/pgsc_calc -profile conda -c "$OUTDIR/laptop.config" \
  --input "$OUTDIR/samplesheet.csv" --target_build GRCh38 --pgs_id "$SCORES" \
  --run_ancestry "$REF" --min_overlap 0.0 --outdir "$OUTDIR/run" -resume

echo "[4/4] done → $OUTDIR/run/$SAMPLE/score/${SAMPLE}_pgs.txt.gz (col percentile_MostSimilarPop)"
echo "    interpret with docs/prs/EUR_vs_EAS_PRS_interpretation.md"
