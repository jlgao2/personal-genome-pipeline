/* ── Genome Report — interactive renderer ── */

import {
  META, STATS, SECTIONS, FINDINGS, CROSSREF, LABS, PCP_AGENDA, PRS
} from './data.js';
import { VITALS, WORKOUTS, ACTION_LOOP, HEALTH_PROFILE, MED_ALERTS, ADAPTED_SESSION, SOCIAL, CALENDAR } from './data-vitals.js';
import { VITAL_TARGETS } from './vitals-targets.js';

/* ── Render hero stats ── */
function renderStats() {
  const root = document.getElementById('hero-stats');
  if (!root) return;
  root.innerHTML = STATS.map(s => `
    <div class="hero-stat">
      <div class="hero-stat-label">${s.label}</div>
      <div class="hero-stat-value">${s.value}</div>
      <div class="hero-stat-sub">${s.sub}</div>
    </div>
  `).join('');
}

/* ── Render top action cards (Tier-A only) ── */
function renderActions() {
  const root = document.getElementById('actions-grid');
  if (!root) return;
  const tierA = FINDINGS.filter(f => f.tier === 'A');
  root.innerHTML = tierA.map((f, i) => `
    <article class="action-card" data-id="${f.id}">
      <span class="action-tier" data-tier="${f.tier}">Tier ${f.tier}</span>
      <span class="action-rank">${String(i + 1).padStart(2, '0')} · ${sectionLabel(f.section)}</span>
      <h3 class="action-gene">${f.gene}</h3>
      <p class="action-headline">${f.headline}</p>
      <div class="action-tags">
        <span class="chip chip--accent">${f.subtitle}</span>
        ${f.section === 'drugs' ? '<span class="chip">For doctor</span>' : ''}
        ${f.section === 'cardio' ? '<span class="chip">Screening</span>' : ''}
        ${f.section === 'nutrition' ? '<span class="chip">Lifestyle</span>' : ''}
        ${f.section === 'carrier' ? '<span class="chip">Family planning</span>' : ''}
      </div>
    </article>
  `).join('');
  // Wire click → open the corresponding finding accordion
  root.querySelectorAll('.action-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = card.dataset.id;
      const f = FINDINGS.find(x => x.id === id);
      if (!f) return;
      const sectionId = f.section;
      const findingEl = document.querySelector(`.finding-block[data-id="${id}"]`);
      // Scroll to section, open block
      document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (findingEl) {
        findingEl.classList.add('is-open');
      }
    });
  });
}

function sectionLabel(id) {
  return SECTIONS.find(s => s.id === id)?.label || id;
}

/* ── Render findings sections ── */
function renderFindingsBySection() {
  SECTIONS.forEach(sec => {
    if (sec.id === 'actionable' || sec.id === 'crossref') return;  // handled separately
    const root = document.querySelector(`#${sec.id} .findings-list`);
    if (!root) return;
    const finds = FINDINGS.filter(f => f.section === sec.id);
    if (!finds.length) {
      root.innerHTML = `<p class="u-mono u-dim" style="padding:1rem 0;">No findings in this category.</p>`;
      return;
    }
    root.innerHTML = finds.map((f, i) => renderFindingBlock(f, i)).join('');
  });

  // Wire accordion toggles
  document.querySelectorAll('.finding-trigger').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('.finding-block').classList.toggle('is-open');
    });
  });
}

function renderFindingBlock(f, idx) {
  const num = String(idx + 1).padStart(2, '0');
  const sideRows = [
    f.rsid && { label: 'rsID', value: f.rsid },
    f.genotype && { label: 'Genotype', value: f.genotype, isTrait: f.tier === 'A' },
    f.chrom && { label: 'Position', value: f.chrom },
    f.trait_allele && f.trait_allele !== '—' && { label: 'Trait allele', value: f.trait_allele },
  ].filter(Boolean);

  return `
    <article class="finding-block" data-id="${f.id}" data-tier="${f.tier}" data-section="${f.section}">
      <button class="finding-trigger" type="button">
        <span class="finding-num">${num}</span>
        <span class="finding-title">${f.gene}<small>${f.subtitle}</small></span>
        <span class="finding-tier" data-tier="${f.tier}">Tier ${f.tier}</span>
        <span class="finding-toggle">+</span>
      </button>
      <div class="finding-body">
        <div class="finding-body-inner">
          <div class="finding-content">
            <div class="finding-prose">
              <p><em>${f.headline}</em></p>
              ${f.body || ''}
              ${f.actions ? `
                <div class="finding-actions">
                  <div class="finding-actions-label">${f.actions_label || 'Actions'}</div>
                  <ul>${f.actions.map(a => `<li>${a}</li>`).join('')}</ul>
                </div>` : ''
              }
            </div>
            <aside class="finding-side">
              ${sideRows.map(r => `
                <div class="finding-side-row">
                  <span class="finding-side-label">${r.label}</span>
                  <span class="finding-side-value ${r.isTrait ? 'gt-trait' : ''}">${r.value}</span>
                </div>
              `).join('')}
            </aside>
          </div>
        </div>
      </div>
    </article>
  `;
}

/* ── Render PRS cards ── */
function renderPRS() {
  const root = document.getElementById('prs-grid');
  if (!root) return;
  root.innerHTML = PRS.map(p => `
    <article class="prs-card">
      <span class="prs-card-direction" data-dir="${p.direction}">${p.direction_label}</span>
      <h3 class="prs-card-trait">${p.trait}</h3>
      <p class="prs-card-headline">${p.headline}</p>
      <p class="prs-card-detail">${p.detail}</p>
      <div class="prs-card-meta">
        <span>${p.pgs}</span>
        <span>raw <strong>${p.raw}</strong></span>
        <span>${p.coverage}</span>
      </div>
    </article>
  `).join('');
}

/* ── Render Health Profile panel ── */
function renderHealthProfile() {
  const root = document.getElementById('profile-grid');
  if (!root) return;
  if (!HEALTH_PROFILE) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No health profile loaded — drop one at <code>output/health_profile.json</code>.</p>';
    return;
  }
  const subj = HEALTH_PROFILE.profile_metadata?.subject || {};
  const vp = HEALTH_PROFILE.systemic_vulnerability_profile || {};
  const conds = HEALTH_PROFILE.active_conditions || {};
  const program = HEALTH_PROFILE.training_program || {};
  const meds = HEALTH_PROFILE.medications_to_avoid || [];
  const cur_meds = HEALTH_PROFILE.current_medications || [];
  const plan = HEALTH_PROFILE.action_plan_immediate || [];

  const cards = [];

  if (vp.core_pattern) {
    cards.push(`
      <article class="profile-card profile-card-warn">
        <div class="profile-card-name">Vulnerability profile</div>
        <div class="profile-card-headline">${vp.core_pattern}</div>
        <div>${(vp.affected_sites_confirmed || []).map(s => `<span class="profile-pill" data-status="active">${s}</span>`).join('')}</div>
      </article>
    `);
  }

  const allConds = [
    ...(conds.lower_extremity || []).map(c => ({ name: c, status: 'rehab' })),
    ...(conds.upper_extremity || []).map(c => ({ name: c, status: 'rehab' })),
  ];
  if (allConds.length) {
    cards.push(`
      <article class="profile-card">
        <div class="profile-card-name">Active conditions</div>
        <div>${allConds.map(c => `<span class="profile-pill" data-status="${c.status}">${c.name}</span>`).join('')}</div>
      </article>
    `);
  }

  if (meds.length) {
    cards.push(`
      <article class="profile-card profile-card-warn">
        <div class="profile-card-name">Avoid · prescriber alerts</div>
        <ul class="profile-list">
          ${meds.map(m => `<li><strong>${m.class}</strong> — ${m.reason}</li>`).join('')}
        </ul>
      </article>
    `);
  }

  if (cur_meds.length) {
    cards.push(`
      <article class="profile-card">
        <div class="profile-card-name">Current meds</div>
        <div>${cur_meds.map(m => `<span class="profile-pill" data-status="active">${m}</span>`).join('')}</div>
      </article>
    `);
  }

  if (plan.length) {
    cards.push(`
      <article class="profile-card">
        <div class="profile-card-name">This-week priorities</div>
        <ul class="profile-list">
          ${plan.map(p => `<li>${p}</li>`).join('')}
        </ul>
      </article>
    `);
  }

  if (subj.body_composition_note) {
    const goalNote = `${subj.age || 31} · ${subj.sex || 'M'} · 97kg → goal 90kg`;
    cards.push(`
      <article class="profile-card">
        <div class="profile-card-name">Subject</div>
        <div class="profile-card-headline">${goalNote}</div>
      </article>
    `);
  }

  root.innerHTML = cards.join('');
}

