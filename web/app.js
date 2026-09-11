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
/* The three organizations a user can be registered under: a facility, a
   scheme, a health authority's patch. They narrow the user list for the admin
   whose list spans more than one — the platform's. Everyone else's list is
   already pinned to their own portal by the API, so the pickers would be three
   selects with one answer (``when``). Wrapped in arrows: the registry is built
   before isPlatformScope exists. */
/* The patient's sex, copied onto every report at save time (patient_sex on
   the API). Fixed options rather than a lookup path: the values are the
   patient form's own. */
const SEX_FILTER = { param: 'patient_sex', label: 'Sex', text: (r) => r.name,
  options: [{ id: 'F', name: 'Female' }, { id: 'M', name: 'Male' }, { id: 'other', name: 'Other' }] };

const ORG_FILTERS = [
  { param: 'tenant', label: 'Organization', path: '/api/tenants/', text: (r) => r.name },
  { param: 'hmo', label: 'Scheme', path: '/api/pharmacy/hmos/', text: (r) => r.name },
  // The same parameter the platform's state pick uses (apps.tenants.scope):
  // it narrows to that state's subtree — the facilities in it, and the health
  // authority seats sitting on it, who staff no facility at all.
  { param: 'jurisdiction', label: 'Jurisdiction', path: '/api/auth/onboarding/jurisdictions/', text: placeLabel },
].map((f) => ({ ...f, when: () => isPlatformScope() }));

const RESOURCES = {
  'diseases':          { title: 'Diseases',           group: 'Catalog', workflow: true,  search: true,  graph: 'diseases' },
  'medications':       { title: 'Medications',        group: 'Catalog', workflow: true,  search: true,  graph: 'medications' },
  'symptoms':          { title: 'Symptoms',           group: 'Catalog', search: true },
  'interactions':      { title: 'Drug Interactions',  group: 'Catalog' },
  'specialties':       { title: 'Specialties',        group: 'Catalog', search: true,  graph: 'specialties' },
  'procedures':        { title: 'Procedures',         group: 'Catalog', workflow: true,  search: true,  graph: 'procedures' },
  'lab-tests':         { title: 'Lab Tests',          group: 'Catalog', workflow: true,  search: true },
  'articles':          { title: 'Articles',           group: 'Catalog', workflow: true,  search: true },
  // An epidemic-prone case is owed a notification up the IDSR tier within 24
  // hours; sending it stamps the case and takes it off the worklist. The
  // stamp is what hides the button — a second call would not move the clock
  // back, but the case is no longer owed anything.
  'case-reports':      { title: 'Case Reports',       group: 'Reports', report: true, filters: [SEX_FILTER],
                          actions: [{ name: 'notify', label: 'Mark notified up the IDSR tier',
                                      hideWhen: 'notified_at' }] },
  'adverse-reactions': { title: 'Adverse Reactions',  group: 'Reports', report: true, filters: [SEX_FILTER] },
  'lab-results':       { title: 'Lab Results',        group: 'Reports', report: true, filters: [SEX_FILTER] },
  'immunizations':     { title: 'Immunizations',      group: 'Reports', report: true, filters: [SEX_FILTER] },
  'vital-events':      { title: 'Vital Events',       group: 'Reports', report: true, filters: [SEX_FILTER] },
  'stock-reports':     { title: 'Stock Reports',      group: 'Reports', report: true },
  'chw-reports':       { title: 'CHW Reports',        group: 'Reports', report: true, filters: [SEX_FILTER] },
  'facility-metrics':  { title: 'Facility Metrics',   group: 'Reports', report: true },
  'insurance-claims':  { title: 'Insurance Claims',   group: 'Reports', report: true, filters: [SEX_FILTER] },
  'appointments':      { title: 'Appointments',       group: 'Reports', report: true, filters: [SEX_FILTER] },
  // Cancelling one drug stops the whole prescription it was written on — the
  // drugs on it are one decision, and a dispensed one is left alone.
  'prescriptions':     { title: 'Prescriptions',      group: 'Reports', report: true, filters: [SEX_FILTER],
                          actions: [{ name: 'cancel', label: 'Cancel prescription', danger: true,
                                      when: ['prescribed', 'partially_dispensed'] }] },
  'pharmacy-items':         { title: 'Stock Items',     group: 'Pharmacy', path: 'pharmacy/items',           roles: 'admin', search: true },
  // A batch is read-only as a record — stock arrives through the item's
  // receive and leaves through a sale — but the shelf can still be wrong.
  // Correcting it and writing it off are the same endpoint; ``write_off``
  // is what tells shrinkage from a miscount in the ledger.
  'pharmacy-batches':       { title: 'Stock Batches',   group: 'Pharmacy', path: 'pharmacy/batches',         roles: 'staff', search: true, readOnly: true,
                              actions: [{ name: 'adjust', label: 'Correct counted quantity', ask: 'quantity,reason', adminOnly: true },
                                        { name: 'adjust', label: 'Write this batch off', ask: 'reason', danger: true, adminOnly: true,
                                          body: { quantity: 0, write_off: true } }] },
  'pharmacy-movements':     { title: 'Stock Ledger',    group: 'Pharmacy', path: 'pharmacy/movements',       roles: 'staff', readOnly: true },
  'pharmacy-suppliers':     { title: 'Suppliers',       group: 'Pharmacy', path: 'pharmacy/suppliers',       roles: 'admin', search: true },
  'pharmacy-orders':        { title: 'Purchase Orders', group: 'Pharmacy', path: 'pharmacy/purchase-orders', roles: 'staff', search: true, extra: 'purchase',
                              actions: [{ name: 'submit', label: 'Submit to supplier', when: ['draft'] },
                                        { name: 'cancel', label: 'Cancel order', danger: true, when: ['draft', 'submitted', 'partial'] }] },
  'pharmacy-hospitals':     { title: 'Hospitals',      group: 'Pharmacy', path: 'prescriptions/hospitals',   roles: 'admin', search: true },
  // What a prescriber has earned and what is still owed them, on their own
  // page (extra: 'statement') — the two ledgers are settled from there.
  'pharmacy-prescribers':   { title: 'Prescribers',    group: 'Pharmacy', path: 'prescriptions/prescribers', roles: 'admin', search: true, extra: 'statement' },
  // ``signUp``: a scheme joins the platform with the seat that will run its
  // desk, so the two are made together on a page of their own (#/scheme-register)
  // rather than by minting a scheme here and then hunting for its admin.
  'pharmacy-hmos':          { title: 'Schemes',         group: 'Pharmacy', hmo: true, path: 'pharmacy/hmos',            roles: 'admin', search: true, signUp: true },
  'scheme-users':           { title: 'Scheme Users',    group: 'Pharmacy', hmo: true, path: 'users', superOnly: true,
                              search: true, query: { role: 'hmo' }, filters: ORG_FILTERS, signUp: true },
  'pharmacy-enrollments':   { title: 'Scheme Members',  group: 'Pharmacy', hmo: true, path: 'pharmacy/enrollments',     roles: 'staff', search: true },
  // People a principal member asked to have covered under their card. Raised
  // from the patient portal; the scheme's seat answers, and may change its
  // answer at any time — so both buttons show whichever way it stands.
  'pharmacy-dependents':    { title: 'Dependents',      group: 'Pharmacy', hmo: true, path: 'pharmacy/dependents',      roles: 'staff', search: true, readOnly: true,
                              actions: [{ name: 'approve', label: 'Approve', ask: 'member_number', insurer: true, when: ['pending', 'declined'] },
                                        { name: 'decline', label: 'Decline', ask: 'reason', insurer: true, danger: true, when: ['pending', 'approved'] }] },
  // A scheme's price list: what it pays for one drug, and the most it pays
  // for a unit of it. 0 cover is the exclusion; no row means the scheme's own
  // default covers it. The insurer keeps its own list (roles: 'scheme').
  // ``inline``: the two numbers a scheme tunes are edited on the list itself
  // (click the cell); the shelf price is the pharmacy's and stays read-only.
  'pharmacy-item-rules':    { title: 'Price List',      group: 'Pharmacy', hmo: true, path: 'pharmacy/item-rules',      roles: 'scheme', search: true,
                              inline: ['coverage_percent', 'tariff'],
                              filters: [{ param: 'hmo', label: 'Scheme', path: '/api/pharmacy/hmos/', text: (r) => r.name }] },
  // The insurer's answer is four fields at once — a code, what they stand
  // behind, when it lapses, or why they refused — so it gets a form of its own
  // (extra: 'preauth') rather than a chain of prompts.
  'pharmacy-preauths':      { title: 'Authorisations',  group: 'Pharmacy', hmo: true, path: 'pharmacy/pre-authorizations', roles: 'staff', search: true, extra: 'preauth',
                              actions: [{ name: 'cancel', label: 'Withdraw request', ask: 'reason', danger: true, when: ['requested', 'approved'] }] },
  'pharmacy-sales':         { title: 'Sales',           group: 'Pharmacy', path: 'pharmacy/sales',           roles: 'staff', search: true, readOnly: true, receipt: true,
                              actions: [{ name: 'pay', label: 'Take payment', ask: 'amount', choose: 'method:cash,card,transfer', when: ['pending'] },
                                        { name: 'cancel', label: 'Cancel sale', danger: true, when: ['pending', 'paid'] }] },
  'pharmacy-till':          { title: 'Cash Drawer',    group: 'Pharmacy', path: 'pharmacy/till-sessions',   roles: 'staff', createOnly: true,
                              actions: [{ name: 'close', label: 'Close drawer', ask: 'amount,notes', when: ['open'] }] },
  'pharmacy-claims':        { title: 'Claims',          group: 'Pharmacy', hmo: true, path: 'pharmacy/claims',          roles: 'staff', search: true, readOnly: true,
                              actions: [{ name: 'submit', label: 'Submit', when: ['draft', 'rejected'] },
                                        { name: 'approve', label: 'Approve', ask: 'amount', insurer: true, when: ['submitted'] },
                                        { name: 'reject', label: 'Reject', ask: 'reason', insurer: true, when: ['submitted'] },
                                        { name: 'pay', label: 'Record payment', ask: 'amount', adminOnly: true, when: ['approved'] },
                                        { name: 'cancel', label: 'Stop billing', ask: 'reason', danger: true, adminOnly: true,
                                          when: ['draft', 'submitted', 'rejected', 'approved'] }] },
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
  'consultations':     { title: 'Visits',             group: 'Clinical', report: true, filters: [SEX_FILTER], fileFrom: ['prescriptions', 'case-reports'],
                          actions: [{ name: 'diagnose', label: 'Record diagnosis', ask: 'diagnosis',
                                      choose: 'severity:mild,moderate,severe,critical', when: ['open'] },
                                    { name: 'close', label: 'Close visit', ask: 'follow_up_on,notes',
                                      choose: 'disposition:home,follow_up,admitted,referred,deceased', when: ['open'] }] },
  'users':             { title: 'Users',              group: 'Admin', adminOnly: true, search: true,
                          filters: ORG_FILTERS },
  // The same list, narrowed to one kind of seat and sitting in that kind's own
  // section: an insurer's people with the insurance screens, a health
  // authority's with the rollups they read. ``query`` is what narrows it, and
  // the API narrows it again to what the reader may see.
  'authority-users':   { title: 'Authority Users',    group: 'Analytics', path: 'users', superOnly: true,
                          search: true, query: { role: 'government' }, filters: ORG_FILTERS },
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

// List-of-choices fields whose values are names, not row ids: a user's grants.
// Rendered as the same multi-select as the M2M fields, collected as strings.
const STR_LIST_FIELDS = new Set(['privileges']);

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
  privileges: 'Extra screens this person gets on top of their role. You can only pass on what you hold yourself.',
  is_admin: "Lets this seat run its own portal's user list. Meant for an insurer or health authority seat.",
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
  { key: 'prescriptions', label: 'Prescribing Stats', path: '/api/analytics/prescriptions/', dates: true },
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
  { key: 'funnel',        label: 'Funnel',            path: '/api/analytics/funnel/' },
  { key: 'retention',     label: 'Retention',         path: '/api/analytics/retention/' },
  { key: 'benchmark',     label: 'Benchmark',         path: '/api/analytics/benchmark/' },
];

