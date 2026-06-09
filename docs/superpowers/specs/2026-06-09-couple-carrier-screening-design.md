# Couple Carrier Screening Tool — Design Spec

**Status:** Approved design (brainstorming) → ready for implementation planning
**Date:** 2026-06-09
**Repos:** `personal-genome-pipeline` (calling + intersect); `homelab-server` (the gated served page — kept deliberately separate from the personal `prefrontal-cortex` health dashboard)

## Goal

A **personal** tool for the user + one partner: screen both sequenced genomes for
**recessive carrier** status, flag genes where **both** partners carry a pathogenic
variant (→ affected-child risk), and present the result on a **gated homelab page**.
Research-grade, not a clinical carrier screen.

## Locked decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Scope | Personal — user + one partner. No general multi-user UX. |
| Partner data | Sequencing (WGS/WES): a VCF (+ a BAM for the special tier). |
| Gene panel | **Broad** — all ClinVar recessive P/LP genes, with significance flags. |
| Special tier | **Everything**: SMA (SMN1 CN), alpha-thalassemia (HBA del), Fragile X (FMR1 repeat), CFTR (poly-T/TG). |
| Output | **Served gated page** at `carrier.jlgao.net` (Cloudflare Access, single Google identity). |
| Architecture | **Approach A** — reuse the pipeline's calling code + a new `couple_carrier` intersect module + a dedicated gated page. |

## Architecture & data flow

```
person_A (VCF [+BAM]) ─→ per-person carrier calling ─→ carrier_calls.A.json ─┐
person_B (VCF [+BAM]) ─→ per-person carrier calling ─→ carrier_calls.B.json ─┤
                                                                              ├─→ couple_intersect ─→ couple_report.json ─→ carrier.jlgao.net (gated page)
```

Three isolated stages — **call** (per person, independent), **intersect** (join by gene),
**serve** (gated page). Each person's raw data stays on disk; only the per-person
`carrier_calls.json` crosses into the intersect (so a partner could, in future, run the
calling themselves and share only the summary — not built now, but the boundary allows it).

## File structure

```
pipeline/carrier/
  call_carriers.py        # per-person: orchestrates Tier 1 + Tier 2 → carrier_calls.<id>.json
  tier1_clinvar.py        # het ClinVar P/LP in recessive genes (reuses ClinVar machinery)
  tier2_special.py        # dispatch to SMN1 / alpha-thal / FMR1 / CFTR callers, normalise results
  couple_intersect.py     # join two carrier_calls.json → couple_report.json
  schema.py               # carrier_call + couple_report dataclasses / JSON schema
refs/carrier/
  gene_inheritance.tsv    # gene → inheritance (AR / XLR / …), curated from ClinGen/OMIM/gnomAD
data/partner/             # gitignored: partner VCF/BAM/FASTQ
output/carrier/           # gitignored: carrier_calls.*.json, couple_report.json
homelab: sites/carrier/   # static page rendering couple_report.json (Caddy + cloudflared ingress)
tests/carrier/            # TDD for intersect, tier1 filter, schema
```

## Stage 1 — per-person carrier calling

### Tier 1 — SNV/indel carriers (from the VCF)
- Reuse the existing ClinVar annotation path (`06_clinvar_acmg.py` / the ClinVar VCF).
- Keep a variant when **all** hold: genotype is **heterozygous** (`0/1`); ClinVar significance is
  Pathogenic or Likely_pathogenic (not Conflicting); the gene's inheritance ∈ {AR, XLR} per
  `refs/carrier/gene_inheritance.tsv`.
- `gene_inheritance.tsv` is a curated gene→inheritance map compiled from public recessive-gene
  references (ClinGen gene-disease validity, OMIM inheritance, gnomAD recessive lists). Shipped in
  the repo so calling is offline/reproducible.
- Emits: gene, chrom, pos, ref, alt, rsid, zygosity, clnsig, clndn (condition), review stars,
  inheritance, tier=`snv`.

### Tier 2 — special callers (from the BAM)
| Condition | Gene | Caller | Carrier signal |
|---|---|---|---|
| Spinal muscular atrophy | SMN1 | SMNCopyNumberCaller (Illumina, GitHub) | SMN1 full-length copy number = 1 |
| Alpha-thalassemia | HBA1/HBA2 | targeted coverage/CNV over chr16p13.3 (reuse Manta/AnnotSV SV calls if present, else a coverage-ratio check for --SEA / -α3.7 / -α4.2) | known deletion allele present |
| Fragile X | FMR1 | ExpansionHunter (Illumina, GitHub) | CGG repeat in premutation/full range |
| CFTR | CFTR | targeted poly-T/TG tract (5T/7T/9T) + IVS8 | risk tract genotype (common SNVs already in Tier 1) |

- Requires a BAM per person. A VCF-only partner gets Tier 1 + a flagged Tier-2 gap, or we align
  their FASTQ→BAM via `pipeline/wgs/align_fastq.sh` (already built).