/* ── Render Today's Session (rehab + warmup + main + core) ── */
function todaysProgramKey() {
  const dow = new Date().getDay();
  return `Day ${((dow + 6) % 7) + 1}`;
}

/* The adaptive engine on the laptop produces ADAPTED_SESSION.
   This JS now just renders it; no decision logic in the browser. */

function renderTodaySession() {
  const root = document.getElementById('session-grid');
  if (!root) return;
  const protocol = HEALTH_PROFILE && HEALTH_PROFILE.daily_protocol;
  if (!protocol) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No daily protocol loaded.</p>';
    return;
  }
  const dayKey = todaysProgramKey();
  const day = protocol[dayKey];
  if (!day) {
    root.innerHTML = `<p style="padding:1rem;">Unknown day key: ${dayKey}</p>`;
    return;
  }
  const blocks = [];

  // Adaptive engine output — traffic light, intensity, swaps, removed, added, notes
  const adapted = ADAPTED_SESSION;
  if (adapted) {
    const tl = adapted.traffic_light || 'green';
    const im = adapted.intensity_modifier ?? 1.0;
    const imPct = Math.round(im * 100);
    blocks.push(`
      <div class="session-adjustments">
        <div class="session-traffic" data-light="${tl}">
          <span class="traffic-pill">${tl.toUpperCase()}</span>
          <span class="traffic-meta">${imPct}% intensity${adapted.intensity_reason ? ' · ' + adapted.intensity_reason : ''}</span>
        </div>
        ${(adapted.swaps || []).map(s => `
          <div class="session-adjustment" data-severity="warn">
            <span class="adj-msg">↻ Swap: <s>${s.original}</s> → <strong>${s.replacement}</strong></span>
            <span class="adj-suggest">${s.reason}</span>
          </div>`).join('')}
        ${(adapted.removed || []).map(r => `
          <div class="session-adjustment" data-severity="warn">
            <span class="adj-msg">✗ Skip: <s>${r.item}</s></span>
            <span class="adj-suggest">${r.reason}</span>
          </div>`).join('')}
        ${(adapted.added || []).map(a => `
          <div class="session-adjustment" data-severity="info">
            <span class="adj-msg">+ Add: <strong>${a.item}</strong></span>
            <span class="adj-suggest">${a.reason}</span>
          </div>`).join('')}
        ${(adapted.notes || []).map(n => `
          <div class="session-adjustment" data-severity="info">
            <span class="adj-msg">${n}</span>
          </div>`).join('')}
      </div>
    `);
  }

  blocks.push(`
    <div class="session-summary">
      <span class="day-tag">${dayKey}</span>${day.session}
    </div>
  `);
  const order = [
    ['Rehab',   day.rehab],
    ['Warmup',  day.warmup],
    ['Main',    day.main],
    ['Core',    day.core],
  ];
  const state = dailyState('session');
  for (const [name, items] of order) {
    if (!items || items.length === 0) {
      if (dayKey === 'Day 7') continue;
      blocks.push(`<article class="session-block empty"><div class="session-block-title">${name}</div><ul><li>—</li></ul></article>`);
      continue;
    }
    blocks.push(`
      <article class="session-block">
        <div class="session-block-title">${name}</div>
        <ul class="session-checklist">${items.map(i => {
          const id = `${name}:${i}`;
          const done = state.get(id);
          return `<li class="session-item ${done ? 'is-done' : ''}" data-id="${id.replace(/"/g,'&quot;')}" role="button" tabindex="0">
            <span class="session-item-check">${done ? '✓' : '○'}</span>
            <span class="session-item-text">${i}</span>
          </li>`;
        }).join('')}</ul>
      </article>
    `);
  }
  root.innerHTML = blocks.join('');
  root.querySelectorAll('.session-item').forEach(el => {
    el.addEventListener('click', () => {
      const id = el.dataset.id;
      state.set(id, !state.get(id));
      renderTodaySession();
    });
  });
}

