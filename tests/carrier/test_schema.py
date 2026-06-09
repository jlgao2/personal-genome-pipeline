import json
from pipeline.carrier.schema import CarrierCall, CoupleRisk, CoupleReport

def test_carrier_call_roundtrip():
    c = CarrierCall(gene="CFTR", condition="Cystic fibrosis", inheritance="AR",
                    tier="snv", method="clinvar", variant="7:117559590:G:A:rs123",
                    clnsig="Pathogenic", stars=3, confidence="high")
    d = c.to_dict()
    assert d["gene"] == "CFTR" and d["tier"] == "snv"
    assert CarrierCall.from_dict(d) == c

def test_couple_report_serializes_to_json():
    rep = CoupleReport(
        generated_at="2026-06-09T00:00:00Z",
        partners=[{"id": "A", "sex": "XY"}, {"id": "B", "sex": "XX"}],
        couple_risks=[CoupleRisk(gene="CFTR", condition="Cystic fibrosis",
                                 inheritance="AR", risk_pct=25, significance="serious",
                                 partner_A_variant="7:117559590:G:A:rs123",
                                 partner_B_variant="7:117559592:C:T:rs456",
                                 notes="")],
        single_carrier_highlights=[], coverage_caveats=["partner B BAM absent"])
    s = json.dumps(rep.to_dict())
    back = json.loads(s)
    assert back["couple_risks"][0]["risk_pct"] == 25
    assert back["coverage_caveats"] == ["partner B BAM absent"]
