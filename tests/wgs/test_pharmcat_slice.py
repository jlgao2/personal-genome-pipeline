import subprocess
from pathlib import Path


def _bgzip_tabix(path):
    subprocess.run(f"bgzip -f -c {path} > {path}.gz && tabix -f -p vcf {path}.gz",
                   shell=True, check=True)


def test_pharmcat_chr_reconciliation(tmp_path):
    # chr-prefixed positions file (like pharmcat_positions.vcf.bgz)
    pos = tmp_path / "pos.vcf"
    pos.write_text("##fileformat=VCFv4.2\n##contig=<ID=chr1>\n"
                   "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
                   "chr1\t100\t.\tA\tG\t.\t.\t.\n")
    _bgzip_tabix(pos)
    # no-prefix user VCF at the same position
    user = tmp_path / "user.vcf"
    user.write_text("##fileformat=VCFv4.2\n##contig=<ID=1>\n"
                    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
                    "1\t100\t.\tA\tG\t.\tPASS\t.\n")
    _bgzip_tabix(user)

    # WITHOUT renaming, the slice is empty (the shipped bug class)
    bug = subprocess.run(["bcftools", "view", "-H", "-R", f"{pos}.gz", f"{user}.gz"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert bug == ""

    # WITH 1->chr1 rename, the slice is non-empty (the fix)
    rmap = tmp_path / "rename.txt"
    rmap.write_text("1\tchr1\n")
    renamed = tmp_path / "user_chr.vcf.gz"
    subprocess.run(["bcftools", "annotate", "--rename-chrs", str(rmap),
                    f"{user}.gz", "-Oz", "-o", str(renamed)], check=True)
    subprocess.run(["bcftools", "index", "-t", str(renamed)], check=True)
    fixed = subprocess.run(["bcftools", "view", "-H", "-R", f"{pos}.gz", str(renamed)],
                           capture_output=True, text=True, check=True).stdout.strip().splitlines()
    assert len(fixed) == 1
