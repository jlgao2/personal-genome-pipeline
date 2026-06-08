#!/usr/bin/env python3
"""Parse an AnnotSV output TSV into tiered SV/CNV findings.

Uses AnnotSV "full" rows (one per SV, carrying the SV-level ACMG_class 1-5).
Keeps class >= 3; tiers 4-5 -> actionable, 3 -> exploratory; sorts exploratory by
class desc and caps. Emits output/raw_findings/wgs/sv_cnv_findings.tsv.
"""
import argparse
import csv
import sys

COLS = ["chrom", "start", "end", "svtype", "svlen", "gene", "acmg_class",
        "scan_tier", "caller", "summary"]


def parse(annotsv_path, caller, cap):
    rows = []
    with open(annotsv_path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            if r.get("Annotation_mode") != "full":
                continue
            try:
                cls = int(r.get("ACMG_class", ""))
            except ValueError:
                continue
            if cls < 3:
                continue
            svtype = r.get("SV_type", "")
            gene = r.get("Gene_name", "")
            scan_tier = "actionable" if cls >= 4 else "exploratory"
            label = {5: "pathogenic", 4: "likely pathogenic", 3: "uncertain"}.get(cls, str(cls))
            summary = f"{svtype} overlapping {gene} — AnnotSV class {cls} ({label})"
            rows.append({
                "chrom": r.get("SV_chrom", ""), "start": r.get("SV_start", ""),
                "end": r.get("SV_end", ""), "svtype": svtype, "svlen": r.get("SV_length", ""),
                "gene": gene, "acmg_class": cls, "scan_tier": scan_tier,
                "caller": caller, "summary": summary,
            })
    # actionable kept whole; exploratory sorted by class desc then capped
    actionable = [r for r in rows if r["scan_tier"] == "actionable"]
    exploratory = sorted([r for r in rows if r["scan_tier"] == "exploratory"],
                         key=lambda r: -r["acmg_class"])[:cap]
    return actionable + exploratory


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotsv", required=True)
    ap.add_argument("--caller", required=True, choices=["manta", "canvas"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--cap", type=int, default=200)
    args = ap.parse_args()
    rows = parse(args.annotsv, args.caller, args.cap)
    with open(args.out, "a" if args.out.endswith(".append") else "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    sys.stderr.write(f"{args.caller}: wrote {len(rows)} SV/CNV findings to {args.out}\n")


if __name__ == "__main__":
    main()
