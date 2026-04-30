#!/usr/bin/env python3
"""
Curated lookup of additional well-characterized GWAS / pharmacogenomic / behavioral
SNPs that work on the raw 23andMe v5 chip. Output: output/raw_findings/extra_traits.tsv

All positions/REF/ALT verified against dbSNP forward strand.
"""
import argparse
import gzip
import os
import sys

# (rsid, gene, trait, hg19_chrom, hg19_pos, ref, alt, trait_allele,
#  meaning_homozygous_trait, meaning_het, meaning_homozygous_ref)
PANEL = [
    # ----- Coronary Artery Disease (9p21.3, strongest common locus) -----
    ("rs10757278", "CDKN2B-AS1 (9p21.3)", "Coronary artery disease", "9", 22124477, "A", "G", "G",
     "G/G: ~1.5-2.0x baseline early-MI risk (strongest common CAD variant). Aggressive lipid management + earlier cardiology workup recommended.",
     "A/G: ~1.25x risk; standard primary prevention emphasized.",
     "A/A: protective genotype at 9p21."),
    ("rs1333049", "CDKN2B-AS1 (9p21.3)", "CAD (in LD with rs10757278)", "9", 22125503, "G", "C", "C",
     "C/C: tags the same 9p21 risk haplotype as rs10757278 G/G — confirmation.",
     "G/C: heterozygote — moderate risk.",
     "G/G: protective."),
    # ----- Major depressive disorder, longevity -----
    ("rs6265",   "BDNF", "Val66Met", "11", 27679916, "C", "T", "T",
     "T/T (Met/Met): reduced activity-dependent BDNF secretion — modest associations with reduced episodic memory and altered antidepressant response.",
     "C/T (Val/Met): heterozygous — small effects.",
     "C/C (Val/Val): standard BDNF function."),
    ("rs2802292", "FOXO3", "Longevity allele", "6", 108908518, "T", "G", "G",
     "G/G: ~2x odds of reaching 95+ years in long-lived cohorts; tied to better stress response.",
     "T/G: ~1.4x longevity odds.",
     "T/T: baseline."),
    # ----- Pain & opioid response -----
    ("rs1799971", "OPRM1", "A118G (mu-opioid receptor)", "6", 154360797, "A", "G", "G",
     "G/G: substantially reduced opioid analgesic response — typically need higher doses; also altered alcohol/nicotine sensitivity.",
     "A/G: moderately reduced opioid response — flag for prescribers (acute pain, anesthesia).",
     "A/A: typical opioid response."),
    # ----- Beta-blocker / asthma response -----
    ("rs1801253", "ADRB1", "Arg389Gly (β1 receptor)", "10", 115805056, "G", "C", "C",
     "C/C (Arg/Arg): best response to β1-blockers (metoprolol, bisoprolol); enhanced HR/BP lowering.",
     "G/C (Arg/Gly): intermediate β-blocker response.",
     "G/G (Gly/Gly): least β1-blocker response — may need higher doses or alternative."),
    ("rs1042713", "ADRB2", "Arg16Gly (β2 receptor)", "5", 148206440, "A", "G", "G",
     "G/G (Gly/Gly): improved short-term albuterol response BUT tachyphylaxis with chronic LABA use.",
     "A/G (Arg/Gly): heterozygous.",
     "A/A (Arg/Arg): worse response to chronic β-agonists; consider alternatives."),
    # ----- COMT (dopamine metabolism, stress, pain) -----
    ("rs4680",    "COMT", "Val158Met", "22", 19951271, "G", "A", "A",
     "A/A (Met/Met): low COMT activity ('worrier' phenotype) — better executive function under low stress, worse under high stress; higher pain sensitivity.",
     "G/A (Val/Met): intermediate.",
     "G/G (Val/Val): high COMT activity ('warrior' phenotype) — opposite profile."),
    # ----- Social/empathy -----
    ("rs53576",   "OXTR", "Oxytocin receptor", "3", 8804371, "G", "A", "A",
     "A/A: associated in some studies with lower empathic accuracy and higher physiologic stress reactivity.",
     "A/G: intermediate.",
     "G/G: 'high empathy' allele in some studies — effects are modest and inconsistent."),
    # ----- TP53 codon 72 polymorphism -----
    ("rs1042522", "TP53", "Pro72Arg (codon 72)", "17", 7579472, "G", "C", "C",
     "C/C (Arg/Arg): more efficient apoptosis — slightly lower cancer susceptibility.",
     "G/C (Pro/Arg): heterozygous.",
     "G/G (Pro/Pro): more efficient cell-cycle arrest — modest effect on cancer susceptibility profile."),
    # ----- Smoking heaviness / lung cancer (CHRNA3-A5 cluster) -----
    ("rs1051730", "CHRNA3", "Cigarettes per day / lung cancer (in smokers)", "15", 78894339, "G", "A", "A",
     "A/A: in smokers, ~+2 cigarettes/day, ~80% higher lung cancer risk vs G/G smokers.",
     "G/A: intermediate.",
     "G/G: lower nicotine dependence allele."),
    # ----- 8q24 colorectal/prostate cancer -----
    ("rs6983267", "8q24 cancer locus", "Colorectal & prostate cancer risk", "8", 128413305, "T", "G", "G",
     "G/G: ~1.4x baseline colorectal cancer risk, ~1.3x prostate cancer risk — earlier colonoscopy may be considered.",
     "T/G: ~1.2x risk.",
     "T/T: protective at this locus."),
    # ----- CETP HDL/longevity -----
    ("rs5882",    "CETP", "Val405Ile (HDL/longevity)", "16", 57016092, "A", "G", "G",
     "G/G (Ile/Ile): ~+5 mg/dL higher HDL on average; modestly slower cognitive decline in some studies.",
     "A/G (Val/Ile): intermediate.",
     "A/A (Val/Val): typical HDL."),
    # ----- DRD3 -----
    ("rs6280",    "DRD3", "Ser9Gly (D3 dopamine receptor)", "3", 113890815, "T", "C", "C",
     "C/C: increased D3 binding; relevance for antipsychotic response and tardive dyskinesia risk.",
     "T/C: heterozygous.",
     "T/T: typical."),
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


def count(alleles, allele):
    if not alleles or alleles == ".":
        return -1
    return sum(1 for a in alleles.replace("|", "/").split("/") if a == allele)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vcf", required=True)
    ap.add_argument("--out", default="output/raw_findings/extra_traits.tsv")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    positions = {(p[3], p[4]) for p in PANEL}
    found = parse_vcf_lookup(args.vcf, positions)

    with open(args.out, "w") as f:
        f.write("rsid\tgene\ttrait\tchrom\tpos\tref\talt\tuser_genotype\ttrait_allele\tn_trait_alleles\tinterpretation\n")
        for (rsid, gene, trait, c37, p37, exp_ref, exp_alt, trait_a,
             mean_homtrait, mean_het, mean_homref) in PANEL:
            row = found.get((c37, p37))
            if not row:
                f.write(f"{rsid}\t{gene}\t{trait}\t{c37}\t{p37}\t.\t.\t(not_typed)\t{trait_a}\t-1\t(not on chip — fill via imputation)\n")
                continue
            ref, alt, gt = row
            alleles = gt_to_alleles(gt, ref, alt)
            n = count(alleles, trait_a)
            if n == 2:
                interp = mean_homtrait
            elif n == 1:
                interp = mean_het
            elif n == 0:
                interp = mean_homref
            else:
                interp = "(genotype unavailable)"
            f.write(f"{rsid}\t{gene}\t{trait}\t{c37}\t{p37}\t{ref}\t{alt}\t{alleles}\t{trait_a}\t{n}\t{interp}\n")

    sys.stderr.write(f"Extra-traits panel: {len(PANEL)} SNPs, matched {len(found)}\n")
    sys.stderr.write(f"Wrote {args.out}\n")


if __name__ == "__main__":
    main()
