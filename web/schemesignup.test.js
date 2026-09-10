/* Self-check for the scheme sign-up screen in app.js. No DOM beyond FormData,
 * which node has: the pieces worth checking are plain over plain values.
 * Run with: node schemesignup.test.js
 *
 * ponytail: source sliced out of app.js, same as scheme.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');

// The screen is only reachable if the route and the way in are both wired.
assert.ok(/scheme-register\$\/, viewSchemeRegister/.test(src),
  'scheme-register route missing');
assert.ok(/res\.signUp && ME\?\.role === 'super_admin'/.test(src),
  'no way in from the list screens');

const from = src.indexOf('function schemeSignUpBody(');
const to = src.indexOf('async function viewProfile()');
assert.ok(from > 0 && to > from, 'sign-up helpers not found in app.js');
const [schemeSignUpBody, schemeSignUpProblem, flattenSchemeErrors] =
  new Function(`${src.slice(from, to)};
    return [schemeSignUpBody, schemeSignUpProblem, flattenSchemeErrors];`)();

const form = (fields) => {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.set(k, v);
  return fd;
};

const filled = {
  tenant: '7', name: '  AXA Mansard ', code: ' AXA ',
  coverage_percent: '80.00', preauth_threshold: '5000',
  auto_submit_claims: 'on',
  admin_phone: ' 08031234567 ', admin_name: ' Ada ',
  admin_password: 's3curepass99',
};

// The scheme half rides nested (it is the ordinary insurer serializer); the
// admin half sits beside it.
const body = schemeSignUpBody(form(filled));
assert.strictEqual(body.tenant, '7');
assert.deepStrictEqual(body.scheme, {
  name: 'AXA Mansard', code: 'AXA', contact: '', email: '',
  coverage_percent: '80.00', preauth_threshold: '5000',
  auto_submit_claims: true,
});
assert.strictEqual(body.admin_phone, '08031234567');
assert.strictEqual(body.admin_name, 'Ada');

// Left alone, the two decimals are the scheme's defaults — a blank threshold
// is 0 ("never ask first"), not no cover.
const bare = schemeSignUpBody(form({
  tenant: '1', name: 'Hygeia', coverage_percent: '  ', preauth_threshold: '  ',
  admin_phone: '08031234568', admin_password: 's3curepass99',
}));
assert.strictEqual(bare.scheme.preauth_threshold, '0');
assert.strictEqual(bare.scheme.coverage_percent, '100');
assert.strictEqual(bare.scheme.auto_submit_claims, false);

// A password is sent as typed. Trimming one changes it.
assert.strictEqual(
  schemeSignUpBody(form({ ...filled, admin_password: ' spaced pass 99 ' })).admin_password,
  ' spaced pass 99 ');

// What the round trip is saved for.
assert.strictEqual(schemeSignUpProblem(body), null);
for (const [field, says] of [
  ['tenant', /organization/],
  ['name', /Name the scheme/],
  ['admin_phone', /phone number/],
]) {
  const short = schemeSignUpBody(form({ ...filled, [field]: '' }));
  assert.match(schemeSignUpProblem(short), says, `${field} passed unchecked`);
}
assert.match(
  schemeSignUpProblem(schemeSignUpBody(form({ ...filled, admin_password: 'short' }))),
  /8 characters/);

// The scheme's own errors arrive nested; the form is flat, so they are lifted
// to sit beside the admin's.
assert.deepStrictEqual(
  flattenSchemeErrors({ scheme: { name: ['Already taken.'] }, admin_phone: ['Taken.'] }),
  { name: ['Already taken.'], admin_phone: ['Taken.'] });

// A non-field error on the nested serializer comes back as a list, not a dict:
// there is no field to lift it onto, so it is left where it is.
const listed = { scheme: ['Invalid data.'] };
assert.deepStrictEqual(flattenSchemeErrors(listed), listed);

// Nothing to lift, and nothing at all, both pass straight through.
assert.deepStrictEqual(flattenSchemeErrors({ tenant: ['Required.'] }), { tenant: ['Required.'] });
assert.strictEqual(flattenSchemeErrors(null), null);

console.log('schemesignup.test.js ok');
