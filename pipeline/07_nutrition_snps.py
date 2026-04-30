#!/usr/bin/env python3
"""
Look up a curated panel of nutrition / metabolism / wellness SNPs in the user's VCF
and emit a TSV with genotype, # of trait-allele copies, and one-line implication.

All positions and trait_allele values are dbSNP forward-strand (GRCh37 = hg19)
verified via myvariant.info. n_trait_alleles is computed by counting trait_allele
copies in the user's diploid genotype (or 1 copy = "carrier" for X-linked males).

Inputs:
  --vcf    user genotype VCF
  --build  "GRCh37" (default) — only build supported until imputation completes

Output:
  output/raw_findings/nutrition_traits.tsv
"""
import argparse
import gzip
import os
import sys

# Schema:
#  (rsid, gene, trait,
#   chrom_hg19, pos_hg19,
#   chrom_hg38, pos_hg38,
#   trait_allele_hg19_fwd_strand, dbsnp_ref,
#   description,
#   meaning_homozygous_trait, meaning_het, meaning_homozygous_ref)
PANEL = [
    # ----- APOE haplotype-defining SNPs -----
    ("rs429358", "APOE", "APOE-e4 status", "19", 45411941, "19", 44908684, "C", "T",
     "rs429358 + rs7412 jointly define APOE epsilon haplotypes (e2/e3/e4).",
     "C/C: e4/e4 — ~12-15x lifetime Alzheimer's risk vs e3/e3, higher LDL.",
     "T/C: 1 e4 allele — ~3x AD risk vs e3/e3.",
     "T/T: no e4 — combine with rs7412 result for full APOE haplotype."),
    ("rs7412",   "APOE", "APOE-e2 status", "19", 45412079, "19", 44908822, "T", "C",
     "rs429358 + rs7412 jointly define APOE epsilon haplotypes (e2/e3/e4).",
     "T/T: e2/e2 — increased risk of Type III hyperlipoproteinemia, paradoxically lower AD risk.",
     "C/T: 1 e2 allele — generally favorable for AD/lipids unless paired with e4.",
     "C/C: no e2 — haplotype is e3 or e4 depending on rs429358."),
    # ----- MTHFR / one-carbon metabolism -----
    ("rs1801133", "MTHFR", "C677T (folate metabolism)", "1", 11856378, "1", 11796321, "A", "G",
     "MTHFR enzyme activity. cDNA C->T = forward genome G->A.",
     "A/A: ~70% reduced MTHFR activity, elevated homocysteine; consider methylated folate (5-MTHF).",
     "G/A: ~30% reduced activity, mild homocysteine elevation; methylated folate may help.",
     "G/G: full MTHFR activity — no special supplementation needed."),
    ("rs1801131", "MTHFR", "A1298C (folate metabolism)", "1", 11854476, "1", 11794419, "G", "T",
     "Second common MTHFR variant, milder effect than C677T.",
     "G/G: ~40% reduced activity. Compound with C677T worsens.",
     "T/G: mild reduction.",
     "T/T: full activity at this site."),
    # ----- B12 (FUT2 secretor status) -----
    ("rs601338", "FUT2", "Secretor status / B12", "19", 49206674, "19", 48703417, "A", "G",
     "FUT2 W143X. Non-secretors lack ABO antigens in mucus and tend to have HIGHER serum B12 + altered gut microbiota.",
     "A/A: non-secretor — expect higher serum B12, lower Bifidobacterium, lower norovirus susceptibility.",
     "G/A: secretor (heterozygote, normal expression).",
     "G/G: secretor — typical B12 levels (occasionally lower)."),
    # ----- Vitamin D -----
    ("rs2282679", "GC", "Vitamin D binding protein", "4", 72608383, "4", 72742566, "G", "T",
     "GC encodes vitamin D binding protein. G allele lowers 25(OH)D.",
     "G/G: notably lower circulating vitamin D — likely needs higher dietary/sup intake to maintain 25(OH)D.",
     "T/G: modestly lower vitamin D.",
     "T/T: typical vitamin D levels."),
    ("rs2228570", "VDR", "VDR FokI", "12", 48272895, "12", 47879112, "T", "A",
     "VDR receptor functionality. NOTE: dbSNP REF=A on forward strand; the 'F' (functional) allele is C, 'f' is T.",
     "T/T (ff): less active receptor — slightly lower bone density and altered immune response.",
     "A/T (Ff): intermediate.",
     "A/A (FF): full receptor activity."),
    # ----- Iron / hemochromatosis -----
    ("rs1800562", "HFE", "C282Y (hereditary hemochromatosis)", "6", 26093141, "6", 26092913, "A", "G",
     "Most common cause of HFE-related iron overload.",
     "A/A: classical hemochromatosis homozygous — high penetrance, monitor ferritin/transferrin annually.",
     "G/A: heterozygous carrier — slight iron-overload risk; monitor if symptoms.",
     "G/G: no C282Y."),
    ("rs1799945", "HFE", "H63D (hereditary hemochromatosis)", "6", 26091179, "6", 26090951, "G", "C",
     "Second HFE variant; mild iron-overload risk especially compound with C282Y.",
     "G/G: H63D homozygous — usually mild iron overload.",
     "C/G: heterozygous H63D — mild risk; check C282Y status (rs1800562).",
     "C/C: no H63D."),
    # ----- Lactase persistence -----
    ("rs4988235", "MCM6", "Adult lactase persistence", "2", 136608646, "2", 135851076, "A", "G",
     "Single SNP determines lactase persistence in Europeans. dbSNP forward strand A = lactase persistent (corresponds to 'T' in literature).",
     "A/A: fully lactase persistent — can digest lactose lifelong.",
     "G/A: lactase persistent — can digest lactose lifelong.",
     "G/G: lactase NON-persistent — likely lactose-intolerant after early childhood; common in East Asians."),
    # ----- Alcohol metabolism -----
    ("rs671",     "ALDH2", "ALDH2*2 (alcohol/acetaldehyde)", "12", 112241766, "12", 111803962, "A", "G",
     "ALDH2*2 (Glu487Lys) markedly impairs acetaldehyde clearance — flushing reaction; common in East Asians.",
     "A/A: severely deficient ALDH2 — strong alcohol intolerance, very high esophageal cancer risk if drinking; AVOID alcohol.",
     "G/A: ALDH2 heterozygous — flush response, ~6-10x esophageal/head-and-neck cancer risk if drinking heavily; LIMIT alcohol significantly.",
     "G/G: normal ALDH2."),
    ("rs1229984", "ADH1B", "ADH1B*2 (fast EtOH metabolism)", "4", 100239319, "4", 100318162, "A", "G",
     "ADH1B*2 (Arg48His). NOTE: dbSNP forward strand A allele = ADH1B*2 fast metabolizer.",
     "A/A: very fast ethanol -> acetaldehyde — protective against alcoholism, heightened sensitivity. Common in East Asians.",
     "G/A: fast metabolizer, partial protection.",
     "G/G: normal/slow ADH1B."),
    # ----- Caffeine -----
    ("rs762551",  "CYP1A2", "Caffeine metabolism rate", "15", 75041917, "15", 74749247, "C", "A",
     "CYP1A2 *1F (slow) vs *1A (fast). The 'C' allele on forward strand = *1F (slow) inducer.",
     "C/C: slow metabolizer — high coffee intake associated with elevated MI risk and worse sleep.",
     "A/C: intermediate.",
     "A/A: rapid metabolizer — high coffee intake protective vs MI in some studies."),
    # ----- Vitamin A from beta-carotene -----
    ("rs7501331", "BCMO1", "Beta-carotene → retinol conversion", "16", 81314496, "16", 81280892, "T", "C",
     "BCMO1 catalyzes β-carotene → retinal conversion.",
     "T/T: ~60% reduced conversion — supplement preformed vitamin A (retinol) if intake of leafy greens/carrots is your main source.",
     "C/T: ~30% reduced conversion.",
     "C/C: typical conversion."),
    # ----- Omega-3 metabolism -----
    ("rs174537", "FADS1", "Omega-3 desaturase", "11", 61552680, "11", 61784965, "T", "G",
     "T allele lowers FADS1 activity → poorer ALA->EPA/DHA conversion.",
     "T/T: low FADS1 — direct EPA/DHA (fish or supplement) recommended; ALA-only (flaxseed) is poorly converted.",
     "G/T: intermediate.",
     "G/G: high FADS1 — efficient conversion of plant ALA to EPA/DHA."),
    # ----- Salt sensitivity -----
    ("rs699",     "AGT", "Angiotensinogen M235T (salt-sensitive BP)", "1", 230845794, "1", 230710048, "G", "A",
     "AGT M235T. G allele is the 235-Thr variant.",
     "G/G: highest angiotensinogen; greatest salt sensitivity / hypertension risk.",
     "A/G: intermediate.",
     "A/A: lower angiotensinogen, less salt-sensitive."),
    # ----- Type 2 diabetes -----
    ("rs7903146", "TCF7L2", "T2D risk (strongest common variant)", "10", 114758349, "10", 112998590, "T", "C",
     "Strongest common SNP for T2D (~OR 1.4 per allele).",
     "T/T: ~2x baseline T2D risk — earlier glucose/HbA1c screening (annually from 30s).",
     "C/T: ~1.4x baseline T2D risk — moderate.",
     "C/C: baseline."),
    # ----- Obesity / BMI -----
    ("rs9939609", "FTO", "Obesity / BMI", "16", 53820527, "16", 53786615, "A", "T",
     "FTO intron variant; ~+1 kg per A allele on average.",
     "A/A: ~+2 kg trend, slightly higher hunger/satiety hormone effect — exercise blunts the effect.",
     "T/A: ~+1 kg trend.",
     "T/T: no effect from this locus."),
    # ----- Athletic / muscle -----
    ("rs1815739", "ACTN3", "R577X (sprint vs endurance)", "11", 66328095, "11", 66560624, "T", "C",
     "ACTN3 protein in fast-twitch fibers. T allele = X (premature stop, no α-actinin-3).",
     "T/T (XX): no α-actinin-3 — over-represented in elite endurance athletes, under-represented in elite sprinters.",
     "C/T (RX): heterozygous — common, mixed phenotype.",
     "C/C (RR): full ACTN3 — over-represented in elite power/sprint athletes."),
    # ----- Sleep / circadian -----
    ("rs1801260", "CLOCK", "Circadian preference", "4", 56301369, "4", 55435636, "G", "A",
     "CLOCK 3'UTR variant.",
     "G/G: stronger 'evening' chronotype, slightly higher BMI tendency.",
     "A/G: intermediate.",
     "A/A: 'morning' chronotype tendency."),
    ("rs5751876", "ADORA2A", "Caffeine-induced anxiety", "22", 24837301, "22", 24481417, "T", "C",
     "ADORA2A — adenosine A2A receptor; T allele linked to caffeine-induced anxiety/insomnia.",
     "T/T: pronounced caffeine-induced anxiety + sleep disruption.",
     "C/T: moderate sensitivity.",
     "C/C: typical caffeine response (no extra anxiety)."),
    # ----- Drug & dietary metabolism -----
    ("rs1799930", "NAT2", "NAT2*6 acetylator (slow)", "8", 18258103, "8", 18400586, "A", "G",
     "NAT2*6A; A allele = slow acetylator (also see rs1041983, rs1801280).",
     "A/A: slow acetylator — affects isoniazid, sulfa, hydralazine, dietary heterocyclic amines.",
     "G/A: intermediate.",
     "G/G: rapid acetylator (at this locus only — NAT2 status needs ≥3 SNPs)."),
    # ----- Skin / sun -----
    ("rs1805007", "MC1R", "R151C (red hair, sun sensitivity)", "16", 89986117, "T", 89919709, "T", "C",
     "MC1R 'R' loss-of-function variant — fair skin, freckling, melanoma risk ~2x per allele.",
     "T/T: very fair skin, almost certainly red/strawberry-blonde hair, ~4x melanoma risk; aggressive sun protection + dermatology screening.",
     "C/T: ~2x melanoma risk; sun protection important.",
     "C/C: no MC1R R151C — combine with rs1805008 (R160W), rs1805009 (D294H) for full picture."),
    # ----- X-linked: G6PD -----
    ("rs1050828", "G6PD", "G6PD A- (Med./African deficiency)", "X", 153764217, "X", 154535443, "T", "C",
     "G6PD enzymatic deficiency — favism, drug-induced hemolysis (primaquine, sulfa, dapsone, naphthalene).",
     "T/T (or T in males): G6PD deficient — strict avoidance of triggering foods/drugs.",
     "C/T (females only): heterozygous carrier — variable expression, may have mild deficiency.",
     "C/C (or C in males): normal G6PD."),
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


def gt_to_alleles(gt: str, ref: str, alt: str) -> str:
    if not gt:
        return ""
    sep = "|" if "|" in gt else "/"
    parts = gt.replace("|", "/").split("/")
    bases = []
    for p in parts:
        if p == "0":
            bases.append(ref)
        elif p == "1":
            bases.append(alt if alt != "." else ref)
        elif p == ".":
            bases.append(".")
        else:
            bases.append(p)
    return sep.join(bases)


def count_trait(alleles_str: str, trait_allele: str) -> int:
    if not alleles_str or alleles_str == ".":
        return -1
    parts = alleles_str.replace("|", "/").split("/")
    return sum(1 for a in parts if a == trait_allele)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vcf", required=True)
    ap.add_argument("--build", choices=["GRCh37", "GRCh38"], default="GRCh37")
    ap.add_argument("--out", default="output/raw_findings/nutrition_traits.tsv")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    if args.build == "GRCh37":
        positions = {(p[3], p[4]) for p in PANEL}
    else:
        positions = {(p[5], p[6]) for p in PANEL}

    sys.stderr.write(f"Looking up {len(PANEL)} SNPs in {args.vcf} ...\n")
    found = parse_vcf_lookup(args.vcf, positions)
    sys.stderr.write(f"  matched {len(found)}/{len(PANEL)} positions\n")

    with open(args.out, "w") as f:
        f.write(
            "rsid\tgene\ttrait\tchrom\tpos\tref\talt\t"
            "user_genotype\ttrait_allele\tn_trait_alleles\t"
            "interpretation\tdescription\n"
        )
        for (rsid, gene, trait, c37, p37, c38, p38, trait_a, ref_a,
             desc, mean_hom_trait, mean_het, mean_hom_ref) in PANEL:
            chrom = c37 if args.build == "GRCh37" else c38
            pos = p37 if args.build == "GRCh37" else p38
            row = found.get((chrom, pos))
            if not row:
                f.write(
                    f"{rsid}\t{gene}\t{trait}\t{chrom}\t{pos}\t.\t.\t"
                    f"(not_typed)\t{trait_a}\t-1\t"
                    f"(not on chip — will fill in after imputation)\t{desc}\n"
                )
                continue
            ref, alt, gt = row
            alleles = gt_to_alleles(gt, ref, alt)
            n = count_trait(alleles, trait_a)
            if n == 2:
                interp = mean_hom_trait
            elif n == 1:
                interp = mean_het
            elif n == 0:
                interp = mean_hom_ref
            else:
                interp = "(genotype unavailable)"
            f.write(
                f"{rsid}\t{gene}\t{trait}\t{chrom}\t{pos}\t{ref}\t{alt}\t"
                f"{alleles}\t{trait_a}\t{n}\t{interp}\t{desc}\n"
            )

    sys.stderr.write(f"Wrote {args.out}\n")


if __name__ == "__main__":
    main()
