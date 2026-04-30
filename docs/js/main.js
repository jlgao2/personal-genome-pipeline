/* ── Genome Report — interactive renderer ── */

import {
  META, STATS, SECTIONS, FINDINGS, CROSSREF, LABS, PCP_AGENDA, PRS, PROTOCOL
} from './data.js?v=20260430e';

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

/* ── Render z-score distribution graph for a PRS ── */
function prsGraphSvg(z, percentile) {
  if (z == null) {
    return `
      <div class="prs-graph prs-graph--unavailable">
        <span class="prs-graph-na-label">Coverage too low</span>
      </div>
    `;
  }
  // Map z (-3 to +3) to x (20 to 260) on a 280-wide viewBox
  const xZero = 140;
  const xPerSigma = 40;
  const x = Math.max(20, Math.min(260, xZero + z * xPerSigma));

  // Color tier by direction
  let dotColor = 'var(--accent)';
  let dotGlow  = 'rgba(94, 226, 255, 0.6)';
  if (z >= 1.5) {
    dotColor = 'var(--warn)';
    dotGlow  = 'rgba(255, 58, 74, 0.6)';
  } else if (z <= -1.5) {
    dotColor = 'var(--tier-c)';
    dotGlow  = 'rgba(125, 240, 168, 0.6)';
  } else if (Math.abs(z) < 0.4) {
    dotColor = 'var(--fg-dim)';
    dotGlow  = 'rgba(232, 238, 245, 0.3)';
  }

  const zLabel = `z = ${z >= 0 ? '+' : ''}${z.toFixed(1)}σ`;
  const pctLabel = percentile != null ? `${percentile}${pctSuffix(percentile)}` : '';

  return `
    <div class="prs-graph-wrap">
      <svg class="prs-graph" viewBox="0 0 280 50" preserveAspectRatio="none">
        <!-- Bell curve fill -->
        <path d="M20,42 C50,42 80,40 100,33 C115,26 130,12 140,8 C150,12 165,26 180,33 C200,40 230,42 260,42 Z"
              fill="var(--accent-soft)" stroke="var(--accent-deep)" stroke-width="0.8" opacity="0.9" />
        <!-- σ axis line -->
        <line x1="20" y1="42" x2="260" y2="42" stroke="var(--border-strong)" stroke-width="0.5" />
        <!-- σ ticks -->
        <line x1="60"  y1="42" x2="60"  y2="46" stroke="var(--fg-dim)" stroke-width="0.5" />
        <line x1="100" y1="42" x2="100" y2="46" stroke="var(--fg-dim)" stroke-width="0.5" />
        <line x1="140" y1="42" x2="140" y2="48" stroke="var(--fg-dim)" stroke-width="0.7" />
        <line x1="180" y1="42" x2="180" y2="46" stroke="var(--fg-dim)" stroke-width="0.5" />
        <line x1="220" y1="42" x2="220" y2="46" stroke="var(--fg-dim)" stroke-width="0.5" />
        <!-- User marker -->
        <line x1="${x}" y1="6" x2="${x}" y2="42" stroke="${dotColor}" stroke-width="1.2"
              style="filter: drop-shadow(0 0 4px ${dotGlow})" />
        <circle cx="${x}" cy="6" r="3.5" fill="${dotColor}" stroke="var(--bg)" stroke-width="1"
              style="filter: drop-shadow(0 0 6px ${dotGlow})" />
      </svg>
      <div class="prs-graph-meta">
        <span class="prs-graph-tick">−3σ</span>
        <span class="prs-graph-tick">−2</span>
        <span class="prs-graph-tick">−1</span>
        <span class="prs-graph-tick">0</span>
        <span class="prs-graph-tick">+1</span>
        <span class="prs-graph-tick">+2</span>
        <span class="prs-graph-tick">+3σ</span>
      </div>
      <div class="prs-graph-readout">
        <span class="prs-graph-z" style="color: ${dotColor}">${zLabel}</span>
        ${pctLabel ? `<span class="prs-graph-pct" style="color: ${dotColor}">~${pctLabel} percentile</span>` : ''}
      </div>
    </div>
  `;
}

