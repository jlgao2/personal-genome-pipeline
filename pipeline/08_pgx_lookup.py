#!/usr/bin/env python3
"""
Direct lookup of pharmacogenomic-relevant SNPs from CPIC Level A guidelines that can be
called from a 23andMe v5 chip without imputation. This is a stop-gap until full PharmCAT
runs on the imputed VCF; it covers the most clinically actionable PGx variants.

Each SNP is annotated with: gene, key drug(s), the relevant haplotype, and a one-line
implication for each user genotype.

Output: output/raw_findings/pgx_quick.tsv
"""
import argparse
import gzip
import os
import sys

# (rsid, gene, drug_class, haplotype_role, hg19_chrom, hg19_pos, ref, alt,
#  meaning_homozygous_alt, meaning_het, meaning_homozygous_ref)
PGX_PANEL = [
    # ----- VKORC1 / Warfarin sensitivity -----
    ("rs9923231", "VKORC1", "Warfarin", "-1639G>A: A allele = lower warfarin dose required",
     "16", 31107689, "C", "T",
     "T/T (=A/A on cDNA): high warfarin sensitivity, ~50% lower starting dose. Tell prescriber.",
     "C/T (=G/A): intermediate sensitivity, ~25% lower starting dose.",
     "C/C (=G/G): typical warfarin sensitivity."),
    # ----- CYP2C9 -----
    ("rs1799853", "CYP2C9", "Warfarin, NSAIDs, phenytoin", "*2 (R144C) reduces metabolism",
     "10", 96702047, "C", "T",
     "T/T: CYP2C9 *2/*2 — markedly reduced metabolism of warfarin/NSAIDs.",
     "C/T: CYP2C9 *1/*2 — moderately reduced metabolism.",
     "C/C: no *2 allele."),
    ("rs1057910", "CYP2C9", "Warfarin, NSAIDs, phenytoin", "*3 (I359L) more severely reduces metabolism",
     "10", 96741053, "A", "C",
     "C/C: CYP2C9 *3/*3 — severely reduced metabolism, ~80% dose reduction for warfarin.",
     "A/C: CYP2C9 *1/*3 — significantly reduced metabolism.",
     "A/A: no *3 allele."),
    # ----- CYP2C19 -----
    ("rs4244285", "CYP2C19", "Clopidogrel, PPIs, citalopram, voriconazole", "*2 (681G>A) loss-of-function",
     "10", 96541616, "G", "A",
     "A/A: CYP2C19 *2/*2 — POOR metabolizer; clopidogrel ineffective, alternate antiplatelet recommended; PPI doses may be increased.",
     "G/A: CYP2C19 *1/*2 — INTERMEDIATE metabolizer; reduced clopidogrel efficacy.",
     "G/G: no *2 allele at this position."),
    ("rs4986893", "CYP2C19", "Clopidogrel, PPIs, citalopram, voriconazole", "*3 (636G>A) loss-of-function",
     "10", 96540410, "G", "A",
     "A/A: CYP2C19 *3/*3 — poor metabolizer (rare).",
     "G/A: CYP2C19 *1/*3 — intermediate metabolizer.",
     "G/G: no *3 allele."),
    ("rs12248560", "CYP2C19", "Clopidogrel, PPIs, citalopram, voriconazole", "*17 (-806C>T) gain-of-function",
     "10", 96521657, "C", "T",
     "T/T: CYP2C19 *17/*17 — RAPID metabolizer; lower drug levels for citalopram/escitalopram, higher bleeding risk on clopidogrel.",
     "C/T: CYP2C19 *1/*17 — rapid metabolizer phenotype.",
     "C/C: no *17 allele."),
    # ----- TPMT (thiopurines) -----
    ("rs1800462", "TPMT", "Azathioprine, mercaptopurine, thioguanine", "*2 (A80P) loss-of-function",
     "6", 18143955, "C", "G",
     "G/G: TPMT *2/*2 — DO NOT use standard thiopurines (severe myelosuppression).",
     "C/G: heterozygous *2 — start at 30-70% standard dose with frequent CBC monitoring.",
     "C/C: no *2 allele."),
    ("rs1142345", "TPMT", "Azathioprine, mercaptopurine, thioguanine", "*3C (Y240C) loss-of-function",
     "6", 18130918, "T", "C",
     "C/C: TPMT *3C/*3C — DO NOT use standard thiopurines.",
     "T/C: heterozygous *3C — reduced dose with monitoring.",
     "T/T: no *3C allele."),
    ("rs1800460", "TPMT", "Azathioprine, mercaptopurine, thioguanine", "*3B (A154T) loss-of-function",
     "6", 18139228, "C", "T",
     "T/T: TPMT *3B/*3B — DO NOT use standard thiopurines.",
     "C/T: heterozygous *3B — reduced dose.",
     "C/C: no *3B allele."),
    # ----- DPYD (5-FU / capecitabine toxicity) -----
    ("rs3918290", "DPYD", "5-Fluorouracil, capecitabine", "*2A (splice variant) — strong toxicity",
     "1", 97915614, "C", "T",
     "T/T: DPYD *2A/*2A — DO NOT give 5-FU or capecitabine.",
     "C/T: heterozygous *2A — start at 50% dose; very high risk of severe toxicity.",
     "C/C: no *2A."),
    ("rs55886062", "DPYD", "5-Fluorouracil, capecitabine", "*13 (I560S) — strong toxicity",
     "1", 97981343, "A", "C",
     "C/C: DPYD *13/*13 — DO NOT give 5-FU/capecitabine.",
     "A/C: heterozygous *13 — start at 50% dose.",
     "A/A: no *13."),
    # ----- SLCO1B1 (statin myopathy) -----
    ("rs4149056", "SLCO1B1", "Simvastatin (and other statins to lesser extent)", "*5 (V174A) reduces transporter function",
     "12", 21331549, "T", "C",
     "C/C: SLCO1B1 *5/*5 — high simvastatin myopathy risk; avoid simvastatin or use ≤20mg/d.",
     "T/C: heterozygous *5 — moderate simvastatin myopathy risk; ≤40mg/d.",
     "T/T: typical SLCO1B1 function."),
    # ----- UGT1A1 (irinotecan, atazanavir) -----
    ("rs8175347", "UGT1A1", "Irinotecan, atazanavir", "TA repeat *28 (Gilbert syndrome) — but a chip can't directly call this STR.",
     "2", 234668879, "T", "C", "(Tag SNP not directly informative for *28; use PharmCAT post-imputation for accurate calling.)",
     "(Tag SNP not directly informative for *28.)", "(Tag SNP not directly informative for *28.)"),
    # ----- IFNL3/IFNL4 (HCV treatment response) -----
    ("rs12979860", "IFNL3", "Interferon-α / ribavirin (HCV)", "C/C predicts sustained virologic response",
     "19", 39738787, "C", "T",
     "T/T: lower likelihood of HCV treatment response with IFN-based regimens.",
     "C/T: intermediate response likelihood.",
     "C/C: best HCV treatment response."),
    # ----- HLA-B*57:01 tag SNP (abacavir hypersensitivity) -----
    ("rs2395029", "HCP5/HLA-B*57:01", "Abacavir (HIV)", "Tag SNP for HLA-B*57:01 carrier",
     "6", 31431780, "T", "G",
     "G/G: HLA-B*57:01 likely homozygous — DO NOT receive abacavir.",
     "T/G: HLA-B*57:01 carrier — DO NOT receive abacavir.",
     "T/T: not a *57:01 carrier (still confirm HLA test if abacavir is being prescribed)."),
    # ----- F5 Leiden (thrombosis) -----
    ("rs6025", "F5", "Estrogen contraceptives, surgery, immobilization", "Factor V Leiden",
     "1", 169519049, "C", "T",
     "T/T: Factor V Leiden homozygous — markedly elevated VTE risk; avoid combined oral contraceptives, perioperative anticoag prophylaxis.",
     "C/T: F5 Leiden heterozygous — ~5-7x VTE risk; counsel on E2 OCPs, surgery, long flights.",
     "C/C: no F5 Leiden."),
    # ----- F2 prothrombin -----
    ("rs1799963", "F2", "Estrogen contraceptives, VTE", "Prothrombin G20210A",
     "11", 46761055, "G", "A",
     "A/A: prothrombin homozygous (rare) — high VTE risk.",
     "G/A: prothrombin het — ~2-3x VTE risk.",
     "G/G: no prothrombin variant."),
    # ----- G6PD (already in nutrition panel; included here as drug-PGx) -----
    ("rs1050828", "G6PD", "Primaquine, sulfa, dapsone, naphthalene, fava beans", "G6PD A- (Med./African deficiency)",
     "X", 153764217, "C", "T",
     "T/T (or T in males): G6PD deficient — strict avoidance of triggering drugs.",
     "C/T (females): heterozygous, mild deficiency possible.",
     "C/C (or C in males): normal G6PD."),
    # ----- NUDT15 (thiopurine, especially in East Asians) -----
    ("rs116855232", "NUDT15", "Azathioprine, mercaptopurine", "*3 (R139C) loss-of-function (common in East Asians)",
     "13", 48611918, "C", "T",
     "T/T: NUDT15 *3/*3 — DO NOT use standard thiopurines (severe myelosuppression).",
     "C/T: heterozygous *3 — reduced dose with monitoring.",
     "C/C: no *3 variant."),
]


