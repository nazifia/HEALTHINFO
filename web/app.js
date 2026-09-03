/* HEALTH INFO web frontend — hash-routed SPA over the Django REST API.
 * Generic CRUD screens are driven by DRF OPTIONS metadata, so every ViewSet
 * (catalog + reports + users + tenants) gets list/detail/create/edit for free. */
'use strict';

/* ---------------------------------------------------------------- helpers */

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function toast(msg, isError) {
  const t = document.createElement('div');
  t.className = 'toast' + (isError ? ' error' : '');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

function fmtVal(v) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (Array.isArray(v)) return v.map(fmtVal).join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) return v.replace('T', ' ').slice(0, 16);
  return String(v);
}

const label = (k) => k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/* ------------------------------------------------------------------ theme */

function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  const b = $('#theme-toggle');
  if (b) { b.textContent = t === 'dark' ? '☀' : '☾'; b.title = t === 'dark' ? 'Light mode' : 'Dark mode'; }
}
applyTheme(localStorage.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

/* Inline 24px stroke icons (feather-style). One <svg> wrapper, path data only. */
const ICONS = {
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  zap: '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  pill: '<path d="M10.5 20.5l-7-7a5 5 0 0 1 7-7l7 7a5 5 0 0 1-7 7z"/><line x1="8.5" y1="8.5" x2="15.5" y2="15.5"/>',
  flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  chart: '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  grid: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
};
const ico = (name) => ICONS[name]
  ? `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`
  : '';

/* Status-ish values render as tinted pills in tables and detail lists. */
const PILL_COLORS = {
  draft: 'gray', review: 'amber', approved: 'blue', published: 'green', archived: 'gray',
  active: 'green', pending: 'amber', suspended: 'red', rejected: 'red', trial: 'amber', expired: 'red',
  mild: 'green', moderate: 'amber', severe: 'red', critical: 'red', high: 'red', medium: 'amber', low: 'green',
};
const PILL_KEYS = /(^|_)(status|severity|priority|state)$/;
function cellHtml(key, v) {
  if (PILL_KEYS.test(key) && typeof v === 'string' && v) {
    return `<span class="pill pill-${PILL_COLORS[v.toLowerCase()] || 'gray'}">${esc(label(v))}</span>`;
  }
  return esc(fmtVal(v));
}

/* ---------------------------------------------------------------- outbox */

/* Report submissions made while offline queue here and flush when
 * connectivity returns. Creates only — edits race the server copy, so they
 * fail loudly instead. ponytail: localStorage + online event; move to
 * IndexedDB + Background Sync if queues outgrow ~5MB or must survive the tab. */
const Outbox = {
  all: () => JSON.parse(localStorage.getItem('outbox') || '[]'),
  save: (items) => localStorage.setItem('outbox', JSON.stringify(items)),
  push(slug, body) { this.save([...this.all(), { slug, body, ts: Date.now() }]); },
  async flush() {
    const items = this.all();
    if (!items.length || !Api.isLoggedIn) return;
    const kept = [];
    for (const it of items) {
      try {
        await Api.post(`/api/${it.slug}/`, it.body);
      } catch (e) {
        if (e instanceof Api.ApiError) {
          // Server rejected it — drop so it can't retry forever.
          toast(`Queued ${RESOURCES[it.slug]?.title || it.slug} rejected: ${e.message}`, true);
        } else {
          kept.push(it); // still offline
        }
      }
    }
    this.save(kept);
    const sent = items.length - kept.length;
    if (sent) toast(`Synced ${sent} queued report${sent === 1 ? '' : 's'}.`);
  },
};
window.addEventListener('online', () => Outbox.flush());

/* -------------------------------------------------------------- registries */

// Every DRF-routed resource. workflow => transition/history actions exist.
const RESOURCES = {
  'diseases':          { title: 'Diseases',           group: 'Catalog', workflow: true,  search: true,  graph: 'diseases' },
  'medications':       { title: 'Medications',        group: 'Catalog', workflow: true,  search: true,  graph: 'medications' },
  'symptoms':          { title: 'Symptoms',           group: 'Catalog', search: true },
  'interactions':      { title: 'Drug Interactions',  group: 'Catalog' },
  'specialties':       { title: 'Specialties',        group: 'Catalog', search: true,  graph: 'specialties' },
  'procedures':        { title: 'Procedures',         group: 'Catalog', workflow: true,  search: true,  graph: 'procedures' },
  'lab-tests':         { title: 'Lab Tests',          group: 'Catalog', workflow: true,  search: true },
  'articles':          { title: 'Articles',           group: 'Catalog', workflow: true,  search: true },
  'case-reports':      { title: 'Case Reports',       group: 'Reports', report: true },
  'adverse-reactions': { title: 'Adverse Reactions',  group: 'Reports', report: true },
  'lab-results':       { title: 'Lab Results',        group: 'Reports', report: true },
  'immunizations':     { title: 'Immunizations',      group: 'Reports', report: true },
  'vital-events':      { title: 'Vital Events',       group: 'Reports', report: true },
  'stock-reports':     { title: 'Stock Reports',      group: 'Reports', report: true },
  'chw-reports':       { title: 'CHW Reports',        group: 'Reports', report: true },
  'facility-metrics':  { title: 'Facility Metrics',   group: 'Reports', report: true },
  'insurance-claims':  { title: 'Insurance Claims',   group: 'Reports', report: true },
  'appointments':      { title: 'Appointments',       group: 'Reports', report: true },
  'pharmacy-items':         { title: 'Stock Items',     group: 'Pharmacy', path: 'pharmacy/items',           roles: 'admin', search: true },
  'pharmacy-batches':       { title: 'Stock Batches',   group: 'Pharmacy', path: 'pharmacy/batches',         roles: 'staff', search: true, readOnly: true },
  'pharmacy-movements':     { title: 'Stock Ledger',    group: 'Pharmacy', path: 'pharmacy/movements',       roles: 'staff', readOnly: true },
  'pharmacy-suppliers':     { title: 'Suppliers',       group: 'Pharmacy', path: 'pharmacy/suppliers',       roles: 'admin', search: true },
  'pharmacy-orders':        { title: 'Purchase Orders', group: 'Pharmacy', path: 'pharmacy/purchase-orders', roles: 'staff', search: true, extra: 'purchase',
                              actions: [{ name: 'submit', label: 'Submit to supplier', when: ['draft'] },
                                        { name: 'cancel', label: 'Cancel order', danger: true, when: ['draft', 'submitted', 'partial'] }] },
  'pharmacy-hmos':          { title: 'HMOs',            group: 'Pharmacy', path: 'pharmacy/hmos',            roles: 'admin', search: true },
  'pharmacy-enrollments':   { title: 'Scheme Members',  group: 'Pharmacy', path: 'pharmacy/enrollments',     roles: 'staff', search: true },
  'pharmacy-sales':         { title: 'Sales',           group: 'Pharmacy', path: 'pharmacy/sales',           roles: 'staff', search: true, readOnly: true, receipt: true,
                              actions: [{ name: 'pay', label: 'Take payment', ask: 'amount', when: ['pending', 'paid'] },
                                        { name: 'cancel', label: 'Cancel sale', danger: true, when: ['pending', 'paid'] }] },
  'pharmacy-claims':        { title: 'Claims',          group: 'Pharmacy', path: 'pharmacy/claims',          roles: 'staff', search: true, readOnly: true,
                              actions: [{ name: 'submit', label: 'Submit', when: ['draft', 'rejected'] },
                                        { name: 'approve', label: 'Approve', ask: 'amount', adminOnly: true, when: ['submitted'] },
                                        { name: 'reject', label: 'Reject', ask: 'reason', adminOnly: true, when: ['submitted'] },
                                        { name: 'pay', label: 'Record payment', ask: 'amount', adminOnly: true, when: ['approved'] }] },
  'pharmacy-claim-batches': { title: 'Claim Batches',   group: 'Pharmacy', path: 'pharmacy/claim-batches',   roles: 'staff', search: true,
                              actions: [{ name: 'add-claims', label: 'Collect claims', when: ['draft'] },
                                        { name: 'submit', label: 'Submit batch', when: ['draft'] },
                                        { name: 'approve', label: 'Approve all', adminOnly: true, when: ['submitted'] },
                                        { name: 'pay', label: 'Allocate remittance', ask: 'amount', adminOnly: true, when: ['submitted', 'approved'] },
                                        { name: 'cancel', label: 'Cancel batch', danger: true, when: ['draft', 'submitted', 'approved'] }] },
  'users':             { title: 'Users',              group: 'Admin' },
  'tenants':           { title: 'Tenants',            group: 'Admin', superOnly: true, tenantActions: true },
};

// A resource's API path, which is the slug unless the registry overrides it
// (the pharmacy module nests everything under /api/pharmacy/).
const rpath = (slug, suffix = '') => `/api/${RESOURCES[slug]?.path || slug}/${suffix}`;

// M2M PK-list fields (catalog serializers). OPTIONS metadata can't tell
// many-related from single-related, so name them.
// ponytail: hardcoded set; derive from /api/schema/ if the model graph grows.
const M2M_FIELDS = new Set(['symptoms', 'medications', 'procedures', 'lab_tests', 'specialties', 'articles']);

// Content workflow edges (mirrors apps/governance/workflow.py TRANSITIONS).
const TRANSITIONS = {
  draft: ['review'],
  review: ['approved', 'draft'],
  approved: ['published', 'review'],
  published: ['archived'],
  archived: ['draft'],
};

// Analytics endpoints. dates => from/to inputs; weeks => weeks input.
const ANALYTICS = [
  { key: 'dashboard',     label: 'Tenant Dashboard',  path: '/api/analytics/tenant/' },
  { key: 'cases',         label: 'Case Stats',        path: '/api/analytics/cases/', dates: true, exportPath: '/api/analytics/cases/export/' },
  { key: 'surveillance',  label: 'Outbreak Alerts',   path: '/api/analytics/surveillance/' },
  { key: 'idsr',          label: 'IDSR Report',       path: '/api/analytics/idsr/', weeks: true, csv: true },
  { key: 'sources',       label: 'Report Sources',    path: '/api/analytics/sources/' },
  { key: 'adr',           label: 'ADR Stats',         path: '/api/analytics/adr/', dates: true },
  { key: 'labs',          label: 'Lab Stats',         path: '/api/analytics/labs/', dates: true },
  { key: 'immunizations', label: 'Immunization Stats', path: '/api/analytics/immunizations/', dates: true },
  { key: 'vitals',        label: 'Vital Stats',       path: '/api/analytics/vitals/', dates: true },
  { key: 'stock',         label: 'Stock Stats',       path: '/api/analytics/stock/', dates: true },
  { key: 'chw',           label: 'CHW Stats',         path: '/api/analytics/chw/', dates: true },
  { key: 'facility',      label: 'Facility Stats',    path: '/api/analytics/facility/', dates: true },
  { key: 'insurance',     label: 'Insurance Stats',   path: '/api/analytics/insurance/', dates: true },
  { key: 'appointments',  label: 'Appointment Stats', path: '/api/analytics/appointments/', dates: true },
  { key: 'funnel',        label: 'Funnel',            path: '/api/analytics/funnel/' },
  { key: 'ai-quality',    label: 'AI Quality',        path: '/api/analytics/ai-quality/', dates: true },
  { key: 'retention',     label: 'Retention',         path: '/api/analytics/retention/' },
  { key: 'benchmark',     label: 'Benchmark',         path: '/api/analytics/benchmark/' },
];

const PLATFORM = [
  { key: 'dashboard',     label: 'Platform Dashboard', path: '/api/analytics/platform/' },
  { key: 'cases',         label: 'Case Stats',         path: '/api/analytics/platform/cases/', dates: true },
  { key: 'surveillance',  label: 'Outbreak Alerts',    path: '/api/analytics/platform/surveillance/' },
  { key: 'idsr',          label: 'IDSR Report',        path: '/api/analytics/platform/idsr/', weeks: true, csv: true },
  { key: 'sources',       label: 'Report Sources',     path: '/api/analytics/platform/sources/' },
  { key: 'adr',           label: 'ADR Stats',          path: '/api/analytics/platform/adr/', dates: true },
  { key: 'labs',          label: 'Lab Stats',          path: '/api/analytics/platform/labs/', dates: true },
  { key: 'immunizations', label: 'Immunization Stats', path: '/api/analytics/platform/immunizations/', dates: true },
  { key: 'vitals',        label: 'Vital Stats',        path: '/api/analytics/platform/vitals/', dates: true },
  { key: 'stock',         label: 'Stock Stats',        path: '/api/analytics/platform/stock/', dates: true },
  { key: 'chw',           label: 'CHW Stats',          path: '/api/analytics/platform/chw/', dates: true },
  { key: 'facility',      label: 'Facility Stats',     path: '/api/analytics/platform/facility/', dates: true },
  { key: 'insurance',     label: 'Insurance Stats',    path: '/api/analytics/platform/insurance/', dates: true },
  { key: 'appointments',  label: 'Appointment Stats',  path: '/api/analytics/platform/appointments/', dates: true },
];

/* ----------------------------------------------------------------- layout */

let ME = null; // current user object

function navHtml() {
  const iconFor = (slug, r) => slug === 'users' ? 'users' : slug === 'tenants' ? 'shield'
    : r.group === 'Reports' ? 'file' : r.group === 'Pharmacy' ? 'pill' : 'book';
  const groups = {};
  for (const [slug, r] of Object.entries(RESOURCES)) {
    if (r.superOnly && ME?.role !== 'super_admin') continue;
    if (slug === 'users' && !['super_admin', 'tenant_admin'].includes(ME?.role)) continue;
    if (r.group === 'Pharmacy' && !PHARMACY_STAFF_ROLES.has(ME?.role)) continue;
    (groups[r.group] ||= []).push(`<a href="#/r/${slug}" data-route="/r/${slug}">${ico(iconFor(slug, r))}${esc(r.title)}</a>`);
  }
  const tools = [
    `<a href="#/search" data-route="/search">${ico('search')}Search</a>`,
    `<a href="#/semantic" data-route="/semantic">${ico('grid')}Semantic Search</a>`,
    `<a href="#/ask" data-route="/ask">${ico('chat')}Ask AI</a>`,
    `<a href="#/differential" data-route="/differential">${ico('activity')}Differential Dx</a>`,
    `<a href="#/interaction-check" data-route="/interaction-check">${ico('pill')}Interaction Check</a>`,
    `<a href="#/notifiable" data-route="/notifiable">${ico('flag')}Notifiable Cases</a>`,
  ];
  let html = `<a href="#/" data-route="/" class="nav-home">${ico('home')}Home</a>`;
  html += `<div class="nav-group"><h4>Tools</h4>${tools.join('')}</div>`;
  html += `<div class="nav-group"><h4>Catalog</h4>${groups.Catalog.join('')}</div>`;
  html += `<div class="nav-group"><h4>Reports</h4>${groups.Reports.join('')}</div>`;
  if (groups.Pharmacy?.length) {
    html += `<div class="nav-group"><h4>Pharmacy</h4>` +
      `<a href="#/pharmacy" data-route="/pharmacy">${ico('pill')}Counter</a>` +
      `<a href="#/pharmacy/sell" data-route="/pharmacy/sell">${ico('pill')}Dispense</a>` +
      groups.Pharmacy.join('') + `</div>`;
  }
  html += `<div class="nav-group"><h4>Analytics</h4><a href="#/analytics" data-route="/analytics">${ico('chart')}Tenant Analytics</a>`;
  if (ME?.role === 'super_admin') html += `<a href="#/platform" data-route="/platform">${ico('chart')}Platform Analytics</a>`;
  html += `</div>`;
  if (groups.Admin?.length) html += `<div class="nav-group"><h4>Admin</h4>${groups.Admin.join('')}</div>`;
  return html;
}

async function ensureChrome() {
  if (!ME) {
    try { ME = await Api.myself(); } catch { /* token dead */ }
    if (!ME) { await Api.logout(); location.hash = '#/login'; return false; }
  }
  $('#topbar').hidden = false;
  $('#sidebar').hidden = false;
  $('#tenant-badge').textContent = Api.tenant;
  $('#user-badge').textContent = `${ME.phone || ME.username || 'me'} · ${ME.role}`;
  $('#sidebar').innerHTML = navHtml();
  const route = location.hash.slice(1) || '/';
  for (const a of document.querySelectorAll('#sidebar a')) {
    a.classList.toggle('active', route === a.dataset.route || (a.dataset.route !== '/' && route.startsWith(a.dataset.route)));
  }
  return true;
}

function authChrome() {
  $('#topbar').hidden = true;
  $('#sidebar').hidden = true;
}

function render(html) {
  $('#main').innerHTML = html;
  $('#main').scrollTop = 0;
  $('#sidebar').classList.remove('open');
}

const spinner = () => render('<div class="loading">Loading…</div>');

function errorBox(e) {
  render(`<div class="card error-card"><h3>Error</h3><p>${esc(e.message || e)}</p></div>`);
}

/* ----------------------------------------------------------------- charts */

// Chart chrome + categorical slots as CSS vars so charts re-theme live
// (hexes live in styles.css :root / [data-theme="dark"]). Both modes
// validated: light worst adjacent CVD dE 24.2; dark 10.3 (floor band) —
// relief rule satisfied by bar-tip value labels and the table under
// every chart.
const VIZ = {
  series: ['var(--viz-s1)', 'var(--viz-s2)', 'var(--viz-s3)', 'var(--viz-s4)'],
  grid: 'var(--viz-grid)', axis: 'var(--viz-axis)', muted: 'var(--viz-muted)',
  ink: 'var(--viz-ink)', surface: 'var(--viz-surface)',
};

// An array of objects is chartable when it has exactly one label column and
// 1–4 numeric columns (id excluded). Anything wider stays a table.
function chartable(rows) {
  if (!Array.isArray(rows) || rows.length < 2 || rows.length > 40) return null;
  const keys = Object.keys(rows[0]);
  const numeric = keys.filter((k) => rows.every((r) => r[k] === null || typeof r[k] === 'number'));
  const labels = keys.filter((k) => !numeric.includes(k));
  const numKeys = numeric.filter((k) => k !== 'id').slice(0, 4);
  if (labels.length !== 1 || !numKeys.length) return null;
  if (rows.every((r) => typeof r[labels[0]] !== 'string')) return null;
  return { labelKey: labels[0], numKeys };
}

const timeish = (labels) => labels.every((l) =>
  /^\d{4}([-/]\d{1,2}([-/]\d{1,2})?)?([T ].*)?$/.test(l) || /^\d{4}-?W\d{1,2}$/i.test(l));

// Clean axis max: 1/2/5 x 10^n at or above the data max.
function niceMax(v) {
  if (v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 5, 10]) if (m * pow >= v) return m * pow;
  return 10 * pow;
}
const fmtNum = (v) => v >= 10000 ? (v / 1000).toFixed(1).replace(/\.0$/, '') + 'K' : String(v);

