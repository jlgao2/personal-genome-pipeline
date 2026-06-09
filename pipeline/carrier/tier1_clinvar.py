"""Tier-1 carrier calling: heterozygous ClinVar P/LP variants in recessive genes."""
import argparse
import csv
import datetime as _dt
import json
from pathlib import Path

from pipeline.clinvar_lib import parse_vcf_positions, iter_clinvar_matches
from pipeline.carrier.schema import CarrierCall


def load_inheritance(tsv_path):
    """Return {gene: {'inheritance': str, 'severe': bool}} for recessive genes."""
    out = {}
    with open(tsv_path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            inh = row["inheritance"]
            if "AR" not in inh and "XL" not in inh:
                continue
            out[row["gene"]] = {"inheritance": inh,
                                "severe": row["severe"] == "yes"}
    return out


def _recessive_mode(inh):
    """Collapse an inheritance string to the carrier-relevant mode: 'XL' if X-linked
    else 'AR'."""
    return "XL" if "XL" in inh else "AR"


def call_carriers(vcf, clinvar, inheritance_tsv, min_stars=2):
    """Return list[CarrierCall]: heterozygous P/LP variants whose gene is recessive."""
    inheritance = load_inheritance(inheritance_tsv)
    user_vars = parse_vcf_positions(vcf)
    calls = []
    for m in iter_clinvar_matches(user_vars, clinvar, min_stars=min_stars):
        if m["zygosity"] != "heterozygous":      # carriers only (homozygous = affected)
            continue
        gene = m["gene"]
        if gene not in inheritance:               # recessive genes only
            continue
        calls.append(CarrierCall(
            gene=gene,
            condition=m["clndn"],
            inheritance=_recessive_mode(inheritance[gene]["inheritance"]),
            tier="snv",
            method="clinvar",
            variant=f"{m['chrom']}:{m['pos']}:{m['ref']}:{m['alt']}:{m['rsid']}",
            clnsig=m["clnsig"],
            stars=m["stars"],
            confidence="high" if m["stars"] >= 2 else "moderate",
        ))
    return calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vcf", required=True)
    ap.add_argument("--clinvar", default="refs/clinvar_grch38.vcf.gz")
    ap.add_argument("--inheritance", default="pipeline/carrier/data/gene_inheritance.tsv")
    ap.add_argument("--person-id", required=True)
    ap.add_argument("--sex", required=True, choices=["XX", "XY"])
    ap.add_argument("--min-stars", type=int, default=2)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    calls = call_carriers(args.vcf, args.clinvar, args.inheritance, args.min_stars)
    payload = {
        "person_id": args.person_id,
        "sex": args.sex,
        "source": {"vcf": args.vcf, "bam": None},
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "calls": [c.to_dict() for c in calls],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(f"[tier1] {args.person_id}: {len(calls)} carrier calls -> {args.out}")


if __name__ == "__main__":
    main()
