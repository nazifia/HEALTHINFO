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
  return { myGrants, hasPriv, myManageableRoles, narrowUserFields, applyDefaultGrants };`)(me);

const userFields = () => ({
  role: { choices: ['super_admin', 'tenant_admin', 'doctor', 'pharmacist', 'hmo', 'government', 'public']
    .map((value) => ({ value, display_name: value })) },
  privileges: { child: { choices: [{ value: 'manage_users' }, { value: 'pharmacy_admin' }, { value: 'dispense' }] } },
  tenant: {}, hmo: {}, jurisdiction: {}, license_number: {},
});

// The facility's admin staffs the facility: every role of that module, the
// whole grant catalog, and no organization field — it is pinned to their own.
let api = load({ role: 'tenant_admin', tenant: 3 });
assert.deepStrictEqual(api.myGrants(), ['manage_users', 'pharmacy_admin', 'dispense']);
let fields = userFields();
api.narrowUserFields(fields);
assert.deepStrictEqual(fields.role.choices.map((c) => c.value),
  ['tenant_admin', 'doctor', 'pharmacist', 'hmo', 'public']);
assert.strictEqual(fields.tenant, undefined);
assert.strictEqual(fields.jurisdiction, undefined);
assert.ok(fields.hmo);                       // they mint their insurer's seat
assert.ok(fields.license_number);            // their doctors sign in with one

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
assert.strictEqual(fields.license_number, undefined);   // no clinician sits on a desk

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
assert.deepStrictEqual(api.myGrants(), ['manage_users', 'pharmacy_admin', 'dispense', 'decide_claims', 'edit_tariff']);

// Still the platform admin when their own row happens to carry a tenant.
api = load({ role: 'super_admin', tenant: 1 });
assert.strictEqual(api.myManageableRoles(), null);
fields = userFields();
api.narrowUserFields(fields);
assert.strictEqual(fields.role.choices.length, 7);
assert.ok(fields.tenant && fields.jurisdiction && fields.hmo);

// A new seat's role ticks its default grants in the select; others clear it.
const select = { options: ['decide_claims', 'edit_tariff', 'manage_users'].map((value) => ({ value, selected: false })) };
const picked = () => select.options.filter((o) => o.selected).map((o) => o.value);
api.applyDefaultGrants(select, 'hmo');
assert.deepStrictEqual(picked(), ['decide_claims', 'edit_tariff']);
api.applyDefaultGrants(select, 'pharmacist');
assert.deepStrictEqual(picked(), []);
api.applyDefaultGrants(null, 'hmo');   // no select for a seat that holds nothing to pass on

// The user page offers Revoke on grants the writer holds and Grant for the rest
// of what they hold; an admin seat (implicit catalog) or oneself gets nothing.
const panel = slice('const userModule =', 'function wireUserGrants');
const grantsFor = (me, user) => new Function('ME', 'esc', 'label', `${grants}
${panel}
  return userGrantsHtml;`)(me, (x) => x, (x) => x)(user);
const boss = { id: 1, role: 'tenant_admin', tenant: 1 };
const nurse = { id: 2, role: 'nurse', tenant: 1, privileges: ['pharmacy_admin', 'decide_claims'] };
let html = grantsFor(boss, nurse);
assert.ok(html.includes('data-revoke="pharmacy_admin"'));
assert.ok(!html.includes('decide_claims'), 'a scheme grant on a facility seat counts for nothing');
assert.ok(html.includes('<option value="dispense">') && !html.includes('<option value="pharmacy_admin">'));
assert.strictEqual(grantsFor(boss, { id: 3, role: 'tenant_admin' }), '');
assert.strictEqual(grantsFor(boss, { ...nurse, id: 1 }), '');
const limited = { id: 4, role: 'pharmacist', tenant: 1, privileges: ['manage_users'] };
html = grantsFor(limited, nurse);
assert.ok(!html.includes('data-revoke'), 'cannot revoke what you do not hold');

console.log('privileges.test.js ok');
