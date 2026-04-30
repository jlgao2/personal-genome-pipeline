#!/usr/bin/env python3
"""
Run all curated panels (nutrition, PGx, extra traits) against the imputed GRCh38 VCF
using rsID-based lookup. Imputed VCFs from TOPMed include rsIDs in the ID column for
~99.9% of variants, so this is more reliable than hg38 position lookup.

Output: output/raw_findings/imputed_panels.tsv
"""
import argparse
import gzip
import os
import sys

# Combined panel — pulled from the original three scripts (07/08/09).
# Each entry: rsid, gene, category, trait_allele (dbSNP forward strand), description,
#             interpretation_homozygous_trait, interpretation_het, interpretation_homozygous_ref
PANEL = [
    # ===== NUTRITION =====
    ('rs429358', 'APOE', 'nutrition', 'C', 'APOE-e4 status (rs429358 + rs7412 jointly define ε haplotypes)',
     'C/C: e4/e4 homozygous — ~12-15× lifetime AD risk vs e3/e3, higher LDL.',
     'C/T: 1 e4 allele — ~3× AD risk vs e3/e3.',
     'T/T: no e4 — combine with rs7412 result for full APOE haplotype.'),
    ('rs7412', 'APOE', 'nutrition', 'T', 'APOE-e2 status',
     'T/T: e2/e2 — increased risk of Type III hyperlipoproteinemia, paradoxically lower AD risk.',
     'C/T: 1 e2 allele — generally favourable for AD/lipids unless paired with e4.',
     'C/C: no e2 — haplotype is e3 or e4 depending on rs429358.'),
    ('rs1801133', 'MTHFR', 'nutrition', 'A', 'MTHFR C677T (folate metabolism, forward genome G→A = cDNA C→T)',
     'A/A: ~70% reduced MTHFR activity, elevated homocysteine; methylated folate (5-MTHF).',
     'G/A: ~30% reduced activity, mild homocysteine elevation.',
     'G/G: full MTHFR activity.'),
    ('rs1801131', 'MTHFR', 'nutrition', 'G', 'MTHFR A1298C',
     'G/G: ~40% reduced activity at this site.',
     'T/G: mild reduction.',
     'T/T: full activity at this site.'),
    ('rs601338', 'FUT2', 'nutrition', 'A', 'FUT2 W143X — secretor status; non-secretors have higher serum B12',
     'A/A: non-secretor — higher serum B12, altered gut microbiome.',
     'G/A: secretor heterozygote.',
     'G/G: secretor.'),
    ('rs2282679', 'GC', 'nutrition', 'G', 'Vitamin D binding protein (G allele lowers 25-OH-D)',
     'G/G: notably lower vitamin D — likely needs higher dietary/supp intake.',
     'T/G: modestly lower vitamin D.',
     'T/T: typical vitamin D levels.'),
    ('rs2228570', 'VDR', 'nutrition', 'T', 'VDR FokI — T = "f" (less active receptor)',
     'T/T (ff): less active receptor.',
     'A/T (Ff): intermediate.',
     'A/A (FF): full receptor activity.'),
    ('rs1800562', 'HFE', 'nutrition', 'A', 'HFE C282Y — hemochromatosis',
     'A/A: classical hemochromatosis homozygous — monitor ferritin/transferrin annually.',
     'G/A: heterozygous carrier — slight risk.',
     'G/G: no C282Y.'),
    ('rs1799945', 'HFE', 'nutrition', 'G', 'HFE H63D',
     'G/G: H63D homozygous.',
     'C/G: heterozygous.',
     'C/C: no H63D.'),
    ('rs4988235', 'MCM6/LCT', 'nutrition', 'A', 'Lactase persistence (forward A = persistent)',
     'A/A: lactase persistent.',
     'G/A: lactase persistent.',
     'G/G: lactase NON-persistent — likely lactose-intolerant.'),
    ('rs671', 'ALDH2', 'nutrition', 'A', 'ALDH2*2 — alcohol-flush + cancer multiplier',
     'A/A: severely deficient ALDH2 — AVOID alcohol.',
     'G/A: heterozygous — flush, 6-10× esophageal cancer risk if heavy drinking.',
     'G/G: normal ALDH2.'),
    ('rs1229984', 'ADH1B', 'nutrition', 'A', 'ADH1B*2 (Arg48His) — fast ethanol metabolizer',
     'A/A: very fast ethanol → acetaldehyde — protective against alcoholism.',
     'G/A: fast metabolizer.',
     'G/G: normal/slow.'),
    ('rs762551', 'CYP1A2', 'nutrition', 'C', 'CYP1A2 *1F (slow) — C is the *1F allele',
     'C/C: slow caffeine metabolizer.',
     'A/C: intermediate.',
     'A/A: rapid metabolizer (*1A/*1A).'),
    ('rs7501331', 'BCMO1', 'nutrition', 'T', 'β-carotene → retinol conversion',
     'T/T: ~60% reduced conversion — supplement preformed vitamin A.',
     'C/T: ~30% reduced.',
     'C/C: typical.'),
    ('rs174537', 'FADS1', 'nutrition', 'T', 'FADS1 desaturase — T lowers ALA→EPA/DHA',
     'T/T: low FADS1 — direct EPA/DHA recommended.',
     'G/T: intermediate.',
     'G/G: high FADS1.'),
    ('rs699', 'AGT', 'nutrition', 'G', 'AGT M235T — salt sensitivity',
     'G/G: highest angiotensinogen, most salt-sensitive.',
     'A/G: intermediate.',
     'A/A: less salt-sensitive.'),
    ('rs7903146', 'TCF7L2', 'nutrition', 'T', 'Strongest common T2D variant',
     'T/T: ~2× T2D risk — earlier glucose screening.',
     'C/T: ~1.4× T2D risk.',
     'C/C: baseline.'),
    ('rs9939609', 'FTO', 'nutrition', 'A', 'FTO obesity allele',
     'A/A: ~+2 kg trend.',
     'T/A: ~+1 kg trend.',
     'T/T: no effect.'),

    # ===== PHARMACOGENOMICS =====
    ('rs9923231', 'VKORC1', 'pgx', 'T', 'VKORC1 -1639G>A — high warfarin sensitivity',
     'T/T (=A/A on cDNA): start at ~50% standard warfarin dose.',
     'C/T: intermediate sensitivity, ~25% lower starting dose.',
     'C/C: typical warfarin sensitivity.'),
    ('rs1799853', 'CYP2C9', 'pgx', 'T', 'CYP2C9 *2 (R144C)',
     'T/T: CYP2C9 *2/*2 — markedly reduced warfarin/NSAID metabolism.',
     'C/T: *1/*2 heterozygote.',
     'C/C: no *2.'),
    ('rs1057910', 'CYP2C9', 'pgx', 'C', 'CYP2C9 *3 (I359L)',
     'C/C: *3/*3 severely reduced metabolism.',
     'A/C: *1/*3 heterozygote.',
     'A/A: no *3.'),
    ('rs4244285', 'CYP2C19', 'pgx', 'A', 'CYP2C19 *2 — loss of function',
     'A/A: *2/*2 POOR metabolizer — clopidogrel ineffective; alternate antiplatelet needed.',
     'G/A: *1/*2 intermediate.',
     'G/G: no *2.'),
    ('rs4986893', 'CYP2C19', 'pgx', 'A', 'CYP2C19 *3',
     'A/A: *3/*3 (rare).',
     'G/A: *1/*3 intermediate.',
     'G/G: no *3.'),
    ('rs12248560', 'CYP2C19', 'pgx', 'T', 'CYP2C19 *17 — gain of function',
     'T/T: *17/*17 RAPID metabolizer.',
     'C/T: *1/*17.',
     'C/C: no *17.'),
    ('rs1800462', 'TPMT', 'pgx', 'G', 'TPMT *2 (A80P)',
     'G/G: *2/*2 — DO NOT use thiopurines.',
     'C/G: heterozygous *2.',
     'C/C: no *2.'),
    ('rs1142345', 'TPMT', 'pgx', 'C', 'TPMT *3C (Y240C)',
     'C/C: *3C/*3C — DO NOT use thiopurines.',
     'T/C: heterozygous *3C.',
     'T/T: no *3C.'),
    ('rs1800460', 'TPMT', 'pgx', 'T', 'TPMT *3B (A154T)',
     'T/T: *3B/*3B — DO NOT use thiopurines.',
     'C/T: heterozygous *3B.',
     'C/C: no *3B.'),
    ('rs3918290', 'DPYD', 'pgx', 'T', 'DPYD *2A — strong toxicity with 5-FU/capecitabine',
     'T/T: *2A/*2A — DO NOT use 5-FU/capecitabine.',
     'C/T: heterozygous — start at 50% dose.',
     'C/C: no *2A.'),
    ('rs55886062', 'DPYD', 'pgx', 'C', 'DPYD *13',
     'C/C: *13/*13 — DO NOT use 5-FU.',
     'A/C: heterozygous — 50% dose.',
     'A/A: no *13.'),
    ('rs4149056', 'SLCO1B1', 'pgx', 'C', 'SLCO1B1 *5 (V174A) — simvastatin myopathy',
     'C/C: *5/*5 — avoid simvastatin or ≤20mg/d.',
     'T/C: heterozygous — ≤40mg/d.',
     'T/T: typical SLCO1B1.'),
    ('rs12979860', 'IFNL3', 'pgx', 'C', 'HCV interferon response',
     'C/C: best HCV treatment response.',
     'C/T: intermediate.',
     'T/T: lower response.'),
    ('rs2395029', 'HCP5', 'pgx', 'G', 'HLA-B*57:01 tag — abacavir',
     'G/G: HLA-B*57:01 likely homozygous — DO NOT receive abacavir.',
     'T/G: HLA-B*57:01 carrier — DO NOT receive abacavir.',
     'T/T: not a *57:01 carrier.'),
    ('rs6025', 'F5', 'pgx', 'T', 'Factor V Leiden',
     'T/T: F5 Leiden homozygous — markedly elevated VTE risk.',
     'C/T: F5 Leiden heterozygous — ~5-7× VTE risk.',
     'C/C: no F5 Leiden.'),
    ('rs1799963', 'F2', 'pgx', 'A', 'Prothrombin G20210A',
     'A/A: prothrombin homozygous (rare).',
     'G/A: heterozygous — ~2-3× VTE risk.',
     'G/G: no prothrombin variant.'),
    ('rs1050828', 'G6PD', 'pgx', 'T', 'G6PD A- (X-linked, affects males directly)',
     'T/T: G6PD deficient.',
     'C/T (females): heterozygous, mild.',
     'C/C: normal G6PD.'),
    ('rs116855232', 'NUDT15', 'pgx', 'T', 'NUDT15 *3 — thiopurine toxicity (East Asian)',
     'T/T: *3/*3 — DO NOT use thiopurines.',
     'C/T: heterozygous — reduced dose.',
     'C/C: no *3.'),
    ('rs1799971', 'OPRM1', 'pgx', 'G', 'Mu-opioid receptor A118G',
     'G/G: substantially reduced opioid analgesic response.',
     'A/G: moderately reduced opioid response.',
     'A/A: typical opioid response.'),
    ('rs1799930', 'NAT2', 'pgx', 'A', 'NAT2*6A',
     'A/A: slow acetylator at this locus.',
     'G/A: intermediate.',
     'G/G: rapid at this locus (full status needs ≥3 SNPs).'),

    # ===== EXTRA TRAITS / GWAS =====
    ('rs10757278', '9p21.3', 'extra', 'G', '9p21.3 / CDKN2B-AS1 — strongest common CAD locus',
     'G/G: ~1.5-2.0× early-MI risk.',
     'A/G: ~1.25× risk.',
     'A/A: protective.'),
    ('rs1333049', '9p21.3', 'extra', 'C', '9p21 — in LD with rs10757278',
     'C/C: tags the same risk haplotype.',
     'G/C: heterozygote.',
     'G/G: protective.'),
    ('rs6265', 'BDNF', 'extra', 'T', 'Val66Met',
     'T/T (Met/Met): reduced activity-dependent BDNF.',
     'C/T (Val/Met): heterozygous.',
     'C/C (Val/Val): standard.'),
    ('rs2802292', 'FOXO3', 'extra', 'G', 'Longevity allele',
     'G/G: ~2× odds of reaching 95+.',
     'T/G: ~1.4× longevity odds.',
     'T/T: baseline.'),
    ('rs1801253', 'ADRB1', 'extra', 'C', 'β1 receptor Arg389Gly',
     'C/C (Arg/Arg): best β1-blocker response.',
     'G/C (Arg/Gly): intermediate.',
     'G/G (Gly/Gly): least response.'),
    ('rs1042713', 'ADRB2', 'extra', 'G', 'β2 receptor Arg16Gly',
     'G/G (Gly/Gly): improved albuterol response, tachyphylaxis with chronic LABA.',
     'A/G: intermediate.',
     'A/A (Arg/Arg): worse chronic β-agonist response.'),
    ('rs4680', 'COMT', 'extra', 'A', 'Val158Met',
     'A/A (Met/Met): low COMT — "worrier" phenotype.',
     'G/A: intermediate.',
     'G/G (Val/Val): high COMT — "warrior".'),
    ('rs53576', 'OXTR', 'extra', 'A', 'Oxytocin receptor',
     'A/A: associated with lower empathic accuracy in some studies.',
     'A/G: intermediate.',
     'G/G: "high empathy" allele.'),
    ('rs1042522', 'TP53', 'extra', 'C', 'Pro72Arg',
     'C/C (Arg/Arg): more efficient apoptosis.',
     'G/C (Pro/Arg): heterozygous.',
     'G/G (Pro/Pro): more cell-cycle arrest.'),
    ('rs1051730', 'CHRNA3', 'extra', 'A', 'Cigarettes/day in smokers',
     'A/A: ~+2 cigarettes/day if smoking.',
     'G/A: intermediate.',
     'G/G: lower nicotine dependence allele.'),
    ('rs6983267', '8q24', 'extra', 'G', 'Colorectal/prostate cancer locus',
     'G/G: ~1.4× colorectal, ~1.3× prostate cancer risk.',
     'T/G: ~1.2× risk.',
     'T/T: protective.'),
    ('rs5882', 'CETP', 'extra', 'G', 'Val405Ile (HDL/longevity)',
     'G/G (Ile/Ile): ~+5 mg/dL HDL.',
     'A/G (Val/Ile): intermediate.',
     'A/A (Val/Val): typical HDL.'),
    ('rs1815739', 'ACTN3', 'extra', 'T', 'R577X (sprint vs endurance)',
     'T/T (XX): no α-actinin-3 — endurance phenotype.',
     'C/T (RX): heterozygous.',
     'C/C (RR): full ACTN3 — sprint/power.'),
    ('rs1801260', 'CLOCK', 'extra', 'G', 'Circadian preference',
     'G/G: stronger eveningness.',
     'A/G: intermediate.',
     'A/A: morning chronotype.'),
    ('rs5751876', 'ADORA2A', 'extra', 'T', 'Caffeine-induced anxiety',
     'T/T: pronounced caffeine-induced anxiety.',
     'C/T: moderate.',
     'C/C: typical caffeine response.'),
    ('rs1805007', 'MC1R', 'extra', 'T', 'R151C — red hair, melanoma risk',
     'T/T: very fair skin, ~4× melanoma risk.',
     'C/T: ~2× melanoma risk.',
     'C/C: no R151C.'),
    # Connective tissue
    ('rs12722', 'COL5A1', 'extra', 'T', 'Achilles tendon / flexibility',
     'T/T: reduced flexibility, higher Achilles tendinopathy risk.',
     'C/T: one risk allele.',
     'C/C: protective.'),
    ('rs1800012', 'COL1A1', 'extra', 'T', 'Sp1 binding site — bone density / osteoporosis risk',
     'T/T: reduced bone density, higher fracture risk.',
     'C/T: heterozygous.',
     'C/C: typical bone density.'),
    ('rs1800255', 'COL3A1', 'extra', 'A', 'COL3A1 +2092 — joint stability',
     'A/A: connective tissue laxity tendency.',
     'A/G: heterozygous.',
     'G/G: standard.'),
    ('rs2070744', 'NOS3', 'extra', 'T', '−786 NOS3 — endothelial NO',
     'T/T: reduced NO; mild tendinopathy + CV signal.',
     'C/T: heterozygous.',
     'C/C: typical.'),
    # Caffeine extras
    ('rs2472297', 'AHR', 'extra', 'T', 'AHR/CYP1A2 region (coffee intake GWAS)',
     'T/T: higher coffee intake allele.',
     'C/T: intermediate.',
     'C/C: lower-coffee-intake genotype.'),
    ('rs1057868', 'POR', 'pgx', 'T', 'POR*28 — affects CYP3A activity',
     'T/T: POR*28/*28 — altered CYP3A.',
     'C/T: heterozygous.',
     'C/C: typical.'),
]