function legendHtml(numKeys) {
  if (numKeys.length < 2) return '';
  return `<div class="viz-legend">${numKeys.map((k, i) =>
    `<span><i style="background:${VIZ.series[i]}"></i>${esc(label(k))}</span>`).join('')}</div>`;
}

const tip = (labelText, entries) => esc(JSON.stringify({ l: labelText, e: entries }));

/* Horizontal bars: one row per category; single series = one hue (magnitude),
 * 2–4 series = grouped with the categorical slots. Values at bar tips. */
function barChartHtml(rows, { labelKey, numKeys }) {
  const W = 640, labelW = 150, valueW = 46, plotW = W - labelW - valueW;
  const barH = numKeys.length > 1 ? 10 : 16;
  const rowH = numKeys.length * (barH + 2) + 12;
  const H = rows.length * rowH + 22;
  const max = niceMax(Math.max(...rows.flatMap((r) => numKeys.map((k) => r[k] || 0))));
  const x = (v) => (v / max) * plotW;
  let s = '';
  // vertical hairlines + tick labels; skip the midpoint when it isn't a clean integer
  for (const t of (Number.isInteger(max / 2) ? [0, max / 2, max] : [0, max])) {
    s += `<line x1="${labelW + x(t)}" y1="0" x2="${labelW + x(t)}" y2="${H - 20}" stroke="${VIZ.grid}" stroke-width="1"/>` +
      `<text x="${labelW + x(t)}" y="${H - 6}" fill="${VIZ.muted}" font-size="11" text-anchor="middle">${fmtNum(t)}</text>`;
  }
  rows.forEach((r, ri) => {
    const y0 = ri * rowH;
    const name = fmtVal(r[labelKey]);
    s += `<text x="${labelW - 8}" y="${y0 + rowH / 2}" fill="${VIZ.ink}" font-size="12" text-anchor="end" dominant-baseline="middle">${esc(name.length > 22 ? name.slice(0, 21) + '…' : name)}</text>`;
    numKeys.forEach((k, si) => {
      const v = r[k] || 0;
      const y = y0 + 5 + si * (barH + 2);
      const w = Math.max(x(v), v > 0 ? 2 : 0);
      // 4px rounded data-end, square at the baseline
      s += `<path d="M${labelW},${y} h${Math.max(w - 4, 0)} q4,0 4,4 v${barH - 8} q0,4 -4,4 h-${Math.max(w - 4, 0)} z" fill="${VIZ.series[si]}"/>`;
      if (numKeys.length === 1) {
        s += `<text x="${labelW + w + 6}" y="${y + barH / 2}" fill="${VIZ.ink}" font-size="11" dominant-baseline="middle">${fmtNum(v)}</text>`;
      }
    });
    // hit target spans the full row, tooltip lists every series
    s += `<rect class="viz-hit" x="0" y="${y0}" width="${W}" height="${rowH}" fill="transparent"
      data-tip="${tip(name, numKeys.map((k, si) => [label(k), fmtNum(r[k] || 0), VIZ.series[si]]))}"/>`;
  });
  return legendHtml(numKeys) +
    `<svg class="viz" viewBox="0 0 ${W} ${H}" role="img">${s}</svg>`;
}

