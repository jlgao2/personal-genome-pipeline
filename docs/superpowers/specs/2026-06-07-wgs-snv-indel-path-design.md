# WGS SNV/indel Annotation Path — Design (Spec A)

- **Date:** 2026-06-07
- **Status:** Draft for review (revised after adversarial review)
- **Scope:** Spec A of a two-spec effort. Spec B (SV/CNV via AnnotSV) is a separate cycle.

## 1. Context & motivation

The existing pipeline turns a 23andMe v5 chip download into `genomic_findings.json`
via TOPMed imputation, then annotation (ClinVar/ACMG, PharmCAT, rsID panels, PRS).

A 30× whole-genome sequencing dataset from Sequencing.com (sample `SQ8TH633`,
GRCh38.p13, DRAGEN-called) is now available. WGS **supersedes** the imputed set:
variants are directly sequenced — no imputation R²/guesswork — and include rare
variants that chip+imputation fundamentally cannot detect.

Chosen scope (**B**): full parity on the existing annotation layers **plus** the
WGS-only wins — a **tiered** rare-variant ClinVar/ACMG scan (this spec) and full
SV/CNV annotation (Spec B).

## 2. Verified inputs (data inventory)

All in `data/wgs/`, all GRCh38, sample `SQ8TH633`, all integrity-checked:

| File | Content | Role |
|---|---|---|
| `SQ8TH633.30x.snp-indel.genome.vcf.gz` | BGZF gVCF, 12,360,808 records, **5,077,911 variant sites**, ~84% rsID-annotated, `.tbi` indexed | **Spec A input** |
| `SQ8TH633.30x.sv.vcf.gz` | 5,265 Manta SV calls, PASS | Spec B |
| `SQ8TH633.30x.cnv.vcf.gz` | 985 Canvas CNV segments, PASS | Spec B |
| `SQ8TH633.30x.R{1,2}.fq.gz` | 22 GB / 21 GB raw reads | archival only — not pipeline input |

> ⚠ **Operational note:** these are **BGZF** (block-gzip). Always decompress with
> `bgzip`/`bcftools`/`gzip -dc`. **Never** use macOS Archive Utility or `zcat` —
> both stop at the first BGZF block and silently truncate (this is what produced
> the earlier "empty" stub files).

## 3. Scope

- **In scope (Spec A):** gVCF → SNV/indel annotation — prep, tiered ClinVar/ACMG,
  rsID panels, PRS, PharmCAT, findings export.
- **Out of scope (Spec B, separate cycle):** AnnotSV-based annotation of the Manta
  SV and Canvas CNV VCFs.

## 4. Architecture / data flow

All raw TSVs land **flat** under `output/raw_findings/wgs/` (no nested sub-dirs —
see §6/§7 for why this matters to `export_findings`).

```
data/wgs/SQ8TH633.30x.snp-indel.genome.vcf.gz        (gVCF: 5.08M variant sites + ref-blocks)
   │  [NEW] pipeline/wgs/prep_wgs_vcf.sh
   │    1. drop ref-blocks (ALT='.' or '<NON_REF>')
   │    2. keep FILTER=PASS
   │    3. bcftools norm -f <GRCh38 no-prefix FASTA> -m-   (split + LEFT-ALIGN + trim → canonical biallelic)
   │    4. post-split cleanup: drop any residual ALT='<NON_REF>'/'.'
   ▼
data/wgs/SQ8TH633.wgs.pass.vcf.gz                     (canonical biallelic GRCh38 PASS sites VCF, rsIDs intact)
   │   (matched against ClinVar by normalized chrom:pos:REF:ALT — NOT rsID)
   ├─ 06_clinvar_acmg.py --mode actionable    (ACMG SF v3.2 genes, P/LP, ≥2★, + recessive carrier panel)
   │                                            → output/raw_findings/wgs/{clinvar_acmg.tsv, carrier_status.tsv}
   ├─ 06_clinvar_acmg.py --mode exploratory   (genome-wide P/LP, ≥1★, minus actionable dupes, sort by stars→sig, cap 200)
   │                                            → output/raw_findings/wgs/clinvar_exploratory.tsv      [NEW]
   ├─ PharmCAT  (slice to positions, run JAR)         → output/pharmcat/
   ├─ 10_imputed_panels.py --out …/wgs/imputed_panels.tsv   (unchanged script + filename)
   └─ 11_prs.py  --out …/wgs/prs_scores.tsv  --per-variant-out …/wgs/prs_per_variant.tsv  (unchanged script)
   ▼  [NEW] pipeline/00_run_wgs.sh orchestrates, then:
   export_findings --raw output/raw_findings/wgs   (schema v2: +source=wgs, +scan_tier)
                                                     → output/findings/genomic_findings.json  (supersedes imputed)
```

