#!/usr/bin/env python3
"""Look up authoritative GRCh37/GRCh38 position + REF/ALT for each panel rsid via myvariant.info."""
import myvariant
import json

RSIDS = [
    "rs429358", "rs7412", "rs1801133", "rs1801131",
    "rs601338", "rs2282679", "rs2228570",
    "rs1800562", "rs1799945",
    "rs4988235",
    "rs671", "rs1229984", "rs762551",
    "rs7501331", "rs174537", "rs699",
    "rs7903146", "rs9939609",
    "rs1815739", "rs1801260", "rs5751876",
    "rs1799930", "rs1805007", "rs1050828",
]

mv = myvariant.MyVariantInfo()
out = mv.querymany(RSIDS, scopes="dbsnp.rsid", fields="dbsnp,clinvar.hg19,clinvar.hg38,_id", assembly="hg19")

for hit in out:
    if "notfound" in hit:
        print(f"{hit['query']}\tNOT_FOUND")
        continue
    db = hit.get("dbsnp", {})
    rsid = db.get("rsid", hit.get("query"))
    chrom = db.get("chrom", "?")
    hg19 = db.get("hg19", {}).get("start", "?")
    hg38 = db.get("hg38", {}).get("start", "?")
    ref = db.get("ref", "?")
    alts = db.get("alt", [])
    if isinstance(alts, str):
        alts = [alts]
    print(f"{rsid}\tchr{chrom}\thg19:{hg19}\thg38:{hg38}\tREF={ref}\tALT={','.join(alts)}")
