#!/usr/bin/env python3
"""
Annotate the genome VCF against ClinVar and ACMG SF v3.2 actionable gene list.

Outputs:
  output/raw_findings/clinvar_full.tsv      — every P/LP/CIP variant matched in user's VCF
  output/raw_findings/clinvar_acmg.tsv      — restricted to ACMG SF v3.2 genes
  output/raw_findings/clinvar_summary.md    — human-readable summary

Inputs:
  --vcf       user genotype VCF (post-imputation preferred, but works on raw chip too)
  --clinvar   ClinVar VCF (matching genome build)
  --build     "GRCh37" or "GRCh38"
"""
import argparse
import gzip
import sys
import os
from collections import defaultdict

# ACMG Secondary Findings list v3.2 (March 2023). 81 genes.
# Source: ACMG SF v3.2 (Miller et al. Genet Med 2023).
ACMG_SF_V32 = {
    # Hereditary cancer
    "APC", "BMPR1A", "BRCA1", "BRCA2", "BRIP1", "CDH1", "CHEK2", "DICER1",
    "EPCAM", "MAX", "MEN1", "MLH1", "MSH2", "MSH6", "MUTYH", "NF2", "PALB2",
    "PMS2", "PTEN", "RAD51C", "RAD51D", "RB1", "RET", "SDHAF2", "SDHB", "SDHC",
    "SDHD", "SMAD4", "STK11", "TMEM127", "TP53", "TSC1", "TSC2", "VHL", "WT1",
    "NTHL1",
    # Cardiovascular
    "ACTA2", "ACTC1", "APOB", "CASQ2", "COL3A1", "DES", "DSC2", "DSG2", "DSP",
    "FBN1", "FLNC", "GLA", "KCNH2", "KCNQ1", "LDLR", "LMNA", "MYBPC3", "MYH11",
    "MYH7", "MYL2", "MYL3", "PCSK9", "PKP2", "PRKAG2", "RBM20", "RYR2", "SCN5A",
    "SMAD3", "TGFBR1", "TGFBR2", "TMEM43", "TNNC1", "TNNI3", "TNNT2", "TPM1",
    "TRDN", "TTN", "TTR", "VHL",
    # Inborn errors of metabolism / other
    "ATP7B", "BTD", "GAA", "HFE", "HNF1A", "OTC",
    # Malignant hyperthermia
    "RYR1", "CACNA1S",
    # Misc additions in v3.2
    "ACVRL1", "ENG",
}

# ACOG-aligned expanded carrier panel (subset, ~30 highest-yield genes).
ACMG_CARRIER_PANEL = {
    "CFTR", "HBB", "HBA1", "HBA2", "HEXA", "HEXB", "SMN1", "GJB2", "DMD",
    "GBA", "ASPA", "BCKDHA", "BCKDHB", "DBT", "DLD", "MCOLN1", "ASS1",
    "FANCC", "BLM", "IKBKAP", "ELP1", "NEB", "GAA", "PMM2", "FMR1",
    "SLC26A4", "USH2A", "CYBB", "OTC", "G6PD", "F8", "F9", "MEFV",
    "PAH", "GALT", "PCDH15",
}


def parse_vcf_positions(path):
    """Return dict (chrom, pos) -> list of (ref, alt, gt) for each variant."""
    open_fn = gzip.open if path.endswith(".gz") else open
    out = defaultdict(list)
    with open_fn(path, "rt") as f:
        sample_idx = None
        for line in f:
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                # last column is sample
                cols = line.rstrip().split("\t")
                if len(cols) > 9:
                    sample_idx = 9
                continue
            cols = line.rstrip().split("\t")
            if len(cols) < 8:
                continue
            chrom, pos, _, ref, alt = cols[0], cols[1], cols[2], cols[3], cols[4]
            chrom = chrom.replace("chr", "")
            gt = ""
            if sample_idx and len(cols) > sample_idx:
                fmt = cols[8].split(":")
                vals = cols[sample_idx].split(":")
                if "GT" in fmt:
                    gt = vals[fmt.index("GT")]
            for a in alt.split(","):
                out[(chrom, int(pos))].append((ref, a, gt))
    return out


def parse_clinvar_info(info_str):
    """Pull CLNSIG, CLNDN, CLNREVSTAT, GENEINFO from a ClinVar INFO field."""
    fields = {}
    for kv in info_str.split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            fields[k] = v
    return {
        "CLNSIG": fields.get("CLNSIG", ""),
        "CLNDN": fields.get("CLNDN", "").replace("|", "; ").replace("_", " "),
        "CLNREVSTAT": fields.get("CLNREVSTAT", ""),
        "GENEINFO": fields.get("GENEINFO", "").split("|")[0].split(":")[0],
        "MC": fields.get("MC", ""),
        "ALLELEID": fields.get("ALLELEID", ""),
    }


