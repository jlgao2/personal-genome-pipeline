"""Shared ClinVar/VCF helpers (extracted from 06_clinvar_acmg.py so they're importable)."""
import gzip
from collections import defaultdict


def parse_vcf_positions(path):
    """Return dict (chrom, pos) -> list of (ref, alt, gt). chrom is 'chr'-stripped."""
    open_fn = gzip.open if path.endswith(".gz") else open
    out = defaultdict(list)
    with open_fn(path, "rt") as f:
        sample_idx = None
        for line in f:
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                cols = line.rstrip().split("\t")
                sample_idx = 9 if len(cols) > 9 else None
                continue
            cols = line.rstrip().split("\t")
            if len(cols) < 8:
                continue
            chrom, pos, _, ref, alt = cols[0], cols[1], cols[2], cols[3], cols[4]
            chrom = chrom.replace("chr", "")
            gt = ""
            if sample_idx and len(cols) > sample_idx:
                fmt = cols[8].split(":")
                vals = cols[sample_idx].split(":")
                if "GT" in fmt:
                    gt = vals[fmt.index("GT")]
            for a in alt.split(","):
                out[(chrom, int(pos))].append((ref, a, gt))
    return out


def parse_clinvar_info(info_str):
    """Pull CLNSIG, CLNDN, CLNREVSTAT, GENEINFO from a ClinVar INFO field."""
    fields = {}
    for kv in info_str.split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            fields[k] = v
    return {
        "CLNSIG": fields.get("CLNSIG", ""),
        "CLNDN": fields.get("CLNDN", "").replace("|", "; ").replace("_", " "),
        "CLNREVSTAT": fields.get("CLNREVSTAT", ""),
        "GENEINFO": fields.get("GENEINFO", "").split("|")[0].split(":")[0],
        "MC": fields.get("MC", ""),
        "ALLELEID": fields.get("ALLELEID", ""),
    }


def review_status_stars(rev):
    """Map ClinVar review status to star count."""
    rev = rev.lower()
    if "practice_guideline" in rev:
        return 4
    if "reviewed_by_expert_panel" in rev:
        return 3
    if "criteria_provided,_multiple_submitters,_no_conflicts" in rev:
        return 2
    if "criteria_provided,_conflicting_classifications" in rev:
        return 1
    if "criteria_provided,_single_submitter" in rev:
        return 1
    if "no_assertion_criteria_provided" in rev:
        return 0
    if "no_classification_for_the_individual_variant" in rev:
        return 0
    return 0


def is_pathogenic(clnsig: str) -> str:
    s = clnsig.lower()
    if "pathogenic/likely_pathogenic" in s or "pathogenic|likely_pathogenic" in s:
        return "Pathogenic/Likely_pathogenic"
    if "pathogenic" in s and "likely_pathogenic" not in s and "non-pathogenic" not in s:
        return "Pathogenic"
    if "likely_pathogenic" in s:
        return "Likely_pathogenic"
    return ""


def zygosity_of(gt):
    """Map a GT string to ref/ref | heterozygous | homozygous_alt | unknown."""
    if not gt:
        return "unknown"
    a = gt.replace("|", "/").split("/")
    if len(a) != 2:
        return "unknown"
    if a[0] == a[1] == "0":
        return "ref/ref"
    if a[0] == a[1]:
        return "homozygous_alt"
    return "heterozygous"


def iter_clinvar_matches(user_vars, clinvar_path, min_stars=2):
    """Yield dicts for every P/LP, >=min_stars ClinVar variant matching user_vars
    (exact chrom/pos/ref/alt). Each: gene, chrom, pos, ref, alt, rsid, clnsig_class,
    clnsig, clndn, stars, gt, zygosity. ref/ref matches are skipped."""
    open_fn = gzip.open if clinvar_path.endswith(".gz") else open
    with open_fn(clinvar_path, "rt") as cv:
        for line in cv:
            if line.startswith("#"):
                continue
            cols = line.rstrip().split("\t")
            if len(cols) < 8:
                continue
            chrom, pos, rsid, ref, alt = cols[0], cols[1], cols[2], cols[3], cols[4]
            chrom = chrom.replace("chr", "")
            key = (chrom, int(pos))
            if key not in user_vars:
                continue
            info = parse_clinvar_info(cols[7])
            for u_ref, u_alt, u_gt in user_vars[key]:
                if u_ref != ref or u_alt != alt:
                    continue
                cls = is_pathogenic(info["CLNSIG"])
                if not cls:
                    continue
                stars = review_status_stars(info["CLNREVSTAT"])
                if stars < min_stars:
                    continue
                zyg = zygosity_of(u_gt)
                if zyg == "ref/ref":
                    continue
                yield {
                    "gene": info["GENEINFO"], "chrom": chrom, "pos": pos,
                    "ref": ref, "alt": alt, "rsid": rsid, "clnsig_class": cls,
                    "clnsig": info["CLNSIG"], "clndn": info["CLNDN"],
                    "stars": stars, "gt": u_gt, "zygosity": zyg,
                }