def parse_vcf_lookup(path, positions):
    open_fn = gzip.open if path.endswith(".gz") else open
    out = {}
    with open_fn(path, "rt") as f:
        sample_idx = None
        for line in f:
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                cols = line.rstrip().split("\t")
                if len(cols) > 9:
                    sample_idx = 9
                continue
            cols = line.rstrip().split("\t")
            if len(cols) < 8:
                continue
            chrom = cols[0].replace("chr", "")
            try:
                pos = int(cols[1])
            except ValueError:
                continue
            if (chrom, pos) not in positions:
                continue
            ref, alt = cols[3], cols[4]
            gt = ""
            if sample_idx and len(cols) > sample_idx:
                fmt = cols[8].split(":")
                vals = cols[sample_idx].split(":")
                if "GT" in fmt:
                    gt = vals[fmt.index("GT")]
            out[(chrom, pos)] = (ref, alt, gt)
    return out


def gt_to_alleles(gt, ref, alt):
    if not gt:
        return ""
    parts = gt.replace("|", "/").split("/")
    return "/".join(ref if p == "0" else (alt if alt != "." else ref) if p == "1" else "." for p in parts)


def count_alt(alleles, alt):
    if not alleles or alleles == ".":
        return -1
    return sum(1 for a in alleles.replace("|", "/").split("/") if a == alt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vcf", required=True)
    ap.add_argument("--out", default="output/raw_findings/pgx_quick.tsv")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    positions = {(p[4], p[5]) for p in PGX_PANEL}
    found = parse_vcf_lookup(args.vcf, positions)

    flagged = []
    with open(args.out, "w") as f:
        f.write("rsid\tgene\tdrug\thaplotype_role\tchrom\tpos\tref\talt\tuser_genotype\tn_alt\tinterpretation\n")
        for (rsid, gene, drug, role, chrom, pos, exp_ref, exp_alt,
             mean_homalt, mean_het, mean_homref) in PGX_PANEL:
            row = found.get((chrom, pos))
            if not row:
                f.write(f"{rsid}\t{gene}\t{drug}\t{role}\t{chrom}\t{pos}\t.\t.\t(not_typed)\t-1\t(not on chip — fill via imputation)\n")
                continue
            ref, alt, gt = row
            alleles = gt_to_alleles(gt, ref, alt)
            n = count_alt(alleles, exp_alt)
            if n == 2:
                interp = mean_homalt
            elif n == 1:
                interp = mean_het
            elif n == 0:
                interp = mean_homref
            else:
                interp = "(genotype unavailable)"
            f.write(f"{rsid}\t{gene}\t{drug}\t{role}\t{chrom}\t{pos}\t{ref}\t{alt}\t{alleles}\t{n}\t{interp}\n")
            if n >= 1:
                flagged.append((gene, drug, alleles, interp))

    sys.stderr.write(f"PGx panel: {len(PGX_PANEL)} SNPs, matched {len(found)}\n")
    sys.stderr.write(f"Variants present (n_alt >= 1): {len(flagged)}\n")
    for gene, drug, alleles, interp in flagged:
        sys.stderr.write(f"  - {gene} ({drug}): {alleles} → {interp[:100]}\n")
    sys.stderr.write(f"\nWrote {args.out}\n")


if __name__ == "__main__":
    main()
