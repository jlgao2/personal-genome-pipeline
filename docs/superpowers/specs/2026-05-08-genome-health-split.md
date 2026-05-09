# Genome ↔ Health Split

> **Status:** PROPOSAL · approved (path α + symlink option (i))
> **Triggered by:** "split out the health tracking project from the genome parsing project overall — find a neat solution to ingest the genetic data, this should simplify data storage and privacy concerns"

## Why

`snp_gene_analysis` currently does two jobs with different cadences and threat models:

- **Genome parsing** — episodic (annual). High sensitivity (raw genotype, clinically-actionable findings, ~6 GB refs).
- **Health tracking** — continuous (daily). Medium sensitivity (vitals, adherence, calendar).

They're glued together via Python imports rather than a versioned interface, so the health pipeline has the raw genotype and full reference FASTA one `cd` away. Splitting eliminates that adjacency, lets each repo evolve at its own cadence, and frees a future move of the genome repo to an offline disk.

## End-state

Three repos:

| Repo | Path | GitHub | Scope |
|---|---|---|---|
| **personal-genome-pipeline** | `/Users/georgegao/snp_gene_analysis/` | jlgao2/personal-genome-pipeline | Phase 1–3 genome pipeline. Inputs: 23andMe v5 zip. Outputs: TSV findings + **`output/findings/genomic_findings.json`** as the public artifact. |
| **prefrontal-cortex** *(new)* | `/Users/georgegao/prefrontal-cortex/` | jlgao2/prefrontal-cortex *(user creates)* | Health/longitudinal pipeline. Adaptive engine, correlations, DuckDB+Parquet spine, web dashboard, LAN HTTP iOS sync. Reads genomic findings via symlink. |
| **personal-data-ios** | `/Users/georgegao/personal-data-ios/` | jlgao2/personal-data-ios | iOS app. Unchanged except README pointer. |

## Data contract: `genomic_findings.json`

A single JSON file emitted by the genome repo, consumed by the health repo. One row per finding, schema matches today's `pipeline/parsers/genome.py` canonical shape:

```jsonc
{
  "schema_version": 1,
  "exported_at": "2026-05-08T19:32:00Z",
  "source_pipeline_commit": "<short-sha of personal-genome-pipeline HEAD>",
  "rows": [
    {
      "id": "pgx_quick:rs4244285",
      "source_tsv": "pgx_quick",
      "gene": "CYP2C19",
      "rsid": "rs4244285",
      "chrom": "10", "pos": 96541616, "ref": "G", "alt": "A",
      "genotype": "A/A",
      "tier": "A",
      "summary": "CYP2C19 *2/*2 — poor metabolizer",
      "meta": "{\"drug\":\"clopidogrel\",\"haplotype_role\":\"*2\",\"n_alt\":2}"
    }
    // … one row per finding across all source TSVs
  ]
}
```

Existing parquet shape is preserved end-to-end — the health repo's `parsers/genome.py` simply reads this JSON instead of the raw TSVs and emits the same `findings-*.parquet` it does today.

## Transfer mechanism

**Symlink.** In the new health repo:

```
prefrontal-cortex/data/raw/genome → ../personal-genome-pipeline/output/findings/
```

Health side reads `data/raw/genome/genomic_findings.json` exactly like any other BYOD source. Auto-current — when `00_run_phase3.sh` runs in genome repo, the next `refresh.sh` in health repo picks it up.

If/when the user moves the genome repo to an offline disk, the symlink converts to a manual copy via a tiny `bin/sync-genome-findings.sh`.

## Migration phases

### Phase 1 — Genome side: emit the JSON (current repo, additive)

1. New `pipeline/export_findings.py`: reads `output/raw_findings/imputed_grch38/*.tsv` + `output/raw_findings/*.tsv` via the existing `pipeline.parsers.genome` row-extraction functions, writes `output/findings/genomic_findings.json`.
2. Add `output/findings/` to `.gitignore` (personal data — never commit).
3. Hook into `00_run_phase3.sh` after step 8 (PRS) so the JSON is regenerated whenever genome analysis runs.
4. Tests: `tests/test_export_findings.py` exercises a tiny demo TSV → JSON round-trip.
5. Commit in `snp_gene_analysis`.

### Phase 2 — Stand up the new repo

1. `mkdir /Users/georgegao/prefrontal-cortex && git init`.
2. Copy from `snp_gene_analysis`:
   - `pipeline/{__init__.py, adaptive.py, correlations.py, build_vitals.py, ios_serve.py, ios_serve.sh, refresh.sh}`
   - `pipeline/parsers/{__init__.py, healthkit.py, healthkit_types.py, garmin.py, garmin_types.py, fhir.py, fhir_types.py, gcal.py, ios_samples.py, social.py, media.py, cross_refs.py, health_profile.py}`
   - **`pipeline/parsers/genome.py`** — rewrite to read JSON instead of TSVs (~30 lines, drops the per-TSV functions).
   - `tests/{__init__.py, test_adaptive.py, test_build_vitals.py, test_build_vitals_js.py, test_smoke_duckdb.py, test_ios_serve.py}`
   - `tests/parsers/`, `tests/demo_data/` (the relevant subset).
   - `requirements.txt`.
   - `.gitignore` (the health-relevant subset — drop genome/refs entries).
   - `output/health_profile.json`, `output/cross_refs.yaml`, `output/media.yaml` — gitignored personal data, but the files exist.
   - `output/web/` directory (HTML/CSS/JS — data files gitignored).
