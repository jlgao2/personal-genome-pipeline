# WGS SV/CNV Annotation Path — Design (Spec B)

- **Date:** 2026-06-07
- **Status:** Draft for review
- **Scope:** Spec B — structural-variant (SV) and copy-number (CNV) annotation via AnnotSV.
  Follows Spec A (SNV/indel), which is merged to `main`.

## 1. Context & motivation

Spec A annotated the WGS SNV/indel gVCF. The 30× WGS order also produced **structural
variant** and **copy-number** calls that SNV/indel calling and imputation fundamentally
cannot detect (e.g. a whole-exon deletion in a disease gene). This spec annotates them
with **AnnotSV** — the standard SV/CNV interpreter — and folds the results into the same
`genomic_findings.json` contract, using the tiered scheme established in Spec A.

## 2. Verified inputs

| File | Content | Notes |
|---|---|---|
| `data/wgs/SQ8TH633.30x.sv.vcf.gz` | **5,265 Manta SVs** (3,638 DEL, 1,204 INS, 423 DUP), 100 bp–100 kb, all PASS, sequence-resolved | SV input |
| `data/wgs/SQ8TH633.30x.cnv.vcf.gz` | **~489 real Canvas CNVs** (367 `<CN0>` hom-del, 43 `<CN3>` gain, 13 `<DUP>`, 66 `<CN2>`) + **496 `Canvas:REF` segments** (`ALT='.'`) | CNV input — REF segments dropped |

GRCh38, sample `SQ8TH633`, contigs `1..22,X,Y,MT` (no `chr` prefix). BGZF — decompress
only with `bgzip`/`bcftools` (never Archive Utility/`zcat`).

## 3. Scope

- **In scope:** install AnnotSV + GRCh38 annotations; prep SV/CNV VCFs; run AnnotSV;
  parse its ranked output into tiered findings rows; register the parser; a separate
  orchestrator; tests.
- **Out of scope:** the PRS-percentile fix (needs reference allele frequencies +
  ancestry — separate follow-up); the pre-existing imputed-path `export_findings`
  sub-dir bug (Spec A §11).

## 4. Architecture / data flow

AnnotSV is a **heavy, optional** dependency (multi-GB annotation databases), so it lives
in its **own orchestrator** (`00_run_wgs_sv.sh`) — never burdening the core `00_run_wgs.sh`.

```
data/wgs/SQ8TH633.30x.sv.vcf.gz   (5,265 Manta SVs)        ┐
data/wgs/SQ8TH633.30x.cnv.vcf.gz  (~489 real Canvas CNVs)  ┘
   │  [NEW] pipeline/wgs/prep_sv_cnv.sh
   │    - SV : keep FILTER=PASS (already), restrict to 1..22,X,Y
   │    - CNV: drop Canvas REF segments (ALT='.'), keep real CN calls, restrict to 1..22,X,Y
   ▼
   data/wgs/SQ8TH633.sv.pass.vcf.gz  +  data/wgs/SQ8TH633.cnv.pass.vcf.gz
   │  [NEW] AnnotSV -genomeBuild GRCh38 -SVinputFile <vcf> -outputFile <tsv>   (run per file)
   ▼
   AnnotSV ranked TSVs  (one row per SV "full" + per-gene "split"; ACMG_class 1–5,
                         Gene_name, OMIM, ClinGen/dbVar/DGV evidence, AnnotSV_ranking)
   │  [NEW] pipeline/15_parse_annotsv.py
   │    - use per-gene "split" rows; keep ACMG_class >= 3
   │    - tier:  class 4–5 → scan_tier=actionable ; class 3 → scan_tier=exploratory
   │    - dedupe (SV × gene); cap exploratory (default 200, sorted by class desc)
   ▼
   output/raw_findings/wgs/sv_cnv_findings.tsv
   │  [register parse_sv_cnv_tsv in TSV_PARSERS]  →  export_findings --raw …/wgs --source wgs
   ▼
   output/findings/genomic_findings.json   (SV/CNV rows added; schema v2, source=wgs)
```

## 5. Components

### 5.1 New code

1. **`pipeline/wgs/install_annotsv.sh`** — install AnnotSV via bioconda
   (`mamba create -n annotsv -c bioconda -c conda-forge annotsv` or into an existing env),
   then run AnnotSV's annotation-data install for **GRCh38**. Idempotent (skip if present).
   Records the AnnotSV binary path for the orchestrator.
