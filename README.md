# Personal Genome Pipeline

Turn a 23andMe v5 raw genotype download into an interactive dashboard with:
- **Pharmacogenomics** (PharmCAT 3.2 — drug dosing flags for ~16 genes)
- **Polygenic risk scores** (10 traits via PGS Catalog)
- **ClinVar / ACMG SF v3.2** monogenic & carrier findings
- **Curated nutrition + lifestyle SNP panel** (~60 well-known variants)
- **TOPMed-imputed VCF** (~9 M variants at R²≥0.8)
- **Live web dashboard** with filters and search (`output/web/`)

All open-source. Local-first. Only the imputation step uploads data (to NIH-hosted TOPMed).

> ⚠ **Not a clinical test.** Output is research-grade, useful for "discuss with my doctor" prompts. Don't change medications based on this alone — always confirm with a clinical-grade test (Color, Invitae, Mayo PGx) before clinical action.

---

## What you need

- **Mac or Linux** (tested on macOS arm64; Linux x86_64 should work)
- **~10 GB free disk** (3 GB reference FASTA, ~6 GB imputation results)
- **~16 GB RAM** (PRS computation peaks at 4 GB)
- **Homebrew** installed (`https://brew.sh`)
- **A 23andMe v5 raw data download** (`.zip` from your account → "Browse Raw Data" → "Download")
- **An NIH BioData Catalyst account** (free, takes 5 min to register) for the imputation step
- **Comfort in the terminal** — this is a CLI pipeline. ~5 hours hands-on time, ~24 hours wall-clock.

## Cost

**$0** in mandatory costs. Optional ~$30 if you want premium reference data subscriptions, but everything works for free.

---

## Quick-start

### 0. Clone & set up environment (one-time, ~5 min)

```bash
git clone <this-repo> ~/snp_gene_analysis
cd ~/snp_gene_analysis
bash pipeline/00_setup.sh
```

This installs `bcftools`, `samtools`, `p7zip`, `openjdk`, `plink2`, PharmCAT 3.2, plus Python deps.

### 1. Phase 1 — convert + prep for imputation (~30 min)

```bash
# Drop your 23andMe download into ./data/
cp ~/Downloads/genome_*.zip data/

# Set your sample name (used in VCF header + dashboard)
export SAMPLE_NAME="Your_Name"

# Run phase 1 (downloads 3 GB GRCh37 FASTA on first run)
bash pipeline/00_run_phase1.sh
```

End of phase 1: `data/topmed_input_padded_autosomes/` contains 22 `.vcf.gz` files (~11 MB total) ready to upload to TOPMed.

### 2. Phase 2 — TOPMed imputation (manual web step, 3–12 h server time)

1. Register: https://imputation.biodatacatalyst.nhlbi.nih.gov/
2. **Run** → **Genotype Imputation (Minimac4)**
3. Settings:
   - Reference Panel: **TOPMed r3**
   - Array Build: **GRCh37/hg19**
   - Phasing: **Eagle v2.4**
   - Population: **vs. TOPMed Panel** (mixed)
   - Mode: **Quality Control & Imputation**
4. Drag in all 22 files from `data/topmed_input_padded_autosomes/` (NOT the `.tbi` index files)
5. Submit. Wait for "imputation complete" email + a separate email with the **decryption password**.
6. Download the `chr_*.zip` files (~10 GB total) to `data/topmed_output/`. Use the curl command TOPMed gives you (faster than browser).

