#!/usr/bin/env python3
"""
Compute the user's BMI PRS percentile against the East Asian (1000G phase 3 EAS)
reference distribution.

Approach:
1. Parse PGS000302 scoring file (rsID + effect_allele + effect_weight).
2. Look up 1000G EAS allele frequency for each rsID via myvariant.info.
3. Compute expected mean and SD under HWE for the East Asian population.
4. Use the user's raw PRS to compute z-score and percentile.

Output: output/raw_findings/prs_bmi_eas_percentile.tsv
"""
import csv
import gzip
import math
import sys
from pathlib import Path

import myvariant

ROOT = Path(__file__).resolve().parent.parent
SCORE_FILE = ROOT / 'refs' / 'pgs_cache' / 'PGS000302.txt.gz'
PER_VARIANT = ROOT / 'output' / 'raw_findings' / 'prs_per_variant.tsv'
OUT = ROOT / 'output' / 'raw_findings' / 'prs_bmi_eas_percentile.tsv'

USER_PRS_RAW = 106.4925  # from prs_scores.tsv


def parse_score(path):
    """Return list of (rsid, effect_allele, effect_weight)."""
    rows = []
    with gzip.open(path, 'rt') as f:
        header = None
        for line in f:
            if line.startswith('#'):
                continue
            cols = line.rstrip().split('\t')
            if header is None:
                header = cols
                i_rsid = header.index('rsID')
                i_chr  = header.index('chr_name')
                i_pos  = header.index('chr_position')
                i_ea   = header.index('effect_allele')
                i_w    = header.index('effect_weight')
                continue
            try:
                rsid = cols[i_rsid].strip()
                ea   = cols[i_ea].strip().upper()
                w    = float(cols[i_w])
            except (IndexError, ValueError):
                continue
            if not rsid or not rsid.startswith('rs'):
                continue
            rows.append((rsid, ea, w))
    return rows


def lookup_eas_af(rsids):
    """Look up 1000G EAS allele freq + corresponding alt allele via myvariant.info.
    Returns dict rsid -> {'alt': str, 'eas_af': float} (None if not found)."""
    sys.stderr.write(f'Looking up EAS AF for {len(rsids):,} rsIDs via myvariant.info ...\n')
    mv = myvariant.MyVariantInfo()

    out = {}
    # Batch in chunks of 500
    rsids_list = list(rsids)
    for i in range(0, len(rsids_list), 500):
        chunk = rsids_list[i:i + 500]
        sys.stderr.write(f'  batch {i//500 + 1}/{(len(rsids_list)+499)//500} ({len(chunk)} rsids)\n')
        # cadd.1000g.eas has overall EAS AF; we need per-allele
        # dbnsfp has per-allele 1000g freqs
        try:
            res = mv.getvariants(
                chunk,
                fields='dbsnp.alleles,cadd.1000g.eas,dbsnp.alt,dbnsfp.1000gp3.eas_af',
                assembly='hg38',
            )
        except Exception as e:
            sys.stderr.write(f'    error: {e}\n')
            continue
        for hit in res:
            if 'notfound' in hit:
                continue
            qrs = hit.get('query')
            af = None
            alt = None
            # Try dbnsfp.1000gp3.eas_af first (most reliable, per-alt-allele)
            dbn = hit.get('dbnsfp') or {}
            if isinstance(dbn, list):
                dbn = dbn[0] if dbn else {}
            kgp = dbn.get('1000gp3') or {}
            if 'eas_af' in kgp:
                af_val = kgp['eas_af']
                if isinstance(af_val, list):
                    af = af_val[0] if af_val else None
                else:
                    af = af_val
            # Try cadd.1000g.eas as fallback
            if af is None:
                cadd = hit.get('cadd') or {}
                kg = cadd.get('1000g') or {}
                if 'eas' in kg:
                    af = kg['eas']
            # Get alt allele
            dbsnp = hit.get('dbsnp') or {}
            if isinstance(dbsnp, list):
                dbsnp = dbsnp[0] if dbsnp else {}
            alt = dbsnp.get('alt')
            if isinstance(alt, list):
                alt = alt[0] if alt else None
            if af is not None:
                out[qrs] = {'eas_af': af, 'alt': alt}

    sys.stderr.write(f'  found EAS AF for {len(out):,}/{len(rsids):,} rsIDs\n')
    return out