/* Line chart for time-shaped labels. 2px lines, end dot with surface ring,
 * crosshair tooltip reads every series at the nearest X. */
function lineChartHtml(rows, { labelKey, numKeys }) {
  const W = 640, H = 240, padL = 46, padR = 20, padT = 14, padB = 26;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const max = niceMax(Math.max(...rows.flatMap((r) => numKeys.map((k) => r[k] || 0))));
  const px = (i) => padL + (rows.length === 1 ? 0 : (i / (rows.length - 1)) * plotW);
  const py = (v) => padT + plotH - (v / max) * plotH;
  let s = '';
  for (let t = 0; t <= 4; t++) {
    const v = (max / 4) * t;
    s += `<line x1="${padL}" y1="${py(v)}" x2="${W - padR}" y2="${py(v)}" stroke="${VIZ.grid}" stroke-width="1"/>` +
      `<text x="${padL - 6}" y="${py(v)}" fill="${VIZ.muted}" font-size="11" text-anchor="end" dominant-baseline="middle" style="font-variant-numeric:tabular-nums">${fmtNum(v)}</text>`;
  }
  const step = Math.max(1, Math.ceil(rows.length / 6));
  rows.forEach((r, i) => {
    if (i % step && i !== rows.length - 1) return;
    s += `<text x="${px(i)}" y="${H - 8}" fill="${VIZ.muted}" font-size="11" text-anchor="middle">${esc(String(r[labelKey]).slice(0, 10))}</text>`;
  });
  numKeys.forEach((k, si) => {
    const pts = rows.map((r, i) => `${px(i)},${py(r[k] || 0)}`).join(' ');
    if (numKeys.length === 1) {
      s += `<polygon points="${padL},${py(0)} ${pts} ${px(rows.length - 1)},${py(0)}" fill="${VIZ.series[si]}" opacity="0.1"/>`;
    }
    s += `<polyline points="${pts}" fill="none" stroke="${VIZ.series[si]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    const last = rows[rows.length - 1][k] || 0;
    s += `<circle cx="${px(rows.length - 1)}" cy="${py(last)}" r="4" fill="${VIZ.series[si]}" stroke="${VIZ.surface}" stroke-width="2"/>`;
  });
  const data = esc(JSON.stringify({
    labels: rows.map((r) => String(r[labelKey])),
    series: numKeys.map((k, si) => ({ name: label(k), color: VIZ.series[si], values: rows.map((r) => r[k] || 0) })),
    padL, padR, padT, plotH,
  }));
  s += `<line class="viz-xhair" y1="${padT}" y2="${padT + plotH}" stroke="${VIZ.axis}" stroke-width="1" visibility="hidden"/>`;
  return legendHtml(numKeys) +
    `<svg class="viz viz-line" viewBox="0 0 ${W} ${H}" data-line="${data}" role="img">${s}</svg>`;
}

const chartHtml = (rows, c) =>
  (timeish(rows.map((r) => String(r[c.labelKey]))) ? lineChartHtml : barChartHtml)(rows, c) +
  `<details class="tbl"><summary>Table view</summary>${tableHtml(rows)}</details>`;

/* One fixed tooltip element + delegated hover for every chart on the page.
 * Labels are untrusted API data — built with textContent, never innerHTML. */
function vizTip() {
  let el = $('#viz-tip');
  if (!el) {
    el = document.createElement('div');
    el.id = 'viz-tip';
    el.hidden = true;
    document.body.appendChild(el);
  }
  return el;
}

function showTip(x, y, title, entries) {
  const el = vizTip();
  el.textContent = '';
  const h = document.createElement('div');
  h.className = 'tip-title';
  h.textContent = title;
  el.appendChild(h);
  for (const [name, value, color] of entries) {
    const row = document.createElement('div');
    row.className = 'tip-row';
    const key = document.createElement('i');
    key.style.background = color;
    const val = document.createElement('strong');
    val.textContent = value;
    const lbl = document.createElement('span');
    lbl.textContent = name;
    row.append(key, val, lbl);
    el.appendChild(row);
  }
  el.hidden = false;
  const r = el.getBoundingClientRect();
  el.style.left = Math.min(x + 14, innerWidth - r.width - 8) + 'px';
  el.style.top = Math.max(y - r.height - 10, 8) + 'px';
}

document.addEventListener('pointermove', (e) => {
  const hit = e.target.closest?.('[data-tip]');
  const line = e.target.closest?.('svg.viz-line');
  if (hit) {
    const d = JSON.parse(hit.dataset.tip);
    showTip(e.clientX, e.clientY, d.l, d.e);
    return;
  }
  if (line) {
    const d = JSON.parse(line.dataset.line);
    const rect = line.getBoundingClientRect();
    const scale = rect.width / 640;
    const plotW = 640 - d.padL - d.padR;
    const rel = (e.clientX - rect.left) / scale - d.padL;
    const i = Math.max(0, Math.min(d.labels.length - 1, Math.round((rel / plotW) * (d.labels.length - 1))));
    const xh = line.querySelector('.viz-xhair');
    const x = d.padL + (d.labels.length === 1 ? 0 : (i / (d.labels.length - 1)) * plotW);
    xh.setAttribute('x1', x); xh.setAttribute('x2', x);
    xh.setAttribute('visibility', 'visible');
    showTip(e.clientX, e.clientY, d.labels[i], d.series.map((s) => [s.name, fmtNum(s.values[i]), s.color]));
    return;
  }
  vizTip().hidden = true;
  document.querySelectorAll('.viz-xhair').forEach((l) => l.setAttribute('visibility', 'hidden'));
});

/* --------------------------------------------------- generic JSON renderer */

// Renders any stats payload: scalars -> tiles, object-arrays -> tables, nesting -> sections.
function renderData(data, depth = 0) {
  if (data === null || typeof data !== 'object') return `<p class="big-val">${esc(fmtVal(data))}</p>`;
  if (Array.isArray(data)) {
    if (!data.length) return '<p class="muted">No data.</p>';
    if (typeof data[0] === 'object' && data[0] !== null) {
      const c = chartable(data);
      return c ? chartHtml(data, c) : tableHtml(data);
    }
    return `<ul>${data.map((v) => `<li>${esc(fmtVal(v))}</li>`).join('')}</ul>`;
  }
  const tiles = [], sections = [];
  for (const [k, v] of Object.entries(data)) {
    if (v === null || typeof v !== 'object') tiles.push({ k, v });
    else sections.push({ k, v });
  }
  let html = '';
  if (tiles.length) {
    html += `<div class="tiles">${tiles.map(({ k, v }) =>
      `<div class="tile"><span class="tile-label">${esc(label(k))}</span><span class="tile-val">${esc(fmtVal(v))}</span></div>`).join('')}</div>`;
  }
  for (const { k, v } of sections) {
    html += `<section class="sub"><h${Math.min(3 + depth, 5)}>${esc(label(k))}</h${Math.min(3 + depth, 5)}>${renderData(v, depth + 1)}</section>`;
  }
  return html || '<p class="muted">No data.</p>';
}

function tableHtml(rows, linkFor) {
  const cols = pickColumns(rows[0]);
  const head = cols.map((c) => `<th>${esc(label(c))}</th>`).join('');
  const body = rows.map((r, i) => {
    const cells = cols.map((c) => `<td>${cellHtml(c, r[c])}</td>`).join('');
    const href = linkFor && linkFor(r);
    return href ? `<tr class="rowlink" onclick="location.hash='${href}'">${cells}</tr>` : `<tr>${cells}</tr>`;
  }).join('');
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// First rows' keys, favoring identity/status columns, capped for readability.
function pickColumns(row) {
  const keys = Object.keys(row);
  const first = keys.filter((k) => ['id', 'name', 'generic_name', 'title', 'phone', 'slug'].includes(k));
  const rest = keys.filter((k) => !first.includes(k) && typeof row[k] !== 'object'
    && !(typeof row[k] === 'string' && row[k].length > 80));
  return [...first, ...rest].slice(0, 7);
}

/* ------------------------------------------------------------- auth views */

// Branded split-screen shell shared by all auth views.
function authShell(title, subtitle, formHtml, footerHtml) {
  return `
  <div class="auth-wrap">
    <aside class="auth-brand">
      <div class="auth-logo" aria-hidden="true">
        <svg viewBox="0 0 64 64" width="40" height="40"><rect width="64" height="64" rx="14" fill="#fff"/><path d="M28 14h8v14h14v8H36v14h-8V36H14v-8h14z" fill="#0f766e"/></svg>
        <span>HEALTH INFO</span>
      </div>
      <div class="auth-brand-copy">
        <h1>Health data, organized.</h1>
        <p>Secure records and reporting for your organization.</p>
      </div>
    </aside>
    <div class="card auth-card">
      <h2>${esc(title)}</h2>
      ${subtitle ? `<p class="auth-sub muted">${esc(subtitle)}</p>` : ''}
      ${formHtml}
      ${footerHtml || ''}
    </div>
  </div>`;
}

function viewLogin() {
  authChrome();
  render(authShell('Welcome back', 'Sign in to continue', `
    <form id="f">
      <label>Phone or license number
        <input name="identifier" placeholder="08031234567" required>
        <small class="muted">Doctors, nurses, midwives and CHEWs: use your license number.
          Pharmacy staff: the last 6 digits of your phone.</small>
      </label>
      <label>Password<input name="password" type="password" required></label>
      <button type="submit">Sign in</button>
    </form>`, `
    <p class="muted center">No account? <a href="#/register">Register</a> ·
      New organization? <a href="#/onboarding">Sign up</a></p>`));
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await Api.login(fd.get('identifier'), fd.get('password'));
      ME = null;
      location.hash = '#/';
    } catch (err) { toast(err.message, true); }
  };
}

function viewRegister() {
  authChrome();
  render(authShell('Create account', 'Join your organization', `
    <form id="f">
      <label>Organization (tenant slug)<input name="tenant" value="${esc(Api.tenant)}" required></label>
      <label>Display name (optional)<input name="username"></label>
      <label>Phone<input name="phone" placeholder="08031234567" required></label>
      <label>Email<input name="email" type="email" required></label>
      <label>Password<input name="password" type="password" required></label>
      <button type="submit">Register</button>
    </form>`, `
    <p class="muted center"><a href="#/login">Back to sign in</a></p>`));
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    Api.tenant = fd.get('tenant');
    const body = { phone: fd.get('phone'), email: fd.get('email'), password: fd.get('password') };
    if (fd.get('username')) body.username = fd.get('username');
    try {
      const r = await Api.post('/api/auth/register/', body);
      toast(r?.message || 'Account created. You can now sign in.');
      location.hash = '#/login';
    } catch (err) { toast(err.message, true); }
  };
}

async function viewOnboarding() {
  authChrome();
  let jurisdictions = [];
  try { jurisdictions = await Api.public('/api/auth/onboarding/jurisdictions/'); } catch { /* optional */ }
  const jOpts = jurisdictions.map((j) =>
    `<option value="${j.id}">${esc(j.name)} (level ${esc(j.level)})</option>`).join('');
  render(authShell('Register your organization', 'Set up your workspace and admin account', `
    <form id="f">
      <label>Organization name<input name="org_name" required></label>
      <label>Slug (short id, e.g. "my-clinic")<input name="org_slug" required pattern="[a-z0-9-]+"></label>
      <label>Address<input name="org_address" required></label>
      <label>Contact<input name="org_contact" required></label>
      ${jOpts ? `<label>Jurisdiction<select name="jurisdiction"><option value="">—</option>${jOpts}</select></label>` : ''}
      <h3 class="auth-section">Admin account</h3>
      <label>Phone<input name="phone" placeholder="08031234567" required></label>
      <label>Email<input name="email" type="email" required></label>
      <label>Password<input name="password" type="password" required></label>
      <button type="submit">Create organization</button>
    </form>`, `
    <p class="muted center"><a href="#/login">Back to sign in</a></p>`));
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    if (!body.jurisdiction) delete body.jurisdiction;
    try {
      const r = await Api.post('/api/auth/onboarding/', body);
      Api.tenant = r?.org_slug || body.org_slug;
      toast(r?.message || 'Organization created. Sign in to continue.');
      location.hash = '#/login';
    } catch (err) { toast(err.message, true); }
  };
}

async function viewProfile() {
  if (!await ensureChrome()) return;
  spinner();
  try {
    const me = await Api.myself();
    render(`<h2>Profile</h2><div class="card">${dlHtml(me)}</div>
      <div class="actions">
        <button id="logout" class="danger">Sign out</button>
      </div>`);
    $('#logout').onclick = async () => { await Api.logout(); ME = null; location.hash = '#/login'; };
  } catch (e) { errorBox(e); }
}

/* ------------------------------------------------------------------- home */

async function viewHome() {
  if (!await ensureChrome()) return;
  spinner();
  const tiles = [
    ['#/search', 'search', 'Global Search', 'Find diseases, drugs, procedures, tests, articles'],
    ['#/ask', 'chat', 'Ask AI', 'RAG answers grounded in the catalog'],
    ['#/differential', 'activity', 'Differential Dx', 'Rank diseases by matched symptoms'],
    ['#/interaction-check', 'pill', 'Interaction Check', 'Conflicts among a set of medications'],
    ['#/r/case-reports', 'file', 'Case Reports', 'File and browse case reports'],
    ['#/analytics', 'chart', 'Analytics', 'Tenant dashboards and stats'],
  ];
  if (ME.role === 'super_admin') tiles.push(['#/platform', 'chart', 'Platform', 'Cross-tenant analytics'], ['#/r/tenants', 'shield', 'Tenants', 'Approve and manage organizations']);
  const [health, dash] = await Promise.all([
    Api.public('/api/health/').then((h) => `API: ${h.status} · DB: ${h.db}`, () => 'API unreachable'),
    Api.get('/api/analytics/tenant/').catch(() => null),
  ]);
  let dashHtml = '';
  if (dash) {
    const kpis = [
      ['Searches (Total)', dash.total_searches],
      ['Active Users (30d)', dash.active_users],
      ['AI Answers Rated Up', dash.ai_feedback?.up],
      ['AI Answers Rated Down', dash.ai_feedback?.down],
    ].filter(([, v]) => v !== undefined);
    dashHtml = `<div class="tiles">${kpis.map(([k, v]) =>
      `<div class="tile kpi-tile"><span class="tile-label">${esc(k)}</span><span class="tile-val">${esc(fmtVal(v))}</span></div>`).join('')}</div>`;
    const panel = (title, rows) => {
      const c = Array.isArray(rows) && rows.length ? chartable(rows) : null;
      return c ? `<section><h3>${esc(title)}</h3>${chartHtml(rows, c)}</section>` : '';
    };
    const panels = panel('Search Trend (30d)', dash.search_trend) +
      panel('Top Searches', dash.top_searches) +
      panel('Most Viewed Diseases', dash.popular_diseases) +
      panel('Most Viewed Medications', dash.popular_medications);
    if (panels) dashHtml += `<div class="grid-2">${panels}</div>`;
  }
  render(`<h2>Welcome${ME.username ? ', ' + esc(ME.username) : ''}</h2>
    <p class="page-sub">${esc(Api.base)} · ${esc(health)}</p>
    ${dashHtml}
    <h3>Quick Actions</h3>
    <div class="tiles home-tiles">${tiles.map(([href, icon, t, d]) =>
      `<a class="tile linktile" href="${href}"><span class="tile-label">${ico(icon)}${esc(t)}</span><span class="muted">${esc(d)}</span></a>`).join('')}
    </div>`);
}

/* ----------------------------------------------- report summary (charts) */

// Small tallies over the loaded rows, mirroring the mobile report headers.
const distinct = (rows, k) =>
  new Set(rows.map((r) => String(r[k] ?? '').trim()).filter(Boolean)).size;
const countTrue = (rows, k) => rows.filter((r) => r[k] === true).length;
const countEq = (rows, k, v) =>
  rows.filter((r) => String(r[k] ?? '').trim() === v).length;
const sumOf = (rows, k) => rows.reduce((a, r) => a + (Number(r[k]) || 0), 0);

// Group rows by a string field into chart-shaped objects {key, [outLabel]: n},
// biggest first. `valKey` sums that field instead of counting rows.
function groupRows(rows, key, outLabel, { valKey, limit = 8 } = {}) {
  const m = new Map();
  for (const r of rows) {
    const k = String(r[key] ?? '').trim();
    if (!k) continue;
    m.set(k, (m.get(k) || 0) + (valKey ? Number(r[valKey]) || 0 : 1));
  }
  return [...m.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([k, v]) => ({ [key]: k, [outLabel]: v }));
}

// Per-resource summary: KPI tiles + breakdown charts, from the current page.
const REPORT_SUMMARY = {
  'immunizations': (rows) => ({
    kpis: [['Doses', rows.length], ['Vaccines', distinct(rows, 'vaccine')], ['States', distinct(rows, 'region')]],
    charts: [['Doses by vaccine', groupRows(rows, 'vaccine', 'doses')]],
  }),
  'lab-results': (rows) => ({
    kpis: [['Results', rows.length], ['Critical', countEq(rows, 'flag', 'critical')], ['Resistant', countEq(rows, 'susceptibility', 'resistant')]],
    charts: [['Results by flag', groupRows(rows, 'flag', 'results')]],
  }),
  'vital-events': (rows) => ({
    kpis: [['Births', countEq(rows, 'event_type', 'birth')], ['Deaths', countEq(rows, 'event_type', 'death')], ['Maternal', countTrue(rows, 'maternal_death')], ['Infant', countTrue(rows, 'infant_death')]],
    charts: [['Deaths by cause', groupRows(rows, 'cause_name', 'deaths')]],
  }),
  'stock-reports': (rows) => ({
    kpis: [['Medications', distinct(rows, 'medication_name')], ['Shortages', countTrue(rows, 'shortage')], ['Units consumed', sumOf(rows, 'consumed')]],
    charts: [['Most consumed', groupRows(rows, 'medication_name', 'consumed', { valKey: 'consumed' })]],
  }),
  'chw-reports': (rows) => ({
    kpis: [['Reports', rows.length], ['Danger signs', countTrue(rows, 'danger_signs')], ['Referred', countTrue(rows, 'referred')]],
    charts: [['By report type', groupRows(rows, 'report_type', 'reports')]],
  }),
  'facility-metrics': (rows) => ({
    kpis: [['Snapshots', rows.length], ['Patients treated', sumOf(rows, 'patients_treated')], ['Avg staff', rows.length ? Math.round(sumOf(rows, 'staff_on_duty') / rows.length) : 0]],
    charts: [],
  }),
  'insurance-claims': (rows) => ({
    kpis: [['Claims', rows.length], ['Total (₦)', sumOf(rows, 'amount')], ['Approved', countEq(rows, 'status', 'approved') + countEq(rows, 'status', 'paid')]],
    charts: [['By status', groupRows(rows, 'status', 'claims')], ['Top diagnoses', groupRows(rows, 'diagnosis_name', 'claims')]],
  }),
  'appointments': (rows) => ({
    kpis: [['Appointments', rows.length], ['Telemedicine', countEq(rows, 'mode', 'telemedicine')], ['No-shows', countEq(rows, 'status', 'no_show')]],
    charts: [['By status', groupRows(rows, 'status', 'appts')]],
  }),
};

// KPI tiles + any chartable breakdowns. A chart needs ≥2 categories
// (chartable()'s floor); single-category breakdowns just show the tiles.
function reportSummaryHtml(slug, rows) {
  const f = REPORT_SUMMARY[slug];
  if (!f || !rows.length) return '';
  const { kpis, charts } = f(rows);
  const tiles = `<div class="tiles">${kpis.map(([k, v]) =>
    `<div class="tile kpi-tile"><span class="tile-label">${esc(k)}</span><span class="tile-val">${esc(fmtVal(v))}</span></div>`).join('')}</div>`;
  const panels = charts.map(([title, data]) => {
    const c = Array.isArray(data) && data.length ? chartable(data) : null;
    return c ? `<section><h3>${esc(title)}</h3>${chartHtml(data, c)}</section>` : '';
  }).join('');
  return `<div class="report-summary">${tiles}${panels ? `<div class="grid-2">${panels}</div>` : ''}</div>`;
}

/* -------------------------------------------------- generic resource views */

function canWriteRes(slug, res) {
  if (res.readOnly) return false;
  if (res.roles === 'admin') return isPharmacyAdmin();
  if (res.roles === 'staff') return isPharmacyStaff();
  if (slug === 'users') return ['super_admin', 'tenant_admin'].includes(ME.role);
  return res.report ? Api.roleCanReport(ME.role) : Api.roleCanWrite(ME.role);
}

const listState = {}; // per-resource {page, search} kept across visits

async function viewList(slug) {
  const res = RESOURCES[slug];
  if (!res) return errorBox(new Error('Unknown resource: ' + slug));
  if (!await ensureChrome()) return;
  const st = (listState[slug] ||= { page: 1, search: '' });
  spinner();
  const canWrite = canWriteRes(slug, res);
  try {
    const query = { page: st.page };
    if (st.search) query.search = st.search;
    const { rows, count } = await Api.list(rpath(slug), query);
    const pages = count != null ? Math.max(1, Math.ceil(count / 25)) : 1;
    render(`
      <div class="page-head"><h2>${esc(res.title)}</h2>
        ${canWrite && slug !== 'tenants' ? `<a class="btn" href="#/r/${slug}/new">+ New</a>` : ''}
      </div>
      <form id="search-form" class="toolbar">
        <input name="q" placeholder="${res.search ? 'Search…' : 'Filter by search…'}" value="${esc(st.search)}">
        <button>Search</button>
      </form>
      ${res.report ? reportSummaryHtml(slug, rows) : ''}
      ${rows.length ? tableHtml(rows, (r) => `#/r/${slug}/${r.id}`) : '<p class="muted">Nothing here yet.</p>'}
      <div class="pager">
        <button id="prev" ${st.page <= 1 ? 'disabled' : ''}>&larr; Prev</button>
        <span>Page ${st.page}${count != null ? ` of ${pages} (${count})` : ''}</span>
        <button id="next" ${st.page >= pages ? 'disabled' : ''}>Next &rarr;</button>
      </div>`);
    $('#search-form').onsubmit = (e) => {
      e.preventDefault();
      st.search = new FormData(e.target).get('q').trim();
      st.page = 1;
      viewList(slug);
    };
    $('#prev').onclick = () => { st.page--; viewList(slug); };
    $('#next').onclick = () => { st.page++; viewList(slug); };
  } catch (e) { errorBox(e); }
}

function dlHtml(obj) {
  // Nested row lists (a sale's lines, an order's lines) render as their own
  // table — as JSON they are unreadable exactly where the detail matters.
  const cell = (k, v) => Array.isArray(v) && v.length && typeof v[0] === 'object'
    ? tableHtml(v) : cellHtml(k, v);
  return `<dl class="detail">${Object.entries(obj).map(([k, v]) =>
    `<dt>${esc(label(k))}</dt><dd>${cell(k, v)}</dd>`).join('')}</dl>`;
}

async function viewDetail(slug, id) {
  const res = RESOURCES[slug];
  if (!res) return errorBox(new Error('Unknown resource: ' + slug));
  if (!await ensureChrome()) return;
  spinner();
  const canWrite = canWriteRes(slug, res);
  try {
    const obj = await Api.get(rpath(slug, `${id}/`));
    let actions = `<a class="btn ghost" href="#/r/${slug}">&larr; ${esc(res.title)}</a>`;
    if (canWrite) {
      actions += `<a class="btn" href="#/r/${slug}/${id}/edit">Edit</a>
        <button id="del" class="btn danger">Delete</button>`;
    }
    if (res.graph) actions += `<a class="btn ghost" href="#/graph/${res.graph}/${id}">Graph</a>`;
    let workflowHtml = '';
    if (res.workflow && obj.status && canWrite) {
      const targets = TRANSITIONS[obj.status] || [];
      workflowHtml = `<div class="card"><h3>Workflow — ${esc(obj.status)}</h3>
        <div class="actions">${targets.map((t) =>
          `<button class="btn" data-to="${t}">&rarr; ${esc(t)}</button>`).join('') || '<span class="muted">No transitions.</span>'}
        </div><div id="history"></div></div>`;
    }
    let tenantHtml = '';
    if (res.tenantActions) {
      tenantHtml = `<div class="card"><h3>Subscription: ${esc(obj.subscription_status)} · Status: ${esc(obj.status)}</h3>
        <div class="actions">
          <button class="btn" data-ta="approve">Approve</button>
          <button class="btn" data-ta="reject">Reject</button>
          <button class="btn danger" data-ta="suspend">Suspend / Reactivate</button>
        </div></div>`;
    }
    // Module actions (dispensing, claims, orders): each POSTs to its own
    // endpoint; ``ask`` collects the one value the endpoint needs.
    // Offer only the transitions this record's state actually allows — the API
    // rejects the rest, so a button that always fails is just a trap.
    const acts = (res.actions || []).filter((a) =>
      (!a.adminOnly || isPharmacyAdmin()) && (!a.when || a.when.includes(obj.status)));
    const actsHtml = acts.map((a) =>
      `<button class="btn${a.danger ? ' danger' : ''}" data-pa="${a.name}" data-ask="${a.ask || ''}">${esc(a.label)}</button>`).join('');
    if (res.receipt) actions += `<button id="receipt" class="btn ghost">Print receipt</button>`;
    render(`<div class="page-head"><h2>${esc(obj.name || obj.generic_name || obj.title || obj.reference || res.title + ' #' + id)}</h2></div>
      <div class="actions">${actions}</div>
      ${tenantHtml}${workflowHtml}
      ${actsHtml ? `<div class="card"><h3>Actions</h3><div class="actions">${actsHtml}</div></div>` : ''}
      <div class="card">${dlHtml(obj)}</div>
      ${res.extra === 'purchase' ? purchaseReceiveHtml(obj) : ''}`);
    if (res.receipt) $('#receipt').onclick = () => printReceipt(id);
    if (res.extra === 'purchase') wirePurchaseReceive(id, () => viewDetail(slug, id));
    for (const b of document.querySelectorAll('[data-pa]')) {
      b.onclick = async () => {
        const body = {};
        if (b.dataset.ask) {
          const answer = prompt(`${b.textContent} — ${b.dataset.ask}:`);
          if (answer === null) return;
          if (answer !== '') body[b.dataset.ask] = answer;
        }
        try {
          const r = await Api.post(rpath(slug, `${id}/${b.dataset.pa}/`), body);
          toast(r?.message || 'Done.');
          viewDetail(slug, id);
        } catch (e) { toast(e.message, true); }
      };
    }
    if (canWrite) {
      $('#del').onclick = async () => {
        if (!confirm('Delete this record? This cannot be undone.')) return;
        try { await Api.del(rpath(slug, `${id}/`)); toast('Deleted.'); location.hash = `#/r/${slug}`; }
        catch (e) { toast(e.message, true); }
      };
    }
    for (const b of document.querySelectorAll('[data-to]')) {
      b.onclick = async () => {
        const note = prompt(`Note for transition to "${b.dataset.to}" (optional):`) ?? '';
        try { await Api.post(rpath(slug, `${id}/transition/`), { to: b.dataset.to, note }); toast('Status updated.'); viewDetail(slug, id); }
        catch (e) { toast(e.message, true); }
      };
    }
    for (const b of document.querySelectorAll('[data-ta]')) {
      b.onclick = async () => {
        try { const r = await Api.post(rpath(slug, `${id}/${b.dataset.ta}/`)); toast(r?.message || 'Done.'); viewDetail(slug, id); }
        catch (e) { toast(e.message, true); }
      };
    }
    if (res.workflow && $('#history')) {
      try {
        const hist = await Api.get(rpath(slug, `${id}/history/`));
        $('#history').innerHTML = hist.length ? tableHtml(hist) : '<p class="muted">No history.</p>';
      } catch { /* history is optional sugar */ }
    }
  } catch (e) { errorBox(e); }
}