/* ── Pre-workout checklist (interactive, persists in localStorage) ── */
function renderPrepChecklist() {
  const root = document.getElementById('prep-list');
  if (!root) return;
  const items = (HEALTH_PROFILE && HEALTH_PROFILE.prep_checklist_template) || [];
  if (items.length === 0) {
    root.innerHTML = '<li class="prep-item"><span class="prep-text">No checklist defined.</span></li>';
    return;
  }
  const today = new Date().toISOString().slice(0, 10);
  const storageKey = `prep_${today}`;
  let state = {};
  try { state = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch { state = {}; }
  root.innerHTML = items.map((label, i) => `
    <li class="prep-item ${state[i] ? 'done' : ''}" data-idx="${i}">
      <span class="prep-box"></span>
      <span class="prep-text">${label}</span>
    </li>
  `).join('');
  root.querySelectorAll('.prep-item').forEach(el => {
    el.addEventListener('click', () => {
      const idx = el.dataset.idx;
      state[idx] = !state[idx];
      localStorage.setItem(storageKey, JSON.stringify(state));
      el.classList.toggle('done', !!state[idx]);
    });
  });
}

/* ── Pharmacovigilance — flag risky meds ── */
function renderMedAlerts() {
  const root = document.getElementById('med-alerts-list');
  if (!root) return;
  const alerts = (HEALTH_PROFILE && HEALTH_PROFILE.medications_to_avoid) || [];
  // Active medications come from HEALTH_PROFILE.current_medications (self-reported)
  // PLUS WORKOUTS-style events that might come from FHIR with type='medication'.
  // For now we cross-check the self-reported list (FHIR-sourced med events
  // can be added later when MyChart bundle lands).
  const current = (HEALTH_PROFILE && HEALTH_PROFILE.current_medications) || [];

  const flagged = [];
  for (const med of current) {
    for (const a of alerts) {
      const cls = (a.class || '').toLowerCase();
      const m = med.toLowerCase();
      // Crude string match on key fragments
      const danger_terms = {
        'fluoroquinolone': ['cipro', 'levaquin', 'levofloxacin', 'ciprofloxacin', 'moxifloxacin'],
        'statin': ['statin', 'atorvastatin', 'rosuvastatin', 'simvastatin', 'pravastatin'],
        'corticosteroid': ['prednisone', 'prednisolone', 'dexamethasone', 'methylprednisolone'],
        'nsaid': ['ibuprofen', 'naproxen', 'diclofenac', 'celecoxib', 'meloxicam'],
      };
      for (const [k, terms] of Object.entries(danger_terms)) {
        if (cls.includes(k) && terms.some(t => m.includes(t))) {
          flagged.push({ med, reason: a.reason, severity: 'high' });
        }
      }
    }
  }

  // Also fold in FHIR-detected medication alerts (from MyChart) — these trump
  // the self-reported list because they're confirmed prescriptions.
  for (const a of (MED_ALERTS || [])) {
    flagged.push({ med: a.medication, reason: a.reason || a.drug_class || '', severity: 'high', source: 'mychart' });
  }

  if (flagged.length === 0) {
    root.innerHTML = `
      <article class="med-alert">
        <div class="med-alert-clear">No alerts</div>
        <div class="med-alert-rationale">Your current medications (${current.length ? current.join(', ') : 'none on file'}) don't trigger any tendon-vulnerability flags. MyChart medications also clean.</div>
      </article>
      ${alerts.length ? `
        <article class="med-alert" data-severity="medium">
          <div class="med-alert-name">Heads-up — ${alerts.length} drug classes to mention to any new prescriber</div>
          <div class="med-alert-rationale">${alerts.map(a => `<strong>${a.class}</strong> (${a.reason})`).join(' · ')}</div>
        </article>
      ` : ''}
    `;
    return;
  }
  root.innerHTML = flagged.map(f => `
    <article class="med-alert" data-severity="${f.severity}">
      <div>
        <span class="med-alert-name">${f.med}</span>
        <span class="med-alert-flag">⚠ flag</span>
        ${f.source === 'mychart' ? '<span class="med-alert-flag" style="color:var(--accent)">via MyChart</span>' : ''}
      </div>
      <div class="med-alert-rationale">${f.reason}</div>
    </article>
  `).join('');
}

/* ── Weekly Recap (last 7 vs prior 7) ── */
function renderWeeklyRecap() {
  const root = document.getElementById('recap-grid');
  if (!root) return;

  const now = Date.now();
  const day = 86_400_000;
  const window7 = (start_offset, days) => {
    const start = now - (start_offset + days) * day;
    const end   = now - start_offset * day;
    return [start, end];
  };
  const [last_start, last_end] = window7(0, 7);
  const [prev_start, prev_end] = window7(7, 7);

  const inWindow = (ts, start, end) => {
    const t = new Date(ts).getTime();
    return t >= start && t < end;
  };

  // RHR — average from VITALS.heart_rate_resting series
  const rhr_series = (VITALS.heart_rate_resting && VITALS.heart_rate_resting.series) || [];
  const rhr_in = (s, e) => {
    const vs = rhr_series.filter(([d]) => inWindow(d, s, e)).map(([, v]) => v);
    return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
  };
  const rhr_last = rhr_in(last_start, last_end);
  const rhr_prev = rhr_in(prev_start, prev_end);

  // Sleep — average from VITALS.sleep_minutes series
  const sleep_series = (VITALS.sleep_minutes && VITALS.sleep_minutes.series) || [];
  const sleep_in = (s, e) => {
    const vs = sleep_series.filter(([d]) => inWindow(d, s, e)).map(([, v]) => v);
    return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
  };
  const sleep_last = sleep_in(last_start, last_end);
  const sleep_prev = sleep_in(prev_start, prev_end);

  // Workouts — count from WORKOUTS in window
  const wout_in = (s, e) => WORKOUTS.filter(w => inWindow(w.ts_start, s, e)).length;
  const wout_last = wout_in(last_start, last_end);
  const wout_prev = wout_in(prev_start, prev_end);

  // Total training load
  const tl_in = (s, e) => WORKOUTS
    .filter(w => inWindow(w.ts_start, s, e))
    .reduce((sum, w) => sum + (w.training_load || 0), 0);
  const tl_last = tl_in(last_start, last_end);
  const tl_prev = tl_in(prev_start, prev_end);

  const cells = [
    {
      name: 'Sleep avg', unit: 'min',
      curr: sleep_last, prev: sleep_prev,
      better: 'higher',
    },
    {
      name: 'Resting HR', unit: 'bpm',
      curr: rhr_last, prev: rhr_prev,
      better: 'lower',
    },
    {
      name: 'Workouts',  unit: '',
      curr: wout_last, prev: wout_prev,
      better: 'higher',
    },
    {
      name: 'Training load', unit: '',
      curr: tl_last, prev: tl_prev,
      better: 'higher',
    },
  ];

  root.innerHTML = cells.map(c => {
    let trend = 'same';
    let delta_text = '—';
    if (c.curr != null && c.prev != null) {
      const diff = c.curr - c.prev;
      const dpct = c.prev !== 0 ? (diff / c.prev) * 100 : 0;
      if (Math.abs(dpct) < 3) trend = 'same';
      else {
        const positive_delta = (c.better === 'higher' && diff > 0) || (c.better === 'lower' && diff < 0);
        trend = positive_delta ? 'better' : 'worse';
      }
      const sign = diff > 0 ? '+' : '';
      delta_text = `${sign}${diff.toFixed(c.name === 'Workouts' ? 0 : 1)} vs prior 7d`;
    }
    const value = c.curr == null ? '—' : c.curr.toFixed(c.name === 'Workouts' ? 0 : 1);
    return `
      <article class="recap-cell">
        <div class="recap-cell-name">${c.name}</div>
        <div class="recap-cell-value">${value}<span style="font-size:0.5em; margin-left:0.3em; color:var(--fg-mute);">${c.unit}</span></div>
        <div class="recap-cell-delta" data-trend="${trend}">${delta_text}</div>
      </article>
    `;
  }).join('');
}

/* ── Render Supplement Stack ── */
const TIMING_ORDER = ['morning', '30-60 min pre-workout', 'with lunch', 'afternoon', 'evening', 'before bed'];
const TIMING_LABELS = {
  'morning': 'Morning',
  '30-60 min pre-workout': 'Pre-workout',
  'with lunch': 'Lunch',
  'afternoon': 'Afternoon',
  'evening': 'Evening',
  'before bed': 'Before bed',
};

function renderStack() {
  const root = document.getElementById('stack-grid');
  if (!root) return;
  const stack = (HEALTH_PROFILE && HEALTH_PROFILE.supplement_stack) || [];
  if (stack.length === 0) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No supplement protocol defined yet.</p>';
    return;
  }
  // Group by timing
  const byTiming = {};
  for (const item of stack) {
    const t = item.timing || 'unscheduled';
    (byTiming[t] = byTiming[t] || []).push(item);
  }
  const sortedTimings = Object.keys(byTiming).sort((a, b) => {
    const ai = TIMING_ORDER.indexOf(a);
    const bi = TIMING_ORDER.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
  const state = dailyState('stack');
  root.innerHTML = sortedTimings.map(t => {
    const items = byTiming[t];
    const label = TIMING_LABELS[t] || t;
    const food = items.some(i => i.with_food) ? 'with food' : 'fasted';
    return `
      <article class="stack-group">
        <div class="stack-group-header">
          <span class="stack-time-label">${label}</span>
          <span class="stack-time-meta">${food}</span>
        </div>
        ${items.map(i => {
          const id = i.name;
          const done = state.get(id);
          return `
          <div class="stack-item ${done ? 'is-done' : ''}" data-id="${id}" tabindex="0" role="button" aria-pressed="${done}">
            <span class="stack-item-check">${done ? '✓' : '○'}</span>
            <div class="stack-item-name" data-evidence="${i.evidence || 'moderate'}">${i.name}</div>
            <div class="stack-item-dose">${i.dose || ''}</div>
            <div class="stack-item-rationale">${i.rationale || ''}</div>
            ${(i.links && i.links.length) ? `<div class="stack-item-links">${i.links.map(l => `<span class="stack-item-link">→ ${l}</span>`).join('')}</div>` : ''}
          </div>
          `;
        }).join('')}
      </article>
    `;
  }).join('');
  root.querySelectorAll('.stack-item').forEach(el => {
    el.addEventListener('click', () => {
      const id = el.dataset.id;
      state.set(id, !state.get(id));
      renderStack();
    });
  });
}

/* ── Render Action Loop (genome × measured × today) ── */
const SAMPLE_TYPE_LABELS = {
  heart_rate_resting: 'Resting HR',
  vo2max:             'VO₂ Max',
  weight:             'Weight',
  bp_systolic:        'BP Systolic',
  bp_diastolic:       'BP Diastolic',
  sleep_minutes:      'Sleep',
  exercise_minutes:   'Exercise',
  homocysteine:       'Homocysteine',
  ldl_cholesterol:    'LDL',
  warfarin_dose_response:   'Warfarin',
  clopidogrel_response:     'Clopidogrel',
};

const SAMPLE_TYPE_UNITS = {
  heart_rate_resting: 'bpm',
  vo2max:             'mL/min·kg',
  weight:             'lb',
  bp_systolic:        'mmHg',
  bp_diastolic:       'mmHg',
  sleep_minutes:      'min',
  exercise_minutes:   'min',
  homocysteine:       'µmol/L',
  ldl_cholesterol:    'mg/dL',
};

function actionState(latest, target, dir) {
  if (latest == null || target == null) return 'none';
  // 'increase' = elevated risk → we want value BELOW target
  // 'decrease' = depressed function → we want value AT/ABOVE target
  // 'stable'   = monitor; treat 10% drift as warning
  const ratio = latest / target;
  if (dir === 'increase') {
    if (ratio < 0.95) return 'ok';
    if (ratio < 1.10) return 'drift';
    return 'off';
  }
  if (dir === 'decrease') {
    if (ratio >= 1.0)  return 'ok';
    if (ratio >= 0.85) return 'drift';
    return 'off';
  }
  if (Math.abs(1 - ratio) < 0.05) return 'ok';
  if (Math.abs(1 - ratio) < 0.15) return 'drift';
  return 'off';
}

/* ── Hero strip — ONE sentence, tap to expand ── */
function renderHeroCard() {
  const root = document.getElementById('hero-card-body');
  if (!root) return;

  const stateRank = { 'off': 0, 'drift': 1, 'ok': 2, 'none': 3 };
  const sorted = (ACTION_LOOP || []).map(c => ({
    card: c,
    state: actionState(c.latest_value, c.target_value, c.expected_direction),
  })).sort((a, b) => stateRank[a.state] - stateRank[b.state]);
  const worst = sorted[0];

  let sentence, detail, state;
  if (!worst || worst.state === 'ok' || worst.state === 'none') {
    const dayKey = todaysProgramKey();
    const session = HEALTH_PROFILE?.daily_protocol?.[dayKey]?.session || '—';
    sentence = `All clear. Today: ${session}.`;
    detail = 'No vitals off-target. Adhere to the prescribed program.';
    state = 'ok';
  } else {
    const c = worst.card;
    const label = SAMPLE_TYPE_LABELS[c.sample_type] || c.sample_type;
    const unit = SAMPLE_TYPE_UNITS[c.sample_type] || '';
    const actual = c.latest_value != null ? `${c.latest_value.toFixed(1)} ${unit}`.trim() : '—';
    const target = c.target_value != null ? `${c.target_value} ${unit}`.trim() : '?';
    const verb = c.expected_direction === 'increase' ? '<' : '≥';
    sentence = `${c.gene || 'PRS'}: ${label} ${actual} (target ${verb} ${target}).`;
    detail = c.takeaway || c.finding_summary || '';
    state = worst.state === 'off' ? 'warn' : 'drift';
  }

  root.innerHTML = `
    <button class="hero-strip" data-state="${state}" aria-expanded="false">
      <span class="hero-strip-eyebrow">NOW</span>
      <span class="hero-strip-sentence">${sentence}</span>
      <span class="hero-strip-toggle">▾</span>
    </button>
    <div class="hero-strip-detail" hidden>
      <p>${detail}</p>
    </div>
  `;
  const btn = root.querySelector('.hero-strip');
  const det = root.querySelector('.hero-strip-detail');
  btn?.addEventListener('click', () => {
    const isOpen = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!isOpen));
    det.hidden = isOpen;
  });
}