const PLATFORM = [
  { key: 'dashboard',     label: 'Platform Dashboard', path: '/api/analytics/platform/' },
  { key: 'prescriptions', label: 'Prescribing Stats', path: '/api/analytics/platform/prescriptions/', dates: true },
  { key: 'cases',         label: 'Collated Reports',   path: '/api/analytics/platform/cases/', dates: true, exportPath: '/api/analytics/platform/cases/export/' },
  { key: 'surveillance',  label: 'Outbreak Alerts',    path: '/api/analytics/platform/surveillance/' },
  { key: 'idsr',          label: 'IDSR Report',        path: '/api/analytics/platform/idsr/', days: true, csv: true },
  { key: 'sources',       label: 'Report Sources',     path: '/api/analytics/platform/sources/' },
  { key: 'adr',           label: 'ADR Collation',      path: '/api/analytics/platform/adr/', dates: true },
  { key: 'labs',          label: 'Lab Stats',          path: '/api/analytics/platform/labs/', dates: true, clinical: true },
  { key: 'immunizations', label: 'Immunization Stats', path: '/api/analytics/platform/immunizations/', dates: true, clinical: true },
  { key: 'vitals',        label: 'Vital Stats',        path: '/api/analytics/platform/vitals/', dates: true, clinical: true },
  { key: 'stock',         label: 'Stock Stats',        path: '/api/analytics/platform/stock/', dates: true },
  { key: 'chw',           label: 'CHW Stats',          path: '/api/analytics/platform/chw/', dates: true, clinical: true },
  { key: 'facility',      label: 'Facility Stats',     path: '/api/analytics/platform/facility/', dates: true, clinical: true },
  { key: 'insurance',     label: 'Insurance Stats',    path: '/api/analytics/platform/insurance/', dates: true },
  { key: 'appointments',  label: 'Appointment Stats',  path: '/api/analytics/platform/appointments/', dates: true, clinical: true },
  { key: 'consultations', label: 'Visit Stats',        path: '/api/analytics/platform/consultations/', dates: true },
  { key: 'sales',         label: 'State Sales',        path: '/api/analytics/platform/sales/', dates: true, csv: true },
  { key: 'controlled',    label: 'Controlled Drugs',   path: '/api/analytics/platform/controlled/', dates: true, csv: true },
];

/* The health authority reads the surveillance and trading rollups; the
   clinical-service metrics (labs, vaccines, vitals, CHW, facility, appointments) are the
   platform admin's. */
const platformMetrics = () => (ME?.role === 'government' ? PLATFORM.filter((m) => !m.clinical) : PLATFORM);

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

/* An independent prescriber holds a licence and staffs no facility: the row
   carries a state instead of an organization. Their licence is state-wide but
   a prescription is not, so they pick a facility inside that state and write
   under it — the pick is the X-Tenant-ID header, and the server re-checks the
   state on every write (accounts.permissions.may_prescribe_under). */
const isIndependent = () => !!ME?.is_independent;
/* Until they have picked one, every tenant-scoped call answers 403 — so the
   picker is the only screen there is. */
const needsFacility = () => isIndependent() && !Api.tenant;

/* Named grants a seat can hold on top of its role, and where each one means
   something. Mirrors accounts.permissions.MODULE_PRIVILEGES — a grant outside
   the seat's own module counts for nothing, here and on the server. */
const MODULE_PRIVILEGES = {
  facility: ['manage_users', 'pharmacy_admin'],
  scheme: ['manage_users', 'decide_claims', 'edit_tariff'],
  oversight: ['manage_users'],
};

/* Which roles each module's admin may mint (accounts.permissions.MANAGEABLE_ROLES). */
const MODULE_ROLES = {
  facility: ['tenant_admin', 'doctor', 'pharmacist', 'nurse', 'midwife', 'chew', 'hmo', 'public'],
  scheme: ['hmo'],
  oversight: ['government'],
};

const myModule = () => (ME?.role === 'hmo' ? 'scheme'
  : ME?.role === 'government' ? 'oversight'
  : ME?.tenant != null ? 'facility' : null);

/* The grants this seat actually holds: its module's whole catalog when it is
   that module's admin, else what its own row carries, narrowed to the module. */
function myGrants() {
  const module = myModule();
  if (!module) return ME?.role === 'super_admin' ? MODULE_PRIVILEGES.facility : [];
  const catalog = MODULE_PRIVILEGES[module];
  if (['super_admin', 'tenant_admin'].includes(ME?.role) || ME?.is_admin) return catalog;
  return catalog.filter((p) => (ME?.privileges || []).includes(p));
}

const hasPriv = (name) => myGrants().includes(name);

/* Roles this seat may assign, or null for the platform admin who may assign
   any. A grant is not the role: someone trusted with the user list cannot
   mint the admin who could take that trust back. */
function myManageableRoles() {
  const module = myModule();
  if (!module) return null;
  const roles = MODULE_ROLES[module];
  return ME?.role === 'tenant_admin' ? roles : roles.filter((r) => r !== 'tenant_admin');
}

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
    ['#/r/pharmacy-enrollments', 'users', 'Scheme Members'],
    ['#/r/pharmacy-dependents', 'users', 'Dependents'],
    ['#/r/pharmacy-item-rules', 'pill', 'Price List'],
    ['#/r/pharmacy-hmos', 'shield', 'My Scheme'],
    ['#/notifications', 'flag', 'Notifications'],
  ]],
  government: ['#/gov', 'Public Health', [
    ['#/platform/prescriptions', 'chart', 'Prescribing Stats'],
    ['#/platform/surveillance', 'flag', 'Outbreak Alerts'],
    ['#/platform/idsr', 'file', 'IDSR Report'],
    ['#/platform/cases', 'chart', 'Collated Reports'],
    ['#/platform/adr', 'chart', 'ADR Collation'],
    ['#/platform/sources', 'file', 'Report Sources'],
    ['#/platform/sales', 'chart', 'State Sales'],
    ['#/platform/controlled', 'chart', 'Controlled Drugs'],
    ['#/platform', 'chart', 'All Metrics'],
  ]],
};

/* The insurance screens, in registry order — the sidebar's HMO group and the
   HMO dashboard's "Go to" tiles are the same list, read from one place. */
const hmoLinks = () => Object.entries(RESOURCES)
  .filter(([, r]) => r.hmo)
  .map(([slug, r]) => [`#/r/${slug}`, 'shield', r.title]);

const seatLink = ([href, icon, title]) =>
  `<a href="${href}" data-route="${href.slice(1)}">${ico(icon)}${esc(title)}</a>`;

