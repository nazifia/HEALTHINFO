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
  // Cancelling one drug stops the whole prescription it was written on — the
  // drugs on it are one decision, and a dispensed one is left alone.
  'prescriptions':     { title: 'Prescriptions',      group: 'Reports', report: true,
                          actions: [{ name: 'cancel', label: 'Cancel prescription', danger: true,
                                      when: ['prescribed', 'partially_dispensed'] }] },
  'pharmacy-items':         { title: 'Stock Items',     group: 'Pharmacy', path: 'pharmacy/items',           roles: 'admin', search: true },
  'pharmacy-batches':       { title: 'Stock Batches',   group: 'Pharmacy', path: 'pharmacy/batches',         roles: 'staff', search: true, readOnly: true },
  'pharmacy-movements':     { title: 'Stock Ledger',    group: 'Pharmacy', path: 'pharmacy/movements',       roles: 'staff', readOnly: true },
  'pharmacy-suppliers':     { title: 'Suppliers',       group: 'Pharmacy', path: 'pharmacy/suppliers',       roles: 'admin', search: true },
  'pharmacy-orders':        { title: 'Purchase Orders', group: 'Pharmacy', path: 'pharmacy/purchase-orders', roles: 'staff', search: true, extra: 'purchase',
                              actions: [{ name: 'submit', label: 'Submit to supplier', when: ['draft'] },
                                        { name: 'cancel', label: 'Cancel order', danger: true, when: ['draft', 'submitted', 'partial'] }] },
  'pharmacy-hospitals':     { title: 'Hospitals',      group: 'Pharmacy', path: 'prescriptions/hospitals',   roles: 'admin', search: true },
  // What a prescriber has earned and what is still owed them, on their own
  // page (extra: 'statement') — the two ledgers are settled from there.
  'pharmacy-prescribers':   { title: 'Prescribers',    group: 'Pharmacy', path: 'prescriptions/prescribers', roles: 'admin', search: true, extra: 'statement' },
  'pharmacy-hmos':          { title: 'HMOs',            group: 'Pharmacy', path: 'pharmacy/hmos',            roles: 'admin', search: true },
  'pharmacy-enrollments':   { title: 'Scheme Members',  group: 'Pharmacy', path: 'pharmacy/enrollments',     roles: 'staff', search: true },
  // A scheme's price list: what it pays for one drug, and the most it pays
  // for a unit of it. 0 cover is the exclusion; no row means the scheme's own
  // default covers it. The insurer keeps its own list (roles: 'scheme').
  'pharmacy-item-rules':    { title: 'Price List',      group: 'Pharmacy', path: 'pharmacy/item-rules',      roles: 'scheme', search: true,
                              filters: [{ param: 'hmo', label: 'Scheme', path: '/api/pharmacy/hmos/', text: (r) => r.name }] },
  // The insurer's answer is four fields at once — a code, what they stand
  // behind, when it lapses, or why they refused — so it gets a form of its own
  // (extra: 'preauth') rather than a chain of prompts.
  'pharmacy-preauths':      { title: 'Authorisations',   group: 'Pharmacy', path: 'pharmacy/pre-authorizations', roles: 'staff', search: true, extra: 'preauth',
                              actions: [{ name: 'cancel', label: 'Withdraw request', ask: 'reason', danger: true, when: ['requested', 'approved'] }] },
  'pharmacy-sales':         { title: 'Sales',           group: 'Pharmacy', path: 'pharmacy/sales',           roles: 'staff', search: true, readOnly: true, receipt: true,
                              actions: [{ name: 'pay', label: 'Take payment', ask: 'amount', choose: 'method:cash,card,transfer', when: ['pending'] },
                                        { name: 'cancel', label: 'Cancel sale', danger: true, when: ['pending', 'paid'] }] },
  'pharmacy-till':          { title: 'Cash Drawer',    group: 'Pharmacy', path: 'pharmacy/till-sessions',   roles: 'staff', createOnly: true,
                              actions: [{ name: 'close', label: 'Close drawer', ask: 'amount,notes', when: ['open'] }] },
  'pharmacy-claims':        { title: 'Claims',          group: 'Pharmacy', path: 'pharmacy/claims',          roles: 'staff', search: true, readOnly: true,
                              actions: [{ name: 'submit', label: 'Submit', when: ['draft', 'rejected'] },
                                        { name: 'approve', label: 'Approve', ask: 'amount', adminOnly: true, when: ['submitted'] },
                                        { name: 'reject', label: 'Reject', ask: 'reason', adminOnly: true, when: ['submitted'] },
                                        { name: 'pay', label: 'Record payment', ask: 'amount', adminOnly: true, when: ['approved'] },
                                        { name: 'cancel', label: 'Stop billing', ask: 'reason', danger: true, adminOnly: true,
                                          when: ['draft', 'submitted', 'rejected', 'approved'] }] },
  'pharmacy-claim-batches': { title: 'Claim Batches',   group: 'Pharmacy', path: 'pharmacy/claim-batches',   roles: 'staff', search: true,
                              actions: [{ name: 'add-claims', label: 'Collect claims', when: ['draft'] },
                                        { name: 'submit', label: 'Submit batch', when: ['draft'] },
                                        { name: 'approve', label: 'Approve all', adminOnly: true, when: ['submitted'] },
                                        { name: 'pay', label: 'Allocate remittance', ask: 'amount', adminOnly: true, when: ['submitted', 'approved'] },
                                        { name: 'cancel', label: 'Cancel batch', danger: true, when: ['draft', 'submitted', 'approved'] }] },
  // The counter's customer list and their wallets. A balance is the total of
  // the ledger below it, so money moves through the actions — never by typing
  // over the field.
  'pharmacy-customers':     { title: 'Customers',       group: 'Pharmacy', path: 'customers',                roles: 'staff', search: true,
                              actions: [{ name: 'top-up', label: 'Top up wallet', ask: 'amount,note', choose: 'method:cash,pos,transfer' },
                                        { name: 'deduct', label: 'Deduct from wallet', ask: 'amount,note', adminOnly: true, danger: true }] },
  'pharmacy-wallet':        { title: 'Wallet Ledger',   group: 'Pharmacy', path: 'wallet-transactions',      roles: 'staff', readOnly: true, noLink: true },
  // Who owes the counter money, biggest first. The wallet is settled from the
  // customer's own row, so this list is the reading, not another place to act.
  'pharmacy-debtors':       { title: 'Debtors',         group: 'Pharmacy', path: 'customers/debtors',        roles: 'staff', readOnly: true, noLink: true },
  // Raise a stocktake over a set of items, count them, then apply the gaps.
  // ``extra: 'count'`` is the counting sheet; ``complete`` writes the
  // corrections to stock, which is why it sits with the admin.
  'pharmacy-stock-checks':  { title: 'Stock Checks',    group: 'Pharmacy', path: 'pharmacy/stock-checks',    roles: 'staff', extra: 'count',
                              actions: [{ name: 'complete', label: 'Apply and close', adminOnly: true, when: ['pending', 'in_progress'] },
                                        { name: 'cancel', label: 'Abandon count', danger: true, when: ['pending', 'in_progress'] }] },
  // Stock asked for from the other store. Approving moves it in the same
  // breath, so the quantity prompt is the sending store's answer.
  'pharmacy-transfers':     { title: 'Transfers',       group: 'Pharmacy', path: 'pharmacy/transfers',       roles: 'staff',
                              actions: [{ name: 'approve', label: 'Approve and send', ask: 'quantity', when: ['pending'] },
                                        { name: 'reject', label: 'Refuse', ask: 'reason', danger: true, when: ['pending'] },
                                        { name: 'receive', label: 'Confirm received', when: ['approved'] }] },
  'pharmacy-returns':       { title: 'Returns',         group: 'Pharmacy', path: 'pharmacy/returns',         roles: 'staff', readOnly: true, noLink: true },
  'pharmacy-dispensing-log':{ title: 'Dispensing Log',  group: 'Pharmacy', path: 'pharmacy/dispensing-log',  roles: 'staff', search: true, readOnly: true, noLink: true },
  'pharmacy-cashiers':      { title: 'Cashiers',        group: 'Pharmacy', path: 'pharmacy/cashiers',        roles: 'admin', search: true },
  // The dispenser's basket. Nothing leaves the shelf until ``complete`` —
  // until then this is an intention to sell, not a sale.
  // Read-only here: a basket is built at the counter (Dispense -> "Send to a
  // cashier"), where the prices and the stock are on screen.
  'pharmacy-requests':      { title: 'Payment Requests', group: 'Pharmacy', path: 'pharmacy/payment-requests', roles: 'staff', search: true, readOnly: true,
                              actions: [{ name: 'accept', label: 'Take the basket', when: ['pending'] },
                                        { name: 'reject', label: 'Refuse', ask: 'reason', danger: true, when: ['pending'] },
                                        { name: 'cancel', label: 'Withdraw', danger: true, when: ['pending', 'accepted'] },
                                        { name: 'complete', label: 'Turn into a sale', choose: 'payment_method:cash,card,transfer,wallet,hmo,split', when: ['accepted'] }] },
  'pharmacy-expense-cats':  { title: 'Expense Types',   group: 'Pharmacy', path: 'pharmacy/expense-categories', roles: 'admin', search: true },
  'pharmacy-expenses':      { title: 'Expenses',        group: 'Pharmacy', path: 'pharmacy/expenses',        roles: 'staff', search: true },
  // Money owed to a prescriber, raised by a sale. Read is staff-wide; paying
  // it out is the pharmacy's money leaving, so it is the admin's.
  'pharmacy-commissions':   { title: 'Prescriber Commissions', group: 'Pharmacy', path: 'prescriptions/commissions', roles: 'staff', readOnly: true,
                              actions: [{ name: 'pay', label: 'Mark paid', adminOnly: true, when: ['pending'] }] },
  'pharmacy-payouts':       { title: 'Consultation Payouts',   group: 'Pharmacy', path: 'prescriptions/consultation-payouts', roles: 'staff', readOnly: true,
                              actions: [{ name: 'pay', label: 'Mark paid', adminOnly: true, when: ['pending'] }] },
  'pharmacy-commission-configs': { title: 'Staff Commission Rates', group: 'Pharmacy', path: 'reports/commission-configs', roles: 'admin' },
  'branches':          { title: 'Branches',           group: 'Pharmacy', roles: 'admin', search: true },
  'patients':          { title: 'Patients',           group: 'Clinical', roles: 'clinical', search: true, history: true,
                          fileFrom: ['consultations', 'case-reports', 'prescriptions', 'lab-results', 'appointments'],
                          actions: [{ name: 'merge', label: 'Merge a duplicate into this record', ask: 'source', adminOnly: true }] },
  // The encounter itself. Closing settles the booking and the case report with
  // it, so it goes through the action rather than a PATCH of status.
  'consultations':     { title: 'Visits',             group: 'Clinical', report: true, fileFrom: ['prescriptions', 'case-reports'],
                          actions: [{ name: 'diagnose', label: 'Record diagnosis', ask: 'diagnosis',
                                      choose: 'severity:mild,moderate,severe,critical', when: ['open'] },
                                    { name: 'close', label: 'Close visit', ask: 'follow_up_on,notes',
                                      choose: 'disposition:home,follow_up,admitted,referred,deceased', when: ['open'] }] },
  'users':             { title: 'Users',              group: 'Admin', adminOnly: true },
  // The roster. Everyone in the tenant reads it — a nurse needs to know who
  // else is on — but only the tenant admin sets it, same as the API.
  'shifts':            { title: 'Staff Roster',       group: 'Admin', roles: 'tenant_admin',
                          filters: [{ param: 'branch', label: 'Branch', path: '/api/branches/', text: (r) => r.name },
                                    { param: 'user', label: 'Staff', path: '/api/users/', text: (r) => r.username }] },
  // The audit trail of who read which patient record. Tenant admins only, and
  // read-only for them too — the API writes it, nobody edits it.
  'patient-access-log':{ title: 'Patient Access Log', group: 'Admin', path: 'patients/access-log',
                          adminOnly: true, readOnly: true, noLink: true },
  'tenants-hospitals': { title: 'Hospitals',          group: 'Admin', path: 'tenants/hospitals',  superOnly: true, tenantActions: true },
  'tenants-pharmacies':{ title: 'Pharmacies',         group: 'Admin', path: 'tenants/pharmacies', superOnly: true, tenantActions: true },
};

// A resource's API path, which is the slug unless the registry overrides it
// (the pharmacy module nests everything under /api/pharmacy/).
const rpath = (slug, suffix = '') => `/api/${RESOURCES[slug]?.path || slug}/${suffix}`;

// The tenant lists are split by kind (/api/tenants/hospitals/), but a single
// tenant still lives at /api/tenants/<id>/ — strip the kind segment for detail.
const rdetail = (slug, suffix) => slug.startsWith('tenants-')
  ? `/api/tenants/${suffix}` : rpath(slug, suffix);

// M2M PK-list fields (catalog serializers). OPTIONS metadata can't tell
// many-related from single-related, so name them.
// ponytail: hardcoded set; derive from /api/schema/ if the model graph grows.
// ``items`` is the stock check's write-only list of what to count.
const M2M_FIELDS = new Set(['symptoms', 'medications', 'procedures', 'lab_tests', 'specialties', 'articles', 'items']);

// Fields whose blank or zero means something the generated label cannot say.
// DRF sends help_text when the model carries one; this fills in where it
// doesn't, and a real help_text still wins.
const FIELD_HINTS = {
  annual_limit: "Most this member's plan pays out in a calendar year. Blank is uncapped.",
  preauth_threshold: 'Insured amount above which this HMO clears a sale before it happens. 0 asks for no authorisation.',
  tariff: "Most the scheme pays for one unit, whatever the pharmacy charges. Blank covers the shelf price.",
};

// The drug fields of a clinical drug order. Everything else on that form —
// the patient, the region, the notes — is about the prescription as a whole,
// so an extra drug row repeats these and inherits the rest.
const RX_DRUG_FIELDS = ['medication', 'dose', 'frequency', 'duration_days'];

// Content workflow edges (mirrors apps/governance/workflow.py TRANSITIONS).
const TRANSITIONS = {
  draft: ['review'],
  review: ['approved', 'draft'],
  approved: ['published', 'review'],
  published: ['archived'],
  archived: ['draft'],
};