/* ── Adherence chip — did Garmin record a session matching today's prescription? ── */
function renderAdherenceChip() {
  const slot = document.getElementById('session-adherence');
  if (!slot) return;
  const dow = new Date().getDay();
  const dayKey = `Day ${((dow + 6) % 7) + 1}`;
  const protocol = HEALTH_PROFILE?.daily_protocol?.[dayKey];
  if (!protocol) return;

  // Day 7 = rest — no expectation
  if (dayKey === 'Day 7') {
    slot.innerHTML = `<span class="adherence-chip" data-status="rest">rest day</span>`;
    return;
  }

  // Match today's workouts in WORKOUTS array
  const todayStart = new Date(); todayStart.setHours(0, 0, 0, 0);
  const todayEnd = new Date(todayStart); todayEnd.setDate(todayEnd.getDate() + 1);
  const todays = (WORKOUTS || []).filter(w => {
    const t = new Date(w.ts_start);
    return t >= todayStart && t < todayEnd;
  });

  // Sport-to-program match. Strength days (1-4) accept anything that looks
  // like a workout (Garmin logs strength as 'STRENGTH_TRAINING' or just 'GENERIC').
  // Yoga (5) needs a yoga sport. Sport day (6) accepts most physical activity.
  const sports = todays.map(w => (w.sport || '').toUpperCase());
  let matched = false;
  if (['Day 1','Day 2','Day 3','Day 4'].includes(dayKey)) {
    matched = sports.some(s => /(STRENGTH|TRAINING|GENERIC|FITNESS|INDOOR|CARDIO)/i.test(s));
  } else if (dayKey === 'Day 5') {
    matched = sports.some(s => /(YOGA|MEDITATION|PILATES|MOBILITY)/i.test(s));
  } else if (dayKey === 'Day 6') {
    matched = sports.some(s => /(TENNIS|CYCLING|SWIMMING|HIKING|BADMINTON|GOLF|SAILING|SKI|CLIMBING|PADDLE)/i.test(s));
  }

  // Decide pending vs missed by hour-of-day
  const hour = new Date().getHours();
  if (matched) {
    slot.innerHTML = `<span class="adherence-chip" data-status="done">✓ done via Garmin</span>`;
  } else if (hour < 20) {
    slot.innerHTML = `<span class="adherence-chip" data-status="pending">⏱ pending</span>`;
  } else {
    slot.innerHTML = `<span class="adherence-chip" data-status="missed">✗ no match yet</span>`;
  }
}

