# TOPMed Imputation Server — manual submission steps

> The pipeline has prepared per-chromosome VCFs in **`data/topmed_input_padded_autosomes/`**.
> Imputation requires a free NIH-hosted account; you must do this step manually.
> Total wall time: ~3–12 hours (queue + processing).
>
> **Note**: TOPMed enforces a minimum of 20 samples per submission. Your single sample
> has been merged with 23 public 1000 Genomes phase 3 reference samples (mixed-ancestry)
> at your chip's positions, giving 24 samples total. After imputation we extract only
> your sample's results and discard the 1000G ones. This is the standard workaround
> for personal-genome use of TOPMed.

## Step 1 — Register

1. Go to https://imputation.biodatacatalyst.nhlbi.nih.gov/
2. Create an account using your email (georgegao888@gmail.com).
3. Verify the activation email.

## Step 2 — Submit the job

1. Click **Run** → **Genotype Imputation (Minimac4) 1.7.x** (the current production app).
2. Set parameters:
   - **Reference Panel**: `TOPMed r3` (~16K samples, multi-ancestry, ~308M variants)
   - **Array Build**: `GRCh37/hg19`
   - **rsq Filter**: `off` (we'll filter ourselves on R² >= 0.8)
   - **Phasing**: `Eagle v2.4`
   - **Population**: `vs. TOPMed Panel` (mixed; correct for any ancestry)
   - **Mode**: `Quality Control & Imputation`
   - **Build LiftOver**: leave `Yes` (server lifts hg19 → hg38)
   - **AES 256 encryption**: leave `On`
3. **Upload files**: select all 23 files in `data/topmed_input_padded_autosomes/` (chr1.vcf.gz through chr22.vcf.gz + chrX.vcf.gz).
4. Submit.

## Step 3 — Wait for results

- Server emails when QC finishes (usually <30 min) — review the QC report; if pre-imputation QC fails badly (>5% positions flipped/dropped), let me know and we'll re-prep.
- Imputation itself takes 2–10 hours depending on queue.
- When complete, server emails:
  - Encrypted-results password (save this)
  - Per-chromosome download links (valid ~7 days)

## Step 4 — Download

1. Use the wget/curl commands the server provides for each chromosome (faster than browser).
2. Save all `chr_*.zip` files to `data/topmed_output/`.
3. Decrypt each with the password using `7z x -p<PASSWORD> chr_<N>.zip` (install via `brew install p7zip`).
4. After decryption, you'll have `chr<N>.dose.vcf.gz` + `chr<N>.info.gz` for each chromosome.

## Step 5 — Tell me when ready

Run from the project root:

```
ls data/topmed_output/*.dose.vcf.gz | wc -l   # should print 23
```

Then resume the pipeline with `pipeline/05_post_imputation.sh` (will be created in next phase) which:
  - Concatenates per-chrom imputed VCFs into `data/imputed_grch38.vcf.gz`
  - Filters variants to R² >= 0.8 → `data/imputed_grch38_r2_0.8.vcf.gz`
  - Triggers downstream Phase 3 analyses
