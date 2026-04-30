/* =====================================================================
   DEMO DATA — synthetic findings for a fictional subject ("DEMO-0001").
   Plausible but not real. Used to illustrate dashboard features only.
   This file is loaded by the public GitHub Pages demo at:
     https://jlgao2.github.io/personal-genome-pipeline/
   ===================================================================== */

export const META = {
  subject:   'John Doe',
  generated: '2026-04-29',
  source:    'SYNTHETIC sample data — illustrative only',
  build:     'GRCh38',
};

export const STATS = [
  { label: 'SNPs typed',         value: '623,418', sub: 'Demo: 23andMe v5 chip' },
  { label: 'Imputed (R²≥0.8)',   value: '8.7M',    sub: 'Demo: TOPMed r3' },
  { label: 'Tier-A findings',    value: '7',       sub: 'Strong evidence + actionable' },
  { label: 'PGx flags',          value: '4',       sub: 'Drugs to discuss with prescriber' },
  { label: 'ACMG SF v3.2 hits',  value: '2',       sub: 'Need clinical verification' },
  { label: 'Carrier (P/LP, 2★)', value: '1',       sub: 'For family planning' },
  { label: 'Sex inferred',       value: 'Male',    sub: 'chrY genotyped' },
  { label: 'APOE',               value: 'ε3/ε4',   sub: 'One ε4 allele present' },
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

/* PRS tiles */
export const PRS = [
  {
    pgs: 'PGS000334',
    trait: "Alzheimer's disease",
    direction: 'high',
    direction_label: 'Above average',
    raw: 1.82,
    coverage: '22 / 22 (100%)',
    headline: 'APOE-driven elevation. Subject carries one ε4 allele (rs429358 T/C, rs7412 C/C → ε3/ε4).',
    detail: 'APOE ε4 contributes ~+1.13 to the score; remaining +0.69 from polygenic background. 2-3× lifetime AD risk vs ε3/ε3 baseline. Lifestyle modifiers (CV health, sleep, exercise) remain dominant for actual outcome.',
  },
  {
    pgs: 'PGS000018',
    trait: 'Coronary artery disease',
    direction: 'mild-positive',
    direction_label: 'Slightly elevated',
    raw: 0.58,
    coverage: '1,704,229 / 1,745,179 (98%)',
    headline: 'Modest polygenic CAD signal. No dominant single-locus driver.',
    detail: 'No 9p21 risk haplotype. Polygenic accumulation across many small-effect variants. Standard primary prevention applies.',
  },
  {
    pgs: 'PGS000061',
    trait: 'LDL cholesterol',
    direction: 'mild-positive',
    direction_label: 'Slightly elevated',
    raw: 0.41,
    coverage: '36 / 37 (97%)',
    headline: 'Genotype predicts modestly elevated LDL — track on lipid panels.',
    detail: 'Klarin 2018, 37 variants. Modest direction; will manifest more clearly on a fasting lipid panel.',
  },
  {
    pgs: 'PGS000041',
    trait: 'Major depressive disorder',
    direction: 'neutral',
    direction_label: 'Approximately average',
    raw: 0.08,
    coverage: '2,440 / 2,513 (97%)',
    headline: 'No predisposition either direction.',
    detail: 'Howard 2019. Near zero — no genotype-driven mood vulnerability flagged.',
  },
  {
    pgs: 'PGS000338',
    trait: 'Colorectal cancer',
    direction: 'low',
    direction_label: 'Below average',
    raw: -2.1,
    coverage: '95 / 97 (98%)',
    headline: 'Reassuring direction at 8q24 + other loci.',
    detail: 'Standard age-50 colonoscopy still recommended.',
  },
  {
    pgs: 'PGS000004',
    trait: 'Breast cancer',
    direction: 'mild-positive',
    direction_label: 'Slightly elevated',
    raw: 1.23,
    coverage: '309 / 313 (99%)',
    headline: 'Mild PRS elevation — relevant for any female first-degree relatives (sister, daughter).',
    detail: 'Mavaddat 313-variant score. Tier-1 PRS, well-validated. Subject is male, so personally low-impact, but the same haplotype passes to female children at 50% probability. Worth flagging for family.',
  },
  {
    pgs: 'PGS000302',
    trait: 'BMI',
    direction: 'low',
    direction_label: 'Below average',
    raw: 87.2,
    coverage: '953 / 962 (99%)',
    headline: 'Genotype predicts naturally lower BMI.',
    detail: 'Yengo 2018. ~22 PRS-units below population mean — leans toward genetically lean. Phenotype expression still depends on lifestyle.',
  },
  {
    pgs: 'PGS000014',
    trait: 'Type 2 diabetes',
    direction: 'low-confidence',
    direction_label: 'Low coverage',
    raw: 2.42,
    coverage: '622,118 / 6,917,436 (9%)',
    headline: 'Coverage too low — single-locus TCF7L2 finding more informative.',
    detail: 'Mahajan 2018 genome-wide score. Many low-frequency variants poorly imputed at R²≥0.8.',
  },
];

/* ── Findings ── */
export const FINDINGS = [
  /* ===== Pharmacogenomics ===== */
  {
    id: 'cyp2c19-rapid',
    section: 'drugs',
    tier: 'A',
    gene: 'CYP2C19',
    subtitle: '*1/*17 — Rapid metabolizer',
    rsid: 'rs12248560',
    genotype: 'C/T',
    chrom: '10:96521657',
    trait_allele: 'T',
    headline: 'Rapid metabolism of clopidogrel, citalopram, escitalopram, voriconazole. Standard doses may underdose.',
    body: `<p>You carry one copy of the CYP2C19 *17 gain-of-function variant. Combined with no *2 or *3 loss-of-function, the net phenotype is <strong>rapid metabolizer</strong>.</p>
    <p>Practical: clopidogrel works <em>better</em> than average (extra antiplatelet effect → slightly elevated bleeding risk at standard doses). Citalopram and escitalopram clear faster — may need higher doses for therapeutic effect.</p>`,
    actions_label: 'Drug-class adjustments',
    actions: [
      '<strong>Clopidogrel</strong> — standard doses fine; watch for bruising/bleeding.',
      '<strong>Citalopram, escitalopram</strong> — may need higher doses for efficacy.',
      '<strong>Voriconazole</strong> — therapeutic drug monitoring; may need upper-end dosing.',
      '<strong>PPIs</strong> — possibly less effective at standard dose; consider higher dose for H. pylori.',
    ],
  },
  {
    id: 'tpmt-low',
    section: 'drugs',
    tier: 'A',
    gene: 'TPMT',
    subtitle: '*1/*3A — Intermediate metabolizer',
    rsid: 'rs1142345 + rs1800460',
    genotype: 'T/C + C/T',
    chrom: '6:18130918, 6:18139228',
    trait_allele: '*3A',
    headline: 'Reduced thiopurine metabolism — must reduce dose if azathioprine, 6-MP, or thioguanine prescribed.',
    body: `<p>One *3A allele defining haplotype detected. Standard thiopurine doses → severe myelosuppression risk in heterozygotes.</p>`,
    actions_label: 'If thiopurines prescribed',
    actions: [
      'Start at <strong>30-70% standard dose</strong>.',
      'Frequent CBC monitoring during induction.',
      'Document on chart and pharmacy profile.',
    ],
  },
  {
    id: 'slco1b1-myopathy',
    section: 'drugs',
    tier: 'B',
    gene: 'SLCO1B1',
    subtitle: '*1/*5 — Decreased function',
    rsid: 'rs4149056',
    genotype: 'T/C',
    chrom: '12:21331549',
    trait_allele: 'C',
    headline: 'Moderate simvastatin myopathy risk. Use ≤40 mg/d simvastatin, or switch to atorvastatin/rosuvastatin.',
    body: `<p>One copy of the *5 (V174A) variant reduces hepatic statin uptake → higher plasma levels → muscle toxicity risk.</p>`,
    actions_label: 'Practical',
    actions: [
      'Avoid simvastatin >40 mg/d.',
      'Atorvastatin or rosuvastatin preferred (less SLCO1B1-dependent).',
    ],
  },

  /* ===== Cardiology ===== */
  {
    id: 'apoe-e4',
    section: 'cardio',
    tier: 'A',
    gene: 'APOE',
    subtitle: 'ε3/ε4 — One e4 allele',
    rsid: 'rs429358 + rs7412',
    genotype: 'T/C + C/C',
    chrom: '19:45411941, 19:45412079',
    trait_allele: 'C(e4)',
    headline: '~3× lifetime Alzheimer\'s risk vs ε3/ε3. Mildly elevated LDL tendency.',
    body: `<p>One copy of the ε4 allele (rs429358 = C). No ε2 (rs7412 = C/C). Net haplotype: <strong>ε3/ε4</strong>.</p>
    <p>AD risk: ~3× population baseline (compared to ε3/ε3). Modifiable risk factors (CV health, sleep, exercise, social engagement) still dominate eventual outcome.</p>`,
    actions_label: 'Practical',
    actions: [
      'Aggressive cardiovascular risk management — vascular health drives ε4-mediated AD risk.',
      'Aerobic exercise ≥150 min/week (strongest non-pharmacologic AD modifier).',
      'Mediterranean / MIND-style diet.',
      'Sleep hygiene — 7-9 hours; treat any sleep apnea promptly.',
    ],
  },
  {
    id: 'no-9p21',
    section: 'cardio',
    tier: 'C',
    gene: '9p21.3 / CDKN2B-AS1',
    subtitle: 'Reference haplotype',
    rsid: 'rs10757278 + rs1333049',
    genotype: 'A/A + G/G',
    chrom: '9:22124477, 9:22125503',
    trait_allele: '—',
    headline: 'No 9p21 risk haplotype. Standard CAD risk at this locus.',
    body: `<p>Reassuring at the strongest common-variant CAD locus.</p>`,
  },

  /* ===== Carrier ===== */
  {
    id: 'cftr-carrier',
    section: 'carrier',
    tier: 'A',
    gene: 'CFTR',
    subtitle: 'Carrier — F508del (cystic fibrosis)',
    rsid: 'rs113993960',
    genotype: 'heterozygous',
    chrom: '7:117559593',
    trait_allele: 'F508del',
    headline: 'Confirmed P/LP carrier (3-star ClinVar, expert-panel reviewed). Relevant for family planning.',
    body: `<p>One copy of the F508del variant — most common cause of cystic fibrosis. Asymptomatic in carriers. CF only manifests if both parents pass a CF-causing variant.</p>`,
    actions_label: 'Family planning',
    actions: [
      'Partner expanded carrier screening — covers ~280 recessive diseases including all CFTR.',
      'If both partners carry: discuss preimplantation genetic testing (PGT-M) or prenatal CVS/amnio.',
    ],
  },

  /* ===== Nutrition ===== */
  {
    id: 'mthfr-het',
    section: 'nutrition',
    tier: 'B',
    gene: 'MTHFR',
    subtitle: 'C677T heterozygous — ~30% reduced enzyme activity',
    rsid: 'rs1801133',
    genotype: 'G/A',
    chrom: '1:11856378',
    trait_allele: 'A',
    headline: 'Modest folate-pathway impact. Consider methylated folate over standard folic acid.',
    body: `<p>Heterozygous for MTHFR C677T (forward strand A). Mild homocysteine elevation possible under suboptimal nutrition.</p>`,
    actions_label: 'Practical',
    actions: [
      'Methylfolate (5-MTHF) 400 µg/day instead of folic acid.',
      'Adequate B12 + B6 (cofactors).',
      'Annual fasting homocysteine check is reasonable.',
    ],
  },
  {
    id: 'hfe-c282y',
    section: 'nutrition',
    tier: 'A',
    gene: 'HFE',
    subtitle: 'C282Y heterozygous + H63D heterozygous (compound)',
    rsid: 'rs1800562 + rs1799945',
    genotype: 'G/A + C/G',
    chrom: '6:26093141, 6:26091179',
    trait_allele: 'A + G',
    headline: 'Compound heterozygous — mild iron-overload risk. Annual ferritin monitoring.',
    body: `<p>One C282Y allele AND one H63D allele = "compound heterozygous." ~2-5% lifetime risk of clinically significant iron overload (versus ~80% for C282Y/C282Y homozygotes).</p>`,
    actions_label: 'Practical',
    actions: [
      'Annual <strong>ferritin + transferrin saturation</strong> on labs.',
      'Avoid iron supplementation unless documented deficiency.',
      'Limit vitamin C with iron-rich meals (enhances absorption).',
      'Moderate red meat consumption.',
    ],
  },
  {
    id: 'lactose-persistent',
    section: 'nutrition',
    tier: 'C',
    gene: 'MCM6/LCT',
    subtitle: 'Lactase persistent (A/A)',
    rsid: 'rs4988235',
    genotype: 'A/A',
    chrom: '2:136608646',
    trait_allele: 'A',
    headline: 'You can digest lactose lifelong.',
    body: `<p>Homozygous for the lactase-persistence allele.</p>`,
  },

  /* ===== Lifestyle ===== */
  {
    id: 'aldh2-normal',
    section: 'lifestyle',
    tier: 'C',
    gene: 'ALDH2',
    subtitle: 'Normal function (G/G)',
    rsid: 'rs671',
    genotype: 'G/G',
    chrom: '12:112241766',
    trait_allele: '—',
    headline: 'Standard alcohol metabolism. No flush response, no excess cancer risk from drinking.',
    body: `<p>No ALDH2*2 variant. Drinks alcohol without flushing or acetaldehyde accumulation.</p>`,
  },
  {
    id: 'caffeine-slow',
    section: 'lifestyle',
    tier: 'B',
    gene: 'CYP1A2',
    subtitle: 'rs762551 = C/C — Slow metabolizer (*1F/*1F)',
    rsid: 'rs762551',
    genotype: 'C/C',
    chrom: '15:75041917',
    trait_allele: 'C',
    headline: 'Slower caffeine clearance. Heavy coffee intake associated with higher MI risk in slow metabolizers.',
    body: `<p>Caffeine half-life ~6-9 hours instead of ~3-4. Studies link >3 cups/day in slow metabolizers to ~30% increased MI risk.</p>`,
    actions_label: 'Practical',
    actions: [
      'Limit to ≤2 cups coffee per day.',
      'No coffee after noon (sleep impact).',
      'Consider switching to lower-caffeine sources (green tea, matcha).',
    ],
  },
  {
    id: 'actn3-endurance',
    section: 'lifestyle',
    tier: 'C',
    gene: 'ACTN3',
    subtitle: 'XX — Endurance phenotype',
    rsid: 'rs1815739',
    genotype: 'T/T',
    chrom: '11:66328095',
    trait_allele: 'T',
    headline: 'No α-actinin-3 in fast-twitch muscle. Over-represented in elite endurance athletes.',
    body: `<p>Both alleles are the X (premature stop) variant. Approximately 18% of population. Both endurance and strength training work — bias is small in non-elite contexts.</p>`,
  },

  /* ===== Reassuring ===== */
  {
    id: 'reassuring-set',
    section: 'reassuring',
    tier: 'C',
    gene: 'F5 / FTO / TCF7L2 / G6PD',
    subtitle: 'No major-risk alleles',
    rsid: 'rs6025 + rs9939609 + rs7903146 + rs1050828',
    genotype: 'C/C + T/T + C/C + C/C',
    chrom: '—',
    trait_allele: '—',
    headline: 'Several common high-impact alleles you do not carry.',
    body: `<p>Specific common variants <strong>not</strong> in your genotype: Factor V Leiden (rs6025), FTO obesity allele (rs9939609), TCF7L2 T2D risk (rs7903146), G6PD A- deficiency (rs1050828). None of these absences are guarantees, but they're high-impact common alleles that aren't in play for you.</p>`,
  },

  /* ===== Limits ===== */
  {
    id: 'limits-rare',
    section: 'limits',
    tier: 'C',
    gene: 'BRCA1, BRCA2, MLH1/MSH2/MSH6/PMS2',
    subtitle: 'Rare-variant cancer screening',
    rsid: '—',
    genotype: '—',
    chrom: '—',
    trait_allele: '—',
    headline: 'Chip + imputation cannot reliably detect rare pathogenic variants in BRCA / Lynch.',
    body: `<p>Most pathogenic variants in these genes are rare and family-specific. If family history of breast/ovarian/pancreatic/prostate/colorectal cancer ≤60 years emerges, get a clinical NGS panel for a definitive answer.</p>`,
  },
  {
    id: 'limits-cyp2d6',
    section: 'limits',
    tier: 'C',
    gene: 'CYP2D6',
    subtitle: 'Cannot be called from chip data',
    rsid: '—',
    genotype: 'pending PharmCAT',
    chrom: '22q13.2',
    trait_allele: '—',
    headline: 'Copy-number / hybrid-allele gene. PharmCAT will likely report indeterminate.',
    body: `<p>If codeine, tramadol, tamoxifen, or psychiatric drugs become clinically relevant, get a clinical-grade PGx panel.</p>`,
  },
];

/* ── Cross-reference cards ── */
export const CROSSREF = [
  {
    confluence: 'Genotype + family history compound',
    headline: 'APOE ε4 + family history of late-onset dementia',
    pairs: [
      { label: 'Genotype', text: 'APOE ε3/ε4 → ~3× lifetime AD risk' },
      { label: 'Family hx', text: 'Maternal grandmother diagnosed at 78' },
      { label: 'Modifiers', text: 'Sleep, exercise, BP, lipid control all leverage-able' },
    ],
    takeaway: 'Lifestyle margin is wider than genetics. Aggressive CV health → AD prevention.',
  },
  {
    confluence: 'Genotype predicted • Lab convergence',
    headline: 'HFE compound het + ferritin trending high',
    pairs: [
      { label: 'Genotype', text: 'C282Y/H63D compound het → mild iron-overload risk' },
      { label: 'Recent lab', text: 'Ferritin 280 ng/mL (range 30-200, slightly elevated)' },
    ],
    takeaway: 'Confirm with transferrin saturation; avoid iron supplements; recheck in 6 months.',
  },
];

/* ── Lab values ── */
export const LABS = [
  { name: 'LDL Cholesterol',  value: '128',   unit: 'mg/dL',  range: '60–129', flag: 'ok',   note: 'Top of range. Monitor given mild PRS elevation.' },
  { name: 'HDL Cholesterol',  value: '52',    unit: 'mg/dL',  range: '40–80',  flag: 'ok',   note: 'Normal.' },
  { name: 'Triglycerides',    value: '95',    unit: 'mg/dL',  range: '30–149', flag: 'ok',   note: 'Normal.' },
  { name: 'Hemoglobin A1C',   value: '5.3',   unit: '%',      range: '<5.7',   flag: 'ok',   note: 'Normal.' },
  { name: 'Ferritin',         value: '280',   unit: 'ng/mL',  range: '30–200', flag: 'high', note: 'Slightly elevated — confirm with transferrin saturation.' },
  { name: 'TSH',              value: '1.42',  unit: 'µIU/mL', range: '0.30–4.00', flag: 'ok', note: 'Normal.' },
  { name: '25-OH Vitamin D',  value: '38',    unit: 'ng/mL',  range: '20–99',  flag: 'ok',   note: 'Within optimal 30–50.' },
  { name: 'BP',               value: '118/72',unit: 'mmHg',   range: '<120/80',flag: 'ok',   note: 'Optimal.' },
];

/* ── PCP follow-ups ── */
export const PCP_AGENDA = [
  'Add hsCRP, ApoB, Lp(a) to next lipid panel given mild CAD PRS elevation.',
  'Confirm elevated ferritin with transferrin saturation; HFE compound het noted.',
  'Discuss APOE ε3/ε4 implications — lifestyle modifiers for cognitive aging.',
  'Partner expanded carrier screening if family planning (CFTR F508del het).',
  'Continue annual A1C; current 5.3 is healthy.',
  'Photograph PGx flags: CYP2C19 RM (clopidogrel works strong, citalopram needs higher dose), TPMT *1/*3A (reduce thiopurines 30-70%), SLCO1B1 *5 het (avoid simvastatin >40mg/d).',
];