/* ── Vision statement (hand-authored) ── */
function renderVision() {
  const root = document.getElementById('vision-statement');
  if (!root) return;
  const s = HEALTH_PROFILE?.vision_statement;
  if (!s) {
    root.innerHTML = '<em style="color:var(--fg-dim);">Add a vision_statement field to health_profile.json.</em>';
    return;
  }
  root.textContent = s;
}

/* ── Goals with progress bars ── */
function renderGoals() {
  const root = document.getElementById('goals-list');
  if (!root) return;
  const goals = HEALTH_PROFILE?.goals || [];
  if (goals.length === 0) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No goals defined yet — add a goals[] array to health_profile.json.</p>';
    return;
  }
  const today = new Date();
  const overrides = persistentState('goal_current');  // user-edited current values
  root.innerHTML = goals.map(g => {
    const override = overrides.get(g.name);
    const current = override != null ? override : g.current;
    let pct = 0;
    let state = 'pending';
    if (current != null && g.baseline != null && g.target != null) {
      const total = g.target - g.baseline;
      const done = current - g.baseline;
      pct = total !== 0 ? Math.max(0, Math.min(100, (done / total) * 100)) : 0;
      if (g.deadline) {
        const start = new Date('2026-05-01').getTime();
        const end = new Date(g.deadline).getTime();
        if (end > start) {
          const elapsed = (today.getTime() - start) / (end - start);
          const expectedPct = elapsed * 100;
          if (pct >= expectedPct) state = 'ahead';
          else if (pct < expectedPct - 15) state = 'behind';
          else state = 'pending';
        }
      }
    }
    const dl = g.deadline ? new Date(g.deadline).toLocaleDateString('en-US', {month:'short', year:'2-digit'}) : '—';
    const cur = current != null ? `${current}` : '—';
    const tgt = g.target != null ? `${g.target}` : '—';
    const id = (g.name || '').replace(/"/g,'&quot;');
    return `
      <div class="goal-row" data-name="${id}">
        <div class="goal-name">${g.name} ${override != null ? '<span class="goal-edited">·edited</span>' : ''}</div>
        <div class="goal-meta">
          <button class="goal-edit-btn" data-action="edit-current" data-name="${id}">${cur}</button>
          → ${tgt} ${g.units || ''} · by ${dl}
        </div>
        <div class="goal-bar"><div class="goal-bar-fill" data-state="${state}" style="width:${pct.toFixed(0)}%"></div></div>
        <div class="goal-detail">${g.note || ''}</div>
      </div>
    `;
  }).join('');
  // Wire edit buttons — inline prompt to update current value
  root.querySelectorAll('[data-action="edit-current"]').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.name;
      const g = goals.find(x => x.name === name);
      const cur = overrides.get(name) ?? g?.current ?? '';
      const next = prompt(`Update current value for "${name}" (units: ${g?.units || ''}). Leave blank to clear override.`, cur);
      if (next === null) return;
      const trimmed = next.trim();
      if (trimmed === '') overrides.set(name, false);  // clear
      else {
        const num = parseFloat(trimmed);
        if (!Number.isNaN(num)) overrides.set(name, num);
      }
      renderGoals();
    });
  });
}

/* ── Roadmap (responsive: timeline desktop, sections mobile) ── */
function renderRoadmap() {
  const root = document.getElementById('roadmap-grid');
  if (!root) return;
  const blocks = [
    { tick: '0',     title: 'Now · this week',  items: HEALTH_PROFILE?.action_plan_immediate || [] },
    { tick: '4-8w',  title: 'Block 2 · 4-8w',   items: HEALTH_PROFILE?.action_plan_short_term_4_to_8_weeks || [] },
    { tick: '2-3mo', title: 'Block 3 · 2-3mo',  items: HEALTH_PROFILE?.action_plan_medium_term_2_to_3_months || [] },
    { tick: '∞',     title: 'Ongoing',          items: HEALTH_PROFILE?.action_plan_ongoing || [] },
  ];
  const state = persistentState('roadmap_done');
  root.innerHTML = blocks.map(b => `
    <article class="roadmap-block">
      <span class="roadmap-block-tick">${b.tick}</span>
      <span class="roadmap-block-title">${b.title}</span>
      <ul class="roadmap-checklist">${b.items.length
        ? b.items.map(i => {
            const id = `${b.tick}:${i}`;
            const done = state.get(id);
            return `<li class="roadmap-item ${done ? 'is-done' : ''}" data-id="${id.replace(/"/g,'&quot;')}" role="button" tabindex="0">
              <span class="roadmap-item-check">${done ? '✓' : '○'}</span>
              <span class="roadmap-item-text">${i}</span>
            </li>`;
          }).join('')
        : '<li style="opacity:0.5;">—</li>'}</ul>
    </article>
  `).join('');
  root.querySelectorAll('.roadmap-item').forEach(el => {
    el.addEventListener('click', () => {
      const id = el.dataset.id;
      state.set(id, !state.get(id));
      renderRoadmap();
    });
  });
}

/* ── Streak / contribution graph (last 12 weeks: sleep + workouts) ── */
function renderStreak() {
  const root = document.getElementById('streak-graph');
  if (!root) return;

  const now = new Date();
  const days = 84; // 12 weeks
  const cells = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    cells.push(d);
  }
  const dKey = d => d.toISOString().slice(0, 10);

  // Sleep: green if ≥420 min (7h), partial if 360-420, miss if <360, future if no data.
  const sleepSeries = (VITALS.sleep_minutes && VITALS.sleep_minutes.series) || [];
  const sleepMap = Object.fromEntries(sleepSeries.map(([d, v]) => [d, v]));
  const sleepRow = cells.map(d => {
    const v = sleepMap[dKey(d)];
    if (v == null) return 'future';
    if (v >= 420) return 'hit';
    if (v >= 360) return 'partial';
    return 'miss';
  });

  // Workouts: hit if ≥1 workout that day, miss if Day 7 (rest) green by default.
  const workoutSet = new Set((WORKOUTS || []).map(w => (w.ts_start || '').slice(0, 10)));
  const workoutRow = cells.map(d => {
    const dayNum = ((d.getDay() + 6) % 7) + 1;  // Mon=1..Sun=7
    if (dayNum === 7) return 'hit';  // rest day = expected
    return workoutSet.has(dKey(d)) ? 'hit' : 'miss';
  });

  const cellHTML = states => states.map(s =>
    `<div class="streak-cell" data-state="${s}"></div>`
  ).join('');

  root.innerHTML = `
    <div class="streak-row">
      <span class="streak-row-label">Sleep ≥7h</span>
      <div class="streak-cells">${cellHTML(sleepRow)}</div>
    </div>
    <div class="streak-row">
      <span class="streak-row-label">Workout</span>
      <div class="streak-cells">${cellHTML(workoutRow)}</div>
    </div>
    <div class="streak-legend">
      <span class="lg-hit">hit</span>
      <span class="lg-partial">partial</span>
      <span class="lg-miss">miss</span>
    </div>
  `;
}

/* ── Med reference list (avoid drugs — static) ── */
function renderMedReference() {
  const root = document.getElementById('med-reference-list');
  if (!root) return;
  const refs = HEALTH_PROFILE?.medications_to_avoid || [];
  if (refs.length === 0) {
    root.innerHTML = '<li>No reference list configured.</li>';
    return;
  }
  root.innerHTML = refs.map(r => `
    <li>
      <span class="ref-class">${r.class}</span>
      <span class="ref-reason">${r.reason}</span>
    </li>
  `).join('');
}

