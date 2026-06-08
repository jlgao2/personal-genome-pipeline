import subprocess
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "wgs_gvcf_sample.vcf"
SCRIPT = Path("pipeline/wgs/prep_wgs_vcf.sh")
FASTA = Path("refs/grch38_noprefix.fa")


def _prep(tmp_path):
    inp = tmp_path / "in.vcf.gz"
    subprocess.run(f"bgzip -c {FIX} > {inp} && tabix -p vcf {inp}", shell=True, check=True)
    out = tmp_path / "out.vcf.gz"
    subprocess.run(["bash", str(SCRIPT), str(inp), str(out)], check=True, capture_output=True)
    recs = subprocess.run(["bcftools", "view", "-H", str(out)],
                          capture_output=True, text=True, check=True).stdout.strip().splitlines()
    return [r.split("\t") for r in recs if r]


def test_prep_transforms(tmp_path):
    if not FASTA.exists():
        import pytest; pytest.skip("run pipeline/wgs/make_noprefix_fasta.sh first")
    rows = _prep(tmp_path)
    sites = {(r[0], r[1], r[3], r[4]) for r in rows}
    # ref-blocks dropped
    assert not any(r[4] in (".", "<NON_REF>") for r in rows)
    # FAIL dropped
    assert not any(r[1] == "40000" for r in rows)
    # PASS variant without rsID kept
    assert ("1", "50000", "T", "A") in sites
    # rsID retained
    assert any(r[1] == "50000" for r in rows)
    # mixed record: real ALT kept, NON_REF gone
    assert ("1", "30000", "T", "C") in sites
    # multiallelic indel left-aligned/trimmed to canonical biallelic (anchor-trimmed)
    indel = [r for r in rows if r[1] == "82133"]
    assert len(indel) == 2
    for r in indel:
        assert len(r[3]) <= 4 and r[3][0] == "C"
        assert "," not in r[4]


def test_orchestrator_omits_topmed_steps():
    text = Path("pipeline/00_run_wgs.sh").read_text()
    assert "TOPMED_PASS" not in text
    assert "decrypt" not in text.lower()
    assert "--source wgs" in text
    assert "output/raw_findings/wgs" in text