## 5. Components

### 5.1 Code we write (new files + edits to existing files)

1. **`pipeline/wgs/prep_wgs_vcf.sh`** *(new)* — gVCF → canonical biallelic PASS
   variant-only GRCh38 sites VCF. Steps: drop ref-blocks (`ALT='.'`/`<NON_REF>`),
   keep `FILTER=PASS`, **`bcftools norm -f <GRCh38 no-prefix FASTA> -m-`** (split +
   left-align + trim — *mandatory*, see §9), then drop any residual `<NON_REF>`/`.`
   ALT produced by the split. Output `data/wgs/SQ8TH633.wgs.pass.vcf.gz` + `.tbi`.
2. **`pipeline/06_clinvar_acmg.py`** *(edit)* — add `--mode {actionable,exploratory}`
   reusing the existing ClinVar-matching engine (matches by `chrom:pos:REF:ALT`, so
   §9 normalization is correctness-critical, not cosmetic):
   - `actionable` (existing behavior, default): ACMG SF v3.2 gene list, P/LP,
     `--min-stars 2`, + recessive carrier panel → `clinvar_acmg.tsv`,
     `carrier_status.tsv`. **Does not emit `clinvar_full.tsv`** for the WGS path
     (the exploratory tier replaces it — see §5.3).
   - `exploratory` *(new)*: genome-wide P/LP, `--min-stars 1`, no gene restriction,
     **excluding** variants already in the actionable output (dedupe by
     `chrom:pos:REF:ALT`), collect **all** matches then sort by (stars desc,
     significance) and truncate to a cap (default 200) → `clinvar_exploratory.tsv`.
3. **`pipeline/00_run_wgs.sh`** *(new)* — WGS orchestrator: prep → `06 --mode
   actionable` → `06 --mode exploratory` → PharmCAT → `10` → `11` → `export_findings
   --raw output/raw_findings/wgs`. No `TOPMED_PASS`, no decrypt/concat/extract/R².
   **Reuses** (does not duplicate) the build-agnostic ClinVar-download and
   PharmCAT-slice blocks from `00_run_phase3.sh`. Passes `--vcf
   data/wgs/SQ8TH633.wgs.pass.vcf.gz` and `--out/--outdir output/raw_findings/wgs/…`
   to every annotator.