// Analytics endpoints. dates => from/to inputs; days => days input.
const ANALYTICS = [
  { key: 'dashboard',     label: 'Tenant Dashboard',  path: '/api/analytics/tenant/' },
  { key: 'cases',         label: 'Case Stats',        path: '/api/analytics/cases/', dates: true, exportPath: '/api/analytics/cases/export/' },
  { key: 'surveillance',  label: 'Outbreak Alerts',   path: '/api/analytics/surveillance/' },
  { key: 'idsr',          label: 'IDSR Report',       path: '/api/analytics/idsr/', days: true, csv: true },
  { key: 'sources',       label: 'Report Sources',    path: '/api/analytics/sources/' },
  { key: 'on-duty',       label: 'On Duty Now',       path: '/api/shifts/on_duty/' },
  { key: 'adr',           label: 'ADR Stats',         path: '/api/analytics/adr/', dates: true },
  { key: 'labs',          label: 'Lab Stats',         path: '/api/analytics/labs/', dates: true },
  { key: 'immunizations', label: 'Immunization Stats', path: '/api/analytics/immunizations/', dates: true },
  { key: 'vitals',        label: 'Vital Stats',       path: '/api/analytics/vitals/', dates: true },
  { key: 'stock',         label: 'Stock Stats',       path: '/api/analytics/stock/', dates: true },
  { key: 'chw',           label: 'CHW Stats',         path: '/api/analytics/chw/', dates: true },
  { key: 'facility',      label: 'Facility Stats',    path: '/api/analytics/facility/', dates: true },
  { key: 'insurance',     label: 'Insurance Stats',   path: '/api/analytics/insurance/', dates: true },
  { key: 'appointments',  label: 'Appointment Stats', path: '/api/analytics/appointments/', dates: true },
  { key: 'consultations', label: 'Visit Stats',       path: '/api/analytics/consultations/', dates: true },
  { key: 'prescriptions', label: 'Prescribing Stats', path: '/api/analytics/prescriptions/', dates: true },
  { key: 'funnel',        label: 'Funnel',            path: '/api/analytics/funnel/' },
  { key: 'retention',     label: 'Retention',         path: '/api/analytics/retention/' },
  { key: 'benchmark',     label: 'Benchmark',         path: '/api/analytics/benchmark/' },
];

const PLATFORM = [
  { key: 'dashboard',     label: 'Platform Dashboard', path: '/api/analytics/platform/' },
  { key: 'cases',         label: 'Case Stats',         path: '/api/analytics/platform/cases/', dates: true, exportPath: '/api/analytics/platform/cases/export/' },
  { key: 'surveillance',  label: 'Outbreak Alerts',    path: '/api/analytics/platform/surveillance/' },
  { key: 'idsr',          label: 'IDSR Report',        path: '/api/analytics/platform/idsr/', days: true, csv: true },
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
  { key: 'consultations', label: 'Visit Stats',        path: '/api/analytics/platform/consultations/', dates: true },
  { key: 'prescriptions', label: 'Prescribing Stats', path: '/api/analytics/platform/prescriptions/', dates: true },
];

/* The trading reports (/api/reports/*). Kept out of ANALYTICS because the API
   admits pharmacy staff only — a nurse opening the analytics index would get a
   page of 403s. ``ym`` is the monthly report's year/month pair; everything else
   takes the same from/to as the rest. */
const PHARMACY_REPORTS = [
  { key: 'sales',      label: 'Sales',            path: '/api/reports/sales/', dates: true },
  { key: 'profit',     label: 'Profit',           path: '/api/reports/profit/', dates: true },
  { key: 'monthly',    label: 'Month by Day',     path: '/api/reports/monthly/', ym: true },
  { key: 'inventory',  label: 'Stock Valuation',  path: '/api/reports/inventory/' },
  { key: 'customers',  label: 'Customers & Debt', path: '/api/reports/customers/' },
  { key: 'cashiers',   label: 'Cashier Takings',  path: '/api/reports/cashier-sales/', dates: true },
  { key: 'staff',      label: 'Staff Performance', path: '/api/reports/staff-performance/', dates: true },
];

/* ----------------------------------------------------------------- layout */

let ME = null; // current user object
let navCache = null; // last sidebar markup rendered, to skip identical rebuilds

/* Sign out after ME.idle_logout_minutes of no input (0 = never). The tenant
   sets the number; this only counts down to it. Client-side by design: the
   tokens stay valid, this just stops an unattended screen showing records. */
let idleTimer = null;
function armIdleLogout() {
  clearTimeout(idleTimer);
  const mins = ME?.idle_logout_minutes;
  if (!mins) return;
  idleTimer = setTimeout(async () => {
    await Api.logout();
    ME = null;
    toast('Signed out after inactivity.');
    location.hash = '#/login';
  }, mins * 60000);
}
// ponytail: one listener per event, re-arming on every input. Throttle only if
// a profiler ever blames it — clearTimeout/setTimeout is cheap.
for (const ev of ['click', 'keydown', 'mousemove', 'touchstart', 'scroll']) {
  addEventListener(ev, armIdleLogout, { passive: true });
}

// Collapsed nav groups persist across reloads; <details> does the open/close itself.
const NAV_CLOSED = new Set(JSON.parse(localStorage.getItem('navClosed') || '[]'));
/* True when a super-admin is working platform-wide — signed in as one and
   outside every organization. Opening a clinic or a pharmacy (a tenant slug on
   every call) makes them that organization: the cross-tenant views disappear
   until they leave it, and the API refuses them meanwhile. */
const isPlatformScope = () => ME?.role === 'super_admin' && !Api.tenant;

const navGroup = (name, links) =>
  `<details class="nav-group"${NAV_CLOSED.has(name) ? '' : ' open'} data-group="${name}">` +
  `<summary>${esc(name)}</summary>${links}</details>`;

/* The seats that are not a facility's staff. Each one has its own dashboard
   and the handful of screens that dashboard links to — the rest of the
   registry answers 403 for them, so it stays out of their sidebar. */
const SEAT_NAV = {
  hmo: ['#/insurer', 'Claims Desk', [
    ['#/r/pharmacy-preauths', 'flag', 'Authorisation Requests'],
    ['#/r/pharmacy-claims', 'file', 'Claims'],
    ['#/r/pharmacy-claim-batches', 'file', 'Claim Batches'],
    ['#/r/pharmacy-enrollments', 'users', 'Scheme Members'],
    ['#/r/pharmacy-item-rules', 'pill', 'Price List'],
    ['#/r/pharmacy-hmos', 'shield', 'My Scheme'],
    ['#/notifications', 'flag', 'Notifications'],
  ]],
  government: ['#/gov', 'Public Health', [
    ['#/platform/surveillance', 'flag', 'Outbreak Alerts'],
    ['#/platform/idsr', 'file', 'IDSR Report'],
    ['#/platform/cases', 'chart', 'Case Stats'],
    ['#/platform/immunizations', 'chart', 'Immunization Stats'],
    ['#/platform/facility', 'chart', 'Facility Stats'],
    ['#/platform', 'chart', 'All Metrics'],
  ]],
};

const seatLink = ([href, icon, title]) =>
  `<a href="${href}" data-route="${href.slice(1)}">${ico(icon)}${esc(title)}</a>`;

function navHtml() {
  const seat = SEAT_NAV[ME?.role];
  if (seat) {
    const [home, group, links] = seat;
    return `<a href="${home}" data-route="${home.slice(1)}" class="nav-home">${ico('home')}Dashboard</a>`
      + navGroup(group, links.map(seatLink).join(''))
      + navGroup('Account', `<a href="#/profile" data-route="/profile">${ico('users')}Profile</a>`);
  }
  const iconFor = (slug, r) => slug === 'users' || slug === 'patients' ? 'users'
    : r.group === 'Clinical' ? 'activity' : slug.startsWith('tenants') ? 'shield'
    : r.group === 'Reports' ? 'file' : r.group === 'Pharmacy' ? 'pill' : 'book';
  const groups = {};
  for (const [slug, r] of Object.entries(RESOURCES)) {
    if (r.superOnly && ME?.role !== 'super_admin') continue;
    if (r.adminOnly && !['super_admin', 'tenant_admin'].includes(ME?.role)) continue;
    if (r.group === 'Pharmacy' && !PHARMACY_STAFF_ROLES.has(ME?.role)) continue;
    // Patient data is clinical-staff only (apps.accounts.permissions.IsClinicalStaff).
    if (r.group === 'Clinical' && !Api.roleCanReport(ME?.role)) continue;
    (groups[r.group] ||= []).push(`<a href="#/r/${slug}" data-route="/r/${slug}">${ico(iconFor(slug, r))}${esc(r.title)}</a>`);
  }
  const tools = [
    `<a href="#/search" data-route="/search">${ico('search')}Search</a>`,
    `<a href="#/differential" data-route="/differential">${ico('activity')}Differential Dx</a>`,
    `<a href="#/interaction-check" data-route="/interaction-check">${ico('pill')}Interaction Check</a>`,
    `<a href="#/notifiable" data-route="/notifiable">${ico('flag')}Notifiable Cases</a>`,
  ];
  let html = `<a href="#/" data-route="/" class="nav-home">${ico('home')}Home</a>`;
  // A patient reads their own record and nothing else in here. The catalog and
  // the lookup tools built on it are the clinicians' reference, and the API
  // refuses a patient every one of them (IsTenantMember, default-deny for the
  // patient seat) — so this is the menu telling the truth, not the control.
  if (ME?.role === 'public') {
    return `<a href="#/portal" data-route="/portal" class="nav-home">${ico('activity')}My Health</a>`
      + navGroup('Account', `<a href="#/profile" data-route="/profile">${ico('users')}Profile</a>`);
  }
  html += navGroup('Tools', tools.join(''));
  html += navGroup('Catalog', groups.Catalog.join(''));
  html += navGroup('Reports', groups.Reports.join(''));
  if (groups.Pharmacy?.length) {
    html += navGroup('Pharmacy',
      `<a href="#/pharmacy" data-route="/pharmacy">${ico('pill')}Counter</a>` +
      `<a href="#/pharmacy/sell" data-route="/pharmacy/sell">${ico('pill')}Dispense</a>` +
      `<a href="#/trading" data-route="/trading">${ico('chart')}Trading Reports</a>` +
      groups.Pharmacy.join(''));
  }
  const clinical = (isClinicalStaff() ? `<a href="#/clinical" data-route="/clinical">${ico('activity')}Ward</a>` : '')
    + (groups.Clinical || []).join('');
  if (clinical) html += navGroup('Clinical', clinical);
  let analytics = `<a href="#/analytics" data-route="/analytics">${ico('chart')}Tenant Analytics</a>`;
  if (isPlatformScope()) analytics += `<a href="#/platform" data-route="/platform">${ico('chart')}Platform Analytics</a>`;
  html += navGroup('Analytics', analytics);
  if (groups.Admin?.length) html += navGroup('Admin', groups.Admin.join(''));
  // The only route the sidebar did not reach: the topbar badge opens it, which
  // is not obvious on a phone where the badge is a username and nothing else.
  html += navGroup('Account', `<a href="#/profile" data-route="/profile">${ico('users')}Profile</a>`
    + (PHARMACY_STAFF_ROLES.has(ME?.role)
      ? `<a href="#/notifications" data-route="/notifications">${ico('flag')}Notifications</a>` : ''));
  return html;
}

/* The state a platform admin is working in. Empty is the whole country; a
   pick narrows every cross-tenant read — the rollups, the facility list they
   open an organization from, the user list — down to that state and its local
   governments. The server refuses to widen a health authority seat on it, so
   only the platform owner is offered the control.
   A state's local governments hang under it, indented, and pick the same way:
   the header carries any jurisdiction id and the server narrows to that id's
   subtree, so an LGA is one more step down the same drill. */
let PLACES = null;

async function placeOptions() {
  if (!PLACES) {
    try {
      PLACES = await Api.public('/api/auth/onboarding/jurisdictions/');
    } catch { PLACES = []; }
  }
  return PLACES;
}

async function paintStatePicker() {
  const sel = $('#state-badge');
  const show = ME?.role === 'super_admin' && !Api.tenant;
  sel.hidden = !show;
  if (!show) return;
  const places = await placeOptions();
  const states = places.filter((j) => j.level === 'state');
  if (!states.length) return (sel.hidden = true);
  sel.innerHTML = '<option value="">All Nigeria</option>' + states.map((st) =>
    `<option value="${st.id}">${esc(st.name)}</option>` +
    places.filter((j) => j.level === 'local' && j.parent === st.id)
      .map((j) => `<option value="${j.id}">&nbsp;&nbsp;${esc(j.name)}</option>`)
      .join('')).join('');
  sel.value = Api.jurisdiction;
  // A stale id (a state that has gone) reads as no pick; drop it rather than
  // keep filtering every list by something the picker cannot show.
  if (sel.value !== Api.jurisdiction) Api.jurisdiction = '';
  sel.title = 'Where to work: a state, or one local government inside it';
  sel.onchange = () => {
    Api.jurisdiction = sel.value;
    location.reload();
  };
}

