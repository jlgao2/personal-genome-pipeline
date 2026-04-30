/* ── Genome Report — interactive renderer ── */

import {
  META, STATS, SECTIONS, FINDINGS, CROSSREF, LABS, PCP_AGENDA, PRS, PROTOCOL
} from './data.js';

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

/* ── Render protocol (supplements + lifestyle) ── */
function renderProtocol() {
  if (typeof PROTOCOL === 'undefined') return;
  const supRoot  = document.getElementById('protocol-supplements');
  const lifeRoot = document.getElementById('protocol-lifestyle');
  if (!supRoot || !lifeRoot) return;

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