/* ── Social: Reach Out + Birthdays ── */
function attentionTier(score) {
  if (score == null) return 'low';
  if (score >= 60) return 'high';
  if (score >= 30) return 'medium';
  return 'low';
}

function renderReachOut() {
  const root = document.getElementById('reach-out-list');
  if (!root) return;
  const rows = (SOCIAL && SOCIAL.reach_out) || [];
  if (rows.length === 0) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No social data — run <code>refresh.sh</code> with the social-media-graph repo present.</p>';
    return;
  }
  root.innerHTML = rows.map(p => {
    const tier = attentionTier(p.attention_score);
    const since = p.days_since_last != null
      ? `${p.days_since_last}d since last (${p.last_msg_from || '?'})`
      : '—';
    const topics = (p.topics || []).slice(0, 5);
    return `
      <article class="reach-out-row">
        <div class="ro-name">${p.name || '(unknown)'}</div>
        <div class="ro-attention" data-tier="${tier}">attn ${p.attention_score ?? '—'}</div>
        <div class="ro-since">${since}</div>
        ${p.about_what ? `<div class="ro-about">${p.about_what}</div>` : ''}
        ${topics.length ? `<div class="ro-topics">${topics.map(t => `<span class="ro-topic">${t}</span>`).join('')}</div>` : ''}
        ${p.last_excerpt ? `<div class="ro-excerpt">"${p.last_excerpt}"</div>` : ''}
      </article>
    `;
  }).join('');
}

function renderBirthdays() {
  const root = document.getElementById('birthdays-list');
  if (!root) return;
  const rows = (SOCIAL && SOCIAL.birthdays) || [];
  if (rows.length === 0) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No birthdays in next 60 days.</p>';
    return;
  }
  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  root.innerHTML = rows.map(b => {
    const dateStr = (b.month && b.day) ? `${monthNames[b.month-1]} ${b.day}` : '—';
    const days = b.days_until != null ? `in ${b.days_until}d` : '';
    const yk = b.year_known ? '' : '· year unknown';
    return `
      <article class="birthday-row">
        <div class="bd-name">${b.name || '(unknown)'}</div>
        <div class="bd-when">${dateStr} · ${days}</div>
        <div class="bd-detail">${yk}</div>
      </article>
    `;
  }).join('');
}

/* ── Upcoming calendar events (Google) ── */
function renderCalendar() {
  const root = document.getElementById('calendar-list');
  if (!root) return;
  const events = CALENDAR || [];
  if (events.length === 0) {
    root.innerHTML = `<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">
      No calendar connected. One-time setup:
      <code>python3 -m pipeline.parsers.gcal auth</code>
      after dropping <code>google_credentials.json</code> at
      <code>~/.config/personal-data/</code>.</p>`;
    return;
  }
  const fmt = ts => {
    if (!ts) return '—';
    const d = new Date(ts);
    if (ts.length === 10) return d.toLocaleDateString('en-US', {month:'short', day:'numeric'}) + ' · all day';
    return d.toLocaleDateString('en-US', {month:'short', day:'numeric'}) +
           ' · ' + d.toLocaleTimeString('en-US', {hour:'numeric', minute:'2-digit'});
  };
  root.innerHTML = events.slice(0, 10).map(e => `
    <article class="cal-row">
      <div class="cal-when">${fmt(e.start)}</div>
      <div class="cal-summary">${e.summary || '(no title)'}</div>
      ${e.location ? `<div class="cal-location">${e.location}</div>` : ''}
      ${e.url ? `<a class="cal-open" href="${e.url}" target="_blank">open ↗</a>` : ''}
    </article>
  `).join('');
}

/* ── Stateful tracking helpers ──
 * Supps + session items reset daily. Roadmap items + goal current values
 * persist forever (until user un-checks).
 */
function todayKey() { return new Date().toISOString().slice(0, 10); }

function dailyState(prefix) {
  const key = `${prefix}_${todayKey()}`;
  let state = {};
  try { state = JSON.parse(localStorage.getItem(key) || '{}'); } catch { state = {}; }
  return {
    get: id => !!state[id],
    set: (id, v) => {
      state[id] = !!v;
      try { localStorage.setItem(key, JSON.stringify(state)); } catch {}
    },
  };
}

function persistentState(key) {
  let state = {};
  try { state = JSON.parse(localStorage.getItem(key) || '{}'); } catch { state = {}; }
  return {
    get: id => state[id],
    set: (id, v) => {
      if (v == null || v === false) delete state[id];
      else state[id] = v;
      try { localStorage.setItem(key, JSON.stringify(state)); } catch {}
    },
  };
}

/* ── Reach out today — top 3 on the Now tab ── */
function renderReachOutToday() {
  const root = document.getElementById('reach-out-today-list');
  if (!root) return;
  const all = (SOCIAL && SOCIAL.reach_out) || [];
  if (all.length === 0) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No social data — add the social-media-graph repo to refresh.sh.</p>';
    return;
  }
  // Skip people already reached-out today (state)
  const state = dailyState('reachout');
  const top = all.filter(p => !state.get(p.id || p.name)).slice(0, 3);
  if (top.length === 0) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--rune);">All today\'s reach-outs marked done. ✓</p>';
    return;
  }
  root.innerHTML = top.map(p => {
    const tier = attentionTier(p.attention_score);
    const since = p.days_since_last != null
      ? `${p.days_since_last}d since last (${p.last_msg_from || '?'})`
      : '—';
    const id = p.id || p.name;
    const topics = (p.topics || []).slice(0, 5);
    return `
      <article class="reach-out-row" data-pid="${id}">
        <div class="ro-name">${p.name || '(unknown)'}</div>
        <div class="ro-attention" data-tier="${tier}">attn ${p.attention_score ?? '—'}</div>
        <div class="ro-since">${since}</div>
        ${p.about_what ? `<div class="ro-about">${p.about_what}</div>` : ''}
        ${topics.length ? `<div class="ro-topics">${topics.map(t => `<span class="ro-topic">${t}</span>`).join('')}</div>` : ''}
        ${p.last_excerpt ? `<div class="ro-excerpt">"${p.last_excerpt}"</div>` : ''}
        <div class="ro-actions">
          <button class="ro-btn ro-btn-done" data-action="done">Mark done</button>
          <button class="ro-btn" data-action="copy" data-name="${(p.name||'').replace(/"/g,'&quot;')}">Copy name</button>
          ${p.about_what ? `<button class="ro-btn" data-action="prompt">Reflection prompt</button>` : ''}
        </div>
      </article>
    `;
  }).join('');
  // Wire up action buttons
  root.querySelectorAll('.reach-out-row').forEach(row => {
    const id = row.dataset.pid;
    row.querySelector('[data-action="done"]')?.addEventListener('click', () => {
      state.set(id, true);
      renderReachOutToday();
    });
    row.querySelector('[data-action="copy"]')?.addEventListener('click', e => {
      navigator.clipboard?.writeText(e.target.dataset.name || '');
      e.target.textContent = '✓ copied';
      setTimeout(() => e.target.textContent = 'Copy name', 1200);
    });
    row.querySelector('[data-action="prompt"]')?.addEventListener('click', () => {
      const prompts = [
        'What were they working on last time you spoke?',
        'What\'s one specific thing they\'d care to hear about your week?',
        'What\'s a 30-second voice memo you could send instead of a text?',
      ];
      alert(prompts[Math.floor(Math.random() * prompts.length)]);
    });
  });
}