def parse_vcf_by_rsid(path, rsids):
    """Single pass through VCF, extract any variant whose ID matches one of rsids."""
    open_fn = gzip.open if path.endswith('.gz') else open
    out = {}
    rsids_set = set(rsids)
    with open_fn(path, 'rt') as f:
        sample_idx = None
        for line in f:
            if line.startswith('##'):
                continue
            if line.startswith('#CHROM'):
                cols = line.rstrip().split('\t')
                if len(cols) > 9:
                    sample_idx = 9
                continue
            cols = line.rstrip().split('\t')
            if len(cols) < 8:
                continue
            rsid = cols[2]
            if rsid not in rsids_set:
                continue
            chrom = cols[0]
            pos = cols[1]
            ref = cols[3]
            alt = cols[4]
            gt = ''
            if sample_idx and len(cols) > sample_idx:
                fmt = cols[8].split(':')
                vals = cols[sample_idx].split(':')
                if 'GT' in fmt:
                    gt = vals[fmt.index('GT')]
            out[rsid] = (chrom, pos, ref, alt, gt)
    return out


def gt_to_alleles(gt, ref, alt):
    if not gt:
        return ''
    parts = gt.replace('|', '/').split('/')
    sep = '|' if '|' in gt else '/'
    return sep.join(ref if p == '0' else (alt if alt != '.' else ref) if p == '1' else '.' for p in parts)


