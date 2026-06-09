from pipeline.carrier.build_inheritance_map import cgd_rows_to_map

# CGD columns: GENE, HGNC ID, ENTREZ GENE ID, CONDITION, INHERITANCE, AGE GROUP, ...
ROWS = [
    ["CFTR", "1884", "1080", "Cystic fibrosis", "AR", "Pediatric"],
    ["DMD",  "2928", "1756", "Muscular dystrophy", "XL", "Childhood"],
    ["BRCA1","1100", "672",  "Breast cancer", "AD", "Adult"],          # dominant -> dropped
    ["HBB",  "4827", "3043", "Beta thalassemia", "AR", "Infancy"],
    ["ATP7B","870",  "540",  "Wilson disease", "AR", "Adult"],          # AR but adult -> not severe
    ["CFTR", "1884", "1080", "CBAVD", "AR", "Adult"],                   # second CFTR row
]

def test_keeps_only_recessive_genes():
    m = cgd_rows_to_map(ROWS)
    assert set(m) == {"CFTR", "DMD", "HBB", "ATP7B"}   # BRCA1 (AD) excluded

def test_inheritance_and_severe_flags():
    m = cgd_rows_to_map(ROWS)
    assert m["CFTR"]["inheritance"] == "AR" and m["CFTR"]["severe"] is True   # Pediatric
    assert m["DMD"]["inheritance"] == "XL" and m["DMD"]["severe"] is True
    assert m["HBB"]["severe"] is True                                          # Infancy
    assert m["ATP7B"]["severe"] is False                                       # Adult only