/* ── Tab switching ── */
function wireTabs() {
  const setTab = (tabName) => {
    document.body.dataset.activeTab = tabName;
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.toggle('is-active', b.dataset.tab === tabName);
    });
    document.querySelectorAll('.rail-section[data-tab-children]').forEach(n => {
      n.hidden = n.dataset.tabChildren !== tabName;
    });
    // Reset scroll to the top so each tab feels like a fresh view
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => setTab(btn.dataset.tab));
  });

  // Default to Interventions
  setTab('interventions');
}

function renderActionLoop() {
  const root = document.getElementById('action-loop-grid');
  if (!root) return;
  if (!ACTION_LOOP || ACTION_LOOP.length === 0) {
    root.innerHTML = '<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No cross-refs yet — populate <code>output/cross_refs.yaml</code> and run <code>refresh.sh</code>.</p>';
    return;
  }
  const fmtVal = (v, unit) => v == null ? '—' : `${v.toFixed(1)} ${unit || ''}`.trim();
  const fmtAge = ts => {
    if (!ts) return 'no data';
    const days = Math.floor((Date.now() - new Date(ts).getTime()) / 86_400_000);
    if (days === 0) return 'today';
    if (days === 1) return 'yesterday';
    if (days < 7) return `${days}d ago`;
    if (days < 60) return `${Math.floor(days/7)}w ago`;
    return `${Math.floor(days/30)}mo ago`;
  };
  root.innerHTML = ACTION_LOOP.map(c => {
    const label = SAMPLE_TYPE_LABELS[c.sample_type] || c.sample_type;
    const unit = SAMPLE_TYPE_UNITS[c.sample_type] || '';
    const state = actionState(c.latest_value, c.target_value, c.expected_direction);
    const target = c.target_value != null ? `${c.target_value} ${unit}`.trim() : 'conditional';
    const arrow = c.expected_direction === 'increase' ? '↓' : c.expected_direction === 'decrease' ? '↑' : '=';
    return `
      <article class="action-card" data-state="${state}">
        <div class="action-card-header">
          <span class="gene">${c.gene || 'PRS'}</span>
          <span>${c.finding_tier || ''}</span>
        </div>
        <div class="action-card-finding">${c.finding_summary || c.finding_id}</div>
        <div class="action-card-meter" data-state="${state}">
          <span>${label}</span>
          <span class="actual">${fmtVal(c.latest_value, unit)}</span>
          <span>${arrow} ${target}</span>
        </div>
        <div class="action-card-takeaway">${c.takeaway || ''}</div>
        <div class="action-card-stale">${fmtAge(c.latest_ts)}</div>
      </article>
    `;
  }).join('');
}

/* ── Render Vitals (HealthKit time-series cards) ── */
const VITAL_DISPLAY = {
  heart_rate_resting: { label: "Resting HR",    unit: "bpm",        decimals: 0 },
  vo2max:             { label: "VO₂ Max",  unit: "mL/min·kg", decimals: 1 },
  weight:             { label: "Weight",        unit: "lb",         decimals: 1 },
  bp_systolic:        { label: "BP Systolic",   unit: "mmHg",       decimals: 0 },
  bp_diastolic:       { label: "BP Diastolic",  unit: "mmHg",       decimals: 0 },
  sleep_minutes:      { label: "Sleep",         unit: "min/night",  decimals: 0 },
  exercise_minutes:   { label: "Exercise",      unit: "min/day",    decimals: 0 },
};

function vitalSpark(series, target) {
  if (!series || series.length < 2) return "";
  const W = 320, H = 56, PAD = 4;
  const xs = series.map((_, i) => i);
  const ys = series.map(([, v]) => v);
  const minY = Math.min(...ys, target ?? Infinity);
  const maxY = Math.max(...ys, target ?? -Infinity);
  const rangeY = (maxY - minY) || 1;
  const xToPx = i => PAD + (i / (xs.length - 1)) * (W - 2 * PAD);
  const yToPx = v => H - PAD - ((v - minY) / rangeY) * (H - 2 * PAD);

  const pathD = series
    .map(([, v], i) => `${i === 0 ? "M" : "L"} ${xToPx(i).toFixed(1)} ${yToPx(v).toFixed(1)}`)
    .join(" ");

  const targetLine = target != null
    ? `<line class="vital-spark-target" x1="${PAD}" y1="${yToPx(target).toFixed(1)}"
                                         x2="${W - PAD}" y2="${yToPx(target).toFixed(1)}"/>
       <text class="vital-spark-target-label" x="${W - PAD}" y="${(yToPx(target) - 2).toFixed(1)}"
             text-anchor="end">target ${target}</text>`
    : "";

  return `
    <svg class="vital-spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      ${targetLine}
      <path class="vital-spark-line" d="${pathD}"/>
    </svg>
  `;
}

function renderVitals() {
  const root = document.getElementById("vitals-grid");
  if (!root) return;
  if (!VITALS || Object.keys(VITALS).length === 0) {
    root.innerHTML =
      `<p style="padding:1rem; font-family: var(--font-mono); font-size: 0.65rem;
                 color: var(--fg-dim);">
         No HealthKit data yet — drop your export.zip in <code>data/raw/healthkit/</code>
         and run <code>refresh.sh</code>.
       </p>`;
    return;
  }
  const cards = Object.entries(VITALS).map(([key, data]) => {
    const display = VITAL_DISPLAY[key] || { label: key, unit: "", decimals: 1 };
    const target = VITAL_TARGETS[key] || null;
    const fixed = data.latest != null ? data.latest.toFixed(display.decimals) : "—";
    const trendArrow = { up: "↑", down: "↓", flat: "→" }[data.trend] || "";
    return `
      <article class="vital-card">
        <div class="vital-card-name">${display.label}</div>
        <div>
          <span class="vital-card-value">${fixed}</span>
          <span class="vital-card-unit">${display.unit}</span>
        </div>
        ${vitalSpark(data.series, target ? target.value : null)}
        <div class="vital-card-trend" data-trend="${data.trend || 'flat'}">
          ${trendArrow} ${data.trend || "flat"} · last 30d
        </div>
        ${target ? `<div class="vital-card-target">Target: ${target.label}</div>` : ""}
      </article>
    `;
  }).join("");
  root.innerHTML = cards;
}

/* ── Render Workouts (Garmin activities) ── */
function renderWorkouts() {
  const root = document.getElementById('workouts-list');
  if (!root) return;
  if (!WORKOUTS || WORKOUTS.length === 0) {
    root.innerHTML = `<p style="padding:1rem; font-family:var(--font-mono); font-size:0.65rem; color:var(--fg-dim);">No workouts yet — drop a Garmin export in <code>data/raw/garmin/</code> and run <code>refresh.sh</code>.</p>`;
    return;
  }
  const formatDate = ts => new Date(ts).toLocaleDateString('en-US', {month:'short', day:'numeric', year:'2-digit'});
  const formatDuration = s => {
    if (s == null) return '';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };
  const zoneBar = zones => {
    if (!zones) return '';
    const total = Object.values(zones).reduce((a, b) => a + b, 0) || 1;
    return '<div class="hr-zones">' + [0,1,2,3,4,5].map(z => {
      const v = zones[`zone_${z}`] || 0;
      return v > 0 ? `<div class="hr-zone" data-z="${z}" style="width:${(100 * v / total).toFixed(1)}%"></div>` : '';
    }).join('') + '</div>';
  };
  root.innerHTML = WORKOUTS.map(w => `
    <article class="workout-card">
      <div class="workout-date">${formatDate(w.ts_start)}</div>
      <div>
        <span class="workout-label">${w.label}</span>
        <span class="workout-sport">${w.sport || ''}</span>
        ${zoneBar(w.hr_zones)}
      </div>
      <div class="workout-stats">
        ${formatDuration(w.duration_s)}
        ${w.avg_hr ? ' · ' + Math.round(w.avg_hr) + ' bpm avg' : ''}
        ${w.training_load ? ' · TL ' + Math.round(w.training_load) : ''}
      </div>
    </article>
  `).join('');
}

