/* Self-check for the seat routing in app.js: which dashboard each role lands
 * on, and what its sidebar offers. Run with: node dashboards.test.js
 *
 * ponytail: source sliced out of app.js, same as portal.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const slice = (from, to) => {
  const a = src.indexOf(from);
  const b = src.indexOf(to);
  assert.ok(a > 0 && b > a, `block not found in app.js: ${from}`);
  return src.slice(a, b);
};

const load = (code, ret, scope) => new Function(
  ...Object.keys(scope), `${code}; return ${ret};`)(...Object.values(scope));

const CLINICAL_ROLES = new Set(['doctor', 'nurse', 'midwife', 'chew']);
const SEAT_NAV = load(slice('const SEAT_NAV', 'const seatLink'), 'SEAT_NAV',
  { esc: String, ico: () => '' });

// Every role gets its own front door; only the seats that run an organization
// (tenant admin, and a super-admin who opened one) share the generic home.
const homeHash = (role, tenant) => load(
  slice('const homeHash = (role)', 'function route()'),
  `homeHash(${JSON.stringify(role)})`, { Api: { tenant }, CLINICAL_ROLES });

assert.strictEqual(homeHash('super_admin', ''), '#/platform');
assert.strictEqual(homeHash('super_admin', 'ade'), '#/');
assert.strictEqual(homeHash('public', 'ade'), '#/portal');
assert.strictEqual(homeHash('hmo', 'ade'), '#/insurer');
assert.strictEqual(homeHash('government', ''), '#/gov');
assert.strictEqual(homeHash('pharmacist', 'ade'), '#/pharmacy');
for (const r of ['doctor', 'nurse', 'midwife', 'chew']) {
  assert.strictEqual(homeHash(r, 'ade'), '#/clinical', `${r} lands off the ward`);
}
assert.strictEqual(homeHash('tenant_admin', 'ade'), '#/');

// A seat's dashboard is the first thing its sidebar points at, and every link
// under it is a route the app actually has.
const routes = slice('const routes = [', 'const homeHash');
for (const [role, [home, , links]] of Object.entries(SEAT_NAV)) {
  assert.strictEqual(homeHash(role, ''), home, `${role} lands off its dashboard`);
  assert.ok(links.length, `${role} has no links`);
  for (const [href] of links) {
    const top = href.split('/')[1];
    assert.ok(routes.includes(`\/${top}`) || src.includes(`'${top}':`),
      `${role} links to a route the app has not got: ${href}`);
  }
}

// The health authority's desk is surveillance and trade, not clinical service.
const govHrefs = SEAT_NAV.government[2].map(([h]) => h).join(' ');
const platformFor = (role) => load(
  slice('const PLATFORM = [', '/* The trading reports'),
  'platformMetrics().map((m) => m.key)', { ME: { role } });
for (const shut of ['labs', 'immunizations', 'vitals', 'chw', 'facility', 'appointments']) {
  assert.ok(!govHrefs.includes(shut), `government sidebar offers ${shut}`);
  assert.ok(!platformFor('government').includes(shut), `government metrics offer ${shut}`);
  assert.ok(platformFor('super_admin').includes(shut), `super admin lost ${shut}`);
}

// An insurer never gets the pharmacy's own screens in their sidebar.
const insurerHrefs = SEAT_NAV.hmo[2].map(([h]) => h).join(' ');
for (const shut of ['pharmacy-items', 'pharmacy-sales', 'patients', 'users']) {
  assert.ok(!insurerHrefs.includes(shut), `insurer sidebar offers ${shut}`);
}

console.log('dashboards: ok');
