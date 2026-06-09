from pipeline.clinvar_lib import (
    parse_clinvar_info, review_status_stars, is_pathogenic, zygosity_of,
)

def test_is_pathogenic_variants():
    assert is_pathogenic("Pathogenic") == "Pathogenic"
    assert is_pathogenic("Likely_pathogenic") == "Likely_pathogenic"
    assert is_pathogenic("Pathogenic/Likely_pathogenic") == "Pathogenic/Likely_pathogenic"
    assert is_pathogenic("Benign") == ""

def test_review_stars():
    assert review_status_stars("reviewed_by_expert_panel") == 3
    assert review_status_stars("criteria_provided,_multiple_submitters,_no_conflicts") == 2
    assert review_status_stars("no_assertion_criteria_provided") == 0

def test_parse_clinvar_info_geneinfo():
    info = "CLNSIG=Pathogenic;CLNDN=Cystic_fibrosis;CLNREVSTAT=criteria_provided,_multiple_submitters,_no_conflicts;GENEINFO=CFTR:1080"
    d = parse_clinvar_info(info)
    assert d["GENEINFO"] == "CFTR"
    assert d["CLNSIG"] == "Pathogenic"
    assert d["CLNDN"] == "Cystic fibrosis"

def test_zygosity_of():
    assert zygosity_of("0/1") == "heterozygous"
    assert zygosity_of("1|1") == "homozygous_alt"
    assert zygosity_of("0/0") == "ref/ref"
    assert zygosity_of("") == "unknown"