> **Why "padded"?** TOPMed requires ≥20 samples per submission. The `04b_pad_with_1000g.sh` script automatically merges your sample with 30 public 1000 Genomes reference samples (just at your chip's positions). After imputation we extract only your sample and discard the rest.

### 3. Phase 3 — annotation & report (~1 hour)

Once `data/topmed_output/` has the 22 `chr_*.zip` files:

```bash
TOPMED_PASS='your-decryption-password' bash pipeline/00_run_phase3.sh
```

This:
1. Decrypts all zips (4-way parallel)
2. Concatenates per-chrom imputed VCFs
3. Extracts only your sample, drops the 1000G padding samples
4. Filters to R² ≥ 0.8 (keeps ~9 M high-confidence variants)
5. Runs PharmCAT (16+ pharmacogenomic genes)
6. Annotates with ClinVar + ACMG SF v3.2
7. Runs ~60-SNP nutrition / PGx / lifestyle panels
8. Computes 10 polygenic risk scores

### 4. View the dashboard

```bash
python3 -m http.server 8732 --directory output/web
open http://localhost:8732
```

The dashboard has filter chips (Tier A/B/C), section search, accordion findings with side-panel data, lab-table cross-reference, and a checklist for your next PCP visit.

---

## What you'll get

After Phase 3 you'll have:

```
output/
├── action_plan.md                       Markdown report, doctor-ready
├── genetic_clinical_correlation.md      Optional: medical record cross-reference
├── pharmcat/
│   └── *.report.html                    PharmCAT visual report
├── raw_findings/
│   ├── imputed_panels.tsv               60-SNP curated nutrition + PGx + traits
│   ├── prs_scores.tsv                   10 polygenic risk scores
│   ├── prs_per_variant.tsv              Top contributors per PGS
│   ├── prs_bmi_eas_percentile.tsv       BMI vs East Asian reference (if EAS ancestry)
│   └── imputed_grch38/
│       ├── clinvar_acmg.tsv             ACMG SF v3.2 actionable variants
│       ├── carrier_status.tsv           Recessive carrier panel
│       └── clinvar_full.tsv             All P/LP ClinVar matches
└── web/
    ├── index.html                       Dashboard (open in browser)
    ├── howto.html                       This walkthrough as a styled web page
    └── ...
```

---

## Privacy

- **All raw genotype processing is local.** Your 23andMe TSV never leaves your machine after phase 1.
- **Only Phase 2 (imputation) uploads data**, and only to the NIH-hosted TOPMed Imputation Server (federally-funded, FERPA/HIPAA-aware, encrypted-at-rest, results encrypted with a password emailed only to you). They don't sell or research your individual data without consent.
- **Phase 3 lookups** (ClinVar, gnomAD via myvariant.info, PGS Catalog) query publicly-available databases by `rsID` — no genotypes leave your machine.
- **The dashboard is a static site** — no server, no analytics, no telemetry. Open `output/web/index.html` directly in a browser.

If even the TOPMed upload feels too exposed: skip Phase 2. You'll lose the ~50× variant expansion and the polygenic risk scores, but Phase 1 outputs are still useful — run the panel scripts directly on `data/raw_grch37.vcf.gz`.

---

## Architecture

```
data/genome.zip             23andMe download (you provide)
        │
        ▼ pipeline/01_23andme_to_tsv.py
data/raw_calls.tsv          (drop --, II, DD calls; expand hemizygous)
        │
        ▼ pipeline/02_tsv_to_vcf.sh        (uses GRCh37 FASTA)
data/raw_grch37.vcf.gz
        │
        ▼ pipeline/04_split_for_topmed.sh
data/topmed_input/chr*.vcf.gz
        │
        ▼ pipeline/04b_pad_with_1000g.sh   (merge 30 public 1000G samples)
data/topmed_input_padded_autosomes/
        │  → MANUAL: upload to TOPMed Imputation Server
        ▼  ← MANUAL: download encrypted .zip results
data/topmed_output/chr_*.zip
        │
        ▼ pipeline/run_post_imputation_pipeline.sh
data/imputed_grch38.vcf.gz                       (~50M variants, all R² values)
data/imputed_grch38_r2_0.8.vcf.gz                (~9M variants, R²≥0.8)
        │
        ├──▶ PharmCAT          → output/pharmcat/
        ├──▶ ClinVar/ACMG      → output/raw_findings/imputed_grch38/
        ├──▶ rsID panels       → output/raw_findings/imputed_panels.tsv
        └──▶ PGS Catalog PRS   → output/raw_findings/prs_scores.tsv
                                       │
                                       ▼ pipeline/13_build_report.py
                                  output/web/  (interactive dashboard)
```

---

## Customizing the dashboard for a different person

The web dashboard data lives in `output/web/js/data.js`. It's hand-curated — to make it data-driven from someone else's pipeline outputs, you'd write a `pipeline/13_build_report.py` that reads `output/raw_findings/*.tsv` and writes `output/web/js/data.js`. Marked as TODO — for now, copy the structure and adapt the entries.

Or just deliver the markdown reports + the per-finding TSVs without the web layer — those are 100% data-driven and update automatically.

---

## Troubleshooting

**Phase 1 fails on `bcftools convert --tsv2vcf`** — the GRCh37 FASTA didn't index. Manually: `samtools faidx refs/human_g1k_v37.fasta`.

**TOPMed rejects "ChrX nonPAR ambiguous"** — male hemizygous chrX calls don't mix with mixed-sex 1000G padding. Solution: use `data/topmed_input_padded_autosomes/` (autosomes-only) instead of `data/topmed_input_padded/`.

**TOPMed rejects "minimum 20 samples"** — you forgot the padding step (`04b_pad_with_1000g.sh`). Re-run.

**PharmCAT crashes on "Java not found"** — `export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"` (Apple Silicon) or `export PATH="/usr/local/opt/openjdk/bin:$PATH"` (Intel).

**PharmCAT pipeline hangs on "Downloading reference FASTA"** — Zenodo download flaky. Use the JAR-direct approach from `00_run_phase3.sh` which skips that download.

**Disk full during imputation download** — 22 zips × ~500 MB = ~10 GB. Free ~15 GB before downloading.

---

## What this pipeline cannot do

- **Detect rare variants** — chip + imputation handles common variants (>1% MAF). For BRCA1/2, Lynch genes, ACMG actionable rare variants → clinical NGS panel ($250 from Color/Invitae).
- **Call CYP2D6** — copy number / hybrid alleles defeat any chip-based method. Need targeted PGx panel ($200 from Mayo PGx, GeneSight).
- **SMN1 (SMA carrier)** — copy-number based, needs MLPA assay.
- **Triplet-repeat disorders** (Fragile X FMR1, Huntington's HTT, myotonic dystrophy DMPK).
- **Mitochondrial heteroplasmy %** — only homoplasmic calls.

For all of these, **30× whole-genome sequencing** ($200–600 from Nebula, Dante Labs, etc.) is the right next step. The same pipeline runs on WGS-derived VCFs with massively expanded coverage.

---

## License & credits

Pipeline scripts: MIT.

Reference data:
- 1000 Genomes Project (public domain)
- ClinVar (public domain, NCBI)
- PGS Catalog (CC-BY 4.0, EMBL-EBI)
- gnomAD allele frequencies (CC0)
- PharmCAT (Mozilla Public License, Stanford)

This pipeline is a personal-research tool. It's not a substitute for a board-certified genetic counsellor or your physician. Findings should be discussed with a qualified clinician before clinical action.