async function ensureChrome() {
  if (!ME) {
    try { ME = await Api.myself(); } catch { /* token dead */ }
    if (!ME) { await Api.logout(); location.hash = '#/login'; return false; }
  }
  armIdleLogout();
  $('#topbar').hidden = false;
  $('#sidebar').hidden = false;
  const badge = $('#tenant-badge');
  // Name where there is one; the slug is the fallback for a session that
  // switched organizations before the name was known.
  badge.textContent = Api.tenantName || Api.tenant || 'no organization';
  // A super-admin hops between organizations, so their badge is the way back
  // out of the one they opened. Everyone else is stuck to their own tenant.
  badge.classList.toggle('clickable', ME?.role === 'super_admin');
  badge.title = ME?.role === 'super_admin' ? 'Leave this organization' : '';
  badge.onclick = ME?.role === 'super_admin' ? () => {
    Api.tenant = '';
    Api.tenantName = '';
    location.hash = '#/platform';
    location.reload();
  } : null;
  paintStatePicker();
  // Display name only: the sign-in number never reads out in the topbar.
  $('#user-badge').textContent = `${ME.username || 'me'} · ${ME.role}`;
  refreshBell();
  // Re-parsing the same nav on every navigation is the one thing between a
  // hash change and the view. The active-link pass below still runs each time.
  const nav = navHtml();
  if (nav !== navCache) { $('#sidebar').innerHTML = nav; navCache = nav; }
  const route = location.hash.slice(1) || '/';
  for (const a of document.querySelectorAll('#sidebar a')) {
    const on = route === a.dataset.route || (a.dataset.route !== '/' && route.startsWith(a.dataset.route));
    a.classList.toggle('active', on);
    if (on) a.closest('.nav-group')?.setAttribute('open', '');
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

function tableHtml(rows, linkFor, rowAction) {
  const cols = pickColumns(rows);
  const keys = Object.keys(mergedRow(rows));
  const head = cols.map((c) => `<th>${esc(colLabel(keys, c))}</th>`).join('')
    + (rowAction ? '<th></th>' : '');
  const body = rows.map((r, i) => {
    const cells = cols.map((c) => `<td>${cellHtml(c, r[c])}</td>`).join('')
      + (rowAction ? `<td>${rowAction(r)}</td>` : '');
    const href = linkFor && linkFor(r);
    return href ? `<tr class="rowlink" onclick="location.hash='${href}'">${cells}</tr>` : `<tr>${cells}</tr>`;
  }).join('');
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// A key whose row already carries a resolved column - one prefixed with the key
// and ending in `_name(s)`, `_reference` or `_number` - is the bare pk behind a
// name, and tells a reader nothing the named column doesn't.
const namedElsewhere = (keys, k) => keys.some((o) => o !== k && o.startsWith(`${k}_`)
  && /_(names?|reference|number)$/.test(o));

// A resolved name standing in for a hidden pk is headed by the thing itself:
// "Tenant", not "Tenant Name". `full_name` and friends keep their heading —
// there is no `full` column for them to stand in for.
function colLabel(keys, k) {
  const base = k.replace(/_names?$/, '');
  return label(base !== k && keys.includes(base) ? base : k);
}

// One row carrying every key any row has, so a column is judged on the first
// row that actually has a value for it.
function mergedRow(rows) {
  const row = {};
  for (const r of rows) {
    for (const [k, v] of Object.entries(r)) {
      if (!(k in row) || row[k] === null || row[k] === undefined) row[k] = v;
    }
  }
  return row;
}

// Column keys, favoring identity/status columns, capped for readability.
// Sampled across every row, not just the first: a resolved name is absent from
// a row whose foreign key is null (DRF drops it), and one such row at the top
// would otherwise bring the bare pk column back for the whole table.
function pickColumns(rows) {
  const row = mergedRow(rows);
  const keys = Object.keys(row);
  const resolved = (k) => namedElsewhere(keys, k);
  const first = keys.filter((k) => ['id', 'reference', 'status', 'name', 'generic_name', 'title', 'phone', 'slug'].includes(k));
  // null is a scalar here, not an object — a column empty on the sampled row
  // (an unbatched claim's batch) still belongs in the table.
  const rest = keys.filter((k) => !first.includes(k) && !resolved(k)
    && (row[k] === null || typeof row[k] !== 'object')
    && !(typeof row[k] === 'string' && row[k].length > 80));
  return [...first, ...rest].slice(0, 8);
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
    <p class="muted center"><a href="#/forgot">Forgot password?</a></p>
    <p class="muted center">No account? <a href="#/register">Register</a> ·
      New organization? <a href="#/onboarding">Sign up</a></p>`));
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const role = await Api.login(fd.get('identifier'), fd.get('password'));
      ME = null;
      location.hash = homeHash(role);
    } catch (err) { toast(err.message, true); }
  };
}

async function viewRegister() {
  authChrome();
  // Nobody has a tenant to detect before they have an account, so they pick
  // one; the list is the live organizations the server will accept.
  let orgs = [];
  try { orgs = await Api.public('/api/auth/register/organizations/'); } catch { /* offline */ }
  const orgField = orgs.length
    ? `<label>Organization<select name="tenant" required>${orgs.map((o) =>
        `<option value="${esc(o.slug)}"${o.slug === Api.tenant ? ' selected' : ''}>${esc(o.name)} (${esc(o.kind)})</option>`).join('')}</select></label>`
    : `<label>Organization (tenant slug)<input name="tenant" value="${esc(Api.tenant)}" required></label>`;
  render(authShell('Create account', 'Join your organization', `
    <form id="f">
      ${orgField}
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
    Api.tenantName = orgs.find((o) => o.slug === Api.tenant)?.name || '';
    const body = { phone: fd.get('phone'), email: fd.get('email'), password: fd.get('password') };
    if (fd.get('username')) body.username = fd.get('username');
    try {
      const r = await Api.post('/api/auth/register/', body);
      toast(r?.message || 'Account created. You can now sign in.');
      location.hash = '#/login';
    } catch (err) { toast(err.message, true); }
  };
}

/* Forgotten password, in two screens: ask by phone, then set a new one from
   the link that was mailed. The server answers the ask the same way whether or
   not the number is known, so this screen cannot report "no such account"
   either — it says what was attempted, not what was found. */
async function viewForgot() {
  authChrome();
  render(authShell('Forgot password', 'We will email a reset link to the address on your account', `
    <form id="f">
      <label>Phone<input name="phone" placeholder="08031234567" required></label>
      <button type="submit">Send reset link</button>
    </form>`, `
    <p class="muted center"><a href="#/login">Back to sign in</a></p>`));
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const r = await Api.publicPost('/api/auth/password-reset/', { phone: fd.get('phone') });
      toast(r?.message || 'If that account exists, a reset link is on its way.');
    } catch (err) { toast(err.message, true); }
  };
}

function viewReset(m) {
  authChrome();
  const q = new URLSearchParams(m[1] || '');
  const uid = q.get('uid');
  const token = q.get('token');
  if (!uid || !token) {
    render(authShell('Reset password', 'That link is incomplete', '', `
      <p class="muted center"><a href="#/forgot">Ask for a new one</a></p>`));
    return;
  }
  render(authShell('Choose a new password', 'The link expires 30 minutes after it is sent', `
    <form id="f">
      <label>New password<input name="password" type="password" required></label>
      <button type="submit">Save password</button>
    </form>`, `
    <p class="muted center"><a href="#/login">Back to sign in</a></p>`));
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const r = await Api.publicPost('/api/auth/password-reset/confirm/',
        { uid, token, password: fd.get('password') });
      toast(r?.message || 'Password changed. You can now sign in.');
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
      <label>Organization type<select name="org_kind"><option value="pharmacy">Pharmacy</option><option value="hospital">Hospital</option></select></label>
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
      Api.tenantName = body.org_name;
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
    // The tenant's admin sets the idle timeout for everyone in it; a
    // super-admin sets it for whichever organization they have open.
    const canSetIdle = ['tenant_admin', 'super_admin'].includes(me.role) && Api.tenant;
    render(`<h2>Profile</h2><div class="card">${dlHtml(me)}</div>
      ${canSetIdle ? `<div class="card"><h3>Auto sign-out</h3>
        <form id="idle-form">
          <label>Minutes of inactivity before sign-out (0 = never)
            <input name="idle_logout_minutes" type="number" min="0" max="1440"
                   value="${esc(me.idle_logout_minutes ?? 30)}" required></label>
          <button type="submit">Save</button>
        </form></div>` : ''}
      <div class="actions">
        <button id="logout" class="danger">Sign out</button>
      </div>`);
    if (canSetIdle) $('#idle-form').onsubmit = async (e) => {
      e.preventDefault();
      const mins = Number(new FormData(e.target).get('idle_logout_minutes'));
      try {
        const r = await Api.patch('/api/tenants/settings/', { idle_logout_minutes: mins });
        me.idle_logout_minutes = ME.idle_logout_minutes = mins;
        armIdleLogout();
        toast(r?.message || 'Settings saved.');
      } catch (err) { toast(err.message, true); }
    };
    $('#logout').onclick = async () => { await Api.logout(); ME = null; location.hash = '#/login'; };
  } catch (e) { errorBox(e); }
}

/* ------------------------------------------------------------------- home */

