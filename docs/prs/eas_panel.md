# EAS-validated PGS panel (for Han Chinese), tiered by risk priority

All IDs verified live against the PGS Catalog REST API. Most are GRCh37 → pgsc_calc lifts over to our GRCh38 automatically.

## Tier 1 — cardiometabolic (ancestry calibration matters most)
| Trait | EAS score(s) | Why | Variants / build |
|---|---|---|---|
| Type 2 diabetes | **PGS005365**, PGS003353 | PGS005365 is EAS at *every* stage; GWAS includes **China Kadoorie Biobank** (Han Chinese) + Biobank Japan | ~1.0M / GRCh37 |
| Coronary artery disease | **PGS004941**, PGS005143 | PGS004941 *validated in CKB* (Han Chinese); PGS005143 Biobank Japan | 3.7M / 943k, GRCh37 |
| Ischemic stroke | **PGS002725**, PGS004942 | PGS002725 EAS 100% dev, ~6M variants | 6M / GRCh37 |
| Atrial fibrillation | PGS002814, PGS005313 | best available EAS-leaning; AFib EAS scores are thinner | 4.5k / 1.3M |

## Tier 2 — EAS-relevant cancers
| Trait | EAS score(s) | Variants/build |
|---|---|---|
| Gastric cancer | **PGS005161** (EAS 100%) | 12 / GRCh37 (sparse GRS) |
| Colorectal | PGS005402, PGS005162 | 121 / 11k |
| Lung | PGS005163, PGS005169 | 42 / 25 |
| Prostate | PGS005167, PGS004599 | 157 / 102 |

## Tier 3 — other high-impact
| Trait | EAS score(s) | Notes |
|---|---|---|
| Hypertension | **PGS005144** (BBJ), PGS005153 | 908k / GRCh37 |
| Chronic kidney disease | — | **No EAS-developed score in the catalog** → stays European-derived |
| Gout / urate | PGS002290, PGS000755 | small GRS |
| Glaucoma | PGS001792, PGS004944 | medium confidence (multi-ancestry) |

## Run list
**EAS additions (18 high-confidence):**
PGS005365,PGS003353,PGS004941,PGS005143,PGS002725,PGS004942,PGS002814,PGS005161,PGS005402,PGS005162,PGS005163,PGS005169,PGS005167,PGS004599,PGS005144,PGS005153,PGS002290,PGS000755

**Existing 10 (European-derived, keep for side-by-side comparison):**
PGS000018,PGS000014,PGS000016,PGS000039,PGS000334,PGS000049,PGS000338,PGS000041,PGS000302,PGS000061

Running both lets us see how much ancestry calibration moves the percentile for the overlapping traits (T2D, CAD, stroke, AFib).