/* Create/edit form generated from DRF OPTIONS metadata. */
async function viewForm(slug, id) {
  const res = RESOURCES[slug];
  if (!res) return errorBox(new Error('Unknown resource: ' + slug));
  if (!await ensureChrome()) return;
  spinner();
  try {
    const metaPath = id ? rpath(slug, `${id}/`) : rpath(slug);
    const [meta, current] = await Promise.all([
      Api.options(metaPath),
      id ? Api.get(rpath(slug, `${id}/`)) : Promise.resolve({}),
    ]);
    const fields = meta?.actions?.PUT || meta?.actions?.POST;
    if (!fields) return errorBox(new Error('You do not have permission to edit this resource.'));
    const inputs = Object.entries(fields)
      .filter(([, f]) => !f.read_only)
      .map(([name, f]) => fieldHtml(name, f, current[name])).join('');
    render(`<div class="page-head"><h2>${id ? 'Edit' : 'New'} — ${esc(res.title)}</h2></div>
      <form id="f" class="card form-card">${inputs}
        <div class="actions">
          <button type="submit" class="btn">${id ? 'Save' : 'Create'}</button>
          <a class="btn ghost" href="#/r/${slug}${id ? '/' + id : ''}">Cancel</a>
        </div>
      </form>`);
    $('#f').onsubmit = async (e) => {
      e.preventDefault();
      const body = collectForm(e.target, fields);
      try {
        const saved = id ? await Api.patch(rpath(slug, `${id}/`), body)
          : await Api.post(rpath(slug), body);
        toast('Saved.');
        location.hash = `#/r/${slug}/${saved?.id ?? id ?? ''}`;
      } catch (err) {
        if (!id && res.report && !(err instanceof Api.ApiError)) {
          // Network failure on a new report: queue it instead of losing it.
          Outbox.push(slug, body);
          toast('Offline — report queued, will sync when connection returns.');
          location.hash = `#/r/${slug}`;
          return;
        }
        toast(err.message, true);
        showFieldErrors(e.target, err.errors);
      }
    };
  } catch (e) { errorBox(e); }
}