function navHtml() {
  const seat = SEAT_NAV[ME?.role];
  if (seat) {
    const [home, group, links] = seat;
    // A seat flagged as its portal's admin also staffs it: same list screen,
    // narrowed by the API to that scheme's desk or that authority's patch.
    const own = (ME?.is_admin || hasPriv('manage_users'))
      ? links.concat([[`#/r/users`, 'users', 'Portal Users']]) : links;
    return `<a href="${home}" data-route="${home.slice(1)}" class="nav-home">${ico('home')}Dashboard</a>`
      + navGroup(group, own.map(seatLink).join(''))
      + navGroup('Account', `<a href="#/profile" data-route="/profile">${ico('users')}Profile</a>`);
  }
  if (needsFacility()) {
    return `<a href="#/facility" data-route="/facility" class="nav-home">${ico('shield')}Choose Facility</a>`
      + navGroup('Account', `<a href="#/profile" data-route="/profile">${ico('users')}Profile</a>`);
  }
  const iconFor = (slug, r) => slug.endsWith('users') || slug === 'patients' ? 'users'
    : r.hmo ? 'shield'
    : r.group === 'Clinical' ? 'activity' : slug.startsWith('tenants') ? 'shield'
    : r.group === 'Reports' ? 'file' : r.group === 'Pharmacy' ? 'pill' : 'book';
  const groups = {};
  for (const [slug, r] of Object.entries(RESOURCES)) {
    if (r.superOnly && ME?.role !== 'super_admin') continue;
    if (r.adminOnly && !['super_admin', 'tenant_admin'].includes(ME?.role)
        && !(slug === 'users' && hasPriv('manage_users'))) continue;
    if (r.group === 'Pharmacy' && !PHARMACY_STAFF_ROLES.has(ME?.role)) continue;
    // Patient data is clinical-staff only (apps.accounts.permissions.IsClinicalStaff).
    if (r.group === 'Clinical' && !Api.roleCanReport(ME?.role)) continue;
    // Insurance work is the pharmacy's, but it is its own desk — schemes,
    // members, prices, authorisations, claims — so it is read out of the
    // Pharmacy group into one of its own. ``group`` stays 'Pharmacy': it is
    // what the staff gate above and canWriteRes go by.
    (groups[r.hmo ? 'HMO' : r.group] ||= []).push(`<a href="#/r/${slug}" data-route="/r/${slug}">${ico(iconFor(slug, r))}${esc(r.title)}</a>`);
  }
  const tools = [
    `<a href="#/search" data-route="/search">${ico('search')}Search</a>`,
    `<a href="#/differential" data-route="/differential">${ico('activity')}Differential Dx</a>`,
    `<a href="#/interaction-check" data-route="/interaction-check">${ico('pill')}Interaction Check</a>`,
    `<a href="#/notifiable" data-route="/notifiable">${ico('flag')}Notifiable Cases</a>`,
  ];
  /* Someone trusted with the user list but not running the whole facility
     administers one desk, so the link sits in that desk's section instead of
     an Admin group holding nothing else. */
  const usersLink = (groups.Admin || []).find((a) => a.includes('data-route="/r/users"'));
  const deskUsers = usersLink && groups.Pharmacy?.length
    && !['super_admin', 'tenant_admin'].includes(ME?.role);
  if (deskUsers) groups.Admin = groups.Admin.filter((a) => a !== usersLink);
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
      groups.Pharmacy.join('') + (deskUsers ? usersLink : ''));
  }
  if (groups.HMO?.length) {
    html += navGroup('HMO',
      `<a href="#/hmo" data-route="/hmo">${ico('shield')}Insurance Desk</a>` + groups.HMO.join(''));
  }
  const clinical = (isClinicalStaff() ? `<a href="#/clinical" data-route="/clinical">${ico('activity')}Ward</a>` : '')
    + (groups.Clinical || []).join('');
  if (clinical) html += navGroup('Clinical', clinical);
  let analytics = `<a href="#/analytics" data-route="/analytics">${ico('chart')}Tenant Analytics</a>`;
  if (isPlatformScope()) {
    analytics += `<a href="#/platform" data-route="/platform">${ico('chart')}Platform Analytics</a>`
      + (groups.Analytics || []).join('');
  }
  html += navGroup('Analytics', analytics);
  if (groups.Admin?.length) html += navGroup('Admin', groups.Admin.join(''));
  // The only route the sidebar did not reach: the topbar badge opens it, which
  // is not obvious on a phone where the badge is a username and nothing else.
  html += navGroup('Account', `<a href="#/profile" data-route="/profile">${ico('users')}Profile</a>`
    + (isIndependent()
      ? `<a href="#/facility" data-route="/facility">${ico('shield')}Change Facility</a>` : '')
    + (PHARMACY_STAFF_ROLES.has(ME?.role)
      ? `<a href="#/notifications" data-route="/notifications">${ico('flag')}Notifications</a>` : ''));
  return html;
}

/* The state a platform admin is working in. Empty is the whole country; a
   pick narrows every cross-tenant read — the rollups, the facility list they
   open an organization from, the user list — down to that state and its local
   governments. The server refuses to widen a health authority seat on it, so
   only the platform owner is offered the control.
   A state's local governments sit in the same list and pick the same way: the
   header carries any jurisdiction id and the server narrows to that id's
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

/* How one jurisdiction reads in a picker. Local government names repeat across
   states — there is an Ifelodun in Kwara and another in Osun — so a local
   carries its state, or two rows read identically and picking by name is a
   coin toss. Exported for the self-check in places.test.js. */
function placeLabel(j, all) {
  if (j.level !== 'local') return `${j.name} · ${j.level}`;
  const st = all.find((p) => p.id === j.parent);
  return `${j.name} · ${st ? st.name : 'local'}`;
}

/* Label → id for every option of a <select> that carries one, in the order the
   select lists them. The blank "nothing chosen" row is not a choice, so it is
   left out; a label two rows share keeps the first, which is why every long
   list built here labels its rows uniquely (see placeLabel). */
function optionIndex(sel) {
  const byLabel = new Map();
  for (const o of sel.options) {
    const label = String(o.textContent ?? '').trim();
    if (o.value && label && !byLabel.has(label)) byLabel.set(label, String(o.value));
  }
  return byLabel;
}

/* True for anything that is not a letter or a digit, i.e. the character before
   a new word: spaces, hyphens, slashes, commas, the middle dot a label joins on. */
const isWordBoundary = (c) => !/[a-z0-9]/.test(c);

/* True when every character of `q` shows up in `text` in order, gaps allowed. */
function isSubsequence(text, q) {
  let i = 0;
  for (const c of text) {
    if (i === q.length) break;
    if (c === q[i]) i++;
  }
  return i === q.length;
}

/* How well `label` answers query `q`, lower being better; null means no match.
   Exact beats prefix beats word start beats mid-word, and only then a fuzzy
   subsequence ("ifkw" finding "Ifelodun · Kwara"), so a typo-tolerant match
   never outranks a literal one. Same ranking the Flutter app's picker uses, so
   typing the same letters finds the same row on either client. */
function matchScore(label, q) {
  const l = label.toLowerCase();
  if (l === q) return 0;
  if (l.startsWith(q)) return 1;
  const at = l.indexOf(q);
  if (at > 0) return isWordBoundary(l[at - 1]) ? 2 : 3;
  return isSubsequence(l, q) ? 4 : null;
}

/* Labels matching `q`, best first; ties keep the caller's original order, which
   is why the jurisdictions come out grouped by state. Empty query lists them
   all. Split out so the ranking can be checked without driving the menu. */
function rankMatches(labels, q) {
  const query = q.trim().toLowerCase();
  if (!query) return labels;
  const scored = [];
  labels.forEach((label, i) => {
    const s = matchScore(label, query);
    if (s !== null) scored.push([s, i, label]);
  });
  scored.sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]));
  return scored.map((s) => s[2]);
}

// ponytail: 50 rows is what a menu can show before it is a scroll hunt again,
// and the only per-keystroke cost here is painting them. Raise it the day a
// list needs more visible at once than a screenful.
const MENU_ROWS = 50;

let menuSeq = 0;

/* Swap a long <select> for a search box: the user types, the menu below ranks
   what is left, and a hidden field of the same name carries the chosen id — so
   every caller and every FormData reads what it read before. 37 states and 774
   local governments stop being a scroll hunt.
   Text that matches no row leaves the id empty: a half-typed name is not a
   pick. The hidden field fires `change` on every keystroke, so a caller can
   tell "still typing" (box full, id empty) from "cleared" (both empty). */
function makeSearchable(sel, { placeholder = 'Type to search…' } = {}) {
  const byLabel = optionIndex(sel);
  const labels = [...byLabel.keys()];

  const wrap = document.createElement('span');
  wrap.className = 'search-select';
  const box = document.createElement('input');
  box.type = 'text';
  box.autocomplete = 'off';
  box.placeholder = placeholder;
  box.className = sel.className;
  box.setAttribute('role', 'combobox');
  box.setAttribute('aria-autocomplete', 'list');
  box.setAttribute('aria-expanded', 'false');
  if (sel.required) box.required = true;
  // Not data-rel: that is the hook wireRelFields looks the select up by, and a
  // box carrying it would be found again and read for options it has not got.
  for (const a of ['aria-label', 'title']) {
    if (sel.hasAttribute(a)) box.setAttribute(a, sel.getAttribute(a));
  }
  const menu = document.createElement('div');
  menu.className = 'search-menu';
  menu.id = `sm-${++menuSeq}`;
  menu.setAttribute('role', 'listbox');
  menu.hidden = true;
  box.setAttribute('aria-controls', menu.id);

  const hidden = document.createElement('input');
  hidden.type = 'hidden';
  hidden.name = sel.name;
  hidden.value = sel.value || '';
  for (const [label, id] of byLabel) if (id === hidden.value) box.value = label;

  let shown = [];   // labels the menu is listing right now
  let active = -1;  // the one the arrow keys are on, -1 for none

  const close = () => {
    menu.hidden = true;
    active = -1;
    box.setAttribute('aria-expanded', 'false');
  };

  const paint = () => {
    const all = rankMatches(labels, box.value);
    shown = all.slice(0, MENU_ROWS);
    if (!shown.length) {
      menu.innerHTML = '<div class="search-none">No match</div>';
    } else {
      menu.innerHTML = shown.map((l, i) =>
        `<div class="search-opt${i === active ? ' active' : ''}" role="option"`
        + ` aria-selected="${i === active}" data-i="${i}">${esc(l)}</div>`).join('')
        + (all.length > shown.length
          ? `<div class="search-none">${all.length - shown.length} more — keep typing</div>` : '');
    }
    menu.hidden = false;
    box.setAttribute('aria-expanded', 'true');
  };

  const announce = () => hidden.dispatchEvent(new Event('change', { bubbles: true }));

  const pick = (label) => {
    if (label == null) return;
    box.value = label;
    hidden.value = byLabel.get(label) || '';
    close();
    announce();
  };

  box.oninput = () => {
    // A label typed out in full counts even before the menu is clicked, so
    // pasting one and tabbing away still resolves.
    hidden.value = byLabel.get(box.value.trim()) || '';
    active = -1;
    paint();
    announce();
  };
  box.onfocus = paint;
  // mousedown on a row runs before this, and cancels the blur, so closing here
  // never eats the click.
  box.onblur = close;
  box.onkeydown = (e) => {
    if (e.key === 'Escape') return close();
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (menu.hidden) return paint();
      if (!shown.length) return;
      active += e.key === 'ArrowDown' ? 1 : -1;
      if (active >= shown.length) active = 0;
      if (active < 0) active = shown.length - 1;
      return paint();
    }
    if (e.key === 'Enter') {
      // Only when the menu is open with something under the cursor: otherwise
      // Enter is the user submitting the form, not choosing a row.
      if (menu.hidden || active < 0) return;
      e.preventDefault();
      pick(shown[active]);
    }
  };
  menu.onmousedown = (e) => {
    const opt = e.target.closest?.('[data-i]');
    if (!opt) return;
    e.preventDefault();
    pick(shown[Number(opt.dataset.i)]);
  };

  // Anything that fills this field from elsewhere — carryPatientFields reading
  // it off the patient's record — writes to the hidden input, because that is
  // what form.elements still answers with. The box has to follow, or the value
  // is set and invisible.
  hidden.showPick = (value) => {
    const want = String(value ?? '');
    hidden.value = '';
    box.value = '';
    for (const [label, id] of byLabel) {
      if (id === want) { hidden.value = id; box.value = label; break; }
    }
    close();
  };

  sel.replaceWith(wrap);
  wrap.append(box, menu, hidden);
  return { box, menu, hidden };
}

