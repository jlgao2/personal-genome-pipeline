# Reading your PRS: European- vs East-Asian-derived scores

> Research-grade, not clinical. PRS give *relative* genetic risk; they are one input, not a diagnosis.

## The one-sentence version
A polygenic score is only as trustworthy as the population it was built and calibrated in. You are
**Han Chinese (East Asian genetic ancestry)**, so an **EAS-developed score's percentile is meaningful for
you**, while a **European-derived score's percentile is, at best, directional** — the ranking partly
carries over, the exact number does not.

## Why ancestry (not "race") is what matters
"Race" is a social category; what a PRS actually depends on is **genetic ancestry** — the allele
frequencies and linkage patterns of your genome. They usually line up (you're Han Chinese → East Asian
ancestry), but the precise input is ancestry, which `pgsc_calc` *measures* directly by projecting your
genome onto a global reference panel (HGDP + 1000 Genomes) via PCA. Three concrete reasons a
European-trained score misfires in an East Asian genome:

1. **Allele frequencies differ.** A risk variant common in Europeans can be rare or absent in East
   Asians, so it shifts the score distribution differently — your percentile is read against the wrong ruler.
2. **Linkage disequilibrium differs.** GWAS rarely find the causal variant; they find a nearby tag. The
   tag that marks the causal variant in Europeans may not mark it in East Asians, so the effect attenuates.
3. **Effect sizes don't fully transfer.** Gene–environment interaction, allelic heterogeneity, and
   differing baseline exposures mean European effect estimates are only partly portable.

**Net effect:** cross-ancestry PRS typically lose roughly **half to two-thirds of their predictive
accuracy** going European → East Asian. The high-PRS-tends-higher-risk ordering survives; the calibrated
percentile and absolute odds do not.

## What the EUR-vs-EAS comparison in your results shows
For the overlapping cardiometabolic traits (T2D, CAD, stroke, AFib) we score **both** a European-derived
PGS and an EAS-developed PGS. `pgsc_calc`'s ancestry step places you against an **ancestry-matched
reference distribution for both**, so the comparison isolates one thing: *how much the choice of score
matters once calibration is handled fairly.* Expect the EAS-derived score to be the more reliable number;
where they disagree a lot, that gap is the cost of using a transferred European score.

## Absolute vs relative risk — the baseline also differs by population
Your PRS percentile is **relative** risk layered on top of a **population baseline prevalence**, and those
baselines differ markedly between Europeans and East Asians. So even a perfectly calibrated percentile must
be read against the *East Asian* baseline, not the European one. Examples where this matters for you:

| Trait | East-Asian baseline vs European | Implication |
|---|---|---|
| Gastric, esophageal (squamous), nasopharyngeal, liver cancer | **Much higher** in East Asians | A "moderate" EAS percentile can still mean meaningful absolute risk; European scores barely exist here |
| Type 2 diabetes | Onset at **lower BMI** in East Asians | EAS-calibrated metabolic scores matter; don't read against European BMI/risk thresholds |
| Coronary artery disease, atrial fibrillation | Generally **lower** baseline in East Asians | Same percentile → lower absolute event rate than the European figure would suggest |

## How to read each row of your panel
- **EAS-developed score (e.g. T2D `PGS005365`, CAD `PGS004941`, NPC `PGS002291`):** trust the percentile —
  it's ancestry-matched. This is the number to act on (discuss-with-doctor).
- **European-derived score (the original 10):** treat the percentile as a rough direction only. Where an
  EAS score exists for the same trait, **prefer the EAS one**.
- **Either way:** convert percentile → absolute risk using **East-Asian** baseline rates, and remember PRS
  captures only common-variant genetic risk — not rare monogenic variants (those are in your ClinVar/ACMG
  findings), lifestyle, or environment.

## Bottom line
Same genome, two rulers. The EAS ruler is the right one for you; the European ruler is borrowed and bent.
The panel reports both so you can see where borrowing a European score would have misled you — which is
exactly why we curated ~35 ancestry-matched East-Asian scores in the first place.
