"""Join two persons' carrier calls -> couple risk report."""
import argparse
import datetime as _dt
import json
from pathlib import Path

from pipeline.carrier.schema import CarrierCall, CoupleRisk, CoupleReport
from pipeline.carrier.tier1_clinvar import load_inheritance


def _tier(severe, stars_a, stars_b):
    m = min(stars_a, stars_b)        # evidence quality gates the tier
    if severe and m >= 2:
        return "serious"
    if m >= 2:
        return "moderate"
    return "low"                     # weak evidence (<2 stars) -> low regardless of severity


def _by_gene(calls):
    out = {}
    for c in calls:
        out.setdefault(c.gene, []).append(c)
    return out


def intersect(calls_a, sex_a, calls_b, sex_b, severe_by_gene, caveats=None):
    """calls_a/b: list[CarrierCall]. sex_a/b: 'XX'|'XY'. Return CoupleReport."""
    a_by, b_by = _by_gene(calls_a), _by_gene(calls_b)
    risks, highlights = [], []

    # Autosomal recessive: risk only when BOTH partners carry the same gene.
    for gene in sorted(set(a_by) & set(b_by)):
        # AR;XL dual-mode genes (e.g. SHOX) defer to the XL branch below; the AR 25%
        # path is not emitted for them — a known Phase 1 simplification.
        if "XL" in a_by[gene][0].inheritance or "XL" in b_by[gene][0].inheritance:
            continue
        ca, cb = a_by[gene][0], b_by[gene][0]
        severe = severe_by_gene.get(gene, False)
        risks.append(CoupleRisk(
            gene=gene, condition=ca.condition, inheritance="AR", risk_pct=25,
            significance=_tier(severe, ca.stars, cb.stars),
            partner_A_variant=ca.variant, partner_B_variant=cb.variant,
            notes="Both partners carriers -> 25% of pregnancies affected."))

    # X-linked recessive: risk driven by the FEMALE partner's carrier status.
    # exactly one female partner (the in-scope case). XX+XX couples' XL risk is out of Phase 1 scope.
    if (sex_a == "XX") ^ (sex_b == "XX"):
        fcalls = calls_a if sex_a == "XX" else calls_b
        for gene, cs in _by_gene(fcalls).items():
            if "XL" not in cs[0].inheritance:
                continue
            c = cs[0]
            severe = severe_by_gene.get(gene, False)
            risks.append(CoupleRisk(
                gene=gene, condition=c.condition, inheritance="XL", risk_pct=50,
                significance=_tier(severe, c.stars, c.stars),
                partner_A_variant=(c.variant if sex_a == "XX" else ""),
                partner_B_variant=(c.variant if sex_b == "XX" else ""),
                notes="Female partner carries an X-linked recessive variant -> 50% of sons affected; 50% of daughters carriers."))

    # Single-carrier highlights: severe-gene carriers that are NOT a couple risk.
    risk_genes = {r.gene for r in risks}
    for calls in (calls_a, calls_b):
        for c in calls:
            if c.gene not in risk_genes and severe_by_gene.get(c.gene, False):
                highlights.append(c)

    return CoupleReport(
        generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        partners=[{"id": "A", "sex": sex_a}, {"id": "B", "sex": sex_b}],
        couple_risks=sorted(risks, key=lambda r: {"serious": 0, "moderate": 1, "low": 2}[r.significance]),
        single_carrier_highlights=highlights,
        coverage_caveats=caveats or [])


def _load(path):
    d = json.loads(Path(path).read_text())
    return [CarrierCall.from_dict(c) for c in d["calls"]], d["sex"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="carrier_calls.A.json")
    ap.add_argument("--b", required=True, help="carrier_calls.B.json")
    ap.add_argument("--inheritance", default="pipeline/carrier/data/gene_inheritance.tsv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    severe = {g: v["severe"] for g, v in load_inheritance(args.inheritance).items()}
    calls_a, sex_a = _load(args.a)
    calls_b, sex_b = _load(args.b)
    rep = intersect(calls_a, sex_a, calls_b, sex_b, severe)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep.to_dict(), indent=2))
    print(f"[intersect] {len(rep.couple_risks)} couple risks -> {args.out}")


if __name__ == "__main__":
    main()
