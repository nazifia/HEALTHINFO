/* Self-check for the grant helpers and the user form they narrow. No DOM: the
 * functions are sliced out of app.js and run against a stub ME.
 *
 * ponytail: source sliced out of app.js, same as nav.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
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

const grants = slice('const MODULE_PRIVILEGES = {', 'const navGroup =');
const form = slice('function narrowUserFields(fields) {', '/* Repeat the drug fields');

// ME is a module-level global in app.js; the slice reads it off the closure.
const load = (me) => new Function('ME', `${grants}\n${form}
  return { myGrants, hasPriv, myManageableRoles, narrowUserFields };`)(me);

const userFields = () => ({
  role: { choices: ['super_admin', 'tenant_admin', 'doctor', 'pharmacist', 'hmo', 'government', 'public']
    .map((value) => ({ value, display_name: value })) },
  privileges: { child: { choices: [{ value: 'manage_users' }, { value: 'pharmacy_admin' }] } },
  tenant: {}, hmo: {}, jurisdiction: {},
});

// The facility's admin staffs the facility: every role of that module, the
// whole grant catalog, and no organization field — it is pinned to their own.
let api = load({ role: 'tenant_admin', tenant: 3 });
assert.deepStrictEqual(api.myGrants(), ['manage_users', 'pharmacy_admin']);
let fields = userFields();
api.narrowUserFields(fields);
assert.deepStrictEqual(fields.role.choices.map((c) => c.value),
  ['tenant_admin', 'doctor', 'pharmacist', 'hmo', 'public']);
assert.strictEqual(fields.tenant, undefined);
assert.strictEqual(fields.jurisdiction, undefined);
assert.ok(fields.hmo);                       // they mint their insurer's seat

// A pharmacist trusted with the user list passes on that one grant, and cannot
// offer the role that would let someone take the trust back.
api = load({ role: 'pharmacist', tenant: 3, privileges: ['manage_users'] });
assert.deepStrictEqual(api.myGrants(), ['manage_users']);
assert.strictEqual(api.hasPriv('pharmacy_admin'), false);
fields = userFields();
api.narrowUserFields(fields);
assert.ok(!fields.role.choices.some((c) => c.value === 'tenant_admin'));
assert.deepStrictEqual(fields.privileges.child.choices.map((c) => c.value), ['manage_users']);

// An insurer's admin staffs its own desk: one role, no scheme field (pinned),
// no jurisdiction.
api = load({ role: 'hmo', tenant: 3, hmo: 7, is_admin: true });
fields = userFields();
api.narrowUserFields(fields);
assert.deepStrictEqual(fields.role.choices.map((c) => c.value), ['hmo']);
assert.strictEqual(fields.hmo, undefined);
assert.strictEqual(fields.jurisdiction, undefined);

// A health authority's admin keeps the jurisdiction field: they may seat
// someone on a smaller patch inside their own. The money grant is not theirs
// to hold, so it is not offered.
api = load({ role: 'government', jurisdiction: 2, is_admin: true });
assert.deepStrictEqual(api.myGrants(), ['manage_users']);
fields = userFields();
api.narrowUserFields(fields);
assert.deepStrictEqual(fields.role.choices.map((c) => c.value), ['government']);
assert.ok(fields.jurisdiction);
assert.deepStrictEqual(fields.privileges.child.choices.map((c) => c.value), ['manage_users']);

// A seat with no grant of its own is offered no privileges field at all.
api = load({ role: 'pharmacist', tenant: 3 });
fields = userFields();
api.narrowUserFields(fields);
assert.strictEqual(fields.privileges, undefined);

// The platform admin belongs to no module and is narrowed by nothing.
api = load({ role: 'super_admin', tenant: null });
fields = userFields();
api.narrowUserFields(fields);
assert.strictEqual(fields.role.choices.length, 7);
assert.ok(fields.tenant);

console.log('privileges.test.js ok');