def main():
    # Parse score file
    score_rows = parse_score(SCORE_FILE)
    sys.stderr.write(f'BMI score file: {len(score_rows):,} variants\n')

    rsids = {r[0] for r in score_rows}

    # Look up EAS AF
    eas = lookup_eas_af(rsids)

    # Compute expected_mean, expected_var
    # For each variant: assume HWE in EAS population.
    # If the effect allele matches the dbSNP alt: p = eas_af
    # If the effect allele is the ref (i.e., other allele): p = 1 - eas_af
    expected_mean = 0.0
    expected_var = 0.0
    n_used = 0
    n_no_af = 0
    n_strand_unclear = 0

    rows_out = []
    for rsid, ea, w in score_rows:
        info = eas.get(rsid)
        if not info:
            n_no_af += 1
            continue
        eas_af = info['eas_af']
        alt = info['alt']
        if alt is None:
            # Don't know which allele the AF refers to — assume eas_af is for the alt
            # which matches our PGS's effect_allele if it's the variant
            n_strand_unclear += 1
            p = eas_af
        elif ea.upper() == str(alt).upper():
            p = eas_af
        else:
            # effect allele is the ref; AF of effect allele = 1 - eas_af
            p = 1 - eas_af
        expected_mean += 2 * p * w
        expected_var  += 2 * p * (1 - p) * (w ** 2)
        n_used += 1
        rows_out.append((rsid, ea, w, eas_af, alt, p))

    expected_sd = math.sqrt(expected_var) if expected_var > 0 else 0
    z = (USER_PRS_RAW - expected_mean) / expected_sd if expected_sd > 0 else None
    pct = 0.5 * (1 + math.erf(z / math.sqrt(2))) * 100 if z is not None else None

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w') as f:
        f.write(f'# East Asian BMI PRS percentile estimate\n')
        f.write(f'# Score file: PGS000302 (Yengo 2018, BMI)\n')
        f.write(f'# Reference population: 1000G phase 3 EAS (504 samples: CHB+CHS+JPT+KHV+CDX)\n')
        f.write(f'# AF source: dbNSFP via myvariant.info\n')
        f.write(f'# user_raw_prs:    {USER_PRS_RAW}\n')
        f.write(f'# expected_mean:   {expected_mean:.4f}\n')
        f.write(f'# expected_sd:     {expected_sd:.4f}\n')
        f.write(f'# z_score:         {z}\n')
        f.write(f'# percentile:      {pct}\n')
        f.write(f'# n_variants_used: {n_used} / {len(score_rows)}\n')
        f.write(f'# n_no_eas_af:     {n_no_af}\n')
        f.write(f'# n_strand_unclear:{n_strand_unclear}\n')
        f.write(f'\nrsid\teffect_allele\tweight\teas_af\talt_allele\tp_effect_in_eas\n')
        for r in rows_out:
            f.write('\t'.join(map(str, r)) + '\n')

    print()
    print('=== East Asian BMI PRS percentile ===')
    print(f'  User raw PRS         : {USER_PRS_RAW:.4f}')
    print(f'  Expected mean (EAS)  : {expected_mean:.4f}')
    print(f'  Expected SD   (EAS)  : {expected_sd:.4f}')
    print(f'  Z-score              : {z:.3f}' if z is not None else '  Z-score: NA')
    if pct is not None:
        print(f'  Approx percentile    : {pct:.1f}th')
    print(f'  Variants used        : {n_used:,} / {len(score_rows):,}')
    print(f'  (no EAS AF)          : {n_no_af:,}')
    print(f'  (strand unclear)     : {n_strand_unclear:,}')
    print()
    print(f'Output: {OUT}')


if __name__ == '__main__':
    main()