def review_status_stars(rev):
    """Map ClinVar review status to star count."""
    rev = rev.lower()
    if "practice_guideline" in rev:
        return 4
    if "reviewed_by_expert_panel" in rev:
        return 3
    if "criteria_provided,_multiple_submitters,_no_conflicts" in rev:
        return 2
    if "criteria_provided,_conflicting_classifications" in rev:
        return 1
    if "criteria_provided,_single_submitter" in rev:
        return 1
    if "no_assertion_criteria_provided" in rev:
        return 0
    if "no_classification_for_the_individual_variant" in rev:
        return 0
    return 0


def is_pathogenic(clnsig: str) -> str:
    s = clnsig.lower()
    if "pathogenic/likely_pathogenic" in s or "pathogenic|likely_pathogenic" in s:
        return "Pathogenic/Likely_pathogenic"
    if "pathogenic" in s and "likely_pathogenic" not in s and "non-pathogenic" not in s:
        return "Pathogenic"
    if "likely_pathogenic" in s:
        return "Likely_pathogenic"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vcf", required=True)
    ap.add_argument("--clinvar", required=True)
    ap.add_argument("--build", choices=["GRCh37", "GRCh38"], required=True)
    ap.add_argument("--outdir", default="output/raw_findings")
    ap.add_argument("--min-stars", type=int, default=2)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    sys.stderr.write(f"Loading user VCF positions from {args.vcf} ...\n")
    user_vars = parse_vcf_positions(args.vcf)
    sys.stderr.write(f"  {len(user_vars):,} unique positions\n")

    full_path = os.path.join(args.outdir, "clinvar_full.tsv")
    acmg_path = os.path.join(args.outdir, "clinvar_acmg.tsv")
    carrier_path = os.path.join(args.outdir, "carrier_status.tsv")

    header = "chrom\tpos\tref\talt\trsid\tgene\tclnsig_class\tclnsig\tclndn\tclnrevstat\tstars\tuser_gt\tuser_zygosity\n"
    with open(full_path, "w") as f_full, open(acmg_path, "w") as f_acmg, open(carrier_path, "w") as f_carrier:
        f_full.write(header)
        f_acmg.write(header)
        f_carrier.write(header)

        n_clinvar = 0
        n_match = 0
        n_path = 0
        n_acmg = 0
        n_carrier = 0

        open_fn = gzip.open if args.clinvar.endswith(".gz") else open
        with open_fn(args.clinvar, "rt") as cv:
            for line in cv:
                if line.startswith("#"):
                    continue
                cols = line.rstrip().split("\t")
                if len(cols) < 8:
                    continue
                chrom, pos, rsid, ref, alt = cols[0], cols[1], cols[2], cols[3], cols[4]
                chrom = chrom.replace("chr", "")
                info = parse_clinvar_info(cols[7])
                n_clinvar += 1

                key = (chrom, int(pos))
                if key not in user_vars:
                    continue

                # Match REF/ALT against user variant
                for u_ref, u_alt, u_gt in user_vars[key]:
                    if u_ref != ref:
                        continue
                    if u_alt != alt:
                        continue
                    n_match += 1

                    cls = is_pathogenic(info["CLNSIG"])
                    if not cls:
                        continue
                    n_path += 1

                    stars = review_status_stars(info["CLNREVSTAT"])
                    if stars < args.min_stars:
                        continue

                    # Determine zygosity
                    zyg = "unknown"
                    if u_gt:
                        a = u_gt.replace("|", "/").split("/")
                        if len(a) == 2:
                            if a[0] == a[1]:
                                if a[0] == "0":
                                    zyg = "ref/ref"
                                else:
                                    zyg = "homozygous_alt"
                            else:
                                zyg = "heterozygous"

                    # Skip ref/ref calls — these are not findings
                    if zyg == "ref/ref":
                        continue

                    row = (
                        f"{chrom}\t{pos}\t{ref}\t{alt}\t{rsid}\t"
                        f"{info['GENEINFO']}\t{cls}\t{info['CLNSIG']}\t"
                        f"{info['CLNDN']}\t{info['CLNREVSTAT']}\t{stars}\t"
                        f"{u_gt}\t{zyg}\n"
                    )
                    f_full.write(row)

                    if info["GENEINFO"] in ACMG_SF_V32:
                        f_acmg.write(row)
                        n_acmg += 1
                    if info["GENEINFO"] in ACMG_CARRIER_PANEL:
                        f_carrier.write(row)
                        n_carrier += 1

                if n_clinvar % 500000 == 0:
                    sys.stderr.write(f"  ClinVar lines processed: {n_clinvar:,}\n")

    sys.stderr.write(
        f"\nClinVar lines: {n_clinvar:,}\n"
        f"Position+REF+ALT matches in your VCF: {n_match:,}\n"
        f"P/LP matches: {n_path:,}\n"
        f"  ACMG SF v3.2 hits: {n_acmg}\n"
        f"  Carrier-panel hits: {n_carrier}\n\n"
        f"Wrote: {full_path}\n       {acmg_path}\n       {carrier_path}\n"
    )


if __name__ == "__main__":
    main()
