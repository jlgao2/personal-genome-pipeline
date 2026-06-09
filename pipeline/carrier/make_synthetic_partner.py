"""Emit a synthetic partner VCF: heterozygous at the given chrom:pos:ref:alt sites."""
import argparse

def write_vcf(sites, out):
    with open(out, "w") as f:
        f.write("##fileformat=VCFv4.1\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n")
        for chrom, pos, ref, alt in sites:
            f.write(f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\t.\t.\tGT\t0/1\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", action="append", default=[], help="chrom:pos:ref:alt")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    write_vcf([tuple(s.split(":")) for s in args.site], args.out)
    print(f"wrote synthetic partner -> {args.out}")