def count_allele(alleles, allele):
    if not alleles:
        return -1
    return sum(1 for a in alleles.replace('|', '/').split('/') if a == allele)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vcf', required=True)
    ap.add_argument('--out', default='output/raw_findings/imputed_panels.tsv')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    rsids = [p[0] for p in PANEL]
    sys.stderr.write(f'Looking up {len(rsids)} rsIDs in {args.vcf} ...\n')
    found = parse_vcf_by_rsid(args.vcf, rsids)
    sys.stderr.write(f'  matched {len(found)}/{len(rsids)} rsIDs\n')

    n_typed = 0
    n_carrier = 0  # at least 1 trait allele
    with open(args.out, 'w') as f:
        f.write('rsid\tgene\tcategory\tchrom\tpos\tref\talt\tuser_genotype\ttrait_allele\tn_trait\tinterpretation\tdescription\n')
        for (rsid, gene, cat, trait_a, desc, mh, mhe, mhr) in PANEL:
            row = found.get(rsid)
            if not row:
                f.write(f'{rsid}\t{gene}\t{cat}\t.\t.\t.\t.\t(not_imputed)\t{trait_a}\t-1\t(not in imputed VCF)\t{desc}\n')
                continue
            chrom, pos, ref, alt, gt = row
            alleles = gt_to_alleles(gt, ref, alt)
            n = count_allele(alleles, trait_a)
            if n == 2:
                interp = mh
            elif n == 1:
                interp = mhe
            elif n == 0:
                interp = mhr
            else:
                interp = '(genotype unavailable)'
            n_typed += 1
            if n >= 1:
                n_carrier += 1
            f.write(f'{rsid}\t{gene}\t{cat}\t{chrom}\t{pos}\t{ref}\t{alt}\t{alleles}\t{trait_a}\t{n}\t{interp}\t{desc}\n')

    sys.stderr.write(f'Typed: {n_typed}/{len(PANEL)}\n')
    sys.stderr.write(f'With ≥1 trait allele: {n_carrier}\n')
    sys.stderr.write(f'Wrote: {args.out}\n')


if __name__ == '__main__':
    main()
