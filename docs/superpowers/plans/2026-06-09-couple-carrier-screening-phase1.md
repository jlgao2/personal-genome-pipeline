# Couple Carrier Screening — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working couple carrier screen from two sequenced genomes' VCFs — per-person heterozygous ClinVar P/LP carrier calling over recessive genes, a couple intersect that flags shared-gene risk, and a gated homelab page — with the special callers deferred to Phase 2.

**Architecture:** Reuse the existing ClinVar engine (`pipeline/06_clinvar_acmg.py`), extracted into an importable `pipeline/clinvar_lib.py`. A `pipeline/carrier/` package does per-person Tier-1 calling (`tier1_clinvar.py`) → `carrier_calls.<id>.json`, then `couple_intersect.py` joins two of them → `couple_report.json`, rendered by a static page served from the homelab (`carrier.jlgao.net`).

**Tech Stack:** Python 3 (stdlib only — `csv`, `gzip`, `json`, `dataclasses`, `argparse`, `urllib`), pytest. Gene→inheritance from the Clinical Genomic Database (CGD). Homelab: Caddy + cloudflared + Cloudflare Access (existing).

**Hard gates for every implementer (you cannot see the repo's CLAUDE.md — these are restated):** no production code without a failing test first; root-cause over patching; no completion claim without running the test and pasting real output; reuse `clinvar_lib` rather than reimplementing variant parsing; write ONLY the files listed in your task; keep all partner/personal data gitignored (`data/partner/`, `output/carrier/`).

**Scope notes / deviations from the spec (deliberate):**
- The gene→inheritance map lives at **`pipeline/carrier/data/gene_inheritance.tsv` (committed)** rather than `refs/carrier/` — `refs/` is gitignored, and this file is small, non-personal, and worth version-controlling. The `severe` flag is folded into this one TSV (a `severe` column) instead of a separate `severe_genes.txt`.
- Phase 1 carrier calls set `tier="snv"`; Phase 2 adds `tier="special"` calls. The schema already carries `tier` so Phase 2 slots in.

---

## File Structure

| File | Responsibility |
|---|---|
| `pipeline/clinvar_lib.py` (new) | Pure ClinVar/VCF helpers extracted from `06_clinvar_acmg.py`: `parse_vcf_positions`, `parse_clinvar_info`, `review_status_stars`, `is_pathogenic`, `zygosity_of`, `iter_clinvar_matches`. |
| `pipeline/06_clinvar_acmg.py` (modify) | Import the helpers from `clinvar_lib` instead of defining them locally. Behaviour unchanged. |
| `pipeline/carrier/__init__.py` (new) | Package marker. |
| `pipeline/carrier/schema.py` (new) | `CarrierCall`, `CoupleRisk`, `CoupleReport` dataclasses + JSON (de)serialization. |
| `pipeline/carrier/build_inheritance_map.py` (new) | Download CGD → `pipeline/carrier/data/gene_inheritance.tsv` (gene, inheritance, severe). Pure transform `cgd_rows_to_map` is unit-tested. |
| `pipeline/carrier/data/gene_inheritance.tsv` (generated, committed) | gene → inheritance (`AR`/`XL`/`AR;XL`) + `severe` (yes/no). |
| `pipeline/carrier/tier1_clinvar.py` (new) | Per-person VCF → heterozygous P/LP carriers in recessive genes → `carrier_calls.<id>.json`. |
| `pipeline/carrier/couple_intersect.py` (new) | Two `carrier_calls.json` → `couple_report.json` (shared-gene risk, AR/XLR logic, tiering). Has its own CLI; Task 6 chains it after the per-person Tier-1 CLIs (no separate orchestrator needed for Phase 1). |
| `homelab sites/carrier/index.html` + Caddyfile/ingress snippet (new) | Static gated page rendering `couple_report.json`. |
| `tests/carrier/test_*.py` (new) | TDD for the lib, schema, map transform, tier1 filter, intersect. |
| `.gitignore` (modify) | Add `data/partner/`, `output/carrier/`. |

---

## Task 1: Extract `clinvar_lib.py` (reuse, no behaviour change)

**Files:**
- Create: `pipeline/clinvar_lib.py`
- Create: `tests/carrier/__init__.py`, `tests/carrier/test_clinvar_lib.py`
- Modify: `pipeline/06_clinvar_acmg.py` (replace local defs with imports)

- [ ] **Step 1: Write the failing test**

`tests/carrier/test_clinvar_lib.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/carrier/test_clinvar_lib.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.clinvar_lib'`

- [ ] **Step 3: Create `pipeline/clinvar_lib.py`**

Move the four pure functions out of `06_clinvar_acmg.py` verbatim, add `zygosity_of` (factored from the inline zygosity logic) and `iter_clinvar_matches`:
```python
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
    return 0


def is_pathogenic(clnsig):
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
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `python3 -m pytest tests/carrier/test_clinvar_lib.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Refactor `06_clinvar_acmg.py` to import from the lib**

In `pipeline/06_clinvar_acmg.py`: delete the local `parse_vcf_positions`, `parse_clinvar_info`, `review_status_stars`, `is_pathogenic` definitions, and add at the top (after the stdlib imports):
```python
from pipeline.clinvar_lib import (
    parse_vcf_positions, parse_clinvar_info, review_status_stars, is_pathogenic,
)
```
Leave the rest (the `ACMG_SF_V32`/`ACMG_CARRIER_PANEL` sets, `main()`, `iter_matches()`) untouched — it still calls the now-imported names.

- [ ] **Step 6: Verify the existing ClinVar tests still pass (no behaviour change)**

Run: `python3 -m pytest tests/wgs/test_clinvar_modes.py -q`
Expected: PASS (same as before the refactor)

- [ ] **Step 7: Commit**

```bash
git add pipeline/clinvar_lib.py pipeline/06_clinvar_acmg.py tests/carrier/__init__.py tests/carrier/test_clinvar_lib.py
git commit -m "refactor(clinvar): extract importable clinvar_lib from 06_clinvar_acmg"
```

---

## Task 2: Gene→inheritance map (CGD)

**Files:**
- Create: `pipeline/carrier/__init__.py`, `pipeline/carrier/build_inheritance_map.py`
- Create: `tests/carrier/test_inheritance_map.py`
- Generate + commit: `pipeline/carrier/data/gene_inheritance.tsv`

- [ ] **Step 1: Write the failing test** (pure transform only — no network)

`tests/carrier/test_inheritance_map.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/carrier/test_inheritance_map.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.carrier.build_inheritance_map'`

- [ ] **Step 3: Implement `pipeline/carrier/build_inheritance_map.py`**

```python
"""Build gene -> inheritance (AR/XL) + severe flag from the Clinical Genomic Database (CGD).

CGD: https://research.nhgri.nih.gov/CGD/download/txt/CGD.txt.gz
Columns: GENE, HGNC ID, ENTREZ GENE ID, CONDITION, INHERITANCE, AGE GROUP, ...
"""
import gzip
import io
import urllib.request
from pathlib import Path

CGD_URL = "https://research.nhgri.nih.gov/CGD/download/txt/CGD.txt.gz"
OUT = Path(__file__).resolve().parent / "data" / "gene_inheritance.tsv"
SEVERE_AGES = {"antenatal", "neonatal", "infancy", "childhood", "pediatric"}


def cgd_rows_to_map(rows):
    """rows: iterable of CGD columns (list). Return {gene: {inheritance, severe}}
    keeping only genes whose INHERITANCE mentions AR or XL. inheritance is the sorted
    set of recessive modes seen ('AR', 'XL', or 'AR;XL'); severe = any childhood-onset row."""
    agg = {}
    for r in rows:
        if len(r) < 6:
            continue
        gene, inh, age = r[0].strip(), r[4], r[5]
        modes = {m for m in ("AR", "XL") if m in inh}
        if not modes:
            continue
        severe = any(a in age.lower() for a in SEVERE_AGES)
        cur = agg.setdefault(gene, {"modes": set(), "severe": False})
        cur["modes"] |= modes
        cur["severe"] = cur["severe"] or severe
    return {g: {"inheritance": ";".join(sorted(v["modes"])), "severe": v["severe"]}
            for g, v in agg.items()}


def fetch_cgd_rows():
    with urllib.request.urlopen(CGD_URL, timeout=60) as resp:
        data = resp.read()
    text = gzip.GzipFile(fileobj=io.BytesIO(data)).read().decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        yield line.split("\t")


def build():
    m = cgd_rows_to_map(fetch_cgd_rows())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        f.write("gene\tinheritance\tsevere\n")
        for gene in sorted(m):
            f.write(f"{gene}\t{m[gene]['inheritance']}\t{'yes' if m[gene]['severe'] else 'no'}\n")
    return len(m)


if __name__ == "__main__":
    n = build()
    print(f"[build_inheritance_map] wrote {n} recessive genes -> {OUT}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/carrier/test_inheritance_map.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Generate the real map + commit it**

```bash
python3 pipeline/carrier/build_inheritance_map.py   # -> ~3-4k genes
head -3 pipeline/carrier/data/gene_inheritance.tsv
git add pipeline/carrier/__init__.py pipeline/carrier/build_inheritance_map.py \
        pipeline/carrier/data/gene_inheritance.tsv tests/carrier/test_inheritance_map.py
git commit -m "feat(carrier): gene->inheritance (AR/XL)+severe map from CGD"
```
Expected: header `gene  inheritance  severe`, several thousand rows, includes `CFTR AR yes`, `DMD XL yes`.

---

## Task 3: `schema.py` — carrier_call + couple_report

**Files:**
- Create: `pipeline/carrier/schema.py`, `tests/carrier/test_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/carrier/test_schema.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/carrier/test_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.carrier.schema'`

- [ ] **Step 3: Implement `pipeline/carrier/schema.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/carrier/test_schema.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/carrier/schema.py tests/carrier/test_schema.py
git commit -m "feat(carrier): carrier_call + couple_report schema"
```

---

## Task 4: `tier1_clinvar.py` — per-person carrier calling

**Files:**
- Create: `pipeline/carrier/tier1_clinvar.py`, `tests/carrier/test_tier1_clinvar.py`
- Create test fixtures: `tests/carrier/fixtures/person.vcf`, `tests/carrier/fixtures/clinvar.vcf`, `tests/carrier/fixtures/inheritance.tsv`

- [ ] **Step 1: Write the failing test + fixtures**

`tests/carrier/fixtures/inheritance.tsv`:
```
gene	inheritance	severe
CFTR	AR	yes
BRCA1	AD	no
DMD	XL	yes
```
`tests/carrier/fixtures/clinvar.vcf` (minimal; tab-separated):
```
##fileformat=VCFv4.1
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
7	100	rs1	G	A	.	.	CLNSIG=Pathogenic;CLNDN=Cystic_fibrosis;CLNREVSTAT=reviewed_by_expert_panel;GENEINFO=CFTR:1080
7	200	rs2	C	T	.	.	CLNSIG=Pathogenic;CLNDN=Cystic_fibrosis;CLNREVSTAT=reviewed_by_expert_panel;GENEINFO=CFTR:1080
17	300	rs3	A	G	.	.	CLNSIG=Pathogenic;CLNDN=Breast_cancer;CLNREVSTAT=reviewed_by_expert_panel;GENEINFO=BRCA1:672
```
`tests/carrier/fixtures/person.vcf` (het CFTR@100, homozygous CFTR@200, het BRCA1@300):
```
##fileformat=VCFv4.1
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO	FORMAT	SAMPLE
7	100	.	G	A	.	.	.	GT	0/1
7	200	.	C	T	.	.	.	GT	1/1
17	300	.	A	G	.	.	.	GT	0/1
```
`tests/carrier/test_tier1_clinvar.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/carrier/test_tier1_clinvar.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.carrier.tier1_clinvar'`

- [ ] **Step 3: Implement `pipeline/carrier/tier1_clinvar.py`**

```python
"""Tier-1 carrier calling: heterozygous ClinVar P/LP variants in recessive genes."""
import argparse
import csv
import datetime as _dt
import json
from pathlib import Path

from pipeline.clinvar_lib import parse_vcf_positions, iter_clinvar_matches
from pipeline.carrier.schema import CarrierCall


def load_inheritance(tsv_path):
    """Return {gene: {'inheritance': str, 'severe': bool}} for recessive genes."""
    out = {}
    with open(tsv_path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            out[row["gene"]] = {"inheritance": row["inheritance"],
                                "severe": row["severe"] == "yes"}
    return out


def _recessive_mode(inh):
    """Collapse an inheritance string to the carrier-relevant mode: 'XL' if X-linked
    else 'AR'."""
    return "XL" if "XL" in inh else "AR"


def call_carriers(vcf, clinvar, inheritance_tsv, min_stars=2):
    """Return list[CarrierCall]: heterozygous P/LP variants whose gene is recessive."""
    inheritance = load_inheritance(inheritance_tsv)
    user_vars = parse_vcf_positions(vcf)
    calls = []
    for m in iter_clinvar_matches(user_vars, clinvar, min_stars=min_stars):
        if m["zygosity"] != "heterozygous":      # carriers only (homozygous = affected)
            continue
        gene = m["gene"]
        if gene not in inheritance:               # recessive genes only
            continue
        calls.append(CarrierCall(
            gene=gene,
            condition=m["clndn"],
            inheritance=_recessive_mode(inheritance[gene]["inheritance"]),
            tier="snv",
            method="clinvar",
            variant=f"{m['chrom']}:{m['pos']}:{m['ref']}:{m['alt']}:{m['rsid']}",
            clnsig=m["clnsig"],
            stars=m["stars"],
            confidence="high" if m["stars"] >= 2 else "moderate",
        ))
    return calls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vcf", required=True)
    ap.add_argument("--clinvar", default="refs/clinvar_grch38.vcf.gz")
    ap.add_argument("--inheritance", default="pipeline/carrier/data/gene_inheritance.tsv")
    ap.add_argument("--person-id", required=True)
    ap.add_argument("--sex", required=True, choices=["XX", "XY"])
    ap.add_argument("--min-stars", type=int, default=2)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    calls = call_carriers(args.vcf, args.clinvar, args.inheritance, args.min_stars)
    payload = {
        "person_id": args.person_id,
        "sex": args.sex,
        "source": {"vcf": args.vcf, "bam": None},
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "calls": [c.to_dict() for c in calls],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(f"[tier1] {args.person_id}: {len(calls)} carrier calls -> {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/carrier/test_tier1_clinvar.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/carrier/tier1_clinvar.py tests/carrier/test_tier1_clinvar.py tests/carrier/fixtures/
git commit -m "feat(carrier): Tier-1 heterozygous ClinVar recessive carrier calling"
```

---

## Task 5: `couple_intersect.py` — shared-gene risk

**Files:**
- Create: `pipeline/carrier/couple_intersect.py`, `tests/carrier/test_couple_intersect.py`

- [ ] **Step 1: Write the failing test**

`tests/carrier/test_couple_intersect.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/carrier/test_couple_intersect.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.carrier.couple_intersect'`

- [ ] **Step 3: Implement `pipeline/carrier/couple_intersect.py`**

```python
"""Join two persons' carrier calls -> couple risk report."""
import argparse
import datetime as _dt
import json
from pathlib import Path

from pipeline.carrier.schema import CarrierCall, CoupleRisk, CoupleReport


def _tier(severe, stars_a, stars_b):
    m = min(stars_a, stars_b)
    if severe and m >= 2:
        return "serious"
    if m >= 2 or (severe and m >= 1):
        return "moderate"
    return "low"


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
        if "XL" in (a_by[gene][0].inheritance + b_by[gene][0].inheritance):
            continue  # handled below
        ca, cb = a_by[gene][0], b_by[gene][0]
        severe = severe_by_gene.get(gene, False)
        risks.append(CoupleRisk(
            gene=gene, condition=ca.condition, inheritance="AR", risk_pct=25,
            significance=_tier(severe, ca.stars, cb.stars),
            partner_A_variant=ca.variant, partner_B_variant=cb.variant,
            notes="Both partners carriers -> 25% of pregnancies affected."))

    # X-linked recessive: risk driven by the FEMALE partner's carrier status.
    if (sex_a == "XX") ^ (sex_b == "XX"):  # exactly one female partner (expected case)
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
                notes="Female partner carries an X-linked recessive variant -> 50% of sons affected."))

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
    import csv
    severe = {}
    with open(args.inheritance) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            severe[row["gene"]] = row["severe"] == "yes"
    calls_a, sex_a = _load(args.a)
    calls_b, sex_b = _load(args.b)
    rep = intersect(calls_a, sex_a, calls_b, sex_b, severe)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rep.to_dict(), indent=2))
    print(f"[intersect] {len(rep.couple_risks)} couple risks -> {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/carrier/test_couple_intersect.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/carrier/couple_intersect.py tests/carrier/test_couple_intersect.py
git commit -m "feat(carrier): couple intersect (AR 25%, X-linked sex-aware, tiering)"
```

---

## Task 6: `.gitignore` + end-to-end run (your genome + synthetic partner)

**Files:**
- Modify: `.gitignore`
- Create: `pipeline/carrier/make_synthetic_partner.py` (a tiny test-only generator)

- [ ] **Step 1: Add the gitignore entries**

Append to `.gitignore` under the personal-findings section:
```
# ── Couple carrier-screening (personal + partner data) ──
data/partner/
output/carrier/
```

- [ ] **Step 2: Verify the paths are ignored**

Run: `git check-ignore -v data/partner/x.vcf output/carrier/couple_report.json`
Expected: both lines print a `.gitignore` match.

- [ ] **Step 3: Write a synthetic-partner generator**

`pipeline/carrier/make_synthetic_partner.py` — emits a minimal VCF that is heterozygous at a couple of the same ClinVar P/LP recessive sites the user carries (so the intersect has something to show), for end-to-end validation only:
```python
"""Emit a synthetic partner VCF: heterozygous at the given chrom:pos:ref:alt sites."""
import argparse

def write_vcf(sites, out):
    with open(out, "w") as f:
        f.write("##fileformat=VCFv4.1\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE\n")
        for chrom, pos, ref, alt in sites:
            f.write(f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\t.\t.\tGT\t0/1\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", action="append", default=[], help="chrom:pos:ref:alt")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    write_vcf([tuple(s.split(":")) for s in args.site], args.out)
    print(f"wrote synthetic partner -> {args.out}")
```

- [ ] **Step 4: Run the whole pipeline end-to-end**

```bash
# person A = you (autosomes VCF already prepped)
python3 pipeline/carrier/tier1_clinvar.py --vcf data/wgs/SQ8TH633.wgs.pass.vcf.gz \
  --person-id A --sex XY --out output/carrier/carrier_calls.A.json
# pick two of your carrier sites to mirror in the synthetic partner:
python3 -c "import json;cs=json.load(open('output/carrier/carrier_calls.A.json'))['calls'];print('\n'.join(c['variant'] for c in cs[:2]))"
# person B = synthetic, heterozygous at two of A's sites (substitute the printed chrom:pos:ref:alt, dropping the rsid):
python3 pipeline/carrier/make_synthetic_partner.py --site <chrom:pos:ref:alt> --site <chrom:pos:ref:alt> \
  --out data/partner/synthetic.vcf
python3 pipeline/carrier/tier1_clinvar.py --vcf data/partner/synthetic.vcf \
  --person-id B --sex XX --out output/carrier/carrier_calls.B.json
python3 pipeline/carrier/couple_intersect.py --a output/carrier/carrier_calls.A.json \
  --b output/carrier/carrier_calls.B.json --out output/carrier/couple_report.json
python3 -c "import json;r=json.load(open('output/carrier/couple_report.json'));print('couple risks:',len(r['couple_risks']));print(r['couple_risks'][:2])"
```
Expected: A has a non-zero carrier count; the couple_report shows ≥1 shared-gene risk for the mirrored sites.

- [ ] **Step 5: Commit (code only — output/ and data/partner/ are gitignored)**

```bash
git add .gitignore pipeline/carrier/make_synthetic_partner.py
git commit -m "chore(carrier): gitignore partner/output + synthetic-partner generator"
```

---

## Task 7: Gated homelab page (`carrier.jlgao.net`)

**Files:**
- Create (homelab-server repo): `sites/carrier/index.html`
- Modify (homelab-server): the Caddyfile (a `carrier` site on an unused localhost port) + `cloudflared/config.yml` (an ingress entry `hostname: carrier.jlgao.net → http://127.0.0.1:<port>`)

> **USER ACTION (not automatable):** in the Cloudflare dashboard, add the `carrier.jlgao.net` DNS (proxied) and a Cloudflare Access application gating it to `georgegao888@gmail.com` (same policy as `health.jlgao.net`). The page must not be reachable without this — verify before putting any real partner data behind it.

- [ ] **Step 1: Write the static page**

`sites/carrier/index.html` — fetches `couple_report.json` (served alongside) and renders: a prominent disclaimer banner, the `serious` couple risks first (gene, condition, risk %, each partner's variant), `moderate`/`low` collapsed under a "show more" toggle, then single-carrier highlights and coverage caveats. Plain HTML + vanilla JS, no build step (matching the homelab's static-site pattern). Include verbatim disclaimer text:
> "Research-grade, not a clinical carrier screen. Confirm any finding with a clinical laboratory and a genetic counselor before making reproductive decisions. Your partner has consented to this analysis."

- [ ] **Step 2: Wire Caddy + cloudflared**

Add a Caddy site block serving `sites/carrier/` (the HTML + the gitignored `couple_report.json` copied in at publish time) on an unused localhost port, and a cloudflared ingress entry mapping `carrier.jlgao.net` to it — mirroring the existing `health.jlgao.net` entries in `cloudflared/config.yml`.

- [ ] **Step 3: Verify locally + at the edge**

```bash
curl -s -o /dev/null -w "local %{http_code}\n" http://127.0.0.1:<port>/         # 200
curl -s -o /dev/null -w "edge  %{http_code}\n" https://carrier.jlgao.net/        # 302 -> Access login
```
Expected: local 200; edge 302 (gated). **Do not publish real `couple_report.json` until the edge returns 302 (gating confirmed).**

- [ ] **Step 4: Commit (in homelab-server repo)**

```bash
cd ../homelab-server
git add sites/carrier/index.html Caddyfile cloudflared/config.yml
git commit -m "feat: gated carrier.jlgao.net couple-carrier report page"
```

---

## Final validation

- [ ] Run the full carrier test suite: `python3 -m pytest tests/carrier/ -q` → all pass.
- [ ] Run the full repo suite: `python3 -m pytest -q` → no regressions (incl. `tests/wgs/test_clinvar_modes.py`).
- [ ] Confirm `git status` shows no `output/carrier/` or `data/partner/` files tracked.

---

## Deferred to Phase 2 (not in this plan)
Special callers — SMA (SMN1 copy number), alpha-thalassemia (HBA deletions), Fragile X (FMR1 repeat), CFTR poly-T/TG — each adding `tier="special"` `CarrierCall`s. They need both partners' BAMs and GitHub-tool installs (SMNCopyNumberCaller, ExpansionHunter) requiring user approval.
