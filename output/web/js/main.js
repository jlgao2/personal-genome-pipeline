/* ── Genome Report — interactive renderer ── */

import {
  META, STATS, SECTIONS, FINDINGS, CROSSREF, LABS, PCP_AGENDA, PRS
} from './data.js';
import { VITALS, WORKOUTS } from './data-vitals.js';
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
  renderActions();
  renderFindingsBySection();
  renderPRS();
  renderVitals();
  renderWorkouts();
  renderCrossRef();
  renderLabs();
  renderAgenda();
  wireFilters();
  wireScrollSpy();
  wireMobileNav();
  wireNavLinks();
  wirePrint();

  // Show generation timestamp
  const meta = document.getElementById('meta-info');
  if (meta) meta.textContent = `Generated ${META.generated} · ${META.source}`;
});
