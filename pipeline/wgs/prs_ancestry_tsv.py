#!/usr/bin/env python3
"""Emit output/raw_findings/wgs/prs_ancestry.tsv from the pgsc_calc ancestry run
so the trustworthy EAS-calibrated PRS percentiles flow into genomic_findings.json
(and the health dashboard) — replacing the deprecated normal-approximation
prs_scores.tsv, whose percentiles are all NA.

Each scored PGS gets a reliability flag so consumers can separate:
  - inflated  : genome-wide score (>=100k variants) with |Z|>=2.5 — technically
                inflated vs the reference panel (proven by the height null control);
                read as "elevated", not an exact percentile.
  - sparse    : <20 variants — too thin to trust.
  - calibrated: everything else — the trustworthy ancestry-matched signal.

Inputs:
  - score table : output/pgsc_calc/run/<sample>/score/<sample>_pgs.txt.gz
  - meta cache  : output/pgsc_calc/score_meta.json  (pgs_id -> trait, nvar, gwas_top_anc)
"""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = ["pgs_id", "trait", "gwas_ancestry", "eas_percentile",
           "z_eas", "n_variants", "reliability", "summary"]


def classify(nvar: int | None, z: float) -> str:
    if nvar and nvar >= 100_000 and abs(z) >= 2.5:
        return "inflated"
    if nvar is not None and nvar < 20:
        return "sparse"
    return "calibrated"


def _summary(trait: str, pct: float, z: float, reliability: str) -> str:
    base = f"{trait} — {pct:.0f}th percentile (EAS), Z {z:+.2f}"
    if reliability == "inflated":
        return base + " — genome-wide score; magnitude inflated vs reference panel, read as 'elevated' not an exact percentile"
    if reliability == "sparse":
        return base + " — sparse (few variants); unreliable"
    return base


def build(sample: str = "SQ8TH633",
          score_gz: Path | None = None,
          meta_json: Path | None = None,
          out_tsv: Path | None = None) -> int:
    score_gz = score_gz or ROOT / f"output/pgsc_calc/run/{sample}/score/{sample}_pgs.txt.gz"
    meta_json = meta_json or ROOT / "output/pgsc_calc/score_meta.json"
    out_tsv = out_tsv or ROOT / "output/raw_findings/wgs/prs_ancestry.tsv"

    meta = json.loads(Path(meta_json).read_text())
    lines = [l.rstrip("\n").split("\t") for l in gzip.open(score_gz, "rt")]
    idx = {c: i for i, c in enumerate(lines[0])}

    out: list[dict] = []
    for r in lines[1:]:
        if r[idx["IID"]] != sample:
            continue
        pgs_id = r[idx["PGS"]].split("_")[0]
        m = meta.get(pgs_id, {})
        try:
            z = float(r[idx["Z_MostSimilarPop"]])
            pct = float(r[idx["percentile_MostSimilarPop"]])
        except (ValueError, KeyError):
            continue
        nvar = m.get("nvar")
        rel = classify(nvar, z)
        trait = m.get("trait") or pgs_id
        out.append({
            "pgs_id": pgs_id,
            "trait": trait,
            "gwas_ancestry": m.get("gwas_top_anc") or "NR",
            "eas_percentile": f"{pct:.1f}",
            "z_eas": f"{z:.3f}",
            "n_variants": nvar if nvar is not None else "",
            "reliability": rel,
            "summary": _summary(trait, pct, z, rel),
        })

    out.sort(key=lambda d: -float(d["z_eas"]))
    out_tsv = Path(out_tsv)
    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    with out_tsv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t")
        w.writeheader()
        w.writerows(out)
    return len(out)


if __name__ == "__main__":
    n = build()
    print(f"[prs_ancestry_tsv] wrote {n} scores → output/raw_findings/wgs/prs_ancestry.tsv")
