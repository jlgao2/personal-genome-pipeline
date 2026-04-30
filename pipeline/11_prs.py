#!/usr/bin/env python3
"""
Lightweight PRS calculator. For each PGS Catalog score:
1. Downloads the harmonized scoring file (rsID, effect_allele, effect_weight, [AF]).
2. Looks up each variant in the user's imputed VCF.
3. Computes weighted score: PRS = sum(dosage × effect_weight).
4. If allele-frequency column is present, computes z-score:
       expected_mean  = sum(2 × p × w)
       expected_var   = sum(2 × p × (1-p) × w^2)
       z              = (PRS - expected_mean) / sqrt(expected_var)
   then reports approximate percentile.

Output:
  output/raw_findings/prs_scores.tsv        (per-PGS results)
  output/raw_findings/prs_per_variant.tsv   (per-variant contributions, top scores)

Notes / caveats:
- PRS percentiles assume the reference allele-frequencies in the scoring file match
  the user's ancestry. They DO NOT — they're typically European-derived. East-Asian
  ancestry signals in this user's data (ALDH2*2 het, lactase non-persistence) mean
  that PRS percentiles for non-European-pure ancestry are INFLATED OR DEFLATED in
  unpredictable ways. Treat z-scores as ordinal (within-trait comparisons OK; across
  traits less so) rather than absolute.
"""
import argparse
import csv
import gzip
import io
import math
import os
import sys
import urllib.request
from pathlib import Path

# Curated, manageable-size PGS Catalog scores. Each:
# (PGS ID, trait label, brief description)
PGS_SCORES = [
    ('PGS000018', 'CAD',                  'Coronary artery disease — Khera 2018 (genome-wide, ~6M)'),
    ('PGS000014', 'Type 2 diabetes',      'T2D — Mahajan 2018 (~5K variants)'),
    ('PGS000016', 'Atrial fibrillation',  'AF — Khera 2018 (~6M variants)'),
    ('PGS000039', 'Stroke',               'Ischemic stroke — Abraham 2019 (~3K variants)'),
    ('PGS000334', 'Alzheimer disease',    "Alzheimer's — Lambert / Bellenguez (~25 variants)"),
    ('PGS000049', 'Prostate cancer',      'Prostate cancer — Conti 2021 (~600 variants)'),
    ('PGS000338', 'Colorectal cancer',    'Colorectal — Huyghe 2019 (~140 variants)'),
    ('PGS000041', 'Major depressive disorder', 'MDD — Howard 2019 (~6M variants)'),
    ('PGS000302', 'BMI',                  'BMI — Yengo 2018 (~2M variants)'),
    ('PGS000061', 'LDL cholesterol',      'LDL-C — Klarin 2018 (~2K variants)'),
]

PGS_BASE_URL = 'https://ftp.ebi.ac.uk/pub/databases/spot/pgs/scores/{pgs}/ScoringFiles/{pgs}_hmPOS_GRCh38.txt.gz'
PGS_FALLBACK_URL = 'https://ftp.ebi.ac.uk/pub/databases/spot/pgs/scores/{pgs}/ScoringFiles/{pgs}.txt.gz'