4. **`pipeline/export_findings.py` + `pipeline/parsers/genome.py`** *(edit)* — schema v2:
   - Add **two new columns** to **both** `FINDINGS_COLUMNS` (genome.py L19-32) **and**
     the independent `pa.schema` tuple in `parse_to_parquet` (genome.py L209-222):
     - `source` (`wgs` | `imputed`) — stamped on every row by `collect_rows`
       (export) and `parse_to_parquet` via a `source=` argument; defaults `imputed`
       for backward-compat, `wgs` for the WGS run.
     - `scan_tier` (`actionable` | `exploratory`) — set by the parsers; defaults
       `actionable`, set to `exploratory` only for `clinvar_exploratory.tsv` rows.
   - **Leave the existing `tier` (A/B/C) column untouched** — it is the ClinVar-star
     analyst tier consumed by the dashboard; the new scan tier is a *separate* column.
   - **Register** `clinvar_exploratory.tsv` in `TSV_PARSERS` (genome.py L176-185)
     reusing the generic `parse_clinvar_tsv` (its header matches `06`'s output):
     `("clinvar_exploratory.tsv", lambda p: parse_clinvar_tsv(p, "clinvar_exploratory"))`.
   - Bump `SCHEMA_VERSION` 1 → 2 (export_findings.py L26).

### 5.2 Reused unchanged

- `10_imputed_panels.py` — rsID-keyed; the gVCF carries rsIDs for the common panel
  SNPs. Orchestrator passes `--vcf` and `--out output/raw_findings/wgs/imputed_panels.tsv`
  (keep the **existing filename** so the `imputed_panels.tsv` parser registration is
  unchanged; the "imputed_" prefix is legacy, not literal).
- `11_prs.py` — matches by rsID **or** `chrom:pos` (strips `chr`). Orchestrator passes
  `--vcf` and the wgs `--out`/`--per-variant-out`.
- PharmCAT invocation, ClinVar download, PGS scoring-file machinery — unchanged.

### 5.3 `clinvar_full.tsv` resolution

Today `06` always writes `clinvar_full.tsv` (genome-wide P/LP ≥ min-stars) and it is
registered in `TSV_PARSERS`. For the WGS path it would **duplicate** the new
exploratory tier (both genome-wide P/LP). Decision: the WGS run does **not** place a
`clinvar_full.tsv` in `output/raw_findings/wgs/`; the exploratory tier (≥1★,
dedup-against-actionable, capped) is its replacement. `clinvar_full.tsv` stays in
`TSV_PARSERS` for the legacy imputed path; it is simply absent from the WGS dir, so
`collect_rows` skips it (missing files are skipped).

## 6. Outputs

Flat under `output/raw_findings/wgs/`: `clinvar_acmg.tsv`, `carrier_status.tsv`,
`clinvar_exploratory.tsv`, `imputed_panels.tsv`, `prs_scores.tsv`,
`prs_per_variant.tsv`; plus `output/pharmcat/`. `prs_per_variant.tsv` is a **report
artifact only** — it has no `TSV_PARSERS` entry and does not flow into the findings JSON.

**Supersede mechanism (explicit):** `export_findings` overwrites the single fixed
`output/findings/genomic_findings.json`. Because `00_run_wgs.sh` invokes it with
`--raw output/raw_findings/wgs` — an **isolated** directory containing **only** WGS
TSVs — the regenerated artifact is WGS-only. Imputed TSVs remain in their own
`output/raw_findings/` location as history and are **not read** by the WGS export.
`source=wgs` on every row is informational, not a filter.

## 7. Schema changes (`genomic_findings.json`)

- `SCHEMA_VERSION` 1 → 2.
- **New columns:** `source` (`wgs`|`imputed`) and `scan_tier` (`actionable`|`exploratory`).
  The existing `tier` (A/B/C) is **unchanged**. (The earlier draft wrongly described
  `tier` as new — it already exists and is dashboard-load-bearing.)
- Each new column must be added to **both** `FINDINGS_COLUMNS` and the hardcoded
  `pa.schema` tuple in `parse_to_parquet` (they are not derived from each other).
- Additive and backward-compatible at the row level. **Coordination note:** the
  downstream `prefrontal-cortex` reader must tolerate the two new fields (its side).

## 8. Testing (TDD — tests before implementation)

- **Fixtures:** a tiny synthetic gVCF (`tests/parsers/fixtures/wgs_gvcf_sample.vcf`)
  containing: ref-blocks (`ALT='.'`), a `<NON_REF>` ref-block, a **mixed** record
  (`ALT='A,<NON_REF>'`), a multiallelic **non-parsimonious homopolymer indel** (e.g.
  `CAAA → CA,C`), a non-PASS record, and PASS variants with/without rsIDs; a small
  ClinVar subset whose entries are stored in canonical left-aligned form.
- **Tests:**
  - **prep:** ref-blocks + `<NON_REF>` dropped; the multiallelic indel splits and
    **left-aligns/trims to the exact REF/ALT ClinVar uses** (the acceptance check that
    decides §9 — named positions, expected normalized alleles); non-PASS removed;
    rsIDs retained; residual `<NON_REF>` from the mixed record removed.
  - **`06` tiered:** actionable selects only ACMG-SF P/LP ≥2★ + carrier panel
    (`carrier_status.tsv` content asserted); exploratory selects genome-wide P/LP ≥1★,
    excludes actionable dupes, and **sorts the full set before** truncating to the cap
    (tested on a set larger than the cap).
  - **reuse:** `10`/`11` match against the synthetic WGS fixture (rsID for panels,
    rsID-or-pos for PRS) and emit rows.
  - **export:** schema-v2 columns (`source`, `scan_tier`) present in JSON **and**
    parquet; `clinvar_exploratory.tsv` registered and parsed; `source=wgs` stamped.
  - **orchestrator:** `00_run_wgs.sh` runs stages in order and omits the TOPMed
    steps (decrypt/concat/extract/R²); a smoke test on the fixture.

## 9. Reference data & the normalization decision

- **Left-alignment is mandatory.** `bcftools norm -m-` *without* `-f FASTA` splits
  multiallelics but does **not** left-align or trim, so non-parsimonious split indels
  (abundant in this gVCF's homopolymers, e.g. `1:82133 CAAA→CA,C`) would silently fail
  `06`'s exact `chrom:pos:REF:ALT` match against ClinVar's canonical form →
  false-negative P/LP indel findings. Therefore prep runs
  `bcftools norm -f <GRCh38 FASTA> -m-` (single invocation: split + left-align + trim).
- **The FASTA must use the gVCF's contig naming** (`1..22,X,Y,MT`, no `chr` prefix).
  A GRCh38 FASTA exists in-repo at `refs/pharmcat/reference.fna.bgz` but is `chr`-prefixed.
  The plan will resolve this by **reheadering that FASTA to a no-prefix copy**
  (`refs/grch38_noprefix.fa[.gz]` + `.fai`) — a one-time prep step, no new multi-GB
  download — and the prep script uses that. (Fallback if reheadering proves unviable:
  fetch a no-prefix GRCh38 primary-assembly FASTA.)
- **Other dependencies — already present:** ClinVar GRCh38 (`refs/clinvar_grch38.vcf.gz`),
  PharmCAT jar + positions (`refs/pharmcat/`), PGS scoring files (fetched by `11`). The
  gVCF already carries rsIDs, so **no dbSNP download**.

## 10. Risks & mitigations

- **Indel/ClinVar representation** — resolved by mandatory left-align (§9); guarded by
  the named-indel acceptance test (§8).
- **PharmCAT on a full WGS VCF** — verify the positions-slice produces valid PharmCAT
  input (chr-naming, preprocessing); fall back to PharmCAT's own preprocessor if needed.
- **Exploratory-tier volume** — sort-before-cap + dedupe-against-actionable (§5.1).
- **chr-naming** — gVCF/ClinVar/PRS are consistent no-prefix; only PharmCAT and the
  `norm` FASTA need explicit naming handling (§9).

## 11. Pre-existing bug to flag (NOT fixed by this spec)

The reviewers found that the shipped `export_findings.py` reads a **flat**
`output/raw_findings/` and never recurses, yet the imputed pipeline writes ClinVar TSVs
to a **sub-dir** `output/raw_findings/imputed_grch38/` (00_run_phase3.sh) — and the
prior split spec (2026-05-08) says export must read that sub-dir. So the **current
imputed** ClinVar/carrier rows likely never reach `genomic_findings.json` today. This
WGS spec sidesteps the bug by writing WGS TSVs **flat** in the dir it points export at.
The latent imputed-path bug is **out of scope** here — flagged for a separate fix.

## 12. Out of scope — Spec B (separate cycle)

AnnotSV-based annotation of the Manta SV (5,265) and Canvas CNV (985) VCFs, with its
own GRCh38 annotation databases, parsing into findings rows, and schema/export
extension. Built after Spec A is working.
