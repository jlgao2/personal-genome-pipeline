import subprocess, sys
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "annotsv_sample.tsv"
SCRIPT = Path("pipeline/15_parse_annotsv.py")


def test_parse_annotsv_tiers(tmp_path):
    out = tmp_path / "sv_cnv_findings.tsv"
    subprocess.run([sys.executable, str(SCRIPT), "--annotsv", str(FIX),
                    "--caller", "manta", "--out", str(out)], check=True, capture_output=True)
    rows = [l.split("\t") for l in out.read_text().splitlines()]
    header, data = rows[0], rows[1:]
    col = {c: i for i, c in enumerate(header)}
    # class 5 + class 3 kept (full rows only → 2 rows); class 1 dropped; split row not double-counted
    genes = {r[col["gene"]] for r in data}
    assert genes == {"BRCA1", "XYZ"}
    by_gene = {r[col["gene"]]: r for r in data}
    assert by_gene["BRCA1"][col["scan_tier"]] == "actionable"   # class 5
    assert by_gene["XYZ"][col["scan_tier"]] == "exploratory"    # class 3
    assert by_gene["BRCA1"][col["svtype"]] == "DEL"
    assert by_gene["BRCA1"][col["caller"]] == "manta"