def download_score(pgs_id, cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f'{pgs_id}.txt.gz'
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return cache_file
    for url_tmpl in (PGS_BASE_URL, PGS_FALLBACK_URL):
        url = url_tmpl.format(pgs=pgs_id)
        try:
            sys.stderr.write(f'  fetching {url}\n')
            urllib.request.urlretrieve(url, cache_file)
            if cache_file.stat().st_size > 0:
                return cache_file
        except Exception as e:
            sys.stderr.write(f'    {e}\n')
            continue
    raise RuntimeError(f'Could not download {pgs_id}')


def parse_scoring_file(path):
    """Return list of (rsid, chrom, pos, effect_allele, other_allele, weight, allele_freq) tuples.
    Skip the metadata header lines starting with #."""
    open_fn = gzip.open if str(path).endswith('.gz') else open
    rows = []
    with open_fn(path, 'rt') as f:
        # Read header metadata
        meta = {}
        line = f.readline()
        while line.startswith('#'):
            if '=' in line:
                k, v = line[1:].rstrip().split('=', 1)
                meta[k] = v
            line = f.readline()
        # line is now the column header
        cols = line.rstrip().split('\t')
        # Possible column names per PGS scoring spec
        try:
            i_rsid   = cols.index('rsID') if 'rsID' in cols else (cols.index('hm_rsID') if 'hm_rsID' in cols else -1)
        except ValueError:
            i_rsid = -1
        try:
            i_chrom  = cols.index('hm_chr') if 'hm_chr' in cols else (cols.index('chr_name') if 'chr_name' in cols else -1)
        except ValueError:
            i_chrom = -1
        try:
            i_pos    = cols.index('hm_pos') if 'hm_pos' in cols else (cols.index('chr_position') if 'chr_position' in cols else -1)
        except ValueError:
            i_pos = -1
        i_effect = cols.index('effect_allele')
        try:
            i_other = cols.index('other_allele') if 'other_allele' in cols else (cols.index('hm_inferOtherAllele') if 'hm_inferOtherAllele' in cols else -1)
        except ValueError:
            i_other = -1
        i_weight = cols.index('effect_weight')
        i_freq = -1
        for c in ('allelefrequency_effect', 'effect_allele_frequency', 'allele_frequency_effect', 'eaf', 'frequency_effect_allele'):
            if c in cols:
                i_freq = cols.index(c)
                break

        for line in f:
            if not line.strip():
                continue
            r = line.rstrip().split('\t')
            try:
                rsid   = r[i_rsid] if i_rsid >= 0 and r[i_rsid] != '' else ''
                chrom  = r[i_chrom] if i_chrom >= 0 and r[i_chrom] != '' else ''
                try:
                    pos = int(r[i_pos]) if i_pos >= 0 and r[i_pos] != '' else 0
                except ValueError:
                    pos = 0
                ea     = r[i_effect].upper()
                oa     = r[i_other].upper() if i_other >= 0 and r[i_other] != '' else ''
                weight = float(r[i_weight])
                freq   = float(r[i_freq]) if i_freq >= 0 and r[i_freq] not in ('', 'NA') else None
            except (IndexError, ValueError):
                continue
            rows.append((rsid, chrom, pos, ea, oa, weight, freq))
    return meta, rows


def lookup_user_dosages(vcf_path, score_rows):
    """Single pass through the VCF — for any variant whose rsID OR chrom:pos matches
    a score row, record the user's dosage (number of effect-allele copies, 0/1/2)."""
    rsids = {r[0] for r in score_rows if r[0]}
    pos_keys = {(str(r[1]).replace('chr', ''), r[2]): r for r in score_rows if r[1] and r[2]}

    # Also key by rsid for fast lookup
    rsid_to_row = {r[0]: r for r in score_rows if r[0]}

    open_fn = gzip.open if vcf_path.endswith('.gz') else open
    found = {}
    n_lines = 0
    with open_fn(vcf_path, 'rt') as f:
        sample_idx = None
        for line in f:
            if line.startswith('##'):
                continue
            if line.startswith('#CHROM'):
                cols = line.rstrip().split('\t')
                if len(cols) > 9:
                    sample_idx = 9
                continue
            n_lines += 1
            cols = line.rstrip().split('\t')
            if len(cols) < 8:
                continue
            chrom = cols[0].replace('chr', '')
            try:
                pos = int(cols[1])
            except ValueError:
                continue
            rsid = cols[2]
            ref, alt = cols[3], cols[4]

            # Match by rsID first, then by position
            row = rsid_to_row.get(rsid) if rsid in rsids else pos_keys.get((chrom, pos))
            if not row:
                continue

            # Get GT
            if not sample_idx or len(cols) <= sample_idx:
                continue
            fmt = cols[8].split(':')
            vals = cols[sample_idx].split(':')
            if 'GT' not in fmt:
                continue
            gt = vals[fmt.index('GT')]

            # Decode genotype to allele letters
            parts = gt.replace('|', '/').split('/')
            user_alleles = []
            for p in parts:
                if p == '0':
                    user_alleles.append(ref)
                elif p == '1':
                    user_alleles.append(alt if alt != '.' else ref)
                else:
                    user_alleles.append('.')

            ea = row[3]
            n_effect = sum(1 for a in user_alleles if a == ea)
            # If the user's calls don't include the effect allele AT ALL but the variant
            # exists in the VCF, score 0. (Could be ref/ref, alt/alt where alt != ea, etc.)
            found[row[0] or f'{chrom}:{pos}'] = (n_effect, ref, alt, gt, user_alleles)

    return found, n_lines


def compute_score(score_rows, dosages):
    """Compute weighted PRS + z-score if AF available."""
    raw_score = 0.0
    expected_mean = 0.0
    expected_var = 0.0
    n_matched = 0
    n_with_af = 0
    contributions = []  # for top-variant report

    for r in score_rows:
        rsid, chrom, pos, ea, oa, weight, freq = r
        key = rsid or f'{chrom}:{pos}'
        d = dosages.get(key)
        if not d:
            continue
        n_effect = d[0]
        raw_score += n_effect * weight
        n_matched += 1
        contributions.append((rsid or f'{chrom}:{pos}', n_effect, weight, n_effect * weight, ea, d[3]))
        if freq is not None and 0 <= freq <= 1:
            expected_mean += 2 * freq * weight
            expected_var  += 2 * freq * (1 - freq) * (weight ** 2)
            n_with_af += 1

    # z-score is meaningful only if we have AF for at least 50% of matched variants
    z = None
    pct = None
    if n_with_af >= 0.5 * n_matched and expected_var > 0:
        z = (raw_score - expected_mean) / math.sqrt(expected_var)
        # Approximate percentile from z assuming normal
        pct = 0.5 * (1 + math.erf(z / math.sqrt(2))) * 100

    return {
        'raw_score': raw_score,
        'n_matched': n_matched,
        'n_total': len(score_rows),
        'pct_coverage': 100.0 * n_matched / max(1, len(score_rows)),
        'expected_mean': expected_mean,
        'expected_sd': math.sqrt(expected_var) if expected_var > 0 else None,
        'z_score': z,
        'percentile': pct,
        'n_with_af': n_with_af,
        'top_contributions': sorted(contributions, key=lambda x: abs(x[3]), reverse=True)[:5],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vcf', required=True)
    ap.add_argument('--cache', default='refs/pgs_cache')
    ap.add_argument('--out',   default='output/raw_findings/prs_scores.tsv')
    ap.add_argument('--per-variant-out', default='output/raw_findings/prs_per_variant.tsv')
    args = ap.parse_args()

    cache_dir = Path(args.cache)
    out_path  = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows_by_pgs = {}
    for (pgs, trait, desc) in PGS_SCORES:
        try:
            sys.stderr.write(f'\n=== {pgs}: {trait} ===\n')
            score_path = download_score(pgs, cache_dir)
            meta, score_rows = parse_scoring_file(score_path)
            sys.stderr.write(f'  loaded {len(score_rows):,} variants\n')
            rows_by_pgs[pgs] = (trait, desc, meta, score_rows)
        except Exception as e:
            sys.stderr.write(f'  SKIP: {e}\n')
            continue

    # Combine all variants for single-pass VCF lookup (efficiency)
    all_rows = []
    for pgs, (trait, desc, meta, rows) in rows_by_pgs.items():
        all_rows.extend(rows)
    sys.stderr.write(f'\n=== Total unique-ish variants across all PGS: {len(all_rows):,}\n')
    sys.stderr.write(f'Streaming VCF for dosage lookup ...\n')
    dosages, n_lines = lookup_user_dosages(args.vcf, all_rows)
    sys.stderr.write(f'  scanned {n_lines:,} VCF records, matched {len(dosages):,} of {len(all_rows):,} score variants\n')

    # Compute per-PGS scores
    with open(out_path, 'w') as f, open(args.per_variant_out, 'w') as fv:
        f.write('pgs_id\ttrait\tn_matched\tn_total\tpct_coverage\traw_score\texpected_mean\texpected_sd\tz_score\tpercentile_normal_approx\tn_with_af\tdescription\n')
        fv.write('pgs_id\ttrait\trsid_or_pos\tn_effect_alleles\teffect_weight\tcontribution\teffect_allele\tuser_gt\n')

        for pgs, (trait, desc, meta, rows) in rows_by_pgs.items():
            res = compute_score(rows, dosages)
            f.write(
                f'{pgs}\t{trait}\t{res["n_matched"]}\t{res["n_total"]}\t'
                f'{res["pct_coverage"]:.1f}\t{res["raw_score"]:.4f}\t'
                f'{res["expected_mean"]:.4f}\t'
                f'{res["expected_sd"] if res["expected_sd"] is not None else "NA"}\t'
                f'{res["z_score"] if res["z_score"] is not None else "NA"}\t'
                f'{res["percentile"] if res["percentile"] is not None else "NA"}\t'
                f'{res["n_with_af"]}\t{desc}\n'
            )
            for rsid, n_eff, w, contrib, ea, gt in res['top_contributions']:
                fv.write(f'{pgs}\t{trait}\t{rsid}\t{n_eff}\t{w:.4f}\t{contrib:.4f}\t{ea}\t{gt}\n')

    sys.stderr.write(f'\nWrote {out_path}\n')
    sys.stderr.write(f'Wrote {args.per_variant_out}\n')

    # Print short summary
    sys.stderr.write('\n=== Quick read ===\n')
    with open(out_path) as f:
        next(f)  # header
        for line in f:
            cols = line.rstrip().split('\t')
            pgs, trait = cols[0], cols[1]
            n_matched, n_total = cols[2], cols[3]
            cov = float(cols[4])
            raw = float(cols[5])
            z = cols[8]
            pct = cols[9]
            sys.stderr.write(f'  {pgs} {trait:25s}  matched {n_matched}/{n_total} ({cov:.0f}%)  raw={raw:.3f}  z={z}  ~pct={pct}\n')


if __name__ == '__main__':
    main()
