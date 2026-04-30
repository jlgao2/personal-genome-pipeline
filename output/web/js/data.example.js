/* =====================================================================
   data.example.js — TEMPLATE for the dashboard's data layer.
   Copy this to data.js and fill in your own findings. Or build a script
   (pipeline/13_build_report.py — TODO) that reads from
   output/raw_findings/*.tsv and rewrites data.js automatically.
   ===================================================================== */

export const META = {
  subject:    'Subject',
  generated:  '2026-04-29',
  source:     '23andMe v5 raw genotype + TOPMed-imputed VCF',
  build:      'GRCh38',
};

export const STATS = [
  { label: 'SNPs typed',         value: '—',       sub: '23andMe v5 chip, GRCh37' },
  { label: 'Imputed (R²≥0.8)',   value: '—',       sub: 'TOPMed r3 panel, GRCh38' },
  { label: 'Tier-A findings',    value: '—',       sub: 'Strong evidence + actionable' },
  { label: 'PGx flags',          value: '—',       sub: 'Drugs to discuss with prescriber' },
  { label: 'ACMG SF v3.2 hits',  value: '—',       sub: 'Verify with clinical NGS' },
  { label: 'Carrier (P/LP, 2★)', value: '—',       sub: 'For family planning' },
];

export const SECTIONS = [
  { id: 'actionable',  label: 'Actionable' },
  { id: 'drugs',       label: 'Drugs (PGx)' },
  { id: 'cardio',      label: 'Cardiology' },
  { id: 'carrier',     label: 'Carrier' },
  { id: 'nutrition',   label: 'Nutrition' },
  { id: 'lifestyle',   label: 'Lifestyle' },
  { id: 'prs',         label: 'PRS' },
  { id: 'crossref',    label: 'Clinical X-ref' },
  { id: 'reassuring',  label: 'Reassuring' },
  { id: 'limits',      label: 'Limits' },
];

export const FINDINGS = [
  /* Example structure — replace with your findings.
     section: one of the SECTIONS ids above.
     tier:    'A' | 'B' | 'C'  — A = strongest evidence, C = informational
     trait_allele = forward-strand allele that confers the trait
  */
  // {
  //   id: 'example-finding',
  //   section: 'drugs',
  //   tier: 'A',
  //   gene: 'YOUR_GENE',
  //   subtitle: 'Brief variant description',
  //   rsid: 'rs12345678',
  //   genotype: 'A/G',
  //   chrom: '1:12345678',
  //   trait_allele: 'A',
  //   headline: 'One-sentence summary of the finding.',
  //   body: `<p>Long-form explanation with <strong>emphasis</strong> and <code>codes</code>.</p>`,
  //   actions_label: 'Practical actions',
  //   actions: [
  //     'Action 1 with <strong>important</strong> bits.',
  //     'Action 2.',
  //   ],
  // },
];

export const PRS = [
  /* {
       pgs: 'PGS000018',
       trait: 'Coronary artery disease',
       direction: 'mild-positive',  // 'low' | 'neutral' | 'mild-positive' | 'high' | 'low-confidence'
       direction_label: 'Slightly elevated',
       raw: 0.46,
       coverage: '1,686,744 / 1,745,179 (97%)',
       headline: 'One-line direction read.',
       detail: 'Caveats, sources, top contributors.',
     }
  */
];

export const CROSSREF = [
  /* {
       confluence: 'Genotype predicted • Lab confirmed',
       headline: 'Vitamin D insufficient',
       pairs: [
         { label: 'Predicted', text: 'GC rs2282679 T/G → modestly lower 25(OH)D' },
         { label: 'Lab',       text: '25-Hydroxy Vitamin D = 23 ng/mL (target 30–50)' },
       ],
       takeaway: 'Start D3 2,000 IU/day with a meal. Recheck in 3 months.',
     }
  */
];

export const LABS = [
  /* { name: 'LDL', value: '77–83', unit: 'mg/dL', range: '60–129', flag: 'ok', note: '...' } */
];

export const PCP_AGENDA = [
  // 'Discuss item 1 at next visit.',
  // 'Discuss item 2.',
];
