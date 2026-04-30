#!/usr/bin/env python3
"""
Preprocess 23andMe raw genotype TSV into the format bcftools convert --tsv2vcf expects:
    ID<TAB>CHROM<TAB>POS<TAB>ALLELES
Where ALLELES is comma-separated genotype alleles (e.g., "A,T" or "C,C").

Drops:
  - header (#) lines
  - no-calls ("--")
  - indels (II, DD, I, D, DI) -- not standardly placed; use sequencing for indels
  - chrom == "0" or other unrecognized chrom labels
  - hemizygous single-letter calls on X/Y/MT are duplicated to homozygous diploid
    (TOPMed accepts diploid encoding for sex chroms in males)
  - mitochondrial calls (chrom 'MT' -> 'MT') are kept as homozygous

Mappings:
  '1'..'22' -> '1'..'22'
  'X' -> 'X', 'Y' -> 'Y', 'MT' -> 'MT'

Stats are written to stderr.
"""
import sys

VALID_BASES = set("ACGT")
INDEL_TOKENS = {"II", "DD", "I", "D", "DI", "ID"}


def main(in_path: str, out_path: str) -> int:
    n_total = 0
    n_header = 0
    n_nocall = 0
    n_indel = 0
    n_bad_chrom = 0
    n_bad_base = 0
    n_kept = 0
    n_hemi_extended = 0

    with open(in_path) as f, open(out_path, "w") as out:
        for line in f:
            if line.startswith("#"):
                n_header += 1
                continue
            n_total += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                n_bad_base += 1
                continue
            rsid, chrom, pos, gt = parts

            if gt == "--":
                n_nocall += 1
                continue
            if gt in INDEL_TOKENS:
                n_indel += 1
                continue
            # Sometimes encountered: I/D mixed with single base
            if any(c in gt for c in "ID"):
                n_indel += 1
                continue

            if chrom not in {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}:
                n_bad_chrom += 1
                continue

            # Normalize hemizygous (single base) calls: duplicate the base
            if len(gt) == 1:
                if gt not in VALID_BASES:
                    n_bad_base += 1
                    continue
                gt = gt + gt
                n_hemi_extended += 1
            elif len(gt) == 2:
                if gt[0] not in VALID_BASES or gt[1] not in VALID_BASES:
                    n_bad_base += 1
                    continue
            else:
                n_bad_base += 1
                continue

            # bcftools tsv2vcf AA column expects 2-char genotype like "AT", not "A,T"
            out.write(f"{rsid}\t{chrom}\t{pos}\t{gt}\n")
            n_kept += 1

    sys.stderr.write(
        f"Header lines:           {n_header}\n"
        f"Total data lines:       {n_total}\n"
        f"No-calls dropped:       {n_nocall}\n"
        f"Indels dropped:         {n_indel}\n"
        f"Bad chrom dropped:      {n_bad_chrom}\n"
        f"Bad base dropped:       {n_bad_base}\n"
        f"Hemi extended to dipl.: {n_hemi_extended}\n"
        f"KEPT:                   {n_kept}\n"
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("Usage: 01_23andme_to_tsv.py <in.txt> <out.tsv>\n")
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