function pctSuffix(n) {
  if (n % 100 >= 11 && n % 100 <= 13) return 'th';
  switch (n % 10) {
    case 1: return 'st';
    case 2: return 'nd';
    case 3: return 'rd';
    default: return 'th';
  }
}

/* ── Render combined interactive PRS overview chart ── */
function prsColorForZ(z) {
  if (z >= 1.5) return { c: 'var(--warn)', glow: 'rgba(255, 58, 74, 0.6)' };
  if (z <= -1.5) return { c: 'var(--tier-c)', glow: 'rgba(125, 240, 168, 0.6)' };
  if (Math.abs(z) < 0.4) return { c: 'var(--fg-dim)', glow: 'rgba(232, 238, 245, 0.3)' };
  return { c: 'var(--accent)', glow: 'rgba(94, 226, 255, 0.6)' };
}

function renderPRSOverview() {
  const root = document.getElementById('prs-overview');
  if (!root) return;

  const VB_W = 700, VB_H = 240;
  const PAD_L = 30, PAD_R = 30;
  const BASE_Y = 200;
  const APEX_Y = 110;
  const X_ZERO = VB_W / 2;
  const X_PER_SIGMA = (VB_W - PAD_L - PAD_R) / 6;
  const zToX = z => X_ZERO + z * X_PER_SIGMA;

  const NORM_MAX = 0.4;
  let curveD = `M ${PAD_L} ${BASE_Y} `;
  for (let z = -3; z <= 3; z += 0.1) {
    const density = Math.exp(-(z * z) / 2) / Math.sqrt(2 * Math.PI);
    const x = zToX(z);
    const y = BASE_Y - (density / NORM_MAX) * (BASE_Y - APEX_Y);
    curveD += `L ${x.toFixed(1)} ${y.toFixed(1)} `;
  }
  curveD += `L ${VB_W - PAD_R} ${BASE_Y} Z`;

  // Sort all (with-z and low-conf) by trait name for the list, but markers placed by z
  const sortedByZ = PRS.filter(p => p.z != null).slice().sort((a, b) => a.z - b.z);
  const lowConf   = PRS.filter(p => p.z == null);
  const sortedByName = PRS.slice().sort((a, b) => a.trait.localeCompare(b.trait));

  // Stagger marker labels at 3 row heights
  const ROWS = [40, 60, 80];
  const markers = sortedByZ.map((p, i) => {
    const x = zToX(Math.max(-3, Math.min(3, p.z)));
    const labelY = ROWS[i % ROWS.length];
    const { c, glow } = prsColorForZ(p.z);
    const safeName = p.trait.length > 18 ? p.trait.split(' ').slice(0, 2).join(' ') : p.trait;
    return `
      <g class="prs-marker" data-pgs="${p.pgs}" data-trait="${p.trait}">
        <line class="prs-marker-line" x1="${x}" y1="${BASE_Y}" x2="${x}" y2="${labelY + 12}"
              stroke="${c}" />
        <text class="prs-marker-label" x="${x}" y="${labelY}">${safeName}</text>
        <text class="prs-marker-z" x="${x}" y="${labelY + 11}">z=${p.z >= 0 ? '+' : ''}${p.z.toFixed(1)}</text>
        <circle class="prs-marker-dot" cx="${x}" cy="${BASE_Y}" r="5"
                fill="${c}" style="filter: drop-shadow(0 0 6px ${glow})" />
      </g>
    `;
  }).join('');

  const tickEls = [-3, -2, -1, 0, 1, 2, 3].map(z => {
    const x = zToX(z);
    return `
      <line class="prs-tick" x1="${x}" y1="${BASE_Y}" x2="${x}" y2="${BASE_Y + 5}" />
      <text class="prs-tick-label" x="${x}" y="${BASE_Y + 18}" text-anchor="middle">
        ${z > 0 ? '+' : ''}${z}σ
      </text>
    `;
  }).join('');

  // Side list — every PRS, including low-confidence
  const listItems = sortedByName.map(p => {
    const isLow = p.z == null;
    const { c } = isLow ? { c: 'var(--fg-mute)' } : prsColorForZ(p.z);
    const zText = isLow
      ? 'low coverage'
      : `z=${p.z >= 0 ? '+' : ''}${p.z.toFixed(1)}σ${p.percentile != null ? ` · ${p.percentile}${pctSuffix(p.percentile)}` : ''}`;
    return `
      <div class="prs-list-item${isLow ? ' prs-list-item--low' : ''}" data-pgs="${p.pgs}" data-trait="${p.trait}">
        <span class="prs-list-item-dot" style="background: ${c}; ${isLow ? '' : `box-shadow: 0 0 6px ${c};`}"></span>
        <span class="prs-list-item-name">${p.trait}</span>
        <span class="prs-list-item-z">${zText}</span>
      </div>
    `;
  }).join('');

  root.innerHTML = `
    <aside class="prs-overview-list" id="prs-overview-list">
      <div class="prs-overview-list-header">Traits · click to highlight</div>
      ${listItems}
    </aside>
    <div class="prs-overview-chart">
      <svg class="prs-overview-svg" viewBox="0 0 ${VB_W} ${VB_H}" preserveAspectRatio="xMidYMid meet">
        <path class="prs-curve" d="${curveD}" />
        <line class="prs-axis" x1="${PAD_L}" y1="${BASE_Y}" x2="${VB_W - PAD_R}" y2="${BASE_Y}" />
        ${tickEls}
        ${markers}
      </svg>
      <div class="prs-overview-legend">
        <span class="prs-overview-legend-item">
          <span class="prs-overview-legend-dot" style="background: var(--warn); box-shadow: 0 0 6px var(--warn);"></span>Elevated (z ≥ +1.5σ)
        </span>
        <span class="prs-overview-legend-item">
          <span class="prs-overview-legend-dot" style="background: var(--accent); box-shadow: 0 0 6px var(--accent);"></span>Mild direction
        </span>
        <span class="prs-overview-legend-item">
          <span class="prs-overview-legend-dot" style="background: var(--fg-dim);"></span>Neutral (|z| &lt; 0.4σ)
        </span>
        <span class="prs-overview-legend-item">
          <span class="prs-overview-legend-dot" style="background: var(--tier-c); box-shadow: 0 0 6px var(--tier-c);"></span>Below avg (z ≤ −1.5σ)
        </span>
      </div>
    </div>
  `;

  // ── Wire bidirectional interactivity ──
  const cardByPgs = (pgs) => document.querySelector(`.prs-card[data-pgs="${pgs}"]`);
  const markerByPgs = (pgs) => root.querySelector(`.prs-marker[data-pgs="${pgs}"]`);
  const listItemByPgs = (pgs) => root.querySelector(`.prs-list-item[data-pgs="${pgs}"]`);

  function setActive(pgs, on) {
    const m = markerByPgs(pgs);
    const li = listItemByPgs(pgs);
    const card = cardByPgs(pgs);
    [m, li, card].forEach(el => {
      if (!el) return;
      if (on) {
        el.classList.add(el.classList.contains('prs-card') ? 'is-highlighted' : 'is-active');
      } else {
        el.classList.remove(el.classList.contains('prs-card') ? 'is-highlighted' : 'is-active');
      }
    });
  }

  function scrollToCard(pgs) {
    const card = cardByPgs(pgs);
    if (!card) return;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.add('is-highlighted');
    setTimeout(() => card.classList.remove('is-highlighted'), 2400);
  }

  // Markers (chart side)
  root.querySelectorAll('.prs-marker').forEach(m => {
    const pgs = m.dataset.pgs;
    m.addEventListener('mouseenter', () => setActive(pgs, true));
    m.addEventListener('mouseleave', () => setActive(pgs, false));
    m.addEventListener('click', () => scrollToCard(pgs));
  });

  // List items (sidebar)
  root.querySelectorAll('.prs-list-item').forEach(li => {
    const pgs = li.dataset.pgs;
    li.addEventListener('mouseenter', () => setActive(pgs, true));
    li.addEventListener('mouseleave', () => setActive(pgs, false));
    li.addEventListener('click', () => scrollToCard(pgs));
  });
}