/* ── Render cross-reference cards ── */
function renderCrossRef() {
  const root = document.getElementById('crossref-grid');
  if (!root) return;
  root.innerHTML = CROSSREF.map(c => `
    <article class="crossref-card">
      <span class="crossref-confluence">${c.confluence}</span>
      <h3 class="crossref-headline">${c.headline}</h3>
      <div class="crossref-pair">
        ${c.pairs.map(p => `
          <span class="crossref-pair-label">${p.label}</span>
          <span>${p.text}</span>
        `).join('')}
      </div>
      <p class="crossref-takeaway"><strong>→</strong> ${c.takeaway}</p>
    </article>
  `).join('');
}

/* ── Render lab table ── */
function renderLabs() {
  const tbody = document.querySelector('#labs-table tbody');
  if (!tbody) return;
  tbody.innerHTML = LABS.map(l => `
    <tr>
      <td>${l.name}</td>
      <td class="lab-flag-${l.flag}">${l.value}</td>
      <td class="u-dim">${l.unit}</td>
      <td class="u-dim">${l.range}</td>
      <td>${l.note}</td>
    </tr>
  `).join('');
}

/* ── Render PCP agenda checklist ── */
function renderAgenda() {
  const root = document.getElementById('pcp-agenda');
  if (!root) return;
  root.innerHTML = PCP_AGENDA.map((t, i) => `
    <li class="check-item" data-idx="${i}">
      <span class="check-box"></span>
      <span class="check-label">${t}</span>
    </li>
  `).join('');
  // Persist checked state in localStorage
  const KEY = 'genome_report_pcp_checked';
  const saved = JSON.parse(localStorage.getItem(KEY) || '[]');
  root.querySelectorAll('.check-item').forEach(el => {
    const idx = parseInt(el.dataset.idx);
    if (saved.includes(idx)) el.classList.add('is-checked');
    el.addEventListener('click', () => {
      el.classList.toggle('is-checked');
      const cur = [...root.querySelectorAll('.check-item.is-checked')]
        .map(x => parseInt(x.dataset.idx));
      localStorage.setItem(KEY, JSON.stringify(cur));
    });
  });
}

/* ── Filter chips ── */
function wireFilters() {
  const chips = document.querySelectorAll('.filter-chip[data-filter]');
  const search = document.getElementById('search-input');

  function apply() {
    const activeChips = [...chips].filter(c => c.classList.contains('is-active'));
    const tiers = activeChips.filter(c => c.dataset.filter === 'tier').map(c => c.dataset.value);
    const sections = activeChips.filter(c => c.dataset.filter === 'section').map(c => c.dataset.value);
    const q = (search?.value || '').trim().toLowerCase();

    document.querySelectorAll('.finding-block').forEach(el => {
      const tier = el.dataset.tier;
      const sec = el.dataset.section;
      const text = el.innerText.toLowerCase();

      let show = true;
      if (tiers.length && !tiers.includes(tier)) show = false;
      if (sections.length && !sections.includes(sec)) show = false;
      if (q && !text.includes(q)) show = false;
      el.style.display = show ? '' : 'none';
    });

    // Hide empty section containers when filters applied
    document.querySelectorAll('.section[data-findings-section]').forEach(s => {
      const visible = s.querySelectorAll('.finding-block:not([style*="display: none"])').length;
      s.classList.toggle('is-empty', visible === 0 && (tiers.length || sections.length || q));
    });
  }

  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      // For tier chips: toggle individually. For "all" chip: clear all of that group.
      if (chip.dataset.filter === 'all') {
        chips.forEach(c => c.classList.remove('is-active'));
        chip.classList.add('is-active');
      } else {
        document.querySelector('.filter-chip[data-filter="all"]')?.classList.remove('is-active');
        chip.classList.toggle('is-active');
        // If none active anywhere, re-activate the All chip
        if (![...chips].some(c => c.classList.contains('is-active') && c.dataset.filter !== 'all')) {
          document.querySelector('.filter-chip[data-filter="all"]')?.classList.add('is-active');
        }
      }
      apply();
    });
  });

  search?.addEventListener('input', apply);
}

/* ── Sticky nav active section highlighting ── */
function wireScrollSpy() {
  const nav = document.querySelectorAll('.nav-btn[data-section]');
  const sections = SECTIONS.map(s => document.getElementById(s.id)).filter(Boolean);
  if (!('IntersectionObserver' in window)) return;
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        nav.forEach(n => n.classList.toggle('is-active', n.dataset.section === e.target.id));
      }
    });
  }, { rootMargin: '-50% 0px -50% 0px', threshold: 0 });
  sections.forEach(s => obs.observe(s));
}

/* ── Mobile nav toggle ── */
function wireMobileNav() {
  const btn = document.getElementById('nav-menu-btn');
  const links = document.querySelector('.nav-sections');
  btn?.addEventListener('click', () => links?.classList.toggle('is-open'));
  links?.querySelectorAll('a, button').forEach(el => {
    el.addEventListener('click', () => links.classList.remove('is-open'));
  });
}

/* ── Smooth-scroll nav links ── */
function wireNavLinks() {
  document.querySelectorAll('.nav-btn[data-section]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.section;
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

/* ── Print action ── */
function wirePrint() {
  document.getElementById('btn-print')?.addEventListener('click', () => {
    // Open all accordions for print
    document.querySelectorAll('.finding-block').forEach(b => b.classList.add('is-open'));
    setTimeout(() => window.print(), 200);
  });
  document.getElementById('btn-expand')?.addEventListener('click', () => {
    const blocks = document.querySelectorAll('.finding-block');
    const allOpen = [...blocks].every(b => b.classList.contains('is-open'));
    blocks.forEach(b => b.classList.toggle('is-open', !allOpen));
    document.getElementById('btn-expand').textContent = allOpen ? 'Expand all' : 'Collapse all';
  });
}

/* ── Boot ── */
document.addEventListener('DOMContentLoaded', () => {
  renderStats();
  // INTERVENTIONS tab
  renderActionLoop();
  renderHeroCard();
  renderCalendar();
  renderReachOutToday();
  renderTodaySession();
  renderAdherenceChip();
  renderPrepChecklist();
  renderStack();
  renderMedAlerts();
  // PLAN tab
  renderVision();
  renderGoals();
  renderRoadmap();
  renderStreak();
  renderWeeklyRecap();
  renderVitals();
  renderWorkouts();
  // PROFILE tab
  renderMedReference();
  renderHealthProfile();
  renderActions();
  renderFindingsBySection();
  renderPRS();
  renderCrossRef();
  renderLabs();
  renderAgenda();
  // SOCIAL tab
  renderReachOut();
  renderBirthdays();
  // Tab switching + utilities
  wireTabs();
  wireFilters();
  wireScrollSpy();
  wireMobileNav();
  wireNavLinks();
  wirePrint();

  // Show generation timestamp
  const meta = document.getElementById('meta-info');
  if (meta) meta.textContent = `Generated ${META.generated} · ${META.source}`;
});