function fieldHtml(name, f, value) {
  const req = f.required ? ' required' : '';
  const lbl = esc(f.label || label(name)) + (f.required ? ' *' : '');
  const help = f.help_text ? `<small class="muted">${esc(f.help_text)}</small>` : '';
  const v = value ?? '';
  let control;
  if (f.choices) {
    const isMulti = M2M_FIELDS.has(name);
    const sel = new Set(Array.isArray(v) ? v.map(String) : [String(v)]);
    const opts = f.choices.map((c) =>
      `<option value="${esc(c.value)}" ${sel.has(String(c.value)) ? 'selected' : ''}>${esc(c.display_name)}</option>`).join('');
    control = `<select name="${name}" ${isMulti ? 'multiple size="6"' : ''}${req}>${isMulti ? '' : '<option value=""></option>'}${opts}</select>`;
  } else if (f.type === 'boolean') {
    control = `<input type="checkbox" name="${name}" ${v ? 'checked' : ''}>`;
  } else if (f.type === 'integer' || f.type === 'decimal' || f.type === 'float') {
    control = `<input type="number" step="any" name="${name}" value="${esc(v)}"${req}>`;
  } else if (f.type === 'date') {
    control = `<input type="date" name="${name}" value="${esc(String(v).slice(0, 10))}"${req}>`;
  } else if (f.type === 'datetime') {
    control = `<input type="datetime-local" name="${name}" value="${esc(String(v).slice(0, 16))}"${req}>`;
  } else if (M2M_FIELDS.has(name) || Array.isArray(v)) {
    control = `<input name="${name}" value="${esc(Array.isArray(v) ? v.join(',') : v)}" placeholder="ids, comma-separated">`;
  } else if (f.type === 'field') {
    control = `<input type="number" name="${name}" value="${esc(v)}"${req} placeholder="related id">`;
  } else if (!f.max_length || f.max_length > 255) {
    control = `<textarea name="${name}" rows="4"${req}>${esc(v)}</textarea>`;
  } else {
    control = `<input name="${name}" value="${esc(v)}" maxlength="${f.max_length}"${req}>`;
  }
  return `<label data-field="${name}">${lbl}${control}${help}<em class="field-err"></em></label>`;
}