async function viewHome() {
  if (!await ensureChrome()) return;
  // Reloading, or a stale bookmark, lands here whoever you are. The dashboard
  // for the role is the one place the seat's own work is, so go there.
  const home = homeHash(ME.role);
  if (home !== '#/') { location.hash = home; return; }
  spinner();
  const tiles = [
    ['#/search', 'search', 'Global Search', 'Find diseases, drugs, procedures, tests, articles'],
    ['#/differential', 'activity', 'Differential Dx', 'Rank diseases by matched symptoms'],
    ['#/interaction-check', 'pill', 'Interaction Check', 'Conflicts among a set of medications'],
    ['#/r/case-reports', 'file', 'Case Reports', 'File and browse case reports'],
    ['#/analytics', 'chart', 'Analytics', 'Tenant dashboards and stats'],
  ];
  if (ME.role === 'public') tiles.unshift(['#/portal', 'activity', 'My Health',
    'Your record, your medications and where to fill them']);
  if (Api.roleCanReport(ME.role)) tiles.splice(3, 0, ['#/r/patients', 'users', 'Patients', 'Register and open patient records']);
  if (isPlatformScope()) tiles.push(['#/platform', 'chart', 'Platform', 'Cross-tenant analytics']);
  // The organization lists stay inside an organization: they are the way out of it.
  if (ME.role === 'super_admin') tiles.push(['#/r/tenants-hospitals', 'shield', 'Hospitals', 'Approve and manage hospitals'], ['#/r/tenants-pharmacies', 'shield', 'Pharmacies', 'Approve and manage pharmacies']);
  const dash = await Api.get('/api/analytics/tenant/').catch(() => null);
  let dashHtml = '';
  if (dash) {
    const kpis = [
      ['Active Users (30d)', dash.active_users],
    ].filter(([, v]) => v !== undefined);
    dashHtml = `<div class="tiles">${kpis.map(([k, v]) =>
      `<div class="tile kpi-tile"><span class="tile-label">${esc(k)}</span><span class="tile-val">${esc(fmtVal(v))}</span></div>`).join('')}</div>`;
    const panel = (title, rows) => {
      const c = Array.isArray(rows) && rows.length ? chartable(rows) : null;
      return c ? `<section><h3>${esc(title)}</h3>${chartHtml(rows, c)}</section>` : '';
    };
    const panels = panel('Most Viewed Diseases', dash.popular_diseases) +
      panel('Most Viewed Medications', dash.popular_medications);
    if (panels) dashHtml += `<div class="grid-2">${panels}</div>`;
  }
  render(`<h2>Welcome${ME.username ? ', ' + esc(ME.username) : ''}</h2>
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
  'consultations': (rows) => ({
    kpis: [['Visits', rows.length], ['Open', countEq(rows, 'status', 'open')], ['Admitted', countEq(rows, 'disposition', 'admitted')]],
    charts: [['By disposition', groupRows(rows, 'disposition', 'visits')]],
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

/* Acting on a record — submitting a claim, withdrawing a request — is the
   organization's work. A seat that only reads the module (the insurer on its
   own claims) gets the record and none of the buttons the API would refuse. */
const canActRes = (res) => res.group !== 'Pharmacy' || isPharmacyStaff();

// ``createOnly`` resources (the cash drawer) are made and then only acted on:
// the list still offers "+ New", the detail page offers no edit or delete.
function canWriteRes(slug, res) {
  if (res.readOnly || res.createOnly) return false;
  if (res.roles === 'admin') return isPharmacyAdmin();
  // A scheme's price list is written by that scheme, or by the pharmacy admin
  // for a scheme with no seat of its own. Mirrors IsSchemePriceListEditor.
  if (res.roles === 'scheme') return isPharmacyAdmin() || (ME?.role === 'hmo' && !!ME?.hmo);
  if (res.roles === 'staff') return isPharmacyStaff();
  if (res.roles === 'tenant_admin') return ['super_admin', 'tenant_admin'].includes(ME.role);
  // Patients: the same cadres that may read them may register and edit them.
  if (res.roles === 'clinical') return Api.roleCanReport(ME.role);
  if (slug === 'users') return ['super_admin', 'tenant_admin'].includes(ME.role);
  return res.report ? Api.roleCanReport(ME.role) : Api.roleCanWrite(ME.role);
}

// Rows behind a list filter, fetched once per endpoint per session. A filter
// picks from a list that is short and slow to change (branches, staff), so a
// re-fetch on every keystroke would buy nothing.
// ponytail: first 100 rows; paginate the picker if a tenant outgrows that.
const filterCache = {};
const filterOptions = (f) => (filterCache[f.path] ||=
  Api.list(f.path, { page_size: 100 }).then((r) => r.rows).catch(() => []));

const listState = {}; // per-resource {page, search, filters, seq} kept across visits
// True while the list search box is being typed in: the list re-renders on
// every keystroke, so the caret has to be put back afterwards.
let listTyping = false;

async function viewList(slug) {
  const res = RESOURCES[slug];
  if (!res) return errorBox(new Error('Unknown resource: ' + slug));
  if (!await ensureChrome()) return;
  const st = (listState[slug] ||= { page: 1, search: '', filters: {}, seq: 0 });
  clearTimeout(st.timer);  // this render supersedes a keystroke still pending
  const wasTyping = listTyping;
  listTyping = false;
  if (!wasTyping) spinner();  // typing keeps the rows on screen until the new ones land
  const canWrite = canWriteRes(slug, res);
  try {
    const query = { page: st.page };
    if (st.search) query.search = st.search;
    for (const [k, v] of Object.entries(st.filters)) if (v) query[k] = v;
    const seq = ++st.seq;
    const filters = res.filters || [];
    const [{ rows, count }, ...options] = await Promise.all([
      Api.list(rpath(slug), query), ...filters.map(filterOptions),
    ]);
    if (seq !== st.seq) return;  // a later keystroke already asked
    const pages = count != null ? Math.max(1, Math.ceil(count / 25)) : 1;
    render(`
      <div class="page-head"><h2>${esc(res.title)}</h2>
        ${(canWrite || res.createOnly) && !slug.startsWith('tenants') ? `<a class="btn" href="#/r/${slug}/new">+ New</a>` : ''}
      </div>
      <form id="search-form" class="toolbar">
        <input name="q" autocomplete="off"
               placeholder="${res.search ? 'Search…' : 'Filter by search…'}" value="${esc(st.search)}">
        ${filters.map((f, i) => `<label>${esc(f.label)}
          <select name="${f.param}">
            <option value="">All</option>
            ${options[i].map((r) => `<option value="${r.id}"${String(st.filters[f.param] || '') === String(r.id) ? ' selected' : ''}>${esc(f.text(r) ?? r.id)}</option>`).join('')}
          </select></label>`).join('')}
        <button>Search</button>
      </form>
      ${res.report ? reportSummaryHtml(slug, rows) : ''}
      ${rows.length ? tableHtml(slug === 'prescriptions' ? collapseByGroup(rows) : rows,
        res.noLink ? null : (r) => `#/r/${slug}/${r.id}`,
        slug === 'prescriptions' && canWrite ? cancelButtonHtml : null) : '<p class="muted">Nothing here yet.</p>'}
      <div class="pager">
        <button id="prev" ${st.page <= 1 ? 'disabled' : ''}>&larr; Prev</button>
        <span>Page ${st.page}${count != null ? ` of ${pages} (${count})` : ''}</span>
        <button id="next" ${st.page >= pages ? 'disabled' : ''}>Next &rarr;</button>
      </div>`);
    // Results follow the typing (300ms after the last keystroke); the button
    // and Enter still work for anyone who reaches for them.
    const box = $('#search-form').q;
    if (wasTyping) {
      box.focus();
      box.setSelectionRange(box.value.length, box.value.length);
    }
    const run = () => {
      clearTimeout(st.timer);
      st.search = box.value.trim();
      st.page = 1;
      viewList(slug);
    };
    box.oninput = () => {
      listTyping = true;
      clearTimeout(st.timer);
      st.timer = setTimeout(run, 300);
    };
    $('#search-form').onsubmit = (e) => { e.preventDefault(); run(); };
    for (const f of filters) {
      $('#search-form')[f.param].onchange = (e) => {
        st.filters[f.param] = e.target.value;
        st.page = 1;
        viewList(slug);
      };
    }
    // Stopping a prescription from the list, the way the app stops one from
    // the card. The row itself is a link to the record, so the button must not
    // navigate on its way through.
    for (const b of document.querySelectorAll('[data-cancel]')) {
      b.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm('Cancel this prescription? Every drug on it stops, bar anything already dispensed.')) return;
        try {
          const r = await Api.post(rdetail(slug, `${b.dataset.cancel}/cancel/`));
          toast(r?.message || 'Cancelled.');
          viewList(slug);
        } catch (err) { toast(err.message, true); }
      };
    }
    $('#prev').onclick = () => { st.page--; viewList(slug); };
    $('#next').onclick = () => { st.page++; viewList(slug); };
  } catch (e) { errorBox(e); }
}

function dlHtml(obj) {
  // Nested row lists (a sale's lines, an order's lines) render as their own
  // table — as JSON they are unreadable exactly where the detail matters.
  const cell = (k, v) => Array.isArray(v) && v.length && typeof v[0] === 'object'
    ? tableHtml(v) : cellHtml(k, v);
  const keys = Object.keys(obj);
  return `<dl class="detail">${Object.entries(obj)
    .filter(([k]) => !namedElsewhere(keys, k))
    .map(([k, v]) => `<dt>${esc(colLabel(keys, k))}</dt><dd>${cell(k, v)}</dd>`).join('')}</dl>`;
}

async function viewDetail(slug, id) {
  const res = RESOURCES[slug];
  if (!res) return errorBox(new Error('Unknown resource: ' + slug));
  if (!await ensureChrome()) return;
  spinner();
  const canWrite = canWriteRes(slug, res);
  try {
    const obj = await Api.get(rdetail(slug, `${id}/`));
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
      // "Open as" scopes every later call to this organization: a super-admin
      // belongs to none, so without it their session sees no tenant data at all.
      tenantHtml = `<div class="card"><h3>Subscription: ${esc(obj.subscription_status)} · Status: ${esc(obj.status)}</h3>
        <div class="actions">
          <button class="btn" id="open-as" data-slug="${esc(obj.slug)}" data-name="${esc(obj.name)}">Open as this organization</button>
          <button class="btn ghost" id="open-log">Who opened this</button>
          <button class="btn" data-ta="approve">Approve</button>
          <button class="btn" data-ta="reject">Reject</button>
          <button class="btn danger" data-ta="suspend">Suspend / Reactivate</button>
        </div><div id="open-log-out"></div></div>`;
    }
    // Module actions (dispensing, claims, orders): each POSTs to its own
    // endpoint; ``ask`` collects the one value the endpoint needs.
    // Offer only the transitions this record's state actually allows — the API
    // rejects the rest, so a button that always fails is just a trap.
    const acts = (res.actions || []).filter((a) =>
      canActRes(res) && (!a.adminOnly || isPharmacyAdmin())
      && (!a.when || a.when.includes(obj.status)));
    const actsHtml = acts.map((a) =>
      `<button class="btn${a.danger ? ' danger' : ''}" data-pa="${a.name}" data-ask="${a.ask || ''}" data-choose="${a.choose || ''}">${esc(a.label)}</button>`).join('');
    if (res.receipt) actions += `<button id="receipt" class="btn ghost">Print receipt</button>`;
    // Filing a record against the one on screen. The links travel as query
    // params so the new-record form opens with them already filled in. A drug
    // order written off a visit carries that visit's diagnosis, so it is filed
    // against the case rather than floating loose.
    let fileHtml = '';
    if (res.fileFrom && Api.roleCanReport(ME.role)) {
      const link = new URLSearchParams();
      const patient = slug === 'patients' ? id : obj.patient;
      if (patient) link.set('patient', patient);
      if (slug === 'consultations' && obj.case_report) link.set('case_report', obj.case_report);
      fileHtml = `<div class="card"><h3>File a record</h3><div class="actions">${res.fileFrom.map((s) =>
        `<a class="btn ghost" href="#/r/${s}/new?${link}">+ ${esc(RESOURCES[s].title.replace(/s$/, ''))}</a>`).join('')}</div></div>`;
    }
    render(`<div class="page-head"><h2>${esc(obj.name || obj.generic_name || obj.title || obj.full_name || obj.reference || res.title + ' #' + id)}</h2></div>
      <div class="actions">${actions}</div>
      ${tenantHtml}${workflowHtml}
      ${actsHtml ? `<div class="card"><h3>Actions</h3><div class="actions">${actsHtml}</div></div>` : ''}
      ${fileHtml}
      <div class="card">${dlHtml(obj)}</div>
      ${slug === 'prescriptions' && obj.group ? `<div class="card"><h3>Prescribed together</h3>
        <div id="rx-group"><p class="loading">Loading…</p></div></div>` : ''}
      ${res.history ? '<div class="card"><h3>Clinical history</h3><div id="rec-history"><p class="loading">Loading…</p></div></div>' : ''}
      ${res.extra === 'purchase' ? purchaseReceiveHtml(obj) : ''}
      ${res.extra === 'count' ? stockCountHtml(obj) : ''}
      ${res.extra === 'preauth' ? preauthItemsHtml(obj) + preauthDecisionHtml(obj)
        + preauthTrailHtml() : ''}
      ${res.extra === 'statement' ? '<div id="statement"><p class="loading">Loading…</p></div>' : ''}`);
    if (res.receipt) $('#receipt').onclick = () => printReceipt(id);
    if (res.extra === 'purchase') wirePurchaseReceive(id, () => viewDetail(slug, id));
    if (res.extra === 'count') wireStockCount(id, () => viewDetail(slug, id));
    if (res.extra === 'statement') loadStatement(slug, id);
    if (res.extra === 'preauth') {
      wirePreauthItems(() => viewDetail(slug, id));
      wirePreauthDecision(slug, id, () => viewDetail(slug, id));
      loadPreauthTrail(id);
    }
    for (const b of document.querySelectorAll('[data-pa]')) {
      b.onclick = async () => {
        const body = {};
        // ``ask`` is one key, or several comma-separated — an optional one
        // left blank (a drawer's closing note) stays out of the body.
        for (const key of (b.dataset.ask || '').split(',').filter(Boolean)) {
          const answer = prompt(`${b.textContent} — ${key}:`);
          if (answer === null) return;
          if (answer !== '') body[key] = answer;
        }
        // ``choose`` is "key:one,of,these" — the endpoint takes one of a fixed
        // set (how a payment arrived), and the first option is the default.
        if (b.dataset.choose) {
          const [key, list] = b.dataset.choose.split(':');
          const options = list.split(',');
          const picked = prompt(`${b.textContent} — ${key} (${options.join('/')}):`, options[0]);
          if (picked === null) return;
          if (!options.includes(picked)) return toast(`${key} must be one of ${options.join(', ')}.`, true);
          body[key] = picked;
        }
        try {
          const r = await Api.post(rdetail(slug, `${id}/${b.dataset.pa}/`), body);
          toast(r?.message || 'Done.');
          viewDetail(slug, id);
        } catch (e) { toast(e.message, true); }
      };
    }
    if (canWrite) {
      $('#del').onclick = async () => {
        if (!confirm('Delete this record? This cannot be undone.')) return;
        try { await Api.del(rdetail(slug, `${id}/`)); toast('Deleted.'); location.hash = `#/r/${slug}`; }
        catch (e) { toast(e.message, true); }
      };
    }
    for (const b of document.querySelectorAll('[data-to]')) {
      b.onclick = async () => {
        const note = prompt(`Note for transition to "${b.dataset.to}" (optional):`) ?? '';
        try { await Api.post(rdetail(slug, `${id}/transition/`), { to: b.dataset.to, note }); toast('Status updated.'); viewDetail(slug, id); }
        catch (e) { toast(e.message, true); }
      };
    }
    if ($('#open-as')) {
      $('#open-as').onclick = async () => {
        // Record the visit before switching: the trail is the point, and a
        // switch the server never heard about leaves none.
        try { await Api.post(`/api/tenants/${id}/open/`); }
        catch (e) { return toast(e.message, true); }
        Api.tenant = $('#open-as').dataset.slug;
        Api.tenantName = $('#open-as').dataset.name;
        toast(`Working in ${Api.tenantName || Api.tenant}.`);
        location.hash = '#/';
      };
      $('#open-log').onclick = async () => {
        try {
          const rows = await Api.get(`/api/tenants/${id}/access-log/`);
          $('#open-log-out').innerHTML = rows.length
            ? tableHtml(rows.map((r) => ({ who: r.user_phone || `#${r.user}`, when: r.created_at })))
            : '<p class="muted">Nobody has opened this organization yet.</p>';
        } catch (e) { toast(e.message, true); }
      };
    }
    for (const b of document.querySelectorAll('[data-ta]')) {
      b.onclick = async () => {
        try { const r = await Api.post(rdetail(slug, `${id}/${b.dataset.ta}/`)); toast(r?.message || 'Done.'); viewDetail(slug, id); }
        catch (e) { toast(e.message, true); }
      };
    }
    // The other drugs written with this one. A prescription is one decision
    // and the rows are one drug each, so the drug on screen is only part of
    // what the patient was given — and cancelling stops all of them together.
    if ($('#rx-group')) {
      try {
        const { rows } = await Api.list(rpath(slug), { group: obj.group, page_size: 50 });
        const others = rows.filter((r) => String(r.id) !== String(id));
        $('#rx-group').innerHTML = others.length
          ? tableHtml(others, (r) => `#/r/${slug}/${r.id}`)
          : '<p class="muted">One drug on this prescription.</p>';
      } catch (e) { $('#rx-group').innerHTML = `<p class="err">${esc(e.message)}</p>`; }
    }
    // Everything filed against this record, grouped by kind. Empty groups are
    // dropped — ten "No data." headings hide the one group that has rows.
    if (res.history) {
      try {
        const h = await Api.get(rdetail(slug, `${id}/history/`));
        const kinds = Object.entries(h).filter(([k, v]) => k !== 'counts' && Array.isArray(v) && v.length);
        $('#rec-history').innerHTML = kinds.length
          ? kinds.map(([k, rows]) =>
            `<section class="sub"><h4>${esc(label(k))} (${rows.length})</h4>${tableHtml(rows)}</section>`).join('')
          : '<p class="muted">Nothing filed against this patient yet.</p>';
      } catch (e) { $('#rec-history').innerHTML = `<p class="err">${esc(e.message)}</p>`; }
    }
    if (res.workflow && $('#history')) {
      try {
        const hist = await Api.get(rdetail(slug, `${id}/history/`));
        $('#history').innerHTML = hist.length ? tableHtml(hist) : '<p class="muted">No history.</p>';
      } catch { /* history is optional sugar */ }
    }
  } catch (e) { errorBox(e); }
}

/* Create/edit form generated from DRF OPTIONS metadata.
 * ``query`` is the new-record link's own query string ("patient=12"), which
 * seeds the matching fields — filing against a record already on screen
 * shouldn't make anyone retype which record it was. */
