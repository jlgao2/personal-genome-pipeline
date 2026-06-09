from pipeline.carrier.schema import CarrierCall, CoupleReport
from pipeline.carrier.couple_intersect import intersect

def _call(gene, inh, stars, variant):
    return CarrierCall(gene=gene, condition=f"{gene} disease", inheritance=inh,
                       tier="snv", method="clinvar", variant=variant, stars=stars)

SEVERE = {"CFTR": True, "DMD": True, "GJB2": False}  # gene -> severe flag

def test_ar_shared_gene_is_25pct_serious():
    a = [_call("CFTR", "AR", 3, "7:100:G:A:rs1")]
    b = [_call("CFTR", "AR", 2, "7:200:C:T:rs2")]
    rep = intersect(a, "XY", b, "XX", severe_by_gene=SEVERE)
    assert len(rep.couple_risks) == 1
    r = rep.couple_risks[0]
    assert r.gene == "CFTR" and r.risk_pct == 25 and r.significance == "serious"
    assert r.partner_A_variant == "7:100:G:A:rs1"
    assert r.partner_B_variant == "7:200:C:T:rs2"

def test_non_shared_gene_is_single_carrier_highlight_not_risk():
    a = [_call("CFTR", "AR", 3, "7:100:G:A:rs1")]
    b = [_call("GJB2", "AR", 2, "13:50:T:C:rs9")]
    rep = intersect(a, "XY", b, "XX", severe_by_gene=SEVERE)
    assert rep.couple_risks == []
    # CFTR (severe) surfaces as a single-carrier highlight; GJB2 (not severe) does not
    genes = {h.gene for h in rep.single_carrier_highlights}
    assert genes == {"CFTR"}

def test_xlinked_female_carrier_is_50pct_regardless_of_male():
    a = []                                   # male partner not a carrier
    b = [_call("DMD", "XL", 3, "X:300:A:G:rs5")]   # female carrier of X-linked
    rep = intersect(a, "XY", b, "XX", severe_by_gene=SEVERE)
    assert len(rep.couple_risks) == 1
    r = rep.couple_risks[0]
    assert r.gene == "DMD" and r.risk_pct == 50 and "sons" in r.notes.lower()

def test_low_tier_when_below_two_stars():
    a = [_call("CFTR", "AR", 1, "7:100:G:A:rs1")]
    b = [_call("CFTR", "AR", 3, "7:200:C:T:rs2")]
    rep = intersect(a, "XY", b, "XX", severe_by_gene=SEVERE)
    assert rep.couple_risks[0].significance == "low"   # min stars = 1