function collectForm(form, fields) {
  const body = {};
  for (const [name, f] of Object.entries(fields)) {
    if (f.read_only) continue;
    const elm = form.elements[name];
    if (!elm) continue;
    if (f.type === 'boolean') { body[name] = elm.checked; continue; }
    if (elm instanceof HTMLSelectElement && elm.multiple) {
      body[name] = [...elm.selectedOptions].map((o) => Number(o.value));
      continue;
    }
    const raw = elm.value.trim();
    if (raw === '') { if (!f.required) continue; body[name] = null; continue; }
    if (M2M_FIELDS.has(name) && !(elm instanceof HTMLSelectElement)) {
      body[name] = raw.split(',').map((s) => Number(s.trim())).filter((n) => !Number.isNaN(n));
    } else if (f.type === 'integer' || f.type === 'field') {
      body[name] = Number(raw);
    } else if (f.type === 'decimal' || f.type === 'float') {
      body[name] = raw; // DRF accepts string decimals
    } else {
      body[name] = raw;
    }
  }
  return body;
}

function showFieldErrors(form, errors) {
  for (const em of form.querySelectorAll('.field-err')) em.textContent = '';
  if (!errors) return;
  for (const [field, msgs] of Object.entries(errors)) {
    const lab = form.querySelector(`[data-field="${CSS.escape(field)}"] .field-err`);
    if (lab) lab.textContent = Array.isArray(msgs) ? msgs[0] : String(msgs);
  }
}

/* ------------------------------------------------------------- tool views */

