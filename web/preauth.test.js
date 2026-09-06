/* Self-check for the pre-authorization decision card in app.js. No DOM: the
 * builder is a plain function over a plain record. Run with: node preauth.test.js
 *
 * ponytail: source sliced out of app.js, same as portal.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('function preauthDecisionHtml');
const to = src.indexOf('/* Receiving a delivery against a purchase order line.');
assert.ok(from > 0 && to > from, 'pre-auth decision block not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (v) => '₦' + Number(v || 0).toFixed(2);
let admin = true;
const load = new Function('esc', 'money', 'isPharmacyAdmin',
  `${src.slice(from, to)}; return preauthDecisionHtml;`);
const preauthDecisionHtml = load(esc, money, () => admin);

const requested = { status: 'requested', amount: '48000.00' };

// The admin sees every field the insurer's answer needs, and what was asked
// for is the default — they routinely stand behind less.
const html = preauthDecisionHtml(requested);
for (const name of ['code', 'amount', 'expires_on', 'reason']) {
  assert.ok(html.includes(`name="${name}"`), `${name} field missing`);
}
assert.ok(html.includes('value="48000.00"'), 'amount asked for is not the default');
assert.ok(html.includes('data-decide="approve"') && html.includes('data-decide="decline"'));

// Counter staff may raise a request but never answer one — the API refuses
// them, so a form that always fails is not offered.
admin = false;
assert.strictEqual(preauthDecisionHtml(requested), '');

// Nothing left to record once the insurer has answered, or once the request
// was withdrawn.
admin = true;
for (const status of ['approved', 'declined', 'used', 'cancelled']) {
  assert.strictEqual(preauthDecisionHtml({ ...requested, status }), '',
    `decision form still offered on a ${status} request`);
}

console.log('preauth.test.js ok');
