import subprocess
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
SCRIPT = Path("pipeline/wgs/prep_sv_cnv.sh")


def _bgzip(src, dst):
    subprocess.run(f"bgzip -f -c {src} > {dst} && tabix -f -p vcf {dst}", shell=True, check=True)


def test_prep_sv_cnv(tmp_path):
    sv_in, cnv_in = tmp_path / "sv.vcf.gz", tmp_path / "cnv.vcf.gz"
    _bgzip(FIX / "sv_sample.vcf", sv_in)
    _bgzip(FIX / "cnv_sample.vcf", cnv_in)
    sv_out, cnv_out = tmp_path / "sv.clean.vcf.gz", tmp_path / "cnv.clean.vcf.gz"
    subprocess.run(["bash", str(SCRIPT), str(sv_in), str(cnv_in), str(sv_out), str(cnv_out)],
                   check=True, capture_output=True)
    sv = subprocess.run(["bcftools", "view", "-H", str(sv_out)], capture_output=True, text=True, check=True).stdout
    cnv = subprocess.run(["bcftools", "view", "-H", str(cnv_out)], capture_output=True, text=True, check=True).stdout
    # SV: PASS DEL kept, FAIL DUP dropped
    assert "MantaDEL:1" in sv and "MantaDUP:1" not in sv
    # CNV: real CN0 call kept, REF segment dropped
    assert "Canvas:GAIN:1" in cnv and "Canvas:REF:1" not in cnv


def test_sv_orchestrator_shape():
    from pathlib import Path
    text = Path("pipeline/00_run_wgs_sv.sh").read_text()
    assert "mamba run -n annotsv AnnotSV" in text
    assert "15_parse_annotsv.py" in text
    assert "output/raw_findings/wgs" in text