async function viewSearch() {
  if (!await ensureChrome()) return;
  render(`<h2>Global Search</h2>
    <form id="f" class="toolbar"><input name="q" placeholder="At least 2 characters…" required minlength="2" autofocus>
    <button>Search</button></form><div id="out"></div>`);
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const q = new FormData(e.target).get('q').trim();
    $('#out').innerHTML = '<div class="loading">Searching…</div>';
    try {
      const data = await Api.get('/api/search/', { q });
      const links = { diseases: 'diseases', medications: 'medications', procedures: 'procedures', lab_tests: 'lab-tests', articles: 'articles' };
      let html = `<p class="muted">${esc(data.disclaimer || '')} · ${data.total} result(s)</p>`;
      for (const [key, slug] of Object.entries(links)) {
        const rows = data[key] || [];
        if (!rows.length) continue;
        html += `<h3>${esc(label(key))}</h3>` + tableHtml(rows, (r) => `#/r/${slug}/${r.id}`);
      }
      $('#out').innerHTML = html || '<p class="muted">No results.</p>';
    } catch (err) { $('#out').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
}

async function viewSemantic() {
  if (!await ensureChrome()) return;
  render(`<h2>Semantic Search</h2>
    <form id="f" class="toolbar"><input name="q" placeholder="Describe what you need…" required autofocus>
    <button>Search</button></form><div id="out"></div>`);
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    $('#out').innerHTML = '<div class="loading">Searching…</div>';
    try {
      const data = await Api.get('/api/ai/semantic-search/', { q: new FormData(e.target).get('q').trim() });
      $('#out').innerHTML = renderData(data.results ?? data);
    } catch (err) { $('#out').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
}

async function viewAsk() {
  if (!await ensureChrome()) return;
  render(`<h2>Ask AI</h2>
    <p class="muted">Answers are educational only — not medical advice.</p>
    <form id="f" class="toolbar"><input name="q" placeholder="Ask a clinical question…" required autofocus>
    <button>Ask</button></form><div id="out"></div>`);
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    $('#out').innerHTML = '<div class="loading">Thinking…</div>';
    try {
      const data = await Api.get('/api/ai/ask/', { q: new FormData(e.target).get('q').trim() });
      let html = `<div class="card"><p class="answer">${esc(data.answer)}</p>`;
      if (data.interaction_id) {
        html += `<div class="actions"><span class="muted">Helpful?</span>
          <button class="btn ghost" data-vote="up">&#128077;</button>
          <button class="btn ghost" data-vote="down">&#128078;</button></div>`;
      }
      html += '</div>';
      if (data.sources?.length) html += '<h3>Sources</h3>' + renderData(data.sources);
      $('#out').innerHTML = html;
      for (const b of document.querySelectorAll('[data-vote]')) {
        b.onclick = async () => {
          try {
            const r = await Api.post(`/api/analytics/ai/${data.interaction_id}/feedback/`, { vote: b.dataset.vote });
            toast(r?.message || 'Thanks for the feedback.');
          } catch (err) { toast(err.message, true); }
        };
      }
    } catch (err) { $('#out').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
}

// Multi-pick over a searchable list endpoint; used by differential + interaction check.
async function pickerView({ title, blurb, listPath, labelOf, submitLabel, onSubmit }) {
  if (!await ensureChrome()) return;
  const picked = new Map();
  render(`<h2>${esc(title)}</h2><p class="muted">${esc(blurb)}</p>
    <form id="s" class="toolbar"><input name="q" placeholder="Search…"><button>Find</button></form>
    <div id="opts"></div>
    <h3>Selected</h3><div id="picked" class="chips"><span class="muted">Nothing selected.</span></div>
    <div class="actions"><button id="go" class="btn">${esc(submitLabel)}</button></div>
    <div id="out"></div>`);
  const drawPicked = () => {
    $('#picked').innerHTML = picked.size
      ? [...picked.entries()].map(([id, name]) =>
        `<span class="chip">${esc(name)} <button data-un="${id}">&times;</button></span>`).join('')
      : '<span class="muted">Nothing selected.</span>';
    for (const b of document.querySelectorAll('[data-un]')) {
      b.onclick = () => { picked.delete(Number(b.dataset.un)); drawPicked(); };
    }
  };
  const search = async (q) => {
    $('#opts').innerHTML = '<div class="loading">Loading…</div>';
    try {
      const { rows } = await Api.list(listPath, q ? { search: q } : undefined);
      $('#opts').innerHTML = rows.length ? `<div class="chips">${rows.map((r) =>
        `<button class="chip pick" data-id="${r.id}" data-name="${esc(labelOf(r))}">${esc(labelOf(r))}</button>`).join('')}</div>`
        : '<p class="muted">No matches.</p>';
      for (const b of document.querySelectorAll('.pick')) {
        b.onclick = () => { picked.set(Number(b.dataset.id), b.dataset.name); drawPicked(); };
      }
    } catch (err) { $('#opts').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
  $('#s').onsubmit = (e) => { e.preventDefault(); search(new FormData(e.target).get('q').trim()); };
  $('#go').onclick = async () => {
    $('#out').innerHTML = '<div class="loading">Checking…</div>';
    try { $('#out').innerHTML = await onSubmit([...picked.keys()]); }
    catch (err) { $('#out').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
  search('');
}

const viewDifferential = () => pickerView({
  title: 'Differential Diagnosis',
  blurb: 'Pick the presenting symptoms; diseases are ranked by how many match. Decision support, not diagnosis.',
  listPath: '/api/symptoms/',
  labelOf: (r) => r.name,
  submitLabel: 'Rank diseases',
  onSubmit: async (ids) => {
    if (!ids.length) return '<p class="err">Select at least one symptom.</p>';
    const data = await Api.post('/api/differential/', { symptom_ids: ids });
    return `<p class="muted">${esc(data.disclaimer)}</p>` +
      (data.results.length ? tableHtml(data.results, (r) => `#/r/diseases/${r.id}`) : '<p class="muted">No matches.</p>');
  },
});

const viewInteractionCheck = () => pickerView({
  title: 'Drug Interaction Check',
  blurb: 'Pick two or more medications to find every known interaction among them.',
  listPath: '/api/medications/',
  labelOf: (r) => r.generic_name || r.name,
  submitLabel: 'Check interactions',
  onSubmit: async (ids) => {
    if (ids.length < 2) return '<p class="err">Select at least two medications.</p>';
    const data = await Api.post('/api/interactions/check/', { medication_ids: ids });
    return `<p class="muted">${esc(data.disclaimer)}</p>` +
      (data.interactions.length ? tableHtml(data.interactions)
        : '<p class="ok">No known interactions among the selected medications.</p>');
  },
});

async function viewNotifiable() {
  if (!await ensureChrome()) return;
  render(`<h2>Notifiable Cases</h2>
    <p class="muted">Cases of legally-notifiable diseases — the regulator report.</p>
    <form id="f" class="toolbar">
      <label>From <input type="date" name="from"></label>
      <label>To <input type="date" name="to"></label>
      <button>Load</button>
      <button type="button" id="csv" class="ghost">Download CSV</button>
    </form><div id="out"></div>`);
  const params = () => {
    const fd = new FormData($('#f'));
    return { from: fd.get('from'), to: fd.get('to') };
  };
  const load = async () => {
    $('#out').innerHTML = '<div class="loading">Loading…</div>';
    try {
      const data = await Api.get('/api/reports/notifiable/', params());
      $('#out').innerHTML = `<p class="muted">${data.count} case(s)</p>` +
        (data.cases.length ? tableHtml(data.cases) : '<p class="muted">No notifiable cases in range.</p>');
    } catch (err) { $('#out').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
  $('#f').onsubmit = (e) => { e.preventDefault(); load(); };
  $('#csv').onclick = () => Api.download('/api/reports/notifiable/', { ...params(), format: 'csv' }, 'notifiable_cases.csv')
    .catch((err) => toast(err.message, true));
  load();
}

async function viewGraph(type, id) {
  if (!await ensureChrome()) return;
  spinner();
  const slugOf = { diseases: 'diseases', medications: 'medications', procedures: 'procedures', specialties: 'specialties' };
  try {
    const data = await Api.get(`/api/graph/${type}/${id}/`);
    let html = `<h2>Knowledge Graph — ${esc(label(type))} #${esc(id)}</h2>`;
    for (const [key, v] of Object.entries(data)) {
      if (Array.isArray(v)) {
        html += `<h3>${esc(label(key))} (${v.length})</h3>`;
        html += v.length ? tableHtml(v, key in { related_diseases: 1, treats_diseases: 1, diseases: 1 } ? (r) => `#/r/diseases/${r.id}` : null)
          : '<p class="muted">None.</p>';
      } else if (v && typeof v === 'object') {
        html += `<div class="card">${dlHtml(v)}</div>`;
      }
    }
    render(html);
  } catch (e) { errorBox(e); }
}

/* --------------------------------------------------------- analytics views */

function statIndex(title, registry, prefix) {
  return `<h2>${esc(title)}</h2><div class="tiles home-tiles">` +
    registry.map((m) => `<a class="tile linktile" href="#${prefix}/${m.key}"><span class="tile-label">${ico('chart')}${esc(m.label)}</span></a>`).join('') +
    '</div>';
}

async function viewAnalytics(registry, prefix, key) {
  if (!await ensureChrome()) return;
  if (!key) {
    // Index page shows the dashboard inline plus links to every metric.
    spinner();
    let dash = '';
    try { dash = renderData(await Api.get(registry[0].path)); }
    catch (e) { dash = `<p class="err">${esc(e.message)}</p>`; }
    return render(statIndex(prefix === '/platform' ? 'Platform Analytics' : 'Tenant Analytics', registry, prefix) +
      `<h3>${esc(registry[0].label)}</h3>` + dash);
  }
  const m = registry.find((x) => x.key === key);
  if (!m) return errorBox(new Error('Unknown metric: ' + key));
  const controls = [];
  if (m.dates) controls.push('<label>From <input type="date" name="from"></label>', '<label>To <input type="date" name="to"></label>');
  if (m.weeks) controls.push('<label>Weeks <input type="number" name="weeks" min="1" value="4"></label>');
  render(`<div class="page-head"><h2>${esc(m.label)}</h2>
      <a class="btn ghost" href="#${prefix}">&larr; All metrics</a></div>
    <form id="f" class="toolbar">${controls.join('')}
      ${controls.length ? '<button>Load</button>' : ''}
      ${m.csv ? '<button type="button" id="csv" class="ghost">Download CSV</button>' : ''}
      ${m.exportPath ? '<button type="button" id="export" class="ghost">Export CSV</button>' : ''}
    </form><div id="out"></div>`);
  const params = () => {
    const fd = new FormData($('#f'));
    const q = {};
    for (const k of ['from', 'to', 'weeks']) if (fd.get(k)) q[k] = fd.get(k);
    return q;
  };
  const load = async () => {
    $('#out').innerHTML = '<div class="loading">Loading…</div>';
    try { $('#out').innerHTML = renderData(await Api.get(m.path, params())); }
    catch (err) { $('#out').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
  $('#f').onsubmit = (e) => { e.preventDefault(); load(); };
  if (m.csv) $('#csv').onclick = () => Api.download(m.path, { ...params(), format: 'csv' }, `${key}.csv`).catch((e) => toast(e.message, true));
  if (m.exportPath) $('#export').onclick = () => Api.download(m.exportPath, params(), `${key}.csv`).catch((e) => toast(e.message, true));
  load();
}

/* ------------------------------------------------------------- pharmacy */

const PHARMACY_ADMIN_ROLES = new Set(['super_admin', 'tenant_admin']);
const PHARMACY_STAFF_ROLES = new Set([...PHARMACY_ADMIN_ROLES, 'pharmacist']);
const isPharmacyAdmin = () => PHARMACY_ADMIN_ROLES.has(ME?.role);
const isPharmacyStaff = () => PHARMACY_STAFF_ROLES.has(ME?.role);

// Naira, two decimals. Prefixed, because a bare "14,115.00" on a till screen
// is a number without a unit — the mobile client formats it the same way.
const money = (v) => '₦' + Number(v || 0).toLocaleString(undefined, {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});

/* Receipts come back as HTML, not JSON: fetch with the JWT, then hand the
   markup to a new window so the browser's own print dialog does the printing. */
async function printReceipt(saleId) {
  try {
    const html = await Api.text(`/api/pharmacy/sales/${saleId}/receipt/`);
    const w = window.open('', '_blank');
    if (!w) return toast('Allow pop-ups to print the receipt.', true);
    w.document.write(html);
    w.document.close();
  } catch (e) { toast(e.message, true); }
}

/* The counter's own home: what to reorder, what is about to expire, what was
   taken today, and what the insurers still owe. */
async function viewPharmacy() {
  if (!await ensureChrome()) return;
  if (!isPharmacyStaff()) return errorBox(new Error('Pharmacy staff only.'));
  spinner();
  const today = new Date().toISOString().slice(0, 10);
  try {
    const [low, expiring, sales, claims, value] = await Promise.all([
      Api.get('/api/pharmacy/items/low-stock/').catch(() => []),
      Api.get('/api/pharmacy/batches/expiring/', { days: 60 }).catch(() => []),
      Api.get('/api/pharmacy/sales/summary/', { from: today, to: today }).catch(() => null),
      Api.get('/api/pharmacy/claims/summary/').catch(() => null),
      Api.get('/api/pharmacy/items/valuation/').catch(() => null),
    ]);
    const tile = (label, value) =>
      `<div class="tile"><span class="tile-label">${esc(label)}</span><span class="tile-val">${esc(value)}</span></div>`;
    render(`
      <div class="page-head"><h2>Pharmacy</h2>
        <a class="btn" href="#/pharmacy/sell">+ Dispense</a></div>
      <div class="tiles">
        ${tile('Sales today', sales ? sales.sales : '—')}
        ${tile('Billed today', sales ? money(sales.billed) : '—')}
        ${tile('Collected today', sales ? money(sales.collected) : '—')}
        ${tile('Owed by patients', sales ? money(sales.outstanding) : '—')}
        ${tile('Owed by insurers', claims ? money(claims.outstanding) : '—')}
        ${tile('Stock at cost', value ? money(value.cost_value) : '—')}
      </div>
      <div class="card"><h3>Reorder (${low.length})</h3>
        ${low.length ? tableHtml(low.map((r) => ({
          id: r.id, item: r.name, on_hand: r.quantity_on_hand,
          reorder_level: r.reorder_level, unit_price: money(r.unit_price),
        })), (r) => `#/r/pharmacy-items/${r.id}`) : '<p class="muted">Nothing to reorder.</p>'}
      </div>
      <div class="card"><h3>Expiring within 60 days (${expiring.length})</h3>
        ${expiring.length ? tableHtml(expiring.map((b) => ({
          id: b.id, item: b.item_name, batch: b.batch_number,
          expiry_date: b.expiry_date, quantity: b.quantity,
        })), (b) => `#/r/pharmacy-batches/${b.id}`) : '<p class="muted">Nothing expiring.</p>'}
      </div>
      <div class="card"><h3>Insurers</h3>
        ${claims && claims.by_hmo.length ? tableHtml(claims.by_hmo.map((h) => ({
          hmo: h.name, claims: h.claims, claimed: money(h.claimed),
          approved: money(h.approved), paid: money(h.paid),
          outstanding: money(h.outstanding),
        }))) : '<p class="muted">No claims yet.</p>'}
      </div>`);
  } catch (e) { errorBox(e); }
}

/* Dispensing counter. The server picks the batches (first expiry first out),
   so this screen only asks what and how many. */
async function viewSell() {
  if (!await ensureChrome()) return;
  if (!isPharmacyStaff()) return errorBox(new Error('Pharmacy staff only.'));
  spinner();
  const basket = [];
  let items = [];
  try {
    // Walk the pages: the picker is useless if it stops at the first 25 items.
    // ponytail: capped at 10 pages; past ~250 lines this wants a search box.
    for (let page = 1; page <= 10; page++) {
      const { rows, next } = await Api.list('/api/pharmacy/items/', { is_active: true, page });
      items.push(...rows);
      if (!next) break;
    }
  } catch (e) { return errorBox(e); }

  const optionsHtml = items.map((i) =>
    `<option value="${i.id}" data-price="${i.unit_price}" data-stock="${i.quantity_on_hand}">
      ${esc(i.name)} — ${money(i.unit_price)} (${i.quantity_on_hand} in stock)</option>`).join('');

  const basketHtml = () => basket.length ? `
    <table><thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Price</th><th class="num">Total</th><th></th></tr></thead>
    <tbody>${basket.map((b, i) => `<tr>
      <td>${esc(b.name)}</td><td class="num">${b.quantity}</td>
      <td class="num">${money(b.price)}</td><td class="num">${money(b.price * b.quantity)}</td>
      <td><button class="btn ghost" data-drop="${i}">Remove</button></td></tr>`).join('')}
    </tbody></table>
    <p><b>Total: ${money(basket.reduce((a, b) => a + b.price * b.quantity, 0))}</b></p>`
    : '<p class="muted">Nothing added yet.</p>';

  const draw = () => {
    render(`
      <div class="page-head"><h2>Dispense</h2>
        <a class="btn ghost" href="#/pharmacy">&larr; Pharmacy</a></div>
      <form id="add" class="card form-card">
        <label>Item<select name="stock_item">${optionsHtml}</select></label>
        <label>Quantity<input type="number" name="quantity" min="1" value="1"></label>
        <label>Discount<input type="number" name="discount" min="0" step="0.01" value="0"></label>
        <div class="actions"><button class="btn">Add to sale</button></div>
      </form>
      <div class="card"><h3>Sale</h3><div id="basket">${basketHtml()}</div></div>
      <form id="checkout" class="card form-card">
        <label>Patient (optional — leave blank for a walk-in)
          <input name="patient_search" placeholder="Name or hospital number…"></label>
        <div id="patient-hit" class="muted"></div>
        <label>Payment<select name="payment_method">
          <option value="cash">Cash</option><option value="card">Card</option>
          <option value="transfer">Transfer</option><option value="hmo">HMO / scheme</option>
        </select></label>
        <label>Scheme membership<select name="enrollment"><option value="">—</option></select></label>
        <div class="actions"><button class="btn">Complete sale</button></div>
      </form>`);

    $('#add').onsubmit = (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const opt = e.target.stock_item.selectedOptions[0];
      if (!opt) return;
      basket.push({
        item: Number(fd.get('stock_item')), name: opt.textContent.split(' — ')[0].trim(),
        quantity: Number(fd.get('quantity')), price: Number(opt.dataset.price),
        discount: Number(fd.get('discount')) || 0,
      });
      draw();
    };
    for (const b of document.querySelectorAll('[data-drop]')) {
      b.onclick = () => { basket.splice(Number(b.dataset.drop), 1); draw(); };
    }

    // Patient lookup fills the scheme dropdown — an HMO sale needs the card.
    let patientId = null;
    const search = $('#checkout').patient_search;
    search.onchange = async () => {
      patientId = null;
      $('#checkout').enrollment.innerHTML = '<option value="">—</option>';
      const q = search.value.trim();
      if (!q) return ($('#patient-hit').textContent = '');
      try {
        const { rows } = await Api.list('/api/patients/', { search: q, page_size: 5 });
        if (!rows.length) return ($('#patient-hit').textContent = 'No patient found.');
        const p = rows[0];
        patientId = p.id;
        $('#patient-hit').textContent = `${p.full_name || p.first_name} · ${p.hospital_number}`;
        const en = await Api.list('/api/pharmacy/enrollments/', { patient: p.id, is_active: true });
        $('#checkout').enrollment.innerHTML = '<option value="">—</option>' + en.rows.map((r) =>
          `<option value="${r.id}">${esc(r.hmo_name)} · ${esc(r.member_number)} (${r.effective_coverage}%)</option>`).join('');
      } catch (err) { $('#patient-hit').textContent = err.message; }
    };

    $('#checkout').onsubmit = async (e) => {
      e.preventDefault();
      if (!basket.length) return toast('Add at least one item.', true);
      const fd = new FormData(e.target);
      const body = {
        payment_method: fd.get('payment_method'),
        items: basket.map((b) => ({ item: b.item, quantity: b.quantity, discount: b.discount })),
      };
      if (patientId) body.patient = patientId;
      if (fd.get('enrollment')) body.enrollment = Number(fd.get('enrollment'));
      try {
        const sale = await Api.post('/api/pharmacy/sales/', body);
        toast(`Sale ${sale.reference} — patient pays ${money(sale.patient_payable)}.`);
        location.hash = `#/r/pharmacy-sales/${sale.id}`;
      } catch (err) { toast(err.message, true); }
    };
  };
  draw();
}

/* Receiving a delivery against a purchase order line. Rendered under the
   order's detail page, where the outstanding quantities are already listed. */
function purchaseReceiveHtml(order) {
  const open = (order.lines || []).filter((l) => l.outstanding > 0);
  if (!open.length || order.status === 'cancelled') return '';
  return `<div class="card"><h3>Receive a delivery</h3>
    <form id="receive" class="form-card">
      <label>Line<select name="line">${open.map((l) =>
        `<option value="${l.id}">${esc(l.item_name)} — ${l.outstanding} outstanding</option>`).join('')}</select></label>
      <label>Quantity<input type="number" name="quantity" min="1" required></label>
      <label>Batch number<input name="batch_number" required></label>
      <label>Expiry<input type="date" name="expiry_date"></label>
      <label>Unit cost (invoice)<input type="number" name="unit_cost" step="0.01" min="0"></label>
      <div class="actions"><button class="btn">Book in</button></div>
    </form></div>`;
}

function wirePurchaseReceive(orderId, reload) {
  const form = $('#receive');
  if (!form) return;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      line: Number(fd.get('line')), quantity: Number(fd.get('quantity')),
      batch_number: fd.get('batch_number'),
    };
    if (fd.get('expiry_date')) body.expiry_date = fd.get('expiry_date');
    if (fd.get('unit_cost')) body.unit_cost = fd.get('unit_cost');
    try {
      const r = await Api.post(`/api/pharmacy/purchase-orders/${orderId}/receive/`, body);
      toast(r?.message || 'Received.');
      reload();
    } catch (err) { toast(err.message, true); }
  };
}

/* ----------------------------------------------------------------- router */

const routes = [
  [/^\/login$/, viewLogin],
  [/^\/register$/, viewRegister],
  [/^\/onboarding$/, viewOnboarding],
  [/^\/profile$/, viewProfile],
  [/^\/?$/, viewHome],
  [/^\/r\/([a-z-]+)\/new$/, (m) => viewForm(m[1])],
  [/^\/r\/([a-z-]+)\/(\d+)\/edit$/, (m) => viewForm(m[1], m[2])],
  [/^\/r\/([a-z-]+)\/(\d+)$/, (m) => viewDetail(m[1], m[2])],
  [/^\/r\/([a-z-]+)$/, (m) => viewList(m[1])],
  [/^\/search$/, viewSearch],
  [/^\/semantic$/, viewSemantic],
  [/^\/ask$/, viewAsk],
  [/^\/differential$/, viewDifferential],
  [/^\/interaction-check$/, viewInteractionCheck],
  [/^\/notifiable$/, viewNotifiable],
  [/^\/graph\/([a-z]+)\/(\d+)$/, (m) => viewGraph(m[1], m[2])],
  [/^\/pharmacy$/, viewPharmacy],
  [/^\/pharmacy\/sell$/, viewSell],
  [/^\/analytics(?:\/([a-z-]+))?$/, (m) => viewAnalytics(ANALYTICS, '/analytics', m[1])],
  [/^\/platform(?:\/([a-z-]+))?$/, (m) => viewAnalytics(PLATFORM, '/platform', m[1])],
];

function route() {
  const path = location.hash.slice(1) || '/';
  const isAuthRoute = /^\/(login|register|onboarding)$/.test(path);
  if (!Api.isLoggedIn && !isAuthRoute) { location.hash = '#/login'; return; }
  if (Api.isLoggedIn && isAuthRoute) { location.hash = '#/'; return; }
  for (const [re, view] of routes) {
    const m = path.match(re);
    if (m) return view(m);
  }
  errorBox(new Error('Page not found: ' + path));
}

window.addEventListener('hashchange', () => { vizTip().hidden = true; route(); });
$('#nav-toggle').onclick = () => $('#sidebar').classList.toggle('open');
$('#theme-toggle').onclick = () => {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  localStorage.theme = t;
  applyTheme(t);
};
route();
Outbox.flush(); // send anything queued from a previous offline session
