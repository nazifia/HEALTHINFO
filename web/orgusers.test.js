/* Self-check for the organization filters on the user list and the helper the
 * user screens are gated by. No DOM: the blocks are sliced out of app.js and
 * run against stubs.
 *
 * ponytail: source sliced out of app.js, same as privileges.test.js — the app
 * is loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const slice = (start, end) => {
  const from = src.indexOf(start);
  const to = src.indexOf(end);
  assert.ok(from > 0 && to > from, `block not found: ${start}`);
  return src.slice(from, to);
};

const filters = slice('const ORG_FILTERS = [', 'const RESOURCES = {');
const load = (platform) => new Function('isPlatformScope', 'placeLabel',
  `${filters}\nreturn ORG_FILTERS;`)(() => platform, (j, all) => `${j.name}/${all.length}`);

// The pickers are the platform admin's: every other seat's list is pinned to
// its own portal by the API, so three selects with one answer each are noise.
assert.ok(load(true).every((f) => f.when()));
assert.ok(load(false).every((f) => !f.when()));
assert.deepStrictEqual(load(true).map((f) => f.param), ['tenant', 'hmo', 'jurisdiction']);

// A local government is labelled by its state, which is another row of the
// same list — so the option text is handed the whole list, not just its row.
const place = load(true).find((f) => f.param === 'jurisdiction');
assert.strictEqual(place.text({ name: 'Ifelodun' }, [1, 2, 3]), 'Ifelodun/3');
assert.ok(src.includes('f.text(r, options[i])'), 'option text not given the list');

// Every user screen is the same endpoint, so the write gate and the form
// narrowing must go by that and not by the slug that reached them.
const isUserRes = new Function('RESOURCES', `${slice('const isUserRes =', 'function narrowUserFields')}
  return isUserRes;`)({ users: {}, 'scheme-users': { path: 'users' }, patients: {} });
assert.ok(isUserRes('users'));
assert.ok(isUserRes('scheme-users'));
assert.ok(!isUserRes('patients'));
assert.ok(!isUserRes('nope'));

// A section's user list is pinned to the seats that section is about, and the
// pin follows through to the row it creates.
for (const slug of ['scheme-users', 'authority-users']) {
  const line = src.split('\n').find((l) => l.includes(`'${slug}':`));
  assert.ok(line, `${slug} not registered`);
  assert.ok(line.includes("path: 'users'"), line.trim());
  // Cross-tenant by nature: a tenant admin's own list already holds their
  // people, and the API would refuse them these anyway.
  assert.ok(line.includes('superOnly: true'), line.trim());
}
assert.ok(src.includes('const query = { page: st.page, ...res.query };'), 'pinned query not sent');
assert.ok(src.includes("res.query ? '?' + new URLSearchParams(res.query)"), 'New button drops the pin');

console.log('orgusers.test.js ok');
