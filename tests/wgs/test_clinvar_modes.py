import subprocess
import sys
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
CLINVAR = FIX / "clinvar_mini.vcf"
SCRIPT = Path("pipeline/06_clinvar_acmg.py")

USER_VCF = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSQ8TH633
13\t100\trs_brca2\tA\tT\t.\tPASS\t.\tGT\t0/1
7\t200\trs_explore\tG\tC\t.\tPASS\t.\tGT\t0/1
1\t300\trs_carrier\tC\tG\t.\tPASS\t.\tGT\t0/1
"""


def _run(mode, outdir, extra=None):
    vcf = outdir / "user.vcf"
    vcf.write_text(USER_VCF)
    cmd = [sys.executable, str(SCRIPT), "--vcf", str(vcf), "--clinvar", str(CLINVAR),
           "--build", "GRCh38", "--outdir", str(outdir), "--mode", mode, "--min-stars", "1"]
    if extra:
        cmd += extra
    subprocess.run(cmd, check=True, capture_output=True)


def test_actionable_writes_acmg_and_carrier_not_full(tmp_path):
    _run("actionable", tmp_path)
    assert (tmp_path / "clinvar_acmg.tsv").exists()
    assert (tmp_path / "carrier_status.tsv").exists()
    assert not (tmp_path / "clinvar_full.tsv").exists()
    acmg = (tmp_path / "clinvar_acmg.tsv").read_text()
    assert "BRCA2" in acmg
    assert "XYZ" not in acmg
    carrier = (tmp_path / "carrier_status.tsv").read_text()
    assert "CFTR" in carrier


def test_exploratory_genomewide_excludes_actionable(tmp_path):
    _run("actionable", tmp_path)
    _run("exploratory", tmp_path,
         extra=["--exclude", str(tmp_path / "clinvar_acmg.tsv"), "--cap", "200"])
    expl = (tmp_path / "clinvar_exploratory.tsv").read_text()
    assert "XYZ" in expl
    assert "BRCA2" not in expl


def test_legacy_default_writes_full(tmp_path):
    vcf = tmp_path / "user.vcf"
    vcf.write_text(USER_VCF)
    subprocess.run([sys.executable, str(SCRIPT), "--vcf", str(vcf),
                    "--clinvar", str(CLINVAR), "--build", "GRCh38",
                    "--outdir", str(tmp_path), "--min-stars", "1"], check=True, capture_output=True)
    assert (tmp_path / "clinvar_full.tsv").exists()
