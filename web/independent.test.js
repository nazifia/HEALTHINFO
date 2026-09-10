/* Self-check for the independent prescriber's facility pick in app.js.
 * Run: node independent.test.js
 *
 * ponytail: source sliced out of app.js, same as nav.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('const isIndependent = () =>');
const to = src.indexOf('/* Named grants a seat can hold');
assert.ok(from > 0 && to > from, 'independent helpers not found in app.js');

/* The two helpers, with ME and Api handed in the way the app's globals are. */
const helpers = (me, tenant) =>
  new Function('ME', 'Api',
    `${src.slice(from, to)}; return { isIndependent, needsFacility };`
  )(me, { tenant });

const independent = { role: 'doctor', is_independent: true };
const employed = { role: 'doctor', is_independent: false, tenant: 3 };

// No facility picked yet: the picker is the only screen the API will answer.
assert.strictEqual(helpers(independent, '').needsFacility(), true);
// Picked one: they are working, and the badge is the way to change it.
assert.strictEqual(helpers(independent, 'ikeja-clinic').needsFacility(), false);
assert.strictEqual(helpers(independent, 'ikeja-clinic').isIndependent(), true);
// A doctor on a facility's staff never sees any of it.
assert.strictEqual(helpers(employed, 'ikeja-clinic').needsFacility(), false);
assert.strictEqual(helpers(employed, 'ikeja-clinic').isIndependent(), false);
// Signed out, before /api/users/me/ has answered.
assert.strictEqual(helpers(null, '').needsFacility(), false);

/* The redirect ensureChrome makes: everything but the picker and the profile
 * would 403 without a facility, and the profile is where the state on their
 * row reads out. Same literal as app.js — kept in step by the assert below. */
const REDIRECT = /^\/(facility|profile)/;
assert.ok(src.includes(String.raw`/^\/(facility|profile)/.test(here)`),
  'the redirect exemption in ensureChrome has changed');
for (const path of ['/facility', '/profile']) {
  assert.ok(REDIRECT.test(path), `${path} must stay reachable`);
}
for (const path of ['/', '/clinical', '/r/patients', '/platform', '/analytics']) {
  assert.ok(!REDIRECT.test(path), `${path} must send them to the picker`);
}

// The picker's link, route and view have to agree, or the sidebar's front door
// lands on "Page not found".
assert.ok(src.includes('href="#/facility"'), 'no facility link in the sidebar');
assert.ok(src.includes('/facility$/, viewFacility'), 'no /facility route');
assert.ok(src.includes('async function viewFacility()'), 'viewFacility not defined');
assert.ok(src.includes("Api.get('/api/tenants/prescribing/')"),
  'the picker does not read the server list');

// Leaving is not the same act for the two seats that can: the platform admin's
// visit is trailed, a prescriber's pick is not.
assert.ok(src.includes("if (ME?.role === 'super_admin') {"),
  'the leave trail is no longer super-admin only');

console.log('independent.test.js ok');