2. **`pipeline/wgs/prep_sv_cnv.sh`** — SV: `bcftools view -r 1..22,X,Y -f PASS`. CNV:
   same region/PASS plus drop `Canvas:REF` segments (`-e 'ALT="."'`). Outputs two bgzipped
   VCFs + indexes.
3. **`pipeline/15_parse_annotsv.py`** — parse AnnotSV TSV → `sv_cnv_findings.tsv`. Reads
   per-gene "split" rows, keeps `ACMG_class >= 3`, assigns `scan_tier`/`tier`, dedupes by
   (SV coords × gene), sorts exploratory by class and caps. Emits the columns the
   `parse_sv_cnv_tsv` parser expects (chrom, start, end, svtype, svlen, gene, acmg_class,
   caller, evidence, summary).
4. **`pipeline/00_run_wgs_sv.sh`** — orchestrator: `install_annotsv.sh` (idempotent) →
   `prep_sv_cnv.sh` → AnnotSV per file → `15_parse_annotsv.py` → `export_findings --raw
   output/raw_findings/wgs --source wgs`. Re-exporting picks up both the Spec A TSVs and
   the new `sv_cnv_findings.tsv` (flat dir, additive).
5. **`pipeline/parsers/genome.py`** — add `parse_sv_cnv_tsv` and register
   `("sv_cnv_findings.tsv", …)` in `TSV_PARSERS`. Maps to the existing canonical row:
   `source_tsv="sv_cnv"`, `chrom`, `pos`=start, `ref="N"`, `alt="<SVTYPE>"`, `gene`,
   `tier` (5→A,4→B,3→C), `scan_tier` (actionable/exploratory), `summary`
   (e.g. "DEL 12 kb overlapping BRCA1 — AnnotSV class 5 (pathogenic)"), `meta`
   (start/end/svlen/svtype/acmg_class/caller/evidence). **No schema change** — Spec A's
   schema v2 already has `source`/`scan_tier`.

### 5.2 Reused unchanged

`export_findings` (flat `--raw …/wgs`, `--source wgs`), the schema-v2 machinery,
`bcftools`. The core `00_run_wgs.sh` is untouched.

## 6. Tiering (consistent with Spec A)

| AnnotSV ACMG class | meaning | included? | `scan_tier` | `tier` |
|---|---|---|---|---|
| 5 | pathogenic | yes | actionable | A |
| 4 | likely pathogenic | yes | actionable | B |
| 3 | VUS | yes | **exploratory** | C |
| 2 | likely benign | no | — | — |
| 1 | benign | no | — | — |

Exploratory rows are sorted by class (desc) and capped (default 200) — same discipline as
Spec A's ClinVar exploratory tier.

## 7. Testing (TDD)

AnnotSV itself is a heavy external tool — **not** invoked in unit tests; it's validated in
the real run (like Spec A Task 7). Unit tests cover our code:
- **`prep_sv_cnv.sh`:** synthetic SV + CNV VCFs (incl. a `Canvas:REF` segment, a `<CN0>`,
  a non-PASS) → assert REF segments dropped, real calls kept, PASS-filtered, contigs
  restricted.
- **`15_parse_annotsv.py` / `parse_sv_cnv_tsv`:** a small synthetic AnnotSV-format TSV with
  class 1–5 rows → assert class ≥3 kept, class<3 dropped, tier/scan_tier mapping correct,
  exploratory sorted+capped, fields mapped into the canonical row.
- **orchestrator** `00_run_wgs_sv.sh`: text smoke test (installs idempotently, uses
  `--source wgs`, writes to `output/raw_findings/wgs/`).

## 8. Dependencies & risks

- **AnnotSV install on macOS arm64.** bioconda's `annotsv` may resolve only for `osx-64`
  (Rosetta) on Apple Silicon — the plan must verify and fall back to `CONDA_SUBDIR=osx-64`
  or manual install if needed.
- **Annotation databases (~several GB)** download — one-time, via AnnotSV's installer.
- **chr-naming.** AnnotSV's GRCh38 annotations and our no-prefix input must agree — same
  class of issue as the PharmCAT bug in Spec A. The plan must verify AnnotSV's expected
  contig naming and reconcile (rename input if required), with a non-empty-output guard.
- **Canvas symbolic CNV alleles** (`<CN0>`/`<CN3>`) — confirm AnnotSV ingests them (it
  supports symbolic CNV VCFs; verify on the real file).

## 9. Out of scope (follow-ups)

- PRS percentile fix (reference allele frequencies + ancestry-matched reference;
  `n_with_af=0` today so all percentiles are `NA`).
- Imputed-path `export_findings` sub-dir bug (Spec A §11).
