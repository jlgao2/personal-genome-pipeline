"""Build gene -> inheritance (AR/XL) + severe flag from the Clinical Genomic Database (CGD).

CGD: https://research.nhgri.nih.gov/CGD/download/txt/CGD.txt.gz
Columns: GENE, HGNC ID, ENTREZ GENE ID, CONDITION, INHERITANCE, AGE GROUP, ...
"""
import gzip
import io
import urllib.request
from pathlib import Path

CGD_URL = "https://research.nhgri.nih.gov/CGD/download/txt/CGD.txt.gz"
OUT = Path(__file__).resolve().parent / "data" / "gene_inheritance.tsv"
SEVERE_AGES = {"antenatal", "neonatal", "infancy", "childhood", "pediatric"}


def cgd_rows_to_map(rows):
    """rows: iterable of CGD columns (list). Return {gene: {inheritance, severe}}
    keeping only genes whose INHERITANCE mentions AR or XL. inheritance is the sorted
    set of recessive modes seen ('AR', 'XL', or 'AR;XL'); severe = any childhood-onset row."""
    agg = {}
    for r in rows:
        if len(r) < 6:
            continue
        gene, inh, age = r[0].strip(), r[4], r[5]
        modes = {m for m in ("AR", "XL") if m in inh}
        if not modes:
            continue
        severe = any(a in age.lower() for a in SEVERE_AGES)
        cur = agg.setdefault(gene, {"modes": set(), "severe": False})
        cur["modes"] |= modes
        cur["severe"] = cur["severe"] or severe
    return {g: {"inheritance": ";".join(sorted(v["modes"])), "severe": v["severe"]}
            for g, v in agg.items()}


def fetch_cgd_rows():
    with urllib.request.urlopen(CGD_URL, timeout=60) as resp:
        data = resp.read()
    text = gzip.GzipFile(fileobj=io.BytesIO(data)).read().decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        yield line.split("\t")


def build():
    m = cgd_rows_to_map(fetch_cgd_rows())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        f.write("gene\tinheritance\tsevere\n")
        for gene in sorted(m):
            f.write(f"{gene}\t{m[gene]['inheritance']}\t{'yes' if m[gene]['severe'] else 'no'}\n")
    return len(m)


if __name__ == "__main__":
    n = build()
    print(f"[build_inheritance_map] wrote {n} recessive genes -> {OUT}")
