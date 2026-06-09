"""Dataclasses + JSON shapes for carrier calls and the couple report."""
from dataclasses import dataclass, field, asdict


@dataclass
class CarrierCall:
    gene: str
    condition: str
    inheritance: str          # "AR" | "XL" | "AR;XL"
    tier: str                 # "snv" (Phase 1) | "special" (Phase 2)
    method: str               # "clinvar" | "smncopynumber" | ...
    variant: str              # "chrom:pos:ref:alt:rsid" or a special-call descriptor
    clnsig: str = ""
    stars: int = 0
    confidence: str = "moderate"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class CoupleRisk:
    gene: str
    condition: str
    inheritance: str
    risk_pct: int             # 25 (AR both carriers) | 50 (XL, female carrier -> sons)
    significance: str         # "serious" | "moderate" | "low"
    partner_A_variant: str
    partner_B_variant: str    # may be "" for XL female-only carrier
    notes: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class CoupleReport:
    generated_at: str
    partners: list
    couple_risks: list = field(default_factory=list)
    single_carrier_highlights: list = field(default_factory=list)
    coverage_caveats: list = field(default_factory=list)

    def to_dict(self):
        return {
            "generated_at": self.generated_at,
            "partners": self.partners,
            "couple_risks": [r.to_dict() for r in self.couple_risks],
            "single_carrier_highlights": [r.to_dict() for r in self.single_carrier_highlights],
            "coverage_caveats": self.coverage_caveats,
        }
