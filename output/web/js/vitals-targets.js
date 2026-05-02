/* Genotype-driven target overlays for Vitals charts.
 * George Gao: 9p21 CAD risk + APOE ε3/ε4 (per imputed VCF) + HFE C282Y/H63D
 * compound het. Each target is plotted as a dashed line on the matching sparkline.
 */
export const VITAL_TARGETS = {
  bp_systolic: {
    value: 120,
    label: "<120 mmHg (CAD PRS + APOE ε4)",
  },
  bp_diastolic: {
    value: 80,
    label: "<80 mmHg (CAD PRS + APOE ε4)",
  },
  heart_rate_resting: {
    value: 60,
    label: "<60 bpm (cardiovascular fitness)",
  },
  vo2max: {
    value: 35,
    label: "≥35 mL/min·kg (CAD PRS — fitness floor)",
  },
  sleep_minutes: {
    value: 420,
    label: "≥7 h (APOE ε4 — amyloid clearance)",
  },
  exercise_minutes: {
    value: 30,
    label: "≥30 min/day (CAD PRS prevention)",
  },
};