async function viewForm(slug, id, query) {
  const res = RESOURCES[slug];
  if (!res) return errorBox(new Error('Unknown resource: ' + slug));
  if (!await ensureChrome()) return;
  spinner();
  try {
    const metaPath = id ? rdetail(slug, `${id}/`) : rpath(slug);
    const prefill = Object.fromEntries(new URLSearchParams(query || ''));
    const [meta, current] = await Promise.all([
      Api.options(metaPath),
      id ? Api.get(rdetail(slug, `${id}/`)) : Promise.resolve(prefill),
    ]);
    const fields = meta?.actions?.PUT || meta?.actions?.POST;
    if (!fields) return errorBox(new Error('You do not have permission to edit this resource.'));
    const inputs = Object.entries(fields)
      .filter(([, f]) => !f.read_only)
      .map(([name, f]) => fieldHtml(name, f, current[name])).join('');
    // A visit rarely calls for one drug. Extra rows live outside the <form>
    // on purpose: inside it, a second field named `medication` would collide
    // with the first and collectForm would read neither.
    const multiDrug = slug === 'prescriptions' && !id;
    render(`<div class="page-head"><h2>${id ? 'Edit' : 'New'} — ${esc(res.title)}</h2></div>
      <form id="f" class="card form-card">${inputs}
        <div class="actions">
          <button type="submit" class="btn">${id ? 'Save' : 'Create'}</button>
          <a class="btn ghost" href="#/r/${slug}${id ? '/' + id : ''}">Cancel</a>
        </div>
      </form>
      ${multiDrug ? `<div id="drugs"></div>
      <div class="actions">
        <button type="button" id="add-drug" class="btn ghost">Add another drug</button>
      </div>` : ''}`);
    wirePickerFields($('#f'));
    wireItemField($('#f'), current.item);
    wireRelFields($('#f'), current);
    const drugRows = multiDrug ? wireExtraDrugs(fields) : null;
    $('#f').onsubmit = async (e) => {
      e.preventDefault();
      const body = prescriptionPayload(collectForm(e.target, fields),
        drugRows ? [...drugRows.children].map((row) => collectRow(row, fields)) : []);
      try {
        const saved = id ? await Api.patch(rdetail(slug, `${id}/`), body)
          : await Api.post(rpath(slug), body);
        toast('Saved.');
        // A prescription of several drugs comes back as the rows it wrote.
        const first = Array.isArray(saved) ? saved[0] : saved;
        location.hash = `#/r/${slug}/${first?.id ?? id ?? ''}`;
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

/* Repeat the drug fields on demand, so one visit's drugs are prescribed in one
 * go. Returns the container the rows are added to. */
function wireExtraDrugs(fields) {
  const box = $('#drugs');
  $('#add-drug').onclick = () => {
    const row = document.createElement('div');
    row.className = 'card form-card';
    row.innerHTML = RX_DRUG_FIELDS
      .filter((n) => fields[n] && !fields[n].read_only)
      .map((n) => fieldHtml(n, { ...fields[n], required: false }, '')).join('')
      + '<div class="actions"><button type="button" class="btn ghost">Remove</button></div>';
    row.querySelector('button').onclick = () => row.remove();
    box.append(row);
  };
  return box;
}

/* One extra drug row. It is not in a <form>, so the values are read off the
 * row itself rather than through form.elements. */
function collectRow(row, fields) {
  const drug = {};
  for (const name of RX_DRUG_FIELDS) {
    const elm = row.querySelector(`[name="${name}"]`);
    const raw = (elm?.value ?? '').trim();
    if (raw === '') continue;
    const type = fields[name]?.type;
    drug[name] = (type === 'integer' || type === 'field') ? Number(raw) : raw;
  }
  return drug;
}

/* What to POST: the form on its own, or a list of one row per drug.
 *
 * The API takes a list as one prescription of several drugs, written whole or
 * not at all (see PrescriptionViewSet.get_serializer). The fields that are not
 * about the drug — the patient, the diagnosis, the notes — go on every row; a
 * row with no drug picked is an untouched blank and is dropped, not posted. */
function prescriptionPayload(body, extras) {
  const drugs = extras.filter((d) => d.medication);
  if (!drugs.length) return body;
  const shared = { ...body };
  for (const name of RX_DRUG_FIELDS) delete shared[name];
  return [body, ...drugs.map((drug) => ({ ...shared, ...drug }))];
}

/* One row per prescription, not per drug. The drugs written together were one
 * decision; listed apart, a three-drug course reads as three prescriptions.
 * The kept row names every drug on it and links to the first, whose detail
 * page lists the rest. Per-drug directions are dropped from a collapsed row —
 * they belong to one drug and would be read as the whole prescription's.
 *
 * ponytail: collapses within the page it is given, so a prescription split
 * across two pages shows a row on each. Group server-side the day a page of
 * 25 rows routinely splits one. */
function collapseByGroup(rows) {
  const heads = new Map();
  const out = [];
  for (const row of rows) {
    const head = row.group ? heads.get(row.group) : null;
    if (!head) {
      const copy = { ...row, drugs: [row] };
      if (row.group) heads.set(row.group, copy);
      out.push(copy);
      continue;
    }
    head.drugs.push(row);
    // Drugs of one prescription reach the counter separately, so they are not
    // always at the same stage; the row says so rather than picking one.
    if (head.status !== row.status) head.status = 'part-dispensed';
  }
  for (const head of out) {
    const drugs = head.drugs;
    delete head.drugs;             // a column of objects reads as nothing
    if (drugs.length === 1) continue;
    head.medication_name = drugs.map(drugLabel).join('; ');
    // These belong to one drug and would be read as the prescription's.
    head.dose = '';
    head.frequency = '';
    head.duration_days = null;
  }
  return out;
}

/* Nothing to stop once every drug on the prescription is dispensed or
 * cancelled, so the row offers no button at all. */
function cancelButtonHtml(row) {
  const live = ['prescribed', 'partially_dispensed', 'part-dispensed'];
  return live.includes(row.status)
    ? `<button class="btn danger" data-cancel="${row.id}">Cancel</button>` : '';
}

/* One drug of a prescription, named with its own directions. */
function drugLabel(drug) {
  return [
    drug.medication_name,
    drug.dose,
    drug.frequency,
    drug.duration_days ? `${drug.duration_days} day(s)` : '',
  ].filter((v) => v != null && String(v).trim() !== '').join(' ');
}

function fieldHtml(name, f, value) {
  const req = f.required ? ' required' : '';
  const lbl = esc(f.label || label(name)) + (f.required ? ' *' : '');
  const hint = f.help_text || FIELD_HINTS[name] || '';
  const help = hint ? `<small class="muted">${esc(hint)}</small>` : '';
  const v = value ?? '';
  // A tenant's registry outgrows a <select> of every patient in it, and its
  // staff list outgrows one of every account, so both are type-aheads instead
  // (see PICKERS). The picked id lives in the hidden input, which is the one
  // collectForm reads.
  if (PICKERS[name]) {
    return `<label data-field="${name}">${lbl}
      <input type="search" id="${name}-q" autocomplete="off"
             placeholder="${esc(PICKERS[name].placeholder)}">
      <input type="hidden" name="${name}" value="${esc(v)}">
      <div id="${name}-hit" class="muted"></div>${help}<em class="field-err"></em></label>`;
  }
  // Same reason as `patient`: nobody knows a stock item by its id. The list is
  // long but finite, so it is a <select> wireItemField fills after render.
  if (name === 'item') {
    return `<label data-field="item">${lbl}
      <select name="item"${req} data-items><option value="${esc(v)}">Loading…</option></select>
      ${help}<em class="field-err"></em></label>`;
  }
  // A scheme and a jurisdiction are short closed lists, so they come up as a
  // select the app fills after render — same trick as `item`, because an id
  // typed into a number box is nobody's idea of picking an insurer.
  if (!f.choices && (name === 'hmo' || name === 'jurisdiction')) {
    return `<label data-field="${name}">${lbl}
      <select name="${name}"${req} data-rel="${name}"><option value="${esc(v)}">Loading…</option></select>
      ${help}<em class="field-err"></em></label>`;
  }
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

/* ---------------------------------------------------------- field type-ahead */

const patientHitHtml = (p) => {
  // What the registry already holds about them. Shown so the details are read
  // off the record instead of being asked for again, and so an allergy is in
  // front of whoever is about to prescribe.
  const bits = [
    p.age == null ? '' : `${p.age}y`,
    p.sex, p.blood_group, p.genotype, p.region,
  ].filter((v) => String(v ?? '').trim() !== '');
  const allergies = String(p.allergies ?? '').trim();
  const chronic = (p.chronic_condition_names || []).join(', ');
  return `<b>${esc(p.full_name || p.first_name || '')}</b> · ${esc(p.hospital_number || '')}`
    + (bits.length ? `<br><span class="muted">${esc(bits.join(' · '))}</span>` : '')
    + (chronic ? `<br><span class="muted">Chronic: ${esc(chronic)}</span>` : '')
    + (allergies ? `<br><span class="err">Allergies: ${esc(allergies)}</span>` : '');
};

/* One account of the tenant, named the way whoever links it would say it. */
const userHitHtml = (u) => {
  const bits = [u.phone, u.role, u.email].filter((v) => String(v ?? '').trim() !== '');
  return `<b>${esc(u.username || u.phone || `#${u.id}`)}</b>`
    + (bits.length ? `<br><span class="muted">${esc(bits.join(' · '))}</span>` : '');
};

/* Where each type-ahead field searches, how one hit reads, and what a bound
 * row puts back in the box. Both lists are tenant-scoped by the API, so a
 * search here can only ever offer rows this organization owns. */
const PICKERS = {
  patient: {
    path: '/api/patients/', hit: patientHitHtml,
    placeholder: 'Name, hospital number or phone…',
    none: 'No patient found.', which: 'Which patient?',
    name: (p) => p.full_name || '',
  },
  user: {
    path: '/api/users/', hit: userHitHtml,
    placeholder: 'Name, phone or email…',
    none: 'No account found.', which: 'Which account?',
    name: (u) => u.username || u.phone || '',
  },
};

/* Search as the user types (250ms after the last keystroke) and report the
 * resolved row — or null while nothing is resolved — through onPick. One
 * match binds itself; several are listed to be picked, because linking the
 * wrong record is worse than one more click. */
function picker(box, out, cfg, onPick) {
  const bind = (r) => { out.innerHTML = cfg.hit(r); onPick(r); };
  let timer;
  let latest = 0;  // only the newest reply may paint
  const lookup = async () => {
    onPick(null);
    const q = box.value.trim();
    if (!q) return (out.textContent = '');
    const seq = ++latest;
    out.textContent = 'Searching…';
    try {
      const { rows } = await Api.list(cfg.path, { search: q, page_size: 5 });
      if (seq !== latest) return;  // a later keystroke already asked
      if (!rows.length) return (out.textContent = cfg.none);
      if (rows.length === 1) return bind(rows[0]);
      out.innerHTML = `<span class="muted">${esc(cfg.which)}</span><div class="chips">`
        + rows.map((r, i) => `<button type="button" class="chip pick" data-hit="${i}">${cfg.hit(r)}</button>`).join('')
        + '</div>';
      for (const b of out.querySelectorAll('[data-hit]')) {
        b.onclick = () => { ++latest; bind(rows[Number(b.dataset.hit)]); };
      }
    } catch (e) { if (seq === latest) out.textContent = e.message; }
  };
  box.oninput = () => { clearTimeout(timer); timer = setTimeout(lookup, 250); };
  return { bind };
}

/* Whichever type-ahead fields the generated form has. */
function wirePickerFields(form) {
  for (const [name, cfg] of Object.entries(PICKERS)) {
    const box = form.querySelector(`#${name}-q`);
    if (!box) continue;
    const hidden = form.elements[name];
    const out = form.querySelector(`#${name}-hit`);
    const bound = picker(box, out, cfg, (row) => {
      hidden.value = row ? row.id : '';
      if (row && name === 'patient') carryPatientFields(form, row);
    });
    // A record that already names one — an edit, or a form opened from that
    // record — shows who it is rather than an id nobody can read.
    if (hidden.value) {
      Api.get(`${cfg.path}${hidden.value}/`).then((row) => {
        box.value = cfg.name(row);
        bound.bind(row);
      }, () => { out.textContent = `#${hidden.value}`; });
    }
  }
}

/* The dispensable catalogue, fetched once per session - the dispense screen
 * and every `item` field pick from the same rows.
 * ponytail: capped at 10 pages of 100; past ~1000 items this wants a search box. */
let itemCache;
const allItems = () => (itemCache ||= (async () => {
  // An insurer seat is refused /pharmacy/items/ — cost prices and margins are
  // the pharmacy's own business — so it reads names and shelf prices instead.
  if (ME?.role === 'hmo') return Api.get('/api/pharmacy/item-rules/items/');
  const rows = [];
  for (let page = 1; page <= 10; page++) {
    const r = await Api.list('/api/pharmacy/items/', { is_active: true, page, page_size: 100 });
    rows.push(...r.rows);
    if (!r.next) break;
  }
  return rows;
})().catch((e) => { itemCache = null; throw e; }));  // a failed fetch must not stick

/* The generated form's `item` field, if it has one. */
async function wireItemField(form, value) {
  const sel = form.querySelector('[data-items]');
  if (!sel) return;
  let rows = [];
  try { rows = await allItems(); } catch { sel.innerHTML = '<option value="">Catalogue unavailable</option>'; return; }
  // The shelf price rides along in the label: a tariff is a ceiling on what
  // the pharmacy charges, so it is set against that number, not from memory.
  sel.innerHTML = '<option value=""></option>' + rows.map((i) =>
    `<option value="${i.id}"${String(i.id) === String(value ?? '') ? ' selected' : ''}>${
      esc(i.name)}${i.unit_price == null ? '' : ` · ${money(i.unit_price)}`}</option>`).join('');
}

/* Where each related picker gets its rows, and how one reads. The jurisdiction
 * list is the public one: a government seat belongs to no organization, so
 * there is no tenant-scoped list to ask. */
const REL_FIELDS = {
  hmo: ['/api/pharmacy/hmos/', (r) => r.name],
  jurisdiction: ['/api/auth/onboarding/jurisdictions/', (r) => `${r.name} · ${r.level}`],
};

/* Fill the generated form's related selects, if it has any. */
async function wireRelFields(form, current) {
  for (const [name, [path, text]] of Object.entries(REL_FIELDS)) {
    const sel = form.querySelector(`[data-rel="${name}"]`);
    if (!sel) continue;
    let rows;
    try {
      rows = name === 'jurisdiction' ? await Api.public(path)
        : (await Api.list(path)).rows;
    } catch {
      // Outside an organization there is no scheme list to offer. The API
      // still refuses a seat without one, so this fails on save rather than
      // pretending the field is optional.
      sel.innerHTML = '<option value="">Unavailable — open the organization first</option>';
      continue;
    }
    // One choice and nothing chosen yet: pick it. An insurer seat is scoped to
    // its own scheme, so the field is a formality it should not have to fill.
    const v = String(current[name] ?? (rows.length === 1 ? rows[0].id : ''));
    sel.innerHTML = (rows.length === 1 && v ? '' : '<option value=""></option>') + rows.map((r) =>
      `<option value="${r.id}"${String(r.id) === v ? ' selected' : ''}>${esc(text(r))}</option>`).join('');
  }
}

/* Fields the patient's own record already answers, so linking a patient fills
 * them instead of asking again. A value already typed stands: the visit can be
 * somewhere other than where the patient lives. */
function carryPatientFields(form, patient) {
  for (const name of ['region']) {
    const elm = form.elements[name];
    const value = String(patient[name] ?? '').trim();
    if (!elm || !value || String(elm.value ?? '').trim() !== '') continue;
    elm.value = value;
    // A <select> ignores a value it has no option for; leave it blank then.
    if (elm.tagName === 'SELECT' && elm.value !== value) elm.value = '';
  }
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
    const indexTitle = prefix === '/platform' ? 'Platform Analytics'
      : prefix === '/trading' ? 'Trading Reports' : 'Tenant Analytics';
    return render(statIndex(indexTitle, registry, prefix) +
      `<h3>${esc(registry[0].label)}</h3>` + dash);
  }
  const m = registry.find((x) => x.key === key);
  if (!m) return errorBox(new Error('Unknown metric: ' + key));
  const controls = [];
  if (m.dates) controls.push('<label>From <input type="date" name="from"></label>', '<label>To <input type="date" name="to"></label>');
  if (m.days) controls.push('<label>Days <input type="number" name="days" min="1" value="30"></label>');
  if (m.ym) {
    const now = new Date();
    controls.push(`<label>Year <input type="number" name="year" min="2000" value="${now.getFullYear()}"></label>`,
                  `<label>Month <input type="number" name="month" min="1" max="12" value="${now.getMonth() + 1}"></label>`);
  }
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
    for (const k of ['from', 'to', 'days', 'year', 'month']) if (fd.get(k)) q[k] = fd.get(k);
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

/* ------------------------------------------------------------- clinical */

// The nursing cadres: they file reports rather than sell or administer, so
// their landing screen is the reporting workload, not the tenant KPIs.
const CLINICAL_ROLES = new Set(['doctor', 'nurse', 'midwife', 'chew']);
const isClinicalStaff = () => CLINICAL_ROLES.has(ME?.role);

// What each cadre files most; the first entry is their "+ New" button.
const CLINICAL_WORK = {
  doctor:  ['consultations', 'prescriptions', 'case-reports', 'lab-results', 'appointments'],
  nurse:   ['case-reports', 'prescriptions', 'immunizations', 'lab-results', 'appointments'],
  midwife: ['vital-events', 'prescriptions', 'immunizations', 'case-reports', 'appointments'],
  chew:    ['chw-reports', 'prescriptions', 'immunizations', 'case-reports', 'adverse-reactions'],
};

/* The ward's own home: how much of each report exists, and the latest few of
   the one this cadre files most. Counts come from the list endpoints' own
   pagination — no dashboard endpoint to keep in step with the registry. */
async function viewClinical() {
  if (!await ensureChrome()) return;
  if (!isClinicalStaff() && ME?.role !== 'super_admin') {
    return errorBox(new Error('Clinical staff only.'));
  }
  spinner();
  const slugs = CLINICAL_WORK[ME.role] || CLINICAL_WORK.nurse;
  const lists = await Promise.all(slugs.map((slug) =>
    Api.list(rpath(slug), { ordering: '-created_at' }).catch(() => null)));
  const tile = (slug, list) => `<a class="tile linktile kpi-tile" href="#/r/${slug}">
    <span class="tile-label">${esc(RESOURCES[slug].title)}</span>
    <span class="tile-val">${esc(list ? fmtVal(list.count ?? list.rows.length) : '—')}</span></a>`;
  const [primary] = slugs;
  const recent = lists[0]?.rows?.slice(0, 5) || [];
  render(`
    <div class="page-head"><h2>Clinical</h2>
      <a class="btn" href="#/r/${primary}/new">+ ${esc(RESOURCES[primary].title.replace(/s$/, ''))}</a></div>
    <div class="tiles">${slugs.map((slug, i) => tile(slug, lists[i])).join('')}</div>
    <div class="card"><h3>Latest ${esc(RESOURCES[primary].title.toLowerCase())}</h3>
      ${recent.length ? tableHtml(recent, (r) => `#/r/${primary}/${r.id}`)
        : '<p class="muted">Nothing filed yet.</p>'}
    </div>
    <h3>File a report</h3>
    <div class="tiles">${slugs.map((slug) =>
      `<a class="tile linktile" href="#/r/${slug}/new"><span class="tile-label">New</span>
        <span class="tile-val">${esc(RESOURCES[slug].title)}</span></a>`).join('')}</div>`);
}

/* -------------------------------------------------------------- insurer */

/* The insurer's desk. Every call here is scoped to their own scheme by the
   API (see insurer_scope), so this is the pharmacy's claims data with every
   other scheme's rows taken out — what was asked of them, and what they owe. */
async function viewInsurer() {
  if (!await ensureChrome()) return;
  if (ME.role !== 'hmo' && ME.role !== 'super_admin') {
    return errorBox(new Error('Insurer seats only.'));
  }
  spinner();
  const [summary, pending, billed] = await Promise.all([
    Api.get('/api/pharmacy/claims/summary/').catch(() => null),
    Api.list('/api/pharmacy/pre-authorizations/',
             { status: 'requested', ordering: '-created_at' }).catch(() => null),
    Api.list('/api/pharmacy/claims/',
             { status: 'submitted', ordering: '-created_at' }).catch(() => null),
  ]);
  const kpis = [
    ['Awaiting our answer', pending ? fmtVal(pending.count ?? pending.rows.length) : '—'],
    ['Claims submitted', billed ? fmtVal(billed.count ?? billed.rows.length) : '—'],
    ['Claimed', summary ? money(summary.claimed) : '—'],
    ['Approved', summary ? money(summary.approved) : '—'],
    ['Paid', summary ? money(summary.paid) : '—'],
    ['Outstanding', summary ? money(summary.outstanding) : '—'],
  ];
  const card = (title, list, slug) => `<div class="card"><h3>${esc(title)}</h3>
    ${list?.rows?.length ? tableHtml(list.rows.slice(0, 8), (r) => `#/r/${slug}/${r.id}`)
      : '<p class="muted">Nothing waiting.</p>'}</div>`;
  render(`<div class="page-head"><h2>Claims Desk</h2>
      <a class="btn ghost" href="#/r/pharmacy-claims">All claims</a></div>
    <div class="tiles">${kpis.map(([k, v]) =>
      `<div class="tile kpi-tile"><span class="tile-label">${esc(k)}</span><span class="tile-val">${esc(v)}</span></div>`).join('')}</div>
    ${card('Authorisation requests to answer', pending, 'pharmacy-preauths')}
    ${card('Claims submitted to us', billed, 'pharmacy-claims')}
    <h3>Go to</h3>
    <div class="tiles">${SEAT_NAV.hmo[2].map(([href, icon, title]) =>
      `<a class="tile linktile" href="${href}"><span class="tile-label">${ico(icon)}${esc(title)}</span></a>`).join('')}</div>`);
}

/* ----------------------------------------------------------- government */

/* The health authority's desk: the cross-tenant rollups and nothing else. The
   API behind these is aggregate-only (IsPlatformReader), so nothing on this
   screen names a patient — the surveillance signal is the point, not the case. */
async function viewGov() {
  if (!await ensureChrome()) return;
  if (ME.role !== 'government' && ME.role !== 'super_admin') {
    return errorBox(new Error('Health authority seats only.'));
  }
  spinner();
  const [dash, spikes] = await Promise.all([
    Api.get('/api/analytics/platform/').catch(() => null),
    Api.get('/api/analytics/platform/surveillance/').catch(() => null),
  ]);
  const alerts = spikes?.alerts || [];
  const kpis = [
    ['Facilities reporting', dash ? fmtVal(dash.total_tenants) : '—'],
    ['Users', dash ? fmtVal(dash.total_users) : '—'],
    ['Open outbreak alerts', fmtVal(alerts.length)],
  ];
  render(`<div class="page-head"><h2>Public Health</h2>
      <a class="btn ghost" href="#/platform">All metrics</a></div>
    <div class="tiles">${kpis.map(([k, v]) =>
      `<div class="tile kpi-tile"><span class="tile-label">${esc(k)}</span><span class="tile-val">${esc(v)}</span></div>`).join('')}</div>
    <div class="card"><h3>Outbreak alerts</h3>
      ${alerts.length ? tableHtml(alerts) : '<p class="muted">No spike above threshold.</p>'}</div>
    <h3>Go to</h3>
    <div class="tiles">${SEAT_NAV.government[2].map(([href, icon, title]) =>
      `<a class="tile linktile" href="${href}"><span class="tile-label">${ico(icon)}${esc(title)}</span></a>`).join('')}</div>`);
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
    const [low, expiring, sales, claims, value, scripts, people, debtors] = await Promise.all([
      Api.get('/api/pharmacy/items/low-stock/').catch(() => []),
      Api.get('/api/pharmacy/batches/expiring/', { days: 60 }).catch(() => []),
      Api.get('/api/pharmacy/sales/summary/', { from: today, to: today }).catch(() => null),
      Api.get('/api/pharmacy/claims/summary/').catch(() => null),
      Api.get('/api/pharmacy/items/valuation/').catch(() => null),
      // An aggregate, not a page of scripts: the counter only wants the number
      // of prescriptions it still owes someone.
      Api.get('/api/prescriptions/scripts/pending-count/').catch(() => null),
      Api.get('/api/customers/summary/').catch(() => null),
      // Who owes the counter money, biggest first — the server has already
      // dropped everyone square with us.
      Api.get('/api/customers/debtors/').catch(() => []),
    ]);
    const tile = (label, value) =>
      `<div class="tile"><span class="tile-label">${esc(label)}</span><span class="tile-val">${esc(value)}</span></div>`;
    render(`
      <div class="page-head"><h2>Pharmacy</h2>
        <a class="btn" href="#/pharmacy/sell">+ Dispense</a></div>
      <div class="tiles">
        ${tile('Scripts to fill', scripts ? scripts.total : '—')}
        ${tile('Sales today', sales ? sales.sales : '—')}
        ${tile('Billed today', sales ? money(sales.billed) : '—')}
        ${tile('Collected today', sales ? money(sales.collected) : '—')}
        ${tile('Owed by patients', sales ? money(sales.outstanding) : '—')}
        ${tile('Owed by insurers', claims ? money(claims.outstanding) : '—')}
        ${tile('Stock at cost', value ? money(value.cost_value) : '—')}
        ${tile('Customers', people ? fmtVal(people.total) : '—')}
        ${tile('Wallets hold', people ? money(people.wallet_balance) : '—')}
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
      <div class="card"><h3>Debtors (${debtors.length})</h3>
        ${debtors.length ? tableHtml(debtors.slice(0, 10).map((c) => ({
          id: c.id, customer: c.name, phone: c.phone,
          owes: money(c.outstanding_debt), wallet: money(c.wallet_balance),
        })), (c) => `#/r/pharmacy-customers/${c.id}`) : '<p class="muted">Nobody owes us anything.</p>'}
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
  try { items = await allItems(); } catch (e) { return errorBox(e); }

  // Rebuilt each draw: a scan can turn up an item the catalogue page never
  // carried, and that item has to be selectable once it has.
  const optionsHtml = () => items.map((i) =>
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

  // Patient state lives outside draw(): adding or removing a basket line
  // re-renders the form, and the pharmacist should not have to find the
  // patient again (and must never have a picked patient silently dropped).
  let patient = null;      // the chosen row, or null for a walk-in
  let patientQuery = '';   // what is in the search box
  let schemes = [];        // active enrollments for `patient`
  let schemeId = '';
  // Clearances the insurer has already given this member. A high-value covered
  // sale is refused without one, so the counter picks it here.
  let auths = [];
  // What the patient's number turned up, and which of it this sale fills. A
  // prescription written at another facility is dispensable here on that
  // number alone, so the sale carries it back as the proof the API asks for.
  let rxNumber = '';
  let rxFound = null;      // null until a lookup has run
  let filling = null;      // { id, label } of the order being filled

  // Rows of both kinds read the same at the counter: a drug, its directions,
  // and where it was written. The lookup asks for ?undispensed=1, so what
  // comes back is already only what can still be handed over.
  const rxRows = () => [
    ...(rxFound?.orders || []).map((o) => ({ ...o, facility: 'Here' })),
    ...(rxFound?.orders_elsewhere || []),
  ];

  const rxLabel = (o) => [o.medication_name, o.dose, o.frequency,
    o.duration_days ? `${o.duration_days} days` : ''].filter(Boolean).join(' · ');

  const rxHtml = () => {
    if (!rxFound) return '<p class="muted">Enter the number the patient gives you.</p>';
    const rows = rxRows();
    if (!rows.length) return '<p class="muted">Nothing outstanding for that number.</p>';
    return `<table><thead><tr><th>Prescribed</th><th>From</th><th></th></tr></thead>
      <tbody>${rows.map((o) => `<tr>
        <td>${esc(rxLabel(o))}</td><td>${esc(o.facility || '—')}</td>
        <td>${filling?.id === o.id ? '<b>Filling</b>'
          : `<button class="btn ghost" data-fill="${o.id}">Fill this</button>`}</td>
      </tr>`).join('')}</tbody></table>`;
  };

  const authOptions = () => '<option value="">—</option>' + auths.map((r) =>
    `<option value="${r.id}">${esc(r.reference)} · ${money(r.amount_approved)}${
      r.expires_on ? ` · to ${esc(r.expires_on)}` : ''}</option>`).join('');

  const loadAuths = async () => {
    auths = [];
    if (schemeId) {
      const rows = await Api.list('/api/pharmacy/pre-authorizations/',
                                  { enrollment: schemeId, status: 'approved' })
        .catch(() => ({ rows: [] }));
      auths = rows.rows.filter((r) => r.is_usable);
    }
    const form = $('#checkout');
    if (form) form.authorization.innerHTML = authOptions();
  };

  // An uncapped plan reports no remaining benefit; a capped one is worth
  // showing before the basket is priced, because cover stops at the cap and
  // the rest falls to the patient.
  const schemeLabel = (r) => `${r.hmo_name} · ${r.member_number} (${r.effective_coverage}%${
    r.remaining_benefit == null ? '' : `, ${money(r.remaining_benefit)} left this year`})`;

  const schemeOptions = () => '<option value="">—</option>' + schemes.map((r) =>
    `<option value="${r.id}"${String(r.id) === schemeId ? ' selected' : ''}>${esc(schemeLabel(r))}</option>`).join('');

  const draw = () => {
    render(`
      <div class="page-head"><h2>Dispense</h2>
        <a class="btn ghost" href="#/pharmacy">&larr; Pharmacy</a></div>
      <div class="card"><h3>Prescriptions</h3>
        <form id="rx-find" class="toolbar">
          <label>Patient's number
            <input name="number" placeholder="Phone or hospital number…"
                   autocomplete="off" value="${esc(rxNumber)}"></label>
          <button class="btn">Find</button>
        </form>
        <div id="rx-hits">${rxHtml()}</div>
        ${filling ? `<p class="muted">This sale fills: ${esc(filling.label)}
          — the order is marked dispensed when the sale completes.</p>` : ''}
      </div>
      <form id="scan" class="toolbar">
        <label>Scan a barcode
          <input name="code" autocomplete="off" placeholder="Scanner, or type the code…"></label>
        <button class="btn ghost">Find</button>
      </form>
      <form id="add" class="card form-card">
        <label>Item<select name="stock_item">${optionsHtml()}</select></label>
        <label>Quantity<input type="number" name="quantity" min="1" value="1"></label>
        <label>Discount<input type="number" name="discount" min="0" step="0.01" value="0"></label>
        <div class="actions"><button class="btn">Add to sale</button></div>
      </form>
      <div class="card"><h3>Sale</h3><div id="basket">${basketHtml()}</div></div>
      <form id="checkout" class="card form-card">
        <label>Patient (optional — leave blank for a walk-in)
          <input name="patient_search" placeholder="Name, hospital number or phone…"
                 autocomplete="off" value="${esc(patientQuery)}"></label>
        <div id="patient-hit" class="muted">${patient ? patientHitHtml(patient) : ''}</div>
        <label>Payment<select name="payment_method">
          <option value="cash">Cash</option><option value="card">Card</option>
          <option value="transfer">Transfer</option><option value="hmo">HMO / scheme</option>
        </select></label>
        <label>Scheme membership<select name="enrollment">${schemeOptions()}</select></label>
        <label>Authorisation (only for a covered sale above the insurer's threshold)
          <select name="authorization">${authOptions()}</select></label>
        <div class="actions">
          <button type="button" class="btn ghost" id="ask-auth">Ask the insurer</button>
          <button type="button" class="btn ghost" id="to-cashier">Send to a cashier</button>
          <button class="btn">Complete sale</button></div>
      </form>`);

    $('#rx-find').onsubmit = async (e) => {
      e.preventDefault();
      rxNumber = new FormData(e.target).get('number').trim();
      $('#rx-hits').innerHTML = '<div class="loading">Loading…</div>';
      try {
        rxFound = await Api.get('/api/prescriptions/scripts/by-number/',
                                { number: rxNumber, undispensed: 1 });
      } catch (err) { rxFound = null; return toast(err.message, true); }
      draw();
    };
    for (const b of document.querySelectorAll('[data-fill]')) {
      b.onclick = () => {
        const order = rxRows().find((o) => String(o.id) === b.dataset.fill);
        // One order per sale: the API takes one, and the drugs written with it
        // are marked off by the basket lines that match them.
        filling = order ? { id: order.id, label: rxLabel(order) } : null;
        draw();
      };
    }

    // A scanner types the code and presses Enter, which is what this form is:
    // the catalogue is already in memory, so a scan is usually answered here
    // and the API lookup is the fallback for an item past the pages loaded.
    $('#scan').onsubmit = async (e) => {
      e.preventDefault();
      const code = e.target.code.value.trim();
      if (!code) return;
      let hit = items.find((i) => i.barcode === code || i.gtin === code);
      if (!hit) {
        hit = await Api.get('/api/pharmacy/items/barcode/', { code }).catch(() => null);
        if (hit) items.push(hit);
      }
      if (!hit) return toast('No item carries that code.', true);
      draw();
      $('#add').stock_item.value = hit.id;
      $('#add').quantity.select();
    };

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

    // Same registry type-ahead the report forms use; the sale adds the picked
    // patient's active schemes, which is what decides who pays.
    const search = $('#checkout').patient_search;
    let pickSeq = 0;  // only the newest pick's schemes may paint
    picker(search, $('#patient-hit'), PICKERS.patient, async (p) => {
      const seq = ++pickSeq;
      patient = p;
      schemes = [];
      schemeId = '';
      $('#checkout').enrollment.innerHTML = schemeOptions();
      if (!p) return;
      const en = await Api.list('/api/pharmacy/enrollments/',
                                { patient: p.id, is_active: true });
      if (seq !== pickSeq) return;  // the pharmacist has picked again since
      schemes = en.rows;
      schemeId = schemes.length === 1 ? String(schemes[0].id) : '';
      $('#checkout').enrollment.innerHTML = schemeOptions();
      loadAuths();
    });
    // Adding a basket line re-renders the form, so what was typed is kept.
    search.addEventListener('input', () => { patientQuery = search.value; });
    $('#checkout').enrollment.onchange = (e) => {
      schemeId = e.target.value;
      loadAuths();
    };

    // Raise the request without leaving the till. The insurer's share is only
    // known server-side (item rules, the annual cap), so the ask is the basket
    // itself — an approval for more than is billed still covers the sale.
    $('#ask-auth').onclick = async () => {
      if (!schemeId) return toast('Pick the scheme membership first.', true);
      const items = basket.map((b) => ({
        item: b.item, quantity: b.quantity,
        amount: Math.max(b.price * b.quantity - b.discount, 0),
      }));
      const amount = items.reduce((a, b) => a + b.amount, 0);
      if (!amount) return toast('Add the items first — the insurer is asked for a figure.', true);
      try {
        // Itemised: the insurer answers drug by drug, so a refusal on one
        // medication does not cost the pharmacy the rest of the basket.
        const auth = await Api.post('/api/pharmacy/pre-authorizations/',
                                    { enrollment: Number(schemeId), amount, items });
        toast(`Requested ${auth.reference} — it appears above once the insurer answers.`);
      } catch (err) { toast(err.message, true); }
    };

    // Where the dispenser doesn't hold the till: the basket goes to whoever
    // does, and nothing leaves the shelf until the cashier completes it.
    $('#to-cashier').onclick = async () => {
      if (!basket.length) return toast('Add at least one item.', true);
      try {
        const req = await Api.post('/api/pharmacy/payment-requests/', {
          buyer_name: patient ? patient.full_name : '',
          items: basket.map((b) => ({
            item: b.item, name: b.name, quantity: b.quantity,
            unit_price: b.price.toFixed(2),
          })),
        });
        toast(`Request ${req.reference} is with the cashiers.`);
        location.hash = `#/r/pharmacy-requests/${req.id}`;
      } catch (err) { toast(err.message, true); }
    };

    $('#checkout').onsubmit = async (e) => {
      e.preventDefault();
      if (!basket.length) return toast('Add at least one item.', true);
      // A typed-but-unresolved patient means no single match was picked;
      // selling it as a walk-in would quietly lose the billing.
      if (patientQuery.trim() && !patient) {
        return toast('Pick the patient first — the lookup has no single match.', true);
      }
      const fd = new FormData(e.target);
      const body = {
        payment_method: fd.get('payment_method'),
        items: basket.map((b) => ({ item: b.item, quantity: b.quantity, discount: b.discount })),
      };
      if (patient) body.patient = patient.id;
      if (filling) {
        body.prescription = filling.id;
        body.patient_number = rxNumber;
      }
      if (fd.get('enrollment')) body.enrollment = Number(fd.get('enrollment'));
      if (fd.get('authorization')) body.authorization = Number(fd.get('authorization'));
      try {
        const sale = await Api.post('/api/pharmacy/sales/', body);
        toast(`Sale ${sale.reference} — patient pays ${money(sale.patient_payable)}.`);
        location.hash = `#/r/pharmacy-sales/${sale.id}`;
      } catch (err) { toast(err.message, true); }
    };
  };
  draw();
}

/* The ordered medications on one request, each with the insurer's answer.
   Everyone sees the answers — that is the feedback the counter dispenses on —
   but only the admin gets the buttons, because only they may record a decision. */
function preauthItemsHtml(auth) {
  const items = auth.items || [];
  if (!items.length) return '';
  const decides = isPharmacyAdmin() && auth.status === 'requested';
  // A wrong answer is undone rather than lived with, right up until the
  // clearance is spent on a sale.
  const reopens = isPharmacyAdmin()
    && auth.status !== 'used' && auth.status !== 'cancelled';
  const row = (it) => `<tr>
    <td>${esc(it.item_name || it.item)}</td><td>${it.quantity}</td>
    <td>${money(it.amount)}</td>
    <td>${it.status === 'requested' ? 'Awaiting the insurer'
      : `${esc(it.status)}${it.status === 'approved'
        ? ` · ${it.quantity_approved} · ${money(it.amount_approved)}` : ''}${
        it.reason ? ` · ${esc(it.reason)}` : ''}`}</td>
    ${decides || reopens ? `<td>${it.status !== 'requested'
      ? (reopens ? `<input name="reason" maxlength="255" data-for="${it.id}"
             aria-label="Reason" autocomplete="off" placeholder="Reason (optional)">
         <button class="btn danger" data-item="${it.id}" data-decide="reopen">Reopen</button>`
        : '')
      : !decides ? ''
      : `<input name="quantity" type="number" step="1" min="1" max="${it.quantity}"
             value="${it.quantity}" data-for="${it.id}" aria-label="Quantity authorised">
         <input name="amount" type="number" step="0.01" min="0" value=""
             data-for="${it.id}" aria-label="Amount authorised"
             placeholder="${esc(it.amount)}">
         <input name="reason" maxlength="255" data-for="${it.id}" aria-label="Reason"
             autocomplete="off" placeholder="Reason (a refusal)">
         <button class="btn" data-item="${it.id}" data-decide="approve">Approve</button>
         <button class="btn danger" data-item="${it.id}" data-decide="decline">Decline</button>`}</td>` : ''}
  </tr>`;
  return `<div class="card"><h3>Ordered medications</h3>
    <table><thead><tr><th>Medication</th><th>Qty</th><th>Asked</th><th>Insurer</th>
      ${decides || reopens ? '<th></th>' : ''}</tr></thead>
      <tbody>${items.map(row).join('')}</tbody></table>
    <p class="muted">The insurer answers each medication on its own, and may
      clear less than was asked for. The counter dispenses up to the quantity
      cleared; a declined medication is refused at the till.</p>
  </div>`;
}

function wirePreauthItems(reload) {
  for (const b of document.querySelectorAll('[data-item]')) {
    b.onclick = async (e) => {
      e.preventDefault();
      const id = b.dataset.item;
      const field = (name) => document.querySelector(`[name="${name}"][data-for="${id}"]`);
      const approving = b.dataset.decide === 'approve';
      const body = {};
      if (approving) {
        // Blank stands behind the whole ask, which is the API default. A cut
        // quantity with no amount typed bills pro rata, server-side.
        if (field('quantity').value) body.quantity = Number(field('quantity').value);
        if (field('amount').value) body.amount = field('amount').value;
      } else if (field('reason')?.value.trim()) {
        body.reason = field('reason').value.trim();
      }
      try {
        const r = await Api.post(
          `/api/pharmacy/pre-authorization-items/${id}/${b.dataset.decide}/`, body);
        toast(r?.message || 'Done.');
        reload();
      } catch (err) { toast(err.message, true); }
    };
  }
}

/* Recording what the insurer said about one pre-authorization request.
   Rendered under its detail page, admin only — the answer is what the pharmacy
   is later allowed to bill against, so the API refuses anyone else. A request
   already decided has nothing left to record. */
/* A prescriber's statement: what each ledger owes them, the rows behind it,
 * and — for the admin, whose money it is — one button that settles both.
 *
 * Paying is two calls because commissions and consultation fees are two
 * ledgers; the second only runs if the first went through, so a half-failure
 * leaves a figure on screen that still says what is left. */
async function loadStatement(slug, id) {
  const box = $('#statement');
  if (!box) return;
  let st;
  try { st = await Api.get(rdetail(slug, `${id}/statement/`)); }
  catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
  const owed = st.outstanding || {};
  const pending = Number(owed.total || 0) > 0;
  const tile = (k, v) =>
    `<div class="tile kpi-tile"><span class="tile-label">${esc(k)}</span><span class="tile-val">${esc(v)}</span></div>`;
  const ledger = (title, rows) => `<div class="card"><h3>${esc(title)}</h3>
    ${rows.length ? tableHtml(rows) : '<p class="muted">Nothing here yet.</p>'}</div>`;
  box.innerHTML = `<div class="tiles">
      ${tile('Commission due', money(owed.commission))}
      ${tile('Consultations due', money(owed.consultation))}
      ${tile('Total owed', money(owed.total))}
    </div>
    ${pending && isPharmacyAdmin()
      ? `<div class="actions"><button id="pay-all" class="btn">Pay everything owed</button></div>` : ''}
    ${ledger('Commissions', st.commissions || [])}
    ${ledger('Consultation payouts', st.consultation_payouts || [])}`;
  const btn = $('#pay-all');
  if (btn) btn.onclick = async () => {
    btn.disabled = true;
    try {
      await Api.post('/api/prescriptions/commissions/pay-all/', { prescriber: id });
      await Api.post('/api/prescriptions/consultation-payouts/pay-all/', { prescriber: id });
      toast('Paid.');
    } catch (e) { toast(e.message, true); }
    loadStatement(slug, id);
  };
}

function preauthDecisionHtml(auth) {
  if (!isPharmacyAdmin()) return '';
  // An itemised request is answered drug by drug and settles itself once every
  // medication is decided — answering it twice over would contradict that.
  if ((auth.items || []).length) return '';
  // An answer typed wrong is withdrawn and recorded again, until it has been
  // spent on a sale.
  if (auth.status === 'approved' || auth.status === 'declined') {
    return `<div class="card"><h3>The insurer's answer</h3>
      <p class="muted">Recorded wrongly? Withdraw it and record it again.</p>
      <form id="preauth-decide" class="form-card">
        <label>Reason<input name="reason" maxlength="255" autocomplete="off"></label>
        <div class="actions">
          <button class="btn danger" data-decide="reopen">Reopen</button>
        </div>
      </form></div>`;
  }
  if (auth.status !== 'requested') return '';
  return `<div class="card"><h3>Record the insurer's answer</h3>
    <form id="preauth-decide" class="form-card">
      <label>Their code<input name="code" maxlength="60" autocomplete="off"></label>
      <label>Amount authorised
        <input type="number" name="amount" step="0.01" min="0" value="${esc(auth.amount)}">
        <small class="muted">They may stand behind less than the ${money(auth.amount)} asked for.</small></label>
      <label>Expires on<input type="date" name="expires_on">
        <small class="muted">Leave blank if the clearance does not lapse.</small></label>
      <label>Reason (a refusal)<input name="reason" maxlength="255" autocomplete="off"></label>
      <div class="actions">
        <button class="btn" data-decide="approve">Approve</button>
        <button class="btn danger" data-decide="decline">Decline</button>
      </div>
    </form></div>`;
}

function wirePreauthDecision(slug, id, reload) {
  const form = $('#preauth-decide');
  if (!form) return;
  const trimmed = (fd, key) => (fd.get(key) || '').trim();
  for (const b of form.querySelectorAll('[data-decide]')) {
    b.onclick = async (e) => {
      // Both buttons sit in one form: whichever was pressed decides which
      // fields travel, and neither submits the form itself.
      e.preventDefault();
      const fd = new FormData(form);
      const approving = b.dataset.decide === 'approve';
      const body = {};
      if (approving) {
        if (trimmed(fd, 'code')) body.code = trimmed(fd, 'code');
        // Blank means they stood behind the whole ask, which is the API default.
        if (fd.get('amount')) body.amount = fd.get('amount');
        if (fd.get('expires_on')) body.expires_on = fd.get('expires_on');
      } else if (trimmed(fd, 'reason')) {
        body.reason = trimmed(fd, 'reason');
      }
      try {
        const r = await Api.post(rpath(slug, `${id}/${b.dataset.decide}/`), body);
        toast(r?.message || 'Done.');
        reload();
      } catch (err) { toast(err.message, true); }
    };
  }
}

/* Who withdrew an answer on this request, and why. An answer is typed by
   hand, and the record itself keeps only the latest one - so when the insurer
   disputes what they were told, this is the only place that remembers. */
function preauthTrailHtml() {
  return `<div class="card"><h3>Withdrawn answers</h3>
    <div id="preauth-trail"><p class="loading">Loading…</p></div></div>`;
}

async function loadPreauthTrail(id) {
  const box = $('#preauth-trail');
  if (!box) return;
  try {
    const rows = await Api.get(`/api/pharmacy/pre-authorizations/${id}/history/`);
    box.innerHTML = rows.length ? tableHtml(rows)
      : '<p class="muted">No answer on this request has been withdrawn.</p>';
  } catch (e) { box.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
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

/* The counting sheet. Expected is what the shelf said when the line was
   raised — the server snapshots it, so a sale mid-count doesn't move the
   target — and the counter fills in what was actually there.

   ponytail: counts the lines the check was raised over. Finding an item the
   sheet doesn't list means raising it on the check first; add an item picker
   here if that turns out to be the common case rather than the exception. */
function stockCountHtml(check) {
  const lines = check.lines || [];
  if (!lines.length || ['completed', 'cancelled'].includes(check.status)) return '';
  return `<div class="card"><h3>Count</h3>
    <form id="count" class="form-card">
      <div class="table-wrap"><table><thead><tr>
        <th>Item</th><th>Expected</th><th>Counted</th><th>Note</th></tr></thead>
        <tbody>${lines.map((l) => `<tr>
          <td>${esc(l.item_name || `#${l.item}`)}</td>
          <td>${l.expected_quantity ?? '—'}</td>
          <td><input type="number" min="0" data-item="${l.item}"
                     value="${l.actual_quantity ?? ''}" style="width:6rem"></td>
          <td><input data-note="${l.item}" value="${esc(l.notes || '')}"></td>
        </tr>`).join('')}</tbody></table></div>
      <div class="actions"><button class="btn">Save count</button></div>
    </form></div>`;
}

function wireStockCount(checkId, reload) {
  const form = $('#count');
  if (!form) return;
  form.onsubmit = async (e) => {
    e.preventDefault();
    // Only the lines someone actually put a number against: a blank box is
    // "not counted yet", not a count of zero.
    const rows = [...form.querySelectorAll('[data-item]')]
      .filter((i) => i.value !== '')
      .map((i) => ({
        item: Number(i.dataset.item),
        quantity: Number(i.value),
        notes: form.querySelector(`[data-note="${i.dataset.item}"]`).value,
      }));
    if (!rows.length) return toast('Nothing counted yet.', true);
    try {
      const r = await Api.post(`/api/pharmacy/stock-checks/${checkId}/count/`, rows);
      toast(r?.message || 'Counted.');
      reload();
    } catch (err) { toast(err.message, true); }
  };
}

/* --------------------------------------------------------------- portal */

/* A patient's own record on one page: their details, the drugs the pharmacy
   has actually handed over, and where to go and get more.

   Deliberately narrow. The clinical timeline — visits, findings, test results
   — is the facility's working record and the portal API does not serve it, so
   there is nothing here to render it with.

   No patient id is ever sent — the API reads it off the signed-in account
   (apps.patients.portal) — so this client cannot ask for anyone else's
   record even by mistake. */

// Fields a patient is shown about themselves, in the order they read them.
// Not the whole row: the staff notes and the registry bookkeeping are the
// facility's working record, not the card the patient came for.
const PORTAL_FIELDS = [
  'hospital_number', 'full_name', 'sex', 'age', 'date_of_birth', 'phone',
  'address', 'region', 'blood_group', 'genotype', 'allergies',
  'chronic_condition_names', 'patient_type_display', 'nhis_number',
  'next_of_kin_name', 'next_of_kin_phone', 'next_of_kin_relationship',
];

/* The browser's own geolocation, asked once. Resolves to null when the
   patient declines it, the device has no fix, or it takes too long — the
   pharmacy list still answers, it just can't be sorted by distance.
   ponytail: getCurrentPosition, not watchPosition; a shop list doesn't move. */
const myPosition = () => new Promise((resolve) => {
  if (!navigator.geolocation) return resolve(null);
  navigator.geolocation.getCurrentPosition(
    (p) => resolve({ lat: p.coords.latitude.toFixed(6), lng: p.coords.longitude.toFixed(6) }),
    () => resolve(null),
    { timeout: 8000, maximumAge: 300000 },
  );
});

// Only drugs the pharmacy has handed over reach this list — the API sends no
// others — so an empty table means nothing has been collected, not that
// nothing was written.
function portalMedsHtml(rows) {
  if (!rows.length) {
    return '<p class="muted">You have not collected any medication yet.</p>';
  }
  return `<div class="table-wrap"><table><thead><tr>
      <th>Medication</th><th>Dose</th><th>How often</th><th>Days</th>
      <th>Status</th><th></th></tr></thead><tbody>${rows.map((r) => `<tr>
      <td>${esc(r.medication_name || '—')}</td>
      <td>${esc(r.dose || '—')}</td>
      <td>${esc(r.frequency || '—')}</td>
      <td>${esc(r.duration_days ?? '—')}</td>
      <td>${cellHtml('status', r.status)}</td>
      <td><button class="btn find-drug" data-medication="${esc(r.medication)}"
        >Where to get it</button></td></tr>`).join('')}</tbody></table></div>`;
}

function pharmaciesHtml(rows) {
  if (!rows.length) {
    return '<p class="muted">No pharmacy listed for that. Try the full list.</p>';
  }
  // The map link hands the coordinates to whatever maps app the phone has,
  // which is the one that can actually navigate there.
  const map = (r) => r.latitude && r.longitude
    ? `<a href="https://www.google.com/maps/search/?api=1&query=${r.latitude},${r.longitude}"
         target="_blank" rel="noopener">Directions</a>`
    : '<span class="muted">—</span>';
  return `<div class="table-wrap"><table><thead><tr>
      <th>Pharmacy</th><th>Branch</th><th>Address</th><th>Phone</th>
      <th>Distance</th><th></th></tr></thead><tbody>${rows.map((r) => `<tr>
      <td>${esc(r.pharmacy || '—')}</td>
      <td>${esc(r.name || '—')}</td>
      <td>${esc(r.address || '—')}</td>
      <td>${r.phone ? `<a href="tel:${esc(r.phone)}">${esc(r.phone)}</a>` : '—'}</td>
      <td>${r.distance_km == null ? '<span class="muted">—</span>' : esc(r.distance_km) + ' km'}</td>
      <td>${map(r)}</td></tr>`).join('')}</tbody></table></div>`;
}

async function loadPharmacies(medication) {
  const box = $('#pharmacies');
  if (!box) return;
  box.innerHTML = '<div class="loading">Loading…</div>';
  const pos = await myPosition();
  if (!pos) toast('Location off — pharmacies are listed unsorted.');
  try {
    box.innerHTML = pharmaciesHtml(
      await Api.get('/api/portal/pharmacies/', { ...(pos || {}), medication })
    );
  } catch (e) {
    box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
  }
}

async function viewPortal() {
  if (!await ensureChrome()) return;
  spinner();
  let me, meds;
  try {
    [me, meds] = await Promise.all([
      Api.get('/api/portal/me/'),
      Api.get('/api/portal/medications/'),
    ]);
  } catch (e) { return errorBox(e); }

  const details = Object.fromEntries(
    PORTAL_FIELDS.filter((k) => me[k] !== undefined).map((k) => [k, me[k]])
  );

  render(`<div class="page-head"><h2>My Health</h2></div>
    <div class="card">${dlHtml(details)}</div>
    <div class="card"><h3>My medications</h3>${portalMedsHtml(meds)}</div>
    <div class="card"><h3>Where to get them</h3>
      <div class="actions"><button id="find-pharmacies" class="btn">Find pharmacies near me</button></div>
      <div id="pharmacies"></div></div>`);

  $('#find-pharmacies').onclick = () => loadPharmacies();
  for (const b of document.querySelectorAll('.find-drug')) {
    b.onclick = () => {
      loadPharmacies(b.dataset.medication);
      $('#pharmacies').scrollIntoView({ behavior: 'smooth', block: 'center' });
    };
  }
}

/* What the app is telling this user: low stock, an expiry, an insurer's answer
   to a request they raised. The API scopes notifications to the caller and
   admits pharmacy staff only, so everyone else keeps a hidden bell rather than
   a 403 on every page. */
let bellTimer = null;

async function refreshBell() {
  const bell = $('#bell');
  bell.hidden = !PHARMACY_STAFF_ROLES.has(ME?.role) && ME?.role !== 'hmo';
  if (bell.hidden) return;
  // ponytail: one poll for the whole session, cleared on reload. Swap for a
  // websocket if a minute of staleness ever matters.
  if (!bellTimer) bellTimer = setInterval(refreshBell, 60000);
  try {
    const { count } = await Api.list('/api/pos/notifications/',
                                     { is_read: false, page_size: 1 });
    bell.textContent = count ? `\u{1F514} ${count}` : '\u{1F514}';
    bell.classList.toggle('unread', !!count);
  } catch { bell.hidden = true; }
}

function notificationsHtml(rows) {
  if (!rows.length) return '<p class="muted">Nothing waiting.</p>';
  return rows.map((n) => `<div class="card${n.is_read ? '' : ' unread'}">
    <h3>${esc(n.title)}</h3>
    ${n.message ? `<p>${esc(n.message)}</p>` : ''}
    <p class="muted">${esc(n.priority)} · ${esc(n.created_at)}</p>
    ${n.is_read ? '' : `<button class="ghost mark-read" data-id="${n.id}">Mark read</button>`}
    </div>`).join('');
}

async function viewNotifications() {
  if (!await ensureChrome()) return;
  render(`<h2>Notifications</h2>
    <div class="toolbar"><button id="read-all" class="ghost">Mark all read</button></div>
    <div id="out"><p class="loading">Loading…</p></div>`);
  const load = async () => {
    try {
      const { rows } = await Api.list('/api/pos/notifications/');
      $('#out').innerHTML = notificationsHtml(rows);
      for (const b of $('#out').querySelectorAll('.mark-read')) {
        b.onclick = async () => {
          try {
            await Api.patch(`/api/pos/notifications/${b.dataset.id}/`, { is_read: true });
            await refreshBell();
            load();
          } catch (err) { toast(err.message, true); }
        };
      }
    } catch (err) { $('#out').innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
  $('#read-all').onclick = async () => {
    try {
      await Api.post('/api/pos/notifications/read-all/');
      await refreshBell();
      load();
    } catch (err) { toast(err.message, true); }
  };
  load();
}

/* ----------------------------------------------------------------- router */

const routes = [
  [/^\/login$/, viewLogin],
  [/^\/register$/, viewRegister],
  [/^\/onboarding$/, viewOnboarding],
  [/^\/forgot$/, viewForgot],
  [/^\/reset(?:\?(.*))?$/, viewReset],
  [/^\/profile$/, viewProfile],
  [/^\/?$/, viewHome],
  [/^\/r\/([a-z-]+)\/new(?:\?(.*))?$/, (m) => viewForm(m[1], null, m[2])],
  [/^\/r\/([a-z-]+)\/(\d+)\/edit$/, (m) => viewForm(m[1], m[2])],
  [/^\/r\/([a-z-]+)\/(\d+)$/, (m) => viewDetail(m[1], m[2])],
  [/^\/r\/([a-z-]+)$/, (m) => viewList(m[1])],
  [/^\/search$/, viewSearch],
  [/^\/differential$/, viewDifferential],
  [/^\/interaction-check$/, viewInteractionCheck],
  [/^\/notifiable$/, viewNotifiable],
  [/^\/notifications$/, viewNotifications],
  [/^\/graph\/([a-z]+)\/(\d+)$/, (m) => viewGraph(m[1], m[2])],
  [/^\/clinical$/, viewClinical],
  [/^\/portal$/, viewPortal],
  [/^\/insurer$/, viewInsurer],
  [/^\/gov$/, viewGov],
  [/^\/pharmacy$/, viewPharmacy],
  [/^\/pharmacy\/sell$/, viewSell],
  [/^\/analytics(?:\/([a-z-]+))?$/, (m) => viewAnalytics(ANALYTICS, '/analytics', m[1])],
  [/^\/platform(?:\/([a-z-]+))?$/, (m) => viewAnalytics(PLATFORM, '/platform', m[1])],
  [/^\/trading(?:\/([a-z-]+))?$/, (m) => viewAnalytics(PHARMACY_REPORTS, '/trading', m[1])],
];

/* Where a role starts work: the platform owner on cross-tenant analytics, the
   counter on the counter, everyone else on the tenant dashboard. */
const homeHash = (role) => role === 'super_admin' && !Api.tenant ? '#/platform'
  : role === 'public' ? '#/portal'
  : role === 'hmo' ? '#/insurer'
  : role === 'government' ? '#/gov'
  : role === 'pharmacist' ? '#/pharmacy'
  : CLINICAL_ROLES.has(role) ? '#/clinical' : '#/';

function route() {
  const path = location.hash.slice(1) || '/';
  const isAuthRoute = /^\/(login|register|onboarding|forgot|reset)(\?|$)/.test(path);
  if (!Api.isLoggedIn && !isAuthRoute) { location.hash = '#/login'; return; }
  if (Api.isLoggedIn && isAuthRoute) { location.hash = homeHash(ME?.role); return; }
  // Inside an organization there is no platform view — the API refuses the
  // cross-tenant rollups there — so a stale #/platform hash (a bookmark, the
  // back button, a reload after opening a clinic) lands on that organization's
  // dashboard instead of a page of errors.
  if (Api.tenant && /^\/platform(?:\/|$)/.test(path)) { location.hash = '#/'; return; }
  for (const [re, view] of routes) {
    const m = path.match(re);
    if (m) return view(m);
  }
  errorBox(new Error('Page not found: ' + path));
}

window.addEventListener('hashchange', () => { vizTip().hidden = true; route(); });
$('#nav-toggle').onclick = () => $('#sidebar').classList.toggle('open');
$('#sidebar').addEventListener('toggle', e => {
  const g = e.target.dataset?.group;
  if (!g) return;
  e.target.open ? NAV_CLOSED.delete(g) : NAV_CLOSED.add(g);
  localStorage.setItem('navClosed', JSON.stringify([...NAV_CLOSED]));
}, true);
$('#theme-toggle').onclick = () => {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  localStorage.theme = t;
  applyTheme(t);
};
route();
Outbox.flush(); // send anything queued from a previous offline session
