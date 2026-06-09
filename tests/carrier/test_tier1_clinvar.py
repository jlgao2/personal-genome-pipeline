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
