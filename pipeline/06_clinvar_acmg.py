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
import contextlib
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
    ap.add_argument("--mode", choices=["legacy", "actionable", "exploratory"],
                    default="legacy")
    ap.add_argument("--exclude", default=None,
                    help="exploratory mode: TSV whose chrom:pos:ref:alt rows to skip")
    ap.add_argument("--cap", type=int, default=200,
                    help="exploratory mode: max rows after sorting by (stars, sig)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    sys.stderr.write(f"Loading user VCF positions from {args.vcf} ...\n")
    user_vars = parse_vcf_positions(args.vcf)
    sys.stderr.write(f"  {len(user_vars):,} unique positions\n")

    full_path = os.path.join(args.outdir, "clinvar_full.tsv")
    acmg_path = os.path.join(args.outdir, "clinvar_acmg.tsv")
    carrier_path = os.path.join(args.outdir, "carrier_status.tsv")
    explore_path = os.path.join(args.outdir, "clinvar_exploratory.tsv")

    header = "chrom\tpos\tref\talt\trsid\tgene\tclnsig_class\tclnsig\tclndn\tclnrevstat\tstars\tuser_gt\tuser_zygosity\n"

    exclude_keys = set()
    if args.exclude and os.path.exists(args.exclude):
        with open(args.exclude) as ex:
            next(ex, None)  # header
            for ln in ex:
                c = ln.rstrip("\n").split("\t")
                if len(c) >= 4:
                    exclude_keys.add((c[0], c[1], c[2], c[3]))

    def iter_matches():
        """Yield (gene, stars, cls, row_str, key) for every P/LP, >=min-stars,
        non-ref/ref match — the shared engine for all modes."""
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
                key = (chrom, int(pos))
                if key not in user_vars:
                    continue
                for u_ref, u_alt, u_gt in user_vars[key]:
                    if u_ref != ref or u_alt != alt:
                        continue
                    cls = is_pathogenic(info["CLNSIG"])
                    if not cls:
                        continue
                    stars = review_status_stars(info["CLNREVSTAT"])
                    if stars < args.min_stars:
                        continue
                    zyg = "unknown"
                    if u_gt:
                        a = u_gt.replace("|", "/").split("/")
                        if len(a) == 2:
                            zyg = ("ref/ref" if a[0] == a[1] == "0"
                                   else "homozygous_alt" if a[0] == a[1]
                                   else "heterozygous")
                    if zyg == "ref/ref":
                        continue
                    row_str = (
                        f"{chrom}\t{pos}\t{ref}\t{alt}\t{rsid}\t{info['GENEINFO']}\t"
                        f"{cls}\t{info['CLNSIG']}\t{info['CLNDN']}\t{info['CLNREVSTAT']}\t"
                        f"{stars}\t{u_gt}\t{zyg}\n"
                    )
                    yield info["GENEINFO"], stars, cls, row_str, (chrom, pos, ref, alt)

    if args.mode == "exploratory":
        sig_rank = {"Pathogenic": 0, "Pathogenic/Likely_pathogenic": 1, "Likely_pathogenic": 2}
        matches = [m for m in iter_matches() if m[4] not in exclude_keys]
        matches.sort(key=lambda m: (-m[1], sig_rank.get(m[2], 9)))
        with open(explore_path, "w") as f_ex:
            f_ex.write(header)
            for gene, stars, cls, row_str, key in matches[: args.cap]:
                f_ex.write(row_str)
        sys.stderr.write(f"exploratory: {len(matches)} matched, wrote {min(len(matches), args.cap)} → {explore_path}\n")
        return

    write_full = args.mode == "legacy"
    with contextlib.ExitStack() as stack:
        f_acmg = stack.enter_context(open(acmg_path, "w"))
        f_carrier = stack.enter_context(open(carrier_path, "w"))
        f_full = stack.enter_context(open(full_path, "w")) if write_full else None
        f_acmg.write(header)
        f_carrier.write(header)
        if f_full:
            f_full.write(header)
        n_acmg = n_carrier = 0
        for gene, stars, cls, row_str, key in iter_matches():
            if f_full:
                f_full.write(row_str)
            if gene in ACMG_SF_V32:
                f_acmg.write(row_str)
                n_acmg += 1
            if gene in ACMG_CARRIER_PANEL:
                f_carrier.write(row_str)
                n_carrier += 1
    sys.stderr.write(f"mode={args.mode}: ACMG {n_acmg}, carrier {n_carrier}\n")


if __name__ == "__main__":
    main()