- Each special result is normalised into the same carrier-call shape (gene, condition, inheritance,
  tier=`special`, method, result, confidence).

### Per-person output: `output/carrier/carrier_calls.<id>.json`
```
{ person_id, sex, source: {vcf, bam}, generated_at,
  calls: [ {gene, condition, inheritance, tier, method, variant_or_result,
            clnsig, stars, confidence} ] }   # raw clnsig/stars; the serious/moderate/low tier is computed at intersect
```
`person_id` is a label only (e.g. "A"/"B" or initials) — no raw genotypes beyond the called
carrier variants leave this file.

## Stage 2 — couple intersect

- Input: the two `carrier_calls.<id>.json`.
- Join carrier calls **by gene**. Emit a **couple-risk finding** for each gene where **both**
  persons are carriers:
  - **AR genes**: both carriers → **25% affected per pregnancy**; carries each partner's variant.
  - **X-linked recessive genes**: sex-aware — if the **female** partner carries an XLR variant,
    **sons have 50% risk** regardless of the male partner; surface this even when the male is not a
    carrier. (User is XY/male; partner sex is read from `carrier_calls.sex`.)
- **Significance tiering** of each couple-risk finding:
  - `serious` — inheritance AR/XLR **and** ClinVar ≥2★ **and** severe/childhood-onset
    (severe = on a recognized clinical carrier-panel gene list, shipped as
    `refs/carrier/severe_genes.txt`, derived from ACMG/ACOG panels).
  - `low` — <2★, or Conflicting, or mild/adult-onset/low-penetrance.
  - `moderate` — everything in between.
- Output `output/carrier/couple_report.json`:
```
{ generated_at, partners: [{id, sex}, {id, sex}],
  couple_risks: [ {gene, condition, inheritance, risk_pct, significance,
                   partner_A_variant, partner_B_variant, notes} ],
  single_carrier_highlights: [ ... ],   # high-significance genes where only one is a carrier (informational)
  coverage_caveats: [ ... ] }           # e.g. "partner B BAM absent → SMA/alpha-thal not assessed"
```

## Stage 3 — served gated page

- New site `carrier.jlgao.net`: a Caddy site binding an unused localhost port + a cloudflared
  ingress entry + a Cloudflare Access policy (same single-Google-identity policy as `health.jlgao.net`),
  per the homelab `RUNBOOK.md` pattern. Binds localhost only; TLS terminates at the Cloudflare edge.
- Static page reads `couple_report.json`: **serious shared-carrier risks first**, moderate/low
  collapsible, single-carrier highlights and coverage caveats in secondary sections, and a
  prominent disclaimer.
- DNS/Access dashboard setup is a user action (as in the RUNBOOK); the build provides the Caddy
  site, the ingress entry, and the page.

## Privacy, consent & disclaimer

- `data/partner/` (partner VCF/BAM/FASTQ) and `output/carrier/` are **gitignored** — never
  committed, never pushed.
- The served page is gated by Cloudflare Access (single Google identity). Residual exposure: data
  traverses the Cloudflare tunnel (gated, not public). This is the user's accepted trade-off for
  remote access.
- **Partner consent is a prerequisite** — their genome is analyzed and served. Documented in the
  page footer and the repo README for the tool.
- **Disclaimer** (shown on the page): research-grade; **not a clinical/diagnostic carrier screen**;
  confirm any finding with a clinical lab + genetic counselor before reproductive decisions.

## Testing

- **TDD — couple_intersect**: synthetic two-person carrier sets → assert correct shared-gene risks,
  AR 25% vs XLR sex-aware 50%-of-sons logic, and significance tiering (serious/moderate/low).
- **TDD — tier1_clinvar**: synthetic VCF + ClinVar → assert only het, P/LP, recessive-gene variants
  are kept (homozygous, dominant-gene, and benign variants excluded).
- **Special callers**: integration-tested against the user's real BAM; result-parsing unit-tested
  with captured fixtures.
- **Page**: smoke test that it renders a sample `couple_report.json`.

## Phasing

- **Phase 1** — Tier-1 SNV couple screen + `couple_intersect` + gated page (works from VCFs alone;
  no GitHub-tool installs). Delivers a working couple screen.
- **Phase 2** — special callers added incrementally: SMN1 → alpha-thal → FMR1 → CFTR (each may
  need a GitHub-tool install approval).

## Dependencies / open items

- **Partner genome** for a *real* run — not yet available. Build & test now with the user's BAM as
  one person + a **synthetic second person**; the tool is ready when real partner data arrives.
- **Byproduct**: running Tier 1 + Tier 2 on the user's genome finally populates the user's own
  carrier status (the `carrier_status.tsv` = 0-rows gap noted earlier).
- **GitHub tool installs** (SMNCopyNumberCaller, ExpansionHunter) — require explicit user approval.
- **`carrier.jlgao.net`** DNS + Cloudflare Access setup — user dashboard action (per RUNBOOK).