/* ── Render PRS cards (no per-card graph — overview chart at top covers it) ── */
function renderPRS() {
  const root = document.getElementById('prs-grid');
  if (!root) return;
  root.innerHTML = PRS.map(p => `
    <article class="prs-card" data-pgs="${p.pgs}">
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

/* ── Render protocol (supplements + lifestyle) ── */
function renderProtocol() {
  const supRoot  = document.getElementById('protocol-supplements');
  const lifeRoot = document.getElementById('protocol-lifestyle');
  if (!supRoot || !lifeRoot) {
    console.warn('[protocol] containers not found');
    return;
  }
  if (!PROTOCOL || (!PROTOCOL.supplements && !PROTOCOL.lifestyle)) {
    console.warn('[protocol] PROTOCOL data missing or empty');
    supRoot.innerHTML  = `<p style="padding:1rem; font-family: var(--font-mono); font-size: 0.6rem; color: var(--fg-dim);">No supplement recommendations defined.</p>`;
    lifeRoot.innerHTML = `<p style="padding:1rem; font-family: var(--font-mono); font-size: 0.6rem; color: var(--fg-dim);">No lifestyle recommendations defined.</p>`;
    return;
  }
  console.log('[protocol] rendering', PROTOCOL.supplements?.length, 'supplements +', PROTOCOL.lifestyle?.length, 'lifestyle items');

  const renderItem = (item, kind) => {
    const isAvoid = item.name && item.name.startsWith('⚠');
    const tagsHtml = (item.driven_by || [])
      .map(d => `<span class="protocol-driver">${d}</span>`)
      .join('');
    const cadence = item.dose || item.cadence || '';
    const cadenceLabel = kind === 'supplement' ? 'Dose' : 'Cadence';
    const timingRow = item.timing
      ? `<div class="protocol-row"><span class="protocol-row-label">Timing</span><span class="protocol-row-value">${item.timing}</span></div>`
      : '';
    const productRow = item.product
      ? `<div class="protocol-row"><span class="protocol-row-label">Product</span><span class="protocol-row-value protocol-row-value--mono">${item.product}</span></div>`
      : '';
    return `
      <article class="protocol-card${isAvoid ? ' protocol-card--avoid' : ''}" data-tier="${item.tier}">
        <span class="protocol-tier" data-tier="${item.tier}">Tier ${item.tier}</span>
        <h4 class="protocol-name">${item.name}</h4>
        <div class="protocol-row protocol-row--head">
          <span class="protocol-row-label">${cadenceLabel}</span>
          <span class="protocol-row-value protocol-row-value--strong">${cadence}</span>
        </div>
        ${timingRow}
        <div class="protocol-row">
          <span class="protocol-row-label">Driven by</span>
          <span class="protocol-drivers">${tagsHtml}</span>
        </div>
        <p class="protocol-rationale">${item.rationale}</p>
        ${productRow}
      </article>
    `;
  };

  supRoot.innerHTML  = (PROTOCOL.supplements || []).map(i => renderItem(i, 'supplement')).join('');
  lifeRoot.innerHTML = (PROTOCOL.lifestyle    || []).map(i => renderItem(i, 'lifestyle')).join('');
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
  renderPRSOverview();
  renderProtocol();
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
