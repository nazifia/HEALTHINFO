/* Self-check for the pre-authorization decision card in app.js. No DOM: the
 * builder is a plain function over a plain record. Run with: node preauth.test.js
 *
 * ponytail: source sliced out of app.js, same as portal.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('function preauthItemsHtml');
const to = src.indexOf('/* Receiving a delivery against a purchase order line.');
assert.ok(from > 0 && to > from, 'pre-auth decision block not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (v) => '₦' + Number(v || 0).toFixed(2);
let admin = true;
let ME = { role: 'tenant_admin' };
const load = new Function('esc', 'money', 'isPharmacyAdmin', 'ME',
  `const answersForInsurer = () => isPharmacyAdmin() || (ME?.role === 'hmo' && !!ME?.hmo);
   ${src.slice(from, to)}; return { preauthDecisionHtml, preauthItemsHtml };`);
const { preauthDecisionHtml, preauthItemsHtml } = load(esc, money, () => admin, ME);

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

// The insurer's own seat answers its requests itself, in its own voice; a
// seat with no scheme set answers for nothing.
ME.role = 'hmo'; ME.hmo = 3;
assert.ok(preauthDecisionHtml(requested).includes('Your answer'),
  'the insurer seat is not offered the answer form');
ME.hmo = null;
assert.strictEqual(preauthDecisionHtml(requested), '', 'a scheme-less seat is offered the form');
ME.role = 'tenant_admin';

// Nothing left to record once the request was spent or withdrawn.
admin = true;
for (const status of ['used', 'cancelled']) {
  assert.strictEqual(preauthDecisionHtml({ ...requested, status }), '',
    `decision form still offered on a ${status} request`);
}

// An answer already recorded is withdrawn instead - the amount is typed by
// hand and a wrong one would otherwise stand for good.
for (const status of ['approved', 'declined']) {
  const undo = preauthDecisionHtml({ ...requested, status });
  assert.ok(undo.includes('data-decide="reopen"'),
    `no way back from a ${status} request`);
  assert.ok(!undo.includes('data-decide="approve"'),
    `a ${status} request is still offered a fresh answer`);
}
admin = false;
assert.strictEqual(preauthDecisionHtml({ ...requested, status: 'approved' }), '',
  'counter staff are offered the undo');
admin = true;

// An itemised request is answered drug by drug, so the whole-request form
// stands down and the medications carry the buttons instead.
const itemised = {
  ...requested,
  items: [
    { id: 1, item_name: 'Paracetamol', quantity: 10, amount: '125.00', status: 'requested' },
    { id: 2, item_name: 'Vitamin C', quantity: 2, amount: '200.00', status: 'declined',
      amount_approved: '0.00', reason: 'Not covered' },
  ],
};
assert.strictEqual(preauthDecisionHtml(itemised), '',
  'whole-request form still offered on an itemised request');
const items = preauthItemsHtml(itemised);
assert.ok(items.includes('data-item="1"') && items.includes('data-decide="decline"'));
// The insurer may clear less than was asked for, so the quantity is editable
// and capped at what was ordered.
assert.ok(items.includes('name="quantity"') && items.includes('max="10"'),
  'no quantity input capped at the ordered quantity');
// A medication already answered is not decided twice - it is reopened, which
// is the only way back from a figure typed wrong.
assert.ok(items.includes('data-item="2" data-decide="reopen"'),
  'a decided medication cannot be reopened');
assert.ok(!items.includes('data-item="2" data-decide="approve"'),
  'a decided medication is still offered a fresh answer');
assert.ok(items.includes('Not covered'), 'the refusal reason is not shown');

// The reopen stays on offer once the request has settled, and stops the moment
// the clearance is spent.
const settled = preauthItemsHtml({ ...itemised, status: 'approved' });
assert.ok(settled.includes('data-decide="reopen"'),
  'a settled request cannot be unpicked');
assert.ok(!preauthItemsHtml({ ...itemised, status: 'used' })
  .includes('data-decide='), 'a spent clearance is still editable');

// Staff read the answers - that is the feedback they dispense on - but the
// API refuses them a decision, so they get no buttons.
admin = false;
const readOnly = preauthItemsHtml(itemised);
assert.ok(readOnly.includes('Vitamin C') && !readOnly.includes('data-item='));
admin = true;

// A lump-sum request has no medication table at all.
assert.strictEqual(preauthItemsHtml(requested), '');

console.log('preauth.test.js ok');
