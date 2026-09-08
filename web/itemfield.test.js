/* Self-check for the catalogue cache and the `item` field it fills in app.js.
 * No DOM: the select is a stub with the one property the code writes.
 * Run with: node itemfield.test.js
 *
 * ponytail: source sliced out of app.js, same as portal.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('let itemCache;');
const to = src.indexOf("/* Fields the patient's own record already answers,");
assert.ok(from > 0 && to > from, 'item field block not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let calls = [];
let fail = false;
let relRows = [];   // what /api/pharmacy/hmos/ answers with
const Api = {
  list: async (path, params) => {
    // wireRelFields asks for a whole list with no paging; the catalogue pages.
    if (!params) { calls.push(path); return { rows: relRows }; }
    calls.push(params.page);
    if (fail) throw new Error('offline');
    // Two pages, so a catalogue past the first page is still pickable.
    return params.page === 1
      ? { rows: [{ id: 1, name: 'Coartem' }], next: 'p2' }
      : { rows: [{ id: 2, name: 'Panadol <500mg>' }], next: null };
  },
  get: async (path) => {
    calls.push(path);
    return [{ id: 3, name: 'Amoxil', unit_price: '1200.00' }];
  },
};
// ME decides which catalogue the picker asks for, so the seat is part of the
// stub: staff read the stock list, an insurer reads names and shelf prices.
let ME = { role: 'pharmacist' };
const money = (v) => '₦' + Number(v || 0).toFixed(2);
const load = () => new Function('Api', 'esc', 'ME', 'money',
  `${src.slice(from, to)}; return { allItems, wireItemField, wireRelFields };`)(Api, esc, ME, money);

(async () => {
  let { allItems, wireItemField, wireRelFields } = load();
  const sel = { innerHTML: '' };
  const form = { querySelector: () => sel };

  await wireItemField(form, 2);
  assert.deepStrictEqual(calls, [1, 2], 'paging stopped early or ran on');
  assert.ok(sel.innerHTML.includes('>Coartem<'), 'first page missing');
  assert.ok(sel.innerHTML.includes('&lt;500mg&gt;'), 'option label not escaped');
  assert.ok(/<option value="2" selected>/.test(sel.innerHTML), 'current item not selected');
  assert.ok(sel.innerHTML.startsWith('<option value=""></option>'), 'no blank option');

  // Fetched once per session: a second field reuses the rows.
  calls = [];
  await wireItemField(form, null);
  assert.deepStrictEqual(calls, [], 'catalogue re-fetched');

  // A failed fetch says so and is not cached, or the picker stays empty for
  // the rest of the session.
  ({ allItems, wireItemField, wireRelFields } = load());
  fail = true;
  await wireItemField(form, null);
  assert.ok(sel.innerHTML.includes('unavailable'), 'failure not reported');
  fail = false;
  await wireItemField(form, null);
  assert.ok(sel.innerHTML.includes('>Coartem<'), 'failure was cached');

  // The insurer seat is refused the stock list, so its picker asks the price
  // list for the drugs it may price — one call, no paging.
  ME = { role: 'hmo', hmo: 4 };
  ({ allItems, wireItemField } = load());
  calls = [];
  await wireItemField(form, 3);
  assert.deepStrictEqual(calls, ['/api/pharmacy/item-rules/items/'],
                         'insurer read the staff catalogue');
  // The shelf price rides in the label, so a tariff is set against a real
  // number rather than from memory.
  assert.ok(/<option value="3" selected>Amoxil · ₦1200\.00</.test(sel.innerHTML),
            'shelf price missing from the option label');

  // An insurer's scheme list is scoped to its own scheme: one choice, so the
  // field fills itself and offers no blank to leave it on.
  const relSel = { innerHTML: '' };
  const relForm = { querySelector: (q) => (q.includes('hmo') ? relSel : null) };
  relRows = [{ id: 4, name: 'Reliance HMO' }];
  await wireRelFields(relForm, {});
  assert.ok(!relSel.innerHTML.includes('<option value=""></option>'),
            'a single-choice picker still offered a blank');
  assert.ok(/<option value="4" selected>Reliance HMO</.test(relSel.innerHTML));

  // Several schemes stay a real choice: nothing is picked for the user.
  relRows = [{ id: 4, name: 'Reliance HMO' }, { id: 5, name: 'NHIA' }];
  await wireRelFields(relForm, {});
  assert.ok(relSel.innerHTML.startsWith('<option value=""></option>'));
  assert.ok(!relSel.innerHTML.includes('selected'), 'a choice was made for the user');

  console.log('itemfield.test.js ok');
})();