async function paintStatePicker() {
  const slot = $('#state-badge');
  const show = ME?.role === 'super_admin' && !Api.tenant;
  slot.hidden = !show;
  // Built once. ensureChrome runs on every navigation, and the picker has
  // replaced its own <select> by the time it is asked a second time.
  const sel = slot.querySelector('select');
  if (!show || !sel) return;
  const places = await placeOptions();
  const states = places.filter((j) => j.level === 'state');
  if (!states.length) return (slot.hidden = true);
  sel.innerHTML = states.map((st) =>
    `<option value="${st.id}">${esc(st.name)}</option>` +
    places.filter((j) => j.level === 'local' && j.parent === st.id)
      .map((j) => `<option value="${j.id}">${esc(placeLabel(j, places))}</option>`)
      .join('')).join('');
  sel.value = Api.jurisdiction;
  // A stale id (a state that has gone) reads as no pick; drop it rather than
  // keep filtering every list by something the picker cannot show.
  if (sel.value !== Api.jurisdiction) Api.jurisdiction = '';
  sel.title = 'Where to work: type a state or a local government. Empty is all Nigeria';
  const { box, hidden } = makeSearchable(sel, { placeholder: 'All Nigeria' });
  hidden.onchange = () => {
    // Half-typed text is not a decision: only a resolved pick, or a box wiped
    // back to empty, is worth throwing the page away for.
    if (!hidden.value && box.value.trim()) return;
    if (hidden.value === Api.jurisdiction) return;
    Api.jurisdiction = hidden.value;
    location.reload();
  };
}

