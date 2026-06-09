from pathlib import Path
from pipeline.carrier.tier1_clinvar import call_carriers

FIX = Path(__file__).parent / "fixtures"

def test_keeps_only_het_plp_recessive():
    calls = call_carriers(
        vcf=str(FIX / "person.vcf"),
        clinvar=str(FIX / "clinvar.vcf"),
        inheritance_tsv=str(FIX / "inheritance.tsv"),
        min_stars=2,
    )
    genes = {c.gene for c in calls}
    # CFTR@100 het in a recessive gene -> kept.
    # CFTR@200 is homozygous_alt (affected, not a carrier) -> excluded.
    # BRCA1@300 is a dominant gene -> excluded.
    assert genes == {"CFTR"}
    cftr = next(c for c in calls if c.gene == "CFTR")
    assert cftr.variant == "7:100:G:A:rs1"
    assert cftr.inheritance == "AR"
    assert cftr.tier == "snv" and cftr.method == "clinvar"
    assert cftr.stars == 3


def test_min_stars_filters_and_sets_confidence():
    args = dict(vcf=str(FIX / "person.vcf"), clinvar=str(FIX / "clinvar.vcf"),
                inheritance_tsv=str(FIX / "inheritance.tsv"))
    # 1-star CFTR@500 is excluded at the default min_stars=2
    calls2 = call_carriers(min_stars=2, **args)
    assert all(c.variant != "7:500:G:T:rs5" for c in calls2)
    # ...but included at min_stars=1, with moderate confidence
    calls1 = call_carriers(min_stars=1, **args)
    c500 = next(c for c in calls1 if c.variant == "7:500:G:T:rs5")
    assert c500.confidence == "moderate" and c500.stars == 1