3. Symlink: `cd prefrontal-cortex && ln -s ../personal-genome-pipeline/output/findings data/raw/genome`.
4. Update `pipeline/refresh.sh` paths if any are hardcoded.
5. Run full test suite in new repo. Goal: green.
6. Initial commit. Add `README.md` describing scope + setup.

### Phase 3 — Genome side cleanup

1. Delete from `snp_gene_analysis`:
   - All files moved in Phase 2 except `pipeline/parsers/genome.py` (which becomes the source-of-truth row-extraction module the new export_findings.py imports — actually no: Phase 1's export_findings will use it, so it stays in genome repo).
   - Wait — re-think: `parsers/genome.py` has the per-TSV row extractors. Genome repo needs them for export. Health repo needs to *read JSON* (much simpler). So:
     - Genome repo keeps `pipeline/parsers/genome.py` (per-TSV → canonical rows). Used by `export_findings.py`.
     - Health repo gets a NEW `pipeline/parsers/genome.py` that reads JSON → parquet. Different file, same purpose.
2. Files to delete from genome repo:
   - `pipeline/{adaptive.py, correlations.py, build_vitals.py, ios_serve.py, ios_serve.sh, refresh.sh}`
   - `pipeline/parsers/{healthkit*, garmin*, fhir*, gcal, ios_samples, social, media, cross_refs, health_profile}.py`
   - `tests/{test_adaptive, test_build_vitals*, test_smoke_duckdb, test_ios_serve}.py`
   - `tests/parsers/` (health parser tests)
   - `output/{web, ios_export, health_profile.json, cross_refs.yaml, media.yaml}` — gitignored, no commit needed; remove from disk.
3. Trim `README.md` — drop the BYOD section, the iOS sync section, the HealthKit/Garmin/MyChart parser docs.
4. Commit in `snp_gene_analysis`.

### Phase 4 — Documentation + memory

1. Update memory `project_prefrontal_cortex.md` to describe THREE repos and the JSON contract.
2. Update `personal-data-ios/README.md` to point at `jlgao2/prefrontal-cortex` instead of `personal-genome-pipeline` for the laptop-side server.
3. Optional follow-up: user runs `gh repo create jlgao2/prefrontal-cortex --private` and pushes.

## What stays / what moves

| Component | Genome repo | Health repo |
|---|---|---|
| Phase 1 (TSV → VCF) | ✓ | — |
| Phase 2 (TOPMed) | ✓ | — |
| Phase 3 (annotation: ClinVar/ACMG/PRS/PGx/panels) | ✓ | — |
| `pipeline/parsers/genome.py` (TSV → rows) | ✓ | — |
| `pipeline/export_findings.py` *(new)* | ✓ | — |
| `output/raw_findings/` (TSVs) | ✓ | — |
| `output/findings/genomic_findings.json` *(new)* | ✓ | — *(read via symlink)* |
| `refs/` (FASTA) | ✓ | — |
| `data/genome_*.zip` (raw 23andMe) | ✓ | — |
| `pipeline/parsers/genome.py` (JSON → parquet) *(new)* | — | ✓ |
| `pipeline/parsers/{healthkit, garmin, fhir, gcal, ios_samples, social, media, cross_refs, health_profile}.py` | — | ✓ |
| `pipeline/{adaptive, correlations, build_vitals, ios_serve}.py` | — | ✓ |
| `pipeline/{ios_serve, refresh}.sh` | — | ✓ |
| `output/{web, ios_export, health_profile.json, …}` | — | ✓ |
| All current health tests | — | ✓ |

## Out of scope for this migration

- **Memory split** between Claude project dirs. Keep both pointing at same memory dir for now; we'll sort it later by symlinking `.claude/projects/-Users-georgegao-prefrontal-cortex/` to the existing memory dir, or duplicate.
- **Encrypting genome at rest** (git-crypt, LUKS partition). Separate decision once split lands.
- **GitHub remote creation for `prefrontal-cortex`**. User does `gh repo create` after migration.
- **Tasks #13 (did-this-instead) and #14 (replan + launchd)**. Both will land in the new health repo after the split.

## Self-review

- Coverage: every file currently in `snp_gene_analysis` is accounted for (genome / health / both / delete).
- The `parsers/genome.py` collision is real but the two files have different jobs (TSV→rows vs JSON→parquet) and live in different repos — no conflict.
- Symlink target path is relative (`../personal-genome-pipeline/output/findings`), so the layout works as long as both repos sit in `/Users/georgegao/`.
- Test count after split: genome repo gets ~5 new tests (export_findings round-trip); health repo keeps current ~98 tests.