async function ensureChrome() {
  if (!ME) {
    try { ME = await Api.myself(); } catch { /* token dead */ }
    if (!ME) { await Api.logout(); location.hash = '#/login'; return false; }
  }
  // An independent prescriber writes under a facility they pick. Until they
  // have, the picker is the only screen the API will answer — send them there
  // rather than to a page of 403s. Their own profile stays reachable: it is
  // where the state on their row reads out.
  const here = location.hash.slice(1) || '/';
  if (needsFacility() && !/^\/(facility|profile)/.test(here)) {
    location.hash = '#/facility';
    return false;
  }
  armIdleLogout();
  $('#topbar').hidden = false;
  $('#sidebar').hidden = false;
  const badge = $('#tenant-badge');
  // Name where there is one; the slug is the fallback for a session that
  // switched organizations before the name was known.
  badge.textContent = Api.tenantName || Api.tenant
    || (isIndependent() ? 'choose a facility' : 'no organization');
  // A super-admin hops between organizations, so their badge is the way back
  // out of the one they opened. An independent prescriber's badge is the same
  // control for the same reason: the facility they write under is a choice,
  // not where they work. Everyone else is stuck to their own tenant.
  const canLeave = (ME?.role === 'super_admin' || isIndependent()) && !!Api.tenant;
  badge.classList.toggle('clickable', canLeave);
  badge.title = canLeave
    ? (isIndependent() ? 'Write under another facility' : 'Leave this organization') : '';
  badge.onclick = canLeave ? async () => {
    // Close the visit on the server before dropping the header, same as
    // opening records it: a trail that only ever says who went in is half a
    // trail. A failure here must not strand them inside the organization.
    // Only the platform admin's visit is trailed that way — a prescriber never
    // had the run of the facility, and every script they wrote names them.
    if (ME?.role === 'super_admin') {
      try { await Api.post('/api/tenants/leave/'); } catch { /* leave anyway */ }
    }
    const back = isIndependent() ? '#/facility' : '#/platform';
    Api.tenant = '';
    Api.tenantName = '';
    location.hash = back;
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

/* The mobile drawer is one piece of state: the class that slides it in (the
   scrim follows it in CSS) and the toggle's aria-expanded. ``refocus`` is for
   a deliberate open or dismiss — keyboard and screen-reader users land on the
   menu, then get sent back to the button — and stays off for the automatic
   close on navigation, which must not steal focus from the new page. */
function setNav(open, refocus) {
  $('#sidebar').classList.toggle('open', open);
  $('#nav-toggle').setAttribute('aria-expanded', String(open));
  if (refocus) (open ? $('#sidebar').querySelector('a, summary') : $('#nav-toggle'))?.focus();
}
const navOpen = () => $('#sidebar').classList.contains('open');

function render(html) {
  $('#main').innerHTML = html;
  $('#main').scrollTop = 0;
  setNav(false);
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
/* ``linkFor`` is for the reports that are worklists rather than statistics:
   a row that names a record links to it, so the reader can act on the row
   instead of hunting the record down in its own list. */
function renderData(data, depth = 0, linkFor = null) {
  if (data === null || typeof data !== 'object') return `<p class="big-val">${esc(fmtVal(data))}</p>`;
  if (Array.isArray(data)) {
    if (!data.length) return '<p class="muted">No data.</p>';
    if (typeof data[0] === 'object' && data[0] !== null) {
      const c = chartable(data);
      return c ? chartHtml(data, c) : tableHtml(data, linkFor);
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
    html += `<section class="sub"><h${Math.min(3 + depth, 5)}>${esc(label(k))}</h${Math.min(3 + depth, 5)}>${renderData(v, depth + 1, linkFor)}</section>`;
  }
  return html || '<p class="muted">No data.</p>';
}

// ``inline``: {slug, fields} — those columns become click-to-edit cells that
// PATCH the row in place (see the #main click handler below).
function tableHtml(rows, linkFor, rowAction, inline) {
  const cols = pickColumns(rows);
  const keys = Object.keys(mergedRow(rows));
  const head = cols.map((c) => `<th>${esc(colLabel(keys, c))}</th>`).join('')
    + (rowAction ? '<th></th>' : '');
  const body = rows.map((r, i) => {
    const cells = cols.map((c) => inline?.fields.includes(c)
      ? `<td class="inline-edit" title="Click to edit" data-slug="${inline.slug}" data-id="${r.id}" data-field="${c}">${cellHtml(c, r[c])}</td>`
      : `<td>${cellHtml(c, r[c])}</td>`).join('')
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
  // still belongs in the table.
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
    `<option value="${j.id}">${esc(placeLabel(j, jurisdictions))}</option>`).join('');
  render(authShell('Register your organization', 'Set up your workspace and admin account', `
    <form id="f">
      <label>Organization name<input name="org_name" required></label>
      <label>Slug (short id, e.g. "my-clinic")<input name="org_slug" required pattern="[a-z0-9-]+"></label>
      <label>Organization type<select name="org_kind"><option value="pharmacy">Pharmacy</option><option value="hospital">Hospital</option></select></label>
      <label>Address<input name="org_address" required></label>
      <label>Contact<input name="org_contact" required></label>
      ${jOpts ? `<label>Jurisdiction<select name="jurisdiction"><option value=""></option>${jOpts}</select></label>` : ''}
      <h3 class="auth-section">Admin account</h3>
      <label>Phone<input name="phone" placeholder="08031234567" required></label>
      <label>Email<input name="email" type="email" required></label>
      <label>Password<input name="password" type="password" required></label>
      <button type="submit">Create organization</button>
    </form>`, `
    <p class="muted center"><a href="#/login">Back to sign in</a></p>`));
  // 774 local governments: type-ahead, not a scroll hunt.
  const jsel = $('#f').querySelector('select[name="jurisdiction"]');
  if (jsel) makeSearchable(jsel, { placeholder: 'Type a state or local government' });
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

/* Sign an insurer up: the scheme and the seat that will run its desk, made
 * together (POST /api/pharmacy/hmos/register/). Platform admin only — an
 * insurer joining is not the pharmacy's decision — and from here the scheme
 * staffs itself, because the seat minted carries ``is_admin``.
 *
 * Its own page rather than the generated form: one POST writes two records,
 * and OPTIONS metadata has no shape for that. */
async function viewSchemeRegister() {
  if (!await ensureChrome()) return;
  if (ME?.role !== 'super_admin') {
    return errorBox(new Error('Only the platform admin registers a scheme.'));
  }
  spinner();
  let orgs = [];
  try { ({ rows: orgs } = await Api.list('/api/tenants/', { page_size: 100 })); }
  catch (e) { return errorBox(e); }
  const opts = orgs.map((o) =>
    `<option value="${o.id}"${o.slug === Api.tenant ? ' selected' : ''}>${esc(o.name)}</option>`).join('');
  render(`<div class="page-head"><h2>Register a scheme</h2></div>
    <form id="f" class="card form-card">
      <label data-field="tenant">Organization whose claims it answers for
        <select name="tenant" required><option value=""></option>${opts}</select>
        <em class="field-err"></em></label>
      <h3>Scheme</h3>
      <label data-field="name">Name<input name="name" required><em class="field-err"></em></label>
      <label data-field="code">Code<input name="code"><em class="field-err"></em></label>
      <label data-field="contact">Contact<input name="contact"><em class="field-err"></em></label>
      <label data-field="email">Email<input name="email" type="email"><em class="field-err"></em></label>
      <label data-field="coverage_percent">Default cover (%)
        <input name="coverage_percent" type="number" step="0.01" min="0" max="100" value="100.00" required>
        <em class="field-err"></em></label>
      <label data-field="preauth_threshold">Authorisation needed above (₦, 0 = never)
        <input name="preauth_threshold" type="number" step="0.01" min="0" value="0.00" required>
        <em class="field-err"></em></label>
      <label data-field="auto_submit_claims">Submit each claim as the sale happens
        <input name="auto_submit_claims" type="checkbox"><em class="field-err"></em></label>
      <h3>Scheme admin</h3>
      <p class="muted">This seat runs the scheme's desk and adds the rest of its staff itself.</p>
      <label data-field="admin_phone">Phone<input name="admin_phone" placeholder="08031234567" required><em class="field-err"></em></label>
      <label data-field="admin_name">Name<input name="admin_name"><em class="field-err"></em></label>
      <label data-field="admin_email">Email<input name="admin_email" type="email"><em class="field-err"></em></label>
      <label data-field="admin_password">Password<input name="admin_password" type="password" required><em class="field-err"></em></label>
      <div class="actions">
        <button type="submit" class="btn">Register scheme</button>
        <a class="btn ghost" href="#/r/pharmacy-hmos">Cancel</a>
      </div>
    </form>`);
  makeSearchable($('#f').elements.tenant, { placeholder: 'Type an organization' });
  $('#f').onsubmit = async (e) => {
    e.preventDefault();
    const body = schemeSignUpBody(new FormData(e.target));
    const missing = schemeSignUpProblem(body);
    if (missing) return toast(missing, true);
    try {
      const r = await Api.post('/api/pharmacy/hmos/register/', body);
      toast(r?.message || 'Scheme registered. Its admin can now sign in.');
      // The scheme list is one organization's; a platform admin with none open
      // would land on an empty page, so send them to the list that spans them.
      location.hash = Api.tenant ? '#/r/pharmacy-hmos' : '#/r/scheme-users';
    } catch (err) {
      toast(err.message, true);
      showFieldErrors(e.target, flattenSchemeErrors(err.errors));
    }
  };
}

/* The body POST /api/pharmacy/hmos/register/ takes: a scheme, and the seat
   that will run its desk, written together. The scheme's own fields go nested
   under ``scheme`` because that half is the ordinary insurer serializer.

   Decimals travel as the strings they were typed in — DRF parses them, and
   rounding a naira figure through a float on the way out would be this client
   inventing a number nobody typed. A blank threshold is 0: "never ask first",
   which is what the field left alone means. The password is the one value not
   trimmed: trimming one changes it. Mirrors mobile's schemeSignUpBody. */
function schemeSignUpBody(fd) {
  const f = (name) => (fd.get(name) || '').toString().trim();
  const blankTo = (name, fallback) => f(name) || fallback;
  return {
    tenant: f('tenant'),
    scheme: {
      name: f('name'), code: f('code'), contact: f('contact'), email: f('email'),
      coverage_percent: blankTo('coverage_percent', '100'),
      preauth_threshold: blankTo('preauth_threshold', '0'),
      auto_submit_claims: fd.get('auto_submit_claims') === 'on',
    },
    admin_phone: f('admin_phone'),
    admin_name: f('admin_name'),
    admin_email: f('admin_email'),
    admin_password: (fd.get('admin_password') || '').toString(),
  };
}

/* What is still missing from that body, in words, or null when it is ready to
   send. The API refuses all of this too — this only saves the round trip, and
   says it in the same words the mobile sheet does. */
function schemeSignUpProblem(body) {
  if (!body.tenant) {
    return 'Choose the organization whose claims this scheme answers for.';
  }
  if (!body.scheme.name) return 'Name the scheme.';
  if (!body.admin_phone) {
    return "Give the admin's phone number — it is how they sign in.";
  }
  if (body.admin_password.length < 8) {
    return 'The admin password needs 8 characters or more.';
  }
  return null;
}

/* The scheme's own fields come back nested under ``scheme`` (one serializer
   inside another), but the form is flat — lift them so each message lands on
   the field that caused it instead of on nothing. */
function flattenSchemeErrors(errors) {
  if (!errors?.scheme || Array.isArray(errors.scheme)) return errors;
  const { scheme, ...rest } = errors;
  return { ...rest, ...scheme };
}

async function viewProfile() {
  if (!await ensureChrome()) return;
  spinner();
  try {
    const me = await Api.myself();
    // A patient's profile is their own record first; the account row below
    // it is the login they got it through.
    const patient = me.role === 'public' ? await Api.get('/api/portal/me/').catch(() => null) : null;
    // The tenant's admin sets the idle timeout for everyone in it; a
    // super-admin sets it for whichever organization they have open.
    const canSetIdle = ['tenant_admin', 'super_admin'].includes(me.role) && Api.tenant;
    render(`<h2>Profile</h2>
      ${patient ? `<div class="card"><h3>My details</h3>${dlHtml(portalDetails(patient))}</div>` : ''}
      <div class="card">${patient ? '<h3>Account</h3>' : ''}${dlHtml(me)}</div>
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

/* The insurer's answer — to a request or a claim — is given by its own seat,
   or recorded by the pharmacy admin on its behalf. Mirrors answers_for_insurer:
   on the scheme's side the seat needs its admin's decide_claims grant. */
const answersForInsurer = () => isPharmacyAdmin()
  || (ME?.role === 'hmo' && !!ME?.hmo && hasPriv('decide_claims'));

/* Module actions (dispensing, claims, notifications): each POSTs to its own
   endpoint. Offer only the ones this record can actually take — the API
   rejects the rest, so a button that always fails is a trap rather than a
   feature. ``when`` is the states that allow it, ``hideWhen`` a field whose
   presence means it has already been done; ``insurer`` is an answer the
   scheme's own seat may give. */
const visibleActions = (res, obj) => (res.actions || []).filter((a) =>
  (a.insurer ? answersForInsurer() : canActRes(res) && (!a.adminOnly || isPharmacyAdmin()))
  && (!a.when || a.when.includes(obj.status))
  && (!a.hideWhen || !obj[a.hideWhen]));

// ``createOnly`` resources (the cash drawer) are made and then only acted on:
// the list still offers "+ New", the detail page offers no edit or delete.
function canWriteRes(slug, res) {
  if (res.readOnly || res.createOnly) return false;
  if (res.roles === 'admin') return isPharmacyAdmin();
  // A scheme's price list is written by that scheme, or by the pharmacy admin
  // for a scheme with no seat of its own. Mirrors IsSchemePriceListEditor.
  if (res.roles === 'scheme') return isPharmacyAdmin()
    || (ME?.role === 'hmo' && !!ME?.hmo && hasPriv('edit_tariff'));
  if (res.roles === 'staff') return isPharmacyStaff();
  if (res.roles === 'tenant_admin') return ['super_admin', 'tenant_admin'].includes(ME.role);
  // Patients: the same cadres that may read them may register and edit them.
  if (res.roles === 'clinical') return Api.roleCanReport(ME.role);
  // Users: the facility's admin, or a seat flagged as its own portal's admin.
  if (isUserRes(slug)) return ['super_admin', 'tenant_admin'].includes(ME.role)
    || !!ME.is_admin || hasPriv('manage_users');
  return res.report ? Api.roleCanReport(ME.role) : Api.roleCanWrite(ME.role);
}

// Rows behind a list filter, fetched once per endpoint per session. A filter
// picks from a list that is short and slow to change (branches, staff), so a
// re-fetch on every keystroke would buy nothing.
// ponytail: first 100 rows; paginate the picker if a tenant outgrows that.
const filterCache = {};
const filterOptions = (f) => f.options || (filterCache[f.path] ||=
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
    const query = { page: st.page, ...res.query };
    if (st.search) query.search = st.search;
    for (const [k, v] of Object.entries(st.filters)) if (v) query[k] = v;
    const seq = ++st.seq;
    const filters = (res.filters || []).filter((f) => !f.when || f.when());
    const [{ rows, count }, ...options] = await Promise.all([
      Api.list(rpath(slug), query), ...filters.map(filterOptions),
    ]);
    if (seq !== st.seq) return;  // a later keystroke already asked
    const pages = count != null ? Math.max(1, Math.ceil(count / 25)) : 1;
    render(`
      <div class="page-head"><h2>${esc(res.title)}</h2>
        ${(canWrite || res.createOnly) && !slug.startsWith('tenants') ? `<a class="btn" href="#/r/${slug}/new${res.query ? '?' + new URLSearchParams(res.query) : ''}">+ New</a>` : ''}
        ${res.signUp && ME?.role === 'super_admin' ? '<a class="btn" href="#/scheme-register">+ Register scheme</a>' : ''}
      </div>
      <form id="search-form" class="toolbar">
        <input name="q" autocomplete="off"
               placeholder="${res.search ? 'Search…' : 'Filter by search…'}" value="${esc(st.search)}">
        ${filters.map((f, i) => `<label>${esc(f.label)}
          <select name="${f.param}">
            <option value="">All</option>
            ${options[i].map((r) => `<option value="${r.id}"${String(st.filters[f.param] || '') === String(r.id) ? ' selected' : ''}>${esc(f.text(r, options[i]) ?? r.id)}</option>`).join('')}
          </select></label>`).join('')}
        <button>Search</button>
      </form>
      ${res.report ? reportSummaryHtml(slug, rows) : ''}
      ${rows.length ? tableHtml(slug === 'prescriptions' ? collapseByGroup(rows) : rows,
        res.noLink ? null : (r) => `#/r/${slug}/${r.id}`,
        slug === 'prescriptions' && canWrite ? cancelButtonHtml : null,
        canWrite && res.inline ? { slug, fields: res.inline } : null) : '<p class="muted">Nothing here yet.</p>'}
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
    const acts = visibleActions(res, obj);
    const actsHtml = acts.map((a) =>
      `<button class="btn${a.danger ? ' danger' : ''}" data-pa="${a.name}" data-ask="${a.ask || ''}" data-choose="${a.choose || ''}"
        data-body="${a.body ? esc(JSON.stringify(a.body)) : ''}">${esc(a.label)}</button>`).join('');
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
        // ``body`` is what the action always sends — the half of the call the
        // label already states, so the user is not prompted for it.
        const body = b.dataset.body ? JSON.parse(b.dataset.body) : {};
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
            ? tableHtml(rows.map((r) => ({ who: r.user_phone || `#${r.user}`, what: r.to_status, when: r.created_at })))
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
    if (isUserRes(slug)) narrowUserFields(fields);
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
    wireRegionField($('#f'), current);
    wireChoiceFields($('#f'));
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

/* A user form shows a seat only what it may hand out: the roles its own module
 * lets it assign, and the grants it holds itself. The fields that say which
 * module a user lands in are pinned from the writer server-side
 * (accounts.serializers.apply_admin_scope), so they come off the form rather
 * than being offered and then ignored. */
/* True for every registry entry that is the user list — the platform's
   sections each hold one, narrowed to the seats that section is about. */
const isUserRes = (slug) => slug === 'users' || RESOURCES[slug]?.path === 'users';

function narrowUserFields(fields) {
  const module = myModule();
  const roles = myManageableRoles();
  if (!roles) return;                       // the platform admin assigns any
  if (fields.role?.choices) {
    fields.role.choices = fields.role.choices.filter((c) => roles.includes(c.value));
  }
  const grants = myGrants();
  const offered = (fields.privileges?.child?.choices || [])
    .filter((c) => grants.includes(c.value));
  if (fields.privileges) {
    if (offered.length) fields.privileges.child.choices = offered;
    else delete fields.privileges;          // nothing of theirs to pass on
  }
  delete fields.tenant;                     // pinned to the writer's own
  // A licence belongs to a clinical cadre; neither a scheme's desk nor a
  // health authority's office seats one, so the field is noise there.
  if (module !== 'facility') delete fields.license_number;
  if (module === 'scheme') { delete fields.hmo; delete fields.jurisdiction; }
  if (module === 'oversight') delete fields.hmo;
  if (module === 'facility') delete fields.jurisdiction;
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

/* Whether a field takes several values. OPTIONS says so for a relation (see
 * config/metadata.py); M2M_FIELDS still names the ones an older backend can't,
 * and privileges is a list of strings, not of ids. */
function isMultiField(name, f) {
  return !!f.multiple || M2M_FIELDS.has(name) || STR_LIST_FIELDS.has(name);
}

/* A closed list long enough to scroll becomes a type-ahead. The selects the
 * app fills after render carry their own hook and wire themselves. */
function wireChoiceFields(form) {
  for (const sel of form.querySelectorAll('select[data-choice]:not([multiple])')) {
    if (sel.options.length > 12) makeSearchable(sel, { placeholder: 'Type to search…' });
  }
  for (const sel of form.querySelectorAll('select[data-choice][multiple]')) makeMultiPicker(sel);
}

/* A multi-select (a seat's grants) becomes a type-ahead plus chips: type or
   drop the list down to add one, × on a chip to take it back. The <select>
   stays, hidden, as the value — collectForm reads it exactly as before.
   ponytail: native <datalist> does the searching; no menu code of our own. */
function makeMultiPicker(sel) {
  sel.hidden = true;
  const box = document.createElement('input');
  box.type = 'search';
  box.autocomplete = 'off';
  box.placeholder = 'Type or pick to add…';
  box.setAttribute('list', `dl-${++menuSeq}`);
  const list = document.createElement('datalist');
  list.id = box.getAttribute('list');
  const chips = document.createElement('div');
  chips.className = 'chips';
  sel.after(box, list, chips);

  const paint = () => {
    list.innerHTML = [...sel.options].filter((o) => !o.selected)
      .map((o) => `<option value="${esc(o.textContent)}"></option>`).join('');
    chips.innerHTML = [...sel.selectedOptions].map((o) =>
      `<span class="chip">${esc(o.textContent)} <button type="button" aria-label="Remove ${esc(o.textContent)}" data-v="${esc(o.value)}">×</button></span>`).join('');
  };
  box.addEventListener('change', () => {
    const typed = box.value.trim().toLowerCase();
    const hit = [...sel.options].find((o) => o.textContent.trim().toLowerCase() === typed);
    if (hit) { hit.selected = true; box.value = ''; paint(); }
  });
  chips.addEventListener('click', (e) => {
    const v = e.target.closest('button')?.dataset.v;
    if (v == null) return;
    sel.querySelector(`option[value="${CSS.escape(v)}"]`).selected = false;
    paint();
  });
  paint();
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
  // Where the patient lives, held as "LGA, State". Free text spelled it a
  // different way on every desk — Ikeja / IKEJA / Ikeja LGA — and the rollups
  // group by this string, so it comes up as a closed list the app fills after
  // render, same trick as `item`. The Flutter app has always picked it from a
  // list; this is the web catching up.
  if (!f.choices && name === 'region') {
    return `<label data-field="region">${lbl}
      <select name="region"${req} data-region><option value="${esc(v)}">Loading…</option></select>
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
  // A ListField puts its options on the child, not on the field itself.
  if (!f.choices && f.child?.choices) f = { ...f, choices: f.child.choices };
  if (f.choices) {
    const isMulti = isMultiField(name, f);
    const sel = new Set(Array.isArray(v) ? v.map(String) : [String(v)]);
    const opts = f.choices.map((c) =>
      `<option value="${esc(c.value)}" ${sel.has(String(c.value)) ? 'selected' : ''}>${esc(c.display_name)}</option>`).join('');
    control = `<select name="${name}" ${isMulti ? 'multiple size="6"' : ''}${req} data-choice>${isMulti ? '' : '<option value=""></option>'}${opts}</select>`;
  } else if (f.type === 'boolean') {
    control = `<input type="checkbox" name="${name}" ${v ? 'checked' : ''}>`;
  } else if (f.type === 'integer' || f.type === 'decimal' || f.type === 'float') {
    control = `<input type="number" step="any" name="${name}" value="${esc(v)}"${req}>`;
  } else if (f.type === 'date') {
    control = `<input type="date" name="${name}" value="${esc(String(v).slice(0, 10))}"${req}>`;
  } else if (f.type === 'datetime') {
    control = `<input type="datetime-local" name="${name}" value="${esc(String(v).slice(0, 16))}"${req}>`;
  } else if (isMultiField(name, f) || Array.isArray(v)) {
    control = `<input name="${name}" value="${esc(Array.isArray(v) ? v.join(',') : v)}" placeholder="ids, comma-separated">`;
  } else if (f.type === 'field') {
    // Only reached when the relation is too long for OPTIONS to list (see
    // config/metadata.py) and has no picker of its own. ponytail: give the
    // field a PICKERS entry the day one of them turns up.
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
      body[name] = [...elm.selectedOptions].map(
        (o) => (STR_LIST_FIELDS.has(name) ? o.value : Number(o.value)));
      continue;
    }
    const raw = elm.value.trim();
    if (raw === '') { if (!f.required) continue; body[name] = null; continue; }
    if (isMultiField(name, f) && !(elm instanceof HTMLSelectElement)) {
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
  // A full catalogue is a scroll hunt; typing a few letters of the name is not.
  if (rows.length > 12) makeSearchable(sel, { placeholder: 'Type an item name…' });
}

/* Fill the form's region picker, if it has one, from the jurisdiction tree the
 * app already caches — no second copy of the 774 local governments to keep in
 * step with the server's. Stored as "LGA, State", which is what the column has
 * always held and what the analytics group by.
 * A value already on the record that is not on the list (free text typed
 * before this was a picker, or a place outside Nigeria) is offered as its own
 * row, so opening an old record and saving it cannot quietly rewrite it. */
async function wireRegionField(form, current) {
  const sel = form.querySelector('[data-region]');
  if (!sel) return;
  const places = await placeOptions();
  const states = new Map(places.filter((j) => j.level === 'state').map((j) => [j.id, j.name]));
  const regions = places
    .filter((j) => j.level === 'local' && states.has(j.parent))
    .map((j) => `${j.name}, ${states.get(j.parent)}`)
    .sort((a, b) => a.localeCompare(b));
  const v = String(current.region ?? '').trim();
  if (!regions.length) {
    // No tree seeded: a text box beats a picker whose only row is the value
    // the record already had.
    sel.replaceWith(Object.assign(document.createElement('input'), {
      type: 'text', name: 'region', value: v,
    }));
    return;
  }
  if (v && !regions.includes(v)) regions.unshift(v);
  sel.innerHTML = '<option value=""></option>' + regions.map((r) =>
    `<option value="${esc(r)}"${r === v ? ' selected' : ''}>${esc(r)}</option>`).join('');
  sel.value = v;
  makeSearchable(sel, { placeholder: 'Type a local government or state' });
}

/* Where each related picker gets its rows, and how one reads. The jurisdiction
 * list is the public one: a government seat belongs to no organization, so
 * there is no tenant-scoped list to ask. */
const REL_FIELDS = {
  hmo: ['/api/pharmacy/hmos/', (r) => r.name],
  jurisdiction: ['/api/auth/onboarding/jurisdictions/', placeLabel],
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
      `<option value="${r.id}"${String(r.id) === v ? ' selected' : ''}>${esc(text(r, rows))}</option>`).join('');
    // The scheme list is short enough to read; the jurisdictions are not.
    if (name === 'jurisdiction') {
      makeSearchable(sel, { placeholder: 'Type a state or local government' });
    }
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
    // A searchable picker keeps its value in a hidden input and shows the label
    // in the box beside it, so both have to move together.
    elm.showPick?.(value);
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

/* The headline takings from /analytics/platform/sales/: what every pharmacy in
   the patch sold, for the latest day, month and year the payload carries. The
   rows are one per (area, period), so a period's total is the sum of its rows —
   and with a ?from/to window the latest period in range is not today, so the
   tile names the period it is showing instead of implying one. */
function salesHeadline(data) {
  const tiles = [];
  for (const bucket of ['daily', 'monthly', 'yearly']) {
    const rows = data?.[bucket];
    if (!Array.isArray(rows) || !rows.length) continue;
    const period = rows.reduce((latest, r) => (r.period > latest ? r.period : latest), '');
    const hit = rows.filter((r) => r.period === period);
    const revenue = hit.reduce((t, r) => t + Number(r.revenue || 0), 0);
    const count = hit.reduce((t, r) => t + Number(r.sales || 0), 0);
    tiles.push(`<div class="tile kpi-tile">
      <span class="tile-label">${esc(label(bucket))} sales — ${esc(period)}</span>
      <span class="tile-val">${esc(money(revenue))}</span>
      <span class="tile-label">${esc(fmtVal(count))} sale(s)</span></div>`);
  }
  return tiles.length ? `<div class="tiles">${tiles.join('')}</div>` : '';
}

/* The headline from /analytics/platform/controlled/: what the patch wrote for,
   what it handed over, and what went over the counter with no script behind it.
   by_area rows are one per area, so the patch's total is the sum of its rows.
   Lines and units both, because "50 scripts" and "5,000 tablets" are different
   alarms. */
function controlledHeadline(data) {
  const rows = Array.isArray(data?.by_area) ? data.by_area : [];
  if (!rows.length) return '';
  const sum = (k) => rows.reduce((t, r) => t + Number(r[k] || 0), 0);
  const tiles = [
    ['Prescribed', 'prescribed_units', 'prescribed', 'script line(s)'],
    ['Dispensed', 'dispensed_units', 'dispensed', 'line(s) handed over'],
    ['Sold, no script', 'otc_units', 'otc', 'till line(s), net of returns'],
  ].map(([head, units, lines, note]) => `<div class="tile kpi-tile">
      <span class="tile-label">${esc(head)} (units)</span>
      <span class="tile-val">${esc(fmtVal(sum(units)))}</span>
      <span class="tile-label">${esc(fmtVal(sum(lines)))} ${esc(note)}</span></div>`);
  return `<div class="tiles">${tiles.join('')}</div>`;
}

function statIndex(title, registry, prefix) {
  // The dashboard is rendered inline under the tiles, so no tile for it —
  // the first tile is the first metric (prescribing).
  return `<h2>${esc(title)}</h2><div class="tiles home-tiles">` +
    registry.filter((m) => m.key !== 'dashboard').map((m) => `<a class="tile linktile" href="#${prefix}/${m.key}"><span class="tile-label">${ico('chart')}${esc(m.label)}</span></a>`).join('') +
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
  // The IDSR report carries the 24-hour worklist: one row per case still
  // owed a notification. Those rows carry the case id — the daily summary
  // rows beside them do not — so they open the case, where the button that
  // records the notification lives.
  const rowLink = key === 'idsr' ? (r) => (r.id ? `#/r/case-reports/${r.id}` : null) : null;
  const load = async () => {
    $('#out').innerHTML = '<div class="loading">Loading…</div>';
    try {
      const data = await Api.get(m.path, params());
      // The money report leads with its totals; the tables under it are the grain.
      const headline = key === 'sales' ? salesHeadline
        : key === 'controlled' ? controlledHeadline : null;
      $('#out').innerHTML = (headline ? headline(data) : '')
        + renderData(data, 0, rowLink);
    }
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
  const [summary, pending, billed, dependents] = await Promise.all([
    Api.get('/api/pharmacy/claims/summary/').catch(() => null),
    Api.list('/api/pharmacy/pre-authorizations/',
             { status: 'requested', ordering: '-created_at' }).catch(() => null),
    Api.list('/api/pharmacy/claims/',
             { status: 'submitted', ordering: '-created_at' }).catch(() => null),
    Api.list('/api/pharmacy/dependents/',
             { status: 'pending', ordering: '-created_at' }).catch(() => null),
  ]);
  const kpis = [
    ['Awaiting our answer', pending ? fmtVal(pending.count ?? pending.rows.length) : '—'],
    ['Claims submitted', billed ? fmtVal(billed.count ?? billed.rows.length) : '—'],
    ['Dependents to approve', dependents ? fmtVal(dependents.count ?? dependents.rows.length) : '—'],
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
    ${card('Dependents awaiting approval', dependents, 'pharmacy-dependents')}
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
  const [dash, spikes, sales] = await Promise.all([
    Api.get('/api/analytics/platform/').catch(() => null),
    Api.get('/api/analytics/platform/surveillance/').catch(() => null),
    Api.get('/api/analytics/platform/sales/').catch(() => null),
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
    <h3>What the pharmacies sold <a class="btn ghost" href="#/platform/sales">Details</a></h3>
    ${salesHeadline(sales) || '<p class="muted">No sales recorded yet.</p>'}
    <div class="card"><h3>Outbreak alerts</h3>
      ${alerts.length ? tableHtml(alerts) : '<p class="muted">No spike above threshold.</p>'}</div>
    <h3>Go to</h3>
    <div class="tiles">${SEAT_NAV.government[2].map(([href, icon, title]) =>
      `<a class="tile linktile" href="${href}"><span class="tile-label">${ico(icon)}${esc(title)}</span></a>`).join('')}</div>`);
}

/* ------------------------------------------- independent prescriber */

/* Which facility an independent prescriber is writing under.
 *
 * Their licence covers a state; a prescription belongs to one facility inside
 * it. The list is the server's (/api/tenants/prescribing/) and so is the
 * fence: picking here only sets the header every later call carries, and the
 * write is checked against the state on their row all over again.
 */
async function viewFacility() {
  if (!await ensureChrome()) return;
  if (!isIndependent()) {
    return errorBox(new Error('Independent prescribers only.'));
  }
  spinner();
  let rows;
  try {
    rows = await Api.get('/api/tenants/prescribing/');
  } catch (e) { return errorBox(e); }
  const tile = (r) =>
    `<button type="button" class="tile linktile" data-slug="${esc(r.slug)}" data-name="${esc(r.name)}">
      <span class="tile-label">${ico(r.kind === 'pharmacy' ? 'pill' : 'shield')}${esc(r.name)}</span>
      <span class="muted">${esc(r.kind)}</span></button>`;
  render(`<div class="page-head"><h2>Where are you prescribing?</h2></div>
    <p class="muted">Your licence covers the whole state, but a prescription belongs
      to one facility. Pick the one you are working in — you can change it at any
      time from the badge in the top bar.</p>
    ${Api.tenant ? `<p class="muted">Currently writing under <b>${esc(Api.tenantName || Api.tenant)}</b>.</p>` : ''}
    ${rows.length ? `<div class="tiles">${rows.map(tile).join('')}</div>`
      : `<p class="muted">No facility in your state is open to you yet. Ask the
         platform admin to check the state on your account, and that the facility
         you work with has been approved.</p>`}`);
  for (const b of document.querySelectorAll('[data-slug]')) {
    b.onclick = () => {
      Api.tenant = b.dataset.slug;
      Api.tenantName = b.dataset.name;
      // Reload rather than route: every cached list on the page was read in
      // the scope that just changed.
      location.hash = '#/clinical';
      location.reload();
    };
  }
}

/* ------------------------------------------------------------- pharmacy */

const PHARMACY_ADMIN_ROLES = new Set(['super_admin', 'tenant_admin']);
const PHARMACY_STAFF_ROLES = new Set([...PHARMACY_ADMIN_ROLES, 'pharmacist']);
// A grant on the row counts the same as the admin role here, mirroring
// accounts.permissions.is_pharmacy_admin — the staff gate still runs first.
const isPharmacyAdmin = () => PHARMACY_ADMIN_ROLES.has(ME?.role) || hasPriv('pharmacy_admin');
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
    // Already past its expiry date, not merely close to it: expired stock is
    // still counted as stock on hand until it is written off, which is what
    // makes the valuation above it wrong.
    const expired = expiring.filter((b) => b.expiry_date && b.expiry_date < today);
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
        ${expired.length && isPharmacyAdmin() ? `<div class="actions">
          <button id="write-off-expired" class="btn danger">Write off ${expired.length} expired batch(es)</button></div>` : ''}
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
`);
    if ($('#write-off-expired')) {
      $('#write-off-expired').onclick = async () => {
        if (!confirm(`Take ${expired.length} expired batch(es) off the shelf? Each is written off on its own, and none of it comes back.`)) return;
        try {
          const r = await Api.post('/api/pharmacy/batches/write-off-expired/');
          toast(r?.message || 'Done.');
          viewPharmacy();
        } catch (e) { toast(e.message, true); }
      };
    }
  } catch (e) { errorBox(e); }
}

/* ------------------------------------------------------------------ hmo */

/* The pharmacy's side of the insurance desk: what the schemes have been
   billed over a period, what they still owe, and the two queues that stall
   money — requests the insurer has not answered, and claims nobody has
   submitted yet. The insurer's own seat has its own screen (viewInsurer);
   this one is the counter's.

   The queues are today's work, so they are not filtered: a request left
   unanswered since last month is exactly what this screen is for. The dates
   narrow the money — the summary endpoint takes from/to (config.ranges). */
async function viewHmo() {
  if (!await ensureChrome()) return;
  if (!isPharmacyStaff()) return errorBox(new Error('Pharmacy staff only.'));
  render(`<div class="page-head"><h2>Insurance</h2>
      <a class="btn ghost" href="#/r/pharmacy-claims">All claims</a></div>
    <form id="f" class="toolbar">
      <label>From <input type="date" name="from"></label>
      <label>To <input type="date" name="to"></label>
      <button>Load</button>
    </form>
    <div id="out"><div class="loading">Loading…</div></div>`);
  const load = async () => {
    $('#out').innerHTML = '<div class="loading">Loading…</div>';
    const fd = new FormData($('#f'));
    const range = {};
    for (const k of ['from', 'to']) if (fd.get(k)) range[k] = fd.get(k);
    const [claims, waiting, drafts] = await Promise.all([
      Api.get('/api/pharmacy/claims/summary/', range).catch(() => null),
      Api.list('/api/pharmacy/pre-authorizations/',
               { status: 'requested', ordering: '-created_at' }).catch(() => null),
      Api.list('/api/pharmacy/claims/', { status: 'draft', ordering: '-created_at' }).catch(() => null),
    ]);
    const count = (l) => (l ? fmtVal(l.count ?? l.rows.length) : '—');
    const kpis = [
      ['Awaiting authorisation', count(waiting)],
      ['Claims to submit', count(drafts)],
      ['Schemes billed', claims ? fmtVal(claims.by_hmo.length) : '—'],
      ['Claimed', claims ? money(claims.claimed) : '—'],
      ['Approved', claims ? money(claims.approved) : '—'],
      ['Paid', claims ? money(claims.paid) : '—'],
      ['Owed by insurers', claims ? money(claims.outstanding) : '—'],
    ];
    const queue = (title, list, slug, empty) => `<div class="card"><h3>${esc(title)}</h3>
      ${list?.rows?.length ? tableHtml(list.rows.slice(0, 8), (r) => `#/r/${slug}/${r.id}`)
        : `<p class="muted">${esc(empty)}</p>`}</div>`;
    // The amounts arrive as decimal strings; the chart needs numbers, and a
    // scheme's name is the one label column chartHtml groups the bars by.
    const byScheme = (claims?.by_hmo || []).map((h) => ({
      scheme: h.name,
      claimed: Number(h.claimed) || 0,
      paid: Number(h.paid) || 0,
      outstanding: Number(h.outstanding) || 0,
    }));
    $('#out').innerHTML = `
      <div class="tiles">${kpis.map(([k, v]) =>
        `<div class="tile kpi-tile"><span class="tile-label">${esc(k)}</span><span class="tile-val">${esc(v)}</span></div>`).join('')}</div>
      ${queue('Waiting on the insurer', waiting, 'pharmacy-preauths', 'Nothing awaiting an answer.')}
      ${queue('Claims not submitted yet', drafts, 'pharmacy-claims', 'Nothing left in draft.')}
      <div class="card"><h3>By scheme</h3>
        ${byScheme.length
          ? chartHtml(byScheme, { labelKey: 'scheme', numKeys: ['claimed', 'paid', 'outstanding'] })
          : '<p class="muted">No claims in this period.</p>'}
      </div>
      <h3>Go to</h3>
      <div class="tiles">${hmoLinks().map(([href, icon, title]) =>
        `<a class="tile linktile" href="${href}"><span class="tile-label">${ico(icon)}${esc(title)}</span></a>`).join('')}</div>`;
  };
  $('#f').onsubmit = (e) => { e.preventDefault(); load().catch((err) => errorBox(err)); };
  load().catch((err) => errorBox(err));
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
   but only the insurer's seat and the admin get the buttons. */
function preauthItemsHtml(auth) {
  const items = auth.items || [];
  if (!items.length) return '';
  const decides = answersForInsurer() && auth.status === 'requested';
  // A wrong answer is undone rather than lived with, right up until the
  // clearance is spent on a sale.
  const reopens = answersForInsurer()
    && auth.status !== 'used' && auth.status !== 'cancelled';
  const row = (it) => `<tr>
    <td>${esc(it.item_name || it.item)}</td><td>${it.quantity}</td>
    <td>${money(it.amount)}</td>
    <td>${it.status === 'requested' ? 'Awaiting the insurer'
      : `${esc(it.status)}${it.status === 'approved'
        ? ` · ${it.quantity_approved} · ${money(it.amount_approved)}` : ''}${
        it.reason ? ` · ${esc(it.reason)}` : ''}`}</td>
    ${decides || reopens ? `<td><div class="decide">${it.status !== 'requested'
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
         <button class="btn danger" data-item="${it.id}" data-decide="decline">Decline</button>`}</div></td>` : ''}
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

/* The insurer's answer to one pre-authorization request: given by its own
   seat, or recorded by the admin from a call. Rendered under its detail page —
   the answer is what the pharmacy is later allowed to bill against, so the API
   refuses anyone else. A request already decided has nothing left to record. */
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
  if (!answersForInsurer()) return '';
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
  const own = ME?.role === 'hmo';
  return `<div class="card"><h3>${own ? 'Your answer' : "Record the insurer's answer"}</h3>
    <form id="preauth-decide" class="form-card">
      <label>${own ? 'Authorisation code' : 'Their code'}<input name="code" maxlength="60" autocomplete="off"></label>
      <label>Amount authorised
        <input type="number" name="amount" step="0.01" min="0" value="${esc(auth.amount)}">
        <small class="muted">${own ? 'You' : 'They'} may stand behind less than the ${money(auth.amount)} asked for.</small></label>
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

// The patient's details as a card, in the order they read them. Shown on
// the Profile page; the welcome page shows a summary.
const portalDetails = (me) => Object.fromEntries(
  PORTAL_FIELDS.filter((k) => me[k] !== undefined).map((k) => [k, me[k]])
);

// The welcome banner a patient lands on: their name, a greeting for the time
// of day, and the handful of facts a nurse asks for first. The full record
// lives under Profile.
function portalHeroHtml(me, meds) {
  const h = new Date().getHours();
  const greet = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
  const name = me.full_name || ME.username || 'there';
  const initials = name.split(/\s+/).slice(0, 2).map((w) => w[0] || '').join('').toUpperCase();
  const who = [me.sex === 'M' ? 'Male' : me.sex === 'F' ? 'Female' : me.sex,
    me.age != null ? `${me.age} yrs` : ''].filter(Boolean).join(' · ');
  const stat = (label, v) => `<div class="hero-stat"><span>${esc(label)}</span><strong>${esc(fmtVal(v))}</strong></div>`;
  return `<section class="hero">
    <div class="hero-top">
      <div class="hero-avatar" aria-hidden="true">${esc(initials)}</div>
      <div>
        <p class="hero-greet">${greet},</p>
        <h2 class="hero-name">${esc(name)}</h2>
        <p class="hero-sub">${esc(who)}${who && me.hospital_number ? ' · ' : ''}${me.hospital_number ? 'Hospital No. ' + esc(me.hospital_number) : ''}</p>
      </div>
      <a href="#/profile" class="btn hero-link">View full profile</a>
    </div>
    <div class="hero-stats">
      ${stat('Blood group', me.blood_group)}
      ${stat('Genotype', me.genotype)}
      ${stat('Scheme', me.patient_type_display)}
      ${stat('NHIS number', me.nhis_number)}
      ${stat('Medications collected', meds.length)}
      ${stat('Allergies', me.allergies)}
    </div>
  </section>`;
}

/* The people on the principal's card. A dependent is named here and waits
   on the scheme; its answer shows as the status, and can change later. A
   patient on no scheme has nobody to ask, so the form stays hidden. */
function dependentsHtml(cards, rows) {
  const list = !rows.length
    ? '<p class="muted">Nobody added yet.</p>'
    : `<div class="table-wrap"><table><thead><tr>
        <th>Name</th><th>Relationship</th><th>Scheme</th><th>Status</th><th>Note</th>
        </tr></thead><tbody>${rows.map((r) => `<tr>
        <td>${esc(r.full_name)}</td>
        <td>${esc(label(r.relationship))}</td>
        <td>${esc(r.hmo_name || '—')}</td>
        <td>${cellHtml('status', r.status)}</td>
        <td>${esc(r.status === 'approved' && r.member_number ? 'No. ' + r.member_number : r.reason || '')}</td>
        </tr>`).join('')}</tbody></table></div>`;
  if (!cards.length) {
    return list + '<p class="muted">You are not on a scheme yet, so there is nobody to ask.</p>';
  }
  return `${list}
    <form id="dependent-form" class="form-card">
      <h4>Add a dependent</h4>
      ${cards.length > 1 ? `<label>Under which membership
        <select name="enrollment">${cards.map((c) =>
          `<option value="${c.id}">${esc(c.hmo_name)} · ${esc(c.member_number)}</option>`).join('')}</select></label>` : ''}
      <label>Full name<input name="full_name" maxlength="200" required></label>
      <label>Relationship<select name="relationship">
        <option value="child">Child</option><option value="spouse">Spouse</option>
        <option value="parent">Parent</option><option value="other">Other</option></select></label>
      <label>Sex<select name="sex"><option value="">—</option>
        <option value="M">Male</option><option value="F">Female</option></select></label>
      <label>Date of birth<input name="date_of_birth" type="date"></label>
      <label>Phone (optional)<input name="phone" maxlength="20"></label>
      <button type="submit" class="btn">Send for approval</button>
    </form>`;
}

async function viewPortal() {
  if (!await ensureChrome()) return;
  spinner();
  let me, meds, cards, deps;
  try {
    [me, meds, cards, deps] = await Promise.all([
      Api.get('/api/portal/me/'),
      Api.get('/api/portal/medications/'),
      Api.get('/api/portal/enrollments/').catch(() => []),
      Api.get('/api/portal/dependents/').catch(() => []),
    ]);
  } catch (e) { return errorBox(e); }

  render(`${portalHeroHtml(me, meds)}
    <div class="card"><h3>My medications</h3>${portalMedsHtml(meds)}</div>
    <div class="card"><h3>My dependents</h3>${dependentsHtml(cards, deps)}</div>
    <div class="card"><h3>Where to get them</h3>
      <div class="actions"><button id="find-pharmacies" class="btn">Find pharmacies near me</button></div>
      <div id="pharmacies"></div></div>`);

  const form = $('#dependent-form');
  if (form) form.onsubmit = async (e) => {
    e.preventDefault();
    const body = Object.fromEntries([...new FormData(form)].filter(([, v]) => v !== ''));
    try {
      await Api.post('/api/portal/dependents/', body);
      toast('Sent to the scheme for approval.');
      viewPortal();
    } catch (err) { toast(err.message, true); }
  };
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
  [/^\/scheme-register$/, viewSchemeRegister],
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
  [/^\/facility$/, viewFacility],
  [/^\/portal$/, viewPortal],
  [/^\/insurer$/, viewInsurer],
  [/^\/gov$/, viewGov],
  [/^\/pharmacy$/, viewPharmacy],
  [/^\/hmo$/, viewHmo],
  [/^\/pharmacy\/sell$/, viewSell],
  [/^\/analytics(?:\/([a-z-]+))?$/, (m) => viewAnalytics(ANALYTICS, '/analytics', m[1])],
  [/^\/platform(?:\/([a-z-]+))?$/, (m) => viewAnalytics(platformMetrics(), '/platform', m[1])],
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
$('#nav-toggle').onclick = () => setNav(!navOpen(), true);
// Tapping the page behind the drawer dismisses it; the scrim also swallows
// that tap, so the control under it is not fired by the same press.
$('#nav-scrim').onclick = () => setNav(false, true);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && navOpen()) setNav(false, true);
});
// Widened past the breakpoint the sidebar is static again: drop the open
// state so aria-expanded doesn't claim a drawer that is no longer there.
matchMedia('(max-width: 760px)').addEventListener('change', () => setNav(false));
// Re-picking the page you are already on fires no hashchange, so nothing
// re-renders and the drawer would stay over the page it just took you to.
$('#sidebar').addEventListener('click', (e) => { if (e.target.closest('a')) setNav(false); });
// Click-to-edit cells on a list (``inline`` resources): the cell swaps to a
// number box, Enter/blur PATCHes just that field, Escape puts the old value back.
$('#main').addEventListener('click', (e) => {
  const td = e.target.closest('td.inline-edit');
  if (!td) return;
  e.stopPropagation();  // the row's own click would open the detail page
  if (td.querySelector('input')) return;
  const { slug, id, field } = td.dataset;
  const old = td.textContent;
  const input = document.createElement('input');
  input.type = 'number'; input.step = '0.01'; input.min = '0';
  if (field === 'coverage_percent') input.max = '100';
  input.value = old === '—' ? '' : old;
  td.replaceChildren(input);
  input.focus(); input.select();
  let done = false;
  const finish = async (save) => {
    if (done) return; done = true;
    const val = input.value.trim();
    if (!save || val === (old === '—' ? '' : old)) { td.textContent = old; return; }
    try {
      const r = await Api.patch(rdetail(slug, `${id}/`), { [field]: val === '' ? null : val });
      td.textContent = fmtVal(r[field]);
      toast('Saved.');
    } catch (err) { td.textContent = old; toast(err.message, true); }
  };
  input.onkeydown = (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); finish(true); }
    if (ev.key === 'Escape') finish(false);
  };
  input.onblur = () => finish(true);
}, true);
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
$('#topbar-logout').onclick = async () => { await Api.logout(); ME = null; location.hash = '#/login'; };
route();
Outbox.flush(); // send anything queued from a previous offline session
