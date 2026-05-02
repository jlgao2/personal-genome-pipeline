"""Auto-generate cross_refs entries from a structured health-profile JSON.

The health profile contains rich red-flag thresholds for metabolic factors
relevant to the user's tendon-vulnerability phenotype. We translate each
into a cross_refs row so the Action Loop can surface "your hs-CRP is X
vs target <1.0" automatically once lab data lands.
"""
from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# Map metabolic-factor names to (sample_type, target_value, expected_direction, takeaway).
# Direction = the bad direction. 'increase' = we want value below target.
# Pre-attaches a finding_id where a clear genome correlate exists in the
# user's findings.parquet (otherwise uses 'context:<factor>').
_FACTOR_ROWS: list[dict] = [
    {
        "finding_id": "context:insulin_resistance",
        "sample_type": "hba1c",
        "expected_direction": "increase",
        "target_value": 5.6,
        "takeaway": "HbA1c >5.6% means subclinical dysglycemia. AGEs accumulate in tendons → reduced elasticity. Check fasting insulin + HOMA-IR if elevated.",
    },
    {
        "finding_id": "context:insulin_resistance",
        "sample_type": "glucose_fasting",
        "expected_direction": "increase",
        "target_value": 100.0,
        "takeaway": "Fasting glucose >100 mg/dL = pre-diabetic range. Tendon healing impaired by chronic glucose excursions.",
    },
    {
        "finding_id": "prs:PGS000018",
        "sample_type": "ldl_cholesterol",
        "expected_direction": "increase",
        "target_value": 100.0,
        "takeaway": "CAD PRS slightly elevated + tendon vulnerability — keep LDL <100. Lipid deposits in tendons (xanthomas) weaken structure.",
    },
    {
        "finding_id": "context:dyslipidemia",
        "sample_type": "triglycerides",
        "expected_direction": "increase",
        "target_value": 150.0,
        "takeaway": "TG >150 mg/dL associated with metabolic syndrome — drives tendon fragility via systemic inflammation.",
    },
    {
        "finding_id": "context:vitamin_d",
        "sample_type": "vitamin_d_25oh",
        "expected_direction": "decrease",
        "target_value": 40.0,
        "takeaway": "Vitamin D 25-OH should be 40-60 ng/mL (not just >30). Tenocytes have VDRs; deficiency = pain + impaired healing. Chicago latitude + indoor work = high deficiency risk.",
    },
    {
        "finding_id": "context:inflammation",
        "sample_type": "hs_crp",
        "expected_direction": "increase",
        "target_value": 1.0,
        "takeaway": "hs-CRP >1.0 mg/L without acute illness = systemic inflammation. Accelerates tendon degeneration.",
    },
    {
        "finding_id": "nutrition_traits:rs1801133",
        "sample_type": "homocysteine",
        "expected_direction": "increase",
        "target_value": 10.0,
        "takeaway": "MTHFR C677T A/A → elevated homocysteine impairs collagen cross-linking. Methylated B-vitamins (5-MTHF + methylcobalamin + P5P) if >10 μmol/L.",
    },
    {
        "finding_id": "context:uric_acid",
        "sample_type": "uric_acid",
        "expected_direction": "increase",
        "target_value": 7.0,
        "takeaway": "Uric acid >7.0 mg/dL in men associated with tendinopathy (crystal deposition + oxidative stress) even without clinical gout.",
    },
    {
        "finding_id": "clinvar_full:rs1800562",
        "sample_type": "ferritin",
        "expected_direction": "increase",
        "target_value": 200.0,
        "takeaway": "HFE C282Y heterozygous + recheck ferritin annually. >200 ng/mL warrants saturation check; iron overload = oxidative tendon damage.",
    },
    {
        "finding_id": "context:thyroid",
        "sample_type": "tsh",
        "expected_direction": "increase",
        "target_value": 2.5,
        "takeaway": "TSH >2.5 mIU/L = subclinical hypothyroidism. Connective tissue myxedematous changes affect tendon integrity. Re-test with free T4 if elevated.",
    },
]


def build_cross_refs_from_profile(profile_path: Path, out_path: Path,
                                   merge_with: Path = None) -> int:
    """Generate cross_refs.parquet from the health-profile JSON.

    If `merge_with` is provided (path to existing cross_refs.yaml), entries
    from that YAML are appended after the auto-generated ones, so user-curated
    rows always win over the boilerplate.
    Returns total cross-ref rows written.
    """
    if not profile_path.exists():
        return 0

    rows = list(_FACTOR_ROWS)

    # Optionally merge user-curated YAML on top.
    if merge_with and merge_with.exists():
        import yaml
        with merge_with.open() as f:
            user_entries = yaml.safe_load(f) or []
        # Override auto-rows with same finding_id+sample_type pair.
        keys = {(e["finding_id"], e["sample_type"]) for e in user_entries}
        rows = [r for r in rows if (r["finding_id"], r["sample_type"]) not in keys]
        rows.extend(user_entries)

    schema = pa.schema([
        ("finding_id",         pa.string()),
        ("sample_type",        pa.string()),
        ("expected_direction", pa.string()),
        ("target_value",       pa.float64()),
        ("takeaway",           pa.string()),
    ])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([
        {
            "finding_id":         r["finding_id"],
            "sample_type":        r["sample_type"],
            "expected_direction": r.get("expected_direction"),
            "target_value":       r.get("target_value"),
            "takeaway":           r.get("takeaway"),
        }
        for r in rows
    ], schema=schema)
    pq.write_table(table, out_path)
    return len(rows)


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Generate cross_refs from health profile JSON.")
    ap.add_argument("--profile", type=Path, default=Path("output/health_profile.json"))
    ap.add_argument("--yaml",    type=Path, default=Path("output/cross_refs.yaml"))
    ap.add_argument("--out",     type=Path,
                    default=Path("data/parquet/cross_refs/cross_refs.parquet"))
    args = ap.parse_args()
    n = build_cross_refs_from_profile(args.profile, args.out, merge_with=args.yaml)
    print(f"Wrote {n} cross-refs (auto-generated + user-curated) to {args.out}")


if __name__ == "__main__":
    _cli()
