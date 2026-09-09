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
// placeLabel and makeSearchable live above this slice; both are checked in
// places.test.js. Here they only have to exist.
const placeLabel = (j, all) => `${j.name} · ${j.level}`;
let searchable = [];
const makeSearchable = (sel) => { searchable.push(sel); };
// The jurisdiction tree the region picker reads. Two states, three locals, and
// one local whose state is missing — that last one must not become a region.
let places = [
  { id: 1, name: 'Lagos', level: 'state', parent: null },
  { id: 2, name: 'Kwara', level: 'state', parent: null },
  { id: 3, name: 'Ikeja', level: 'local', parent: 1 },
  { id: 4, name: 'Apapa', level: 'local', parent: 1 },
  { id: 5, name: 'Offa', level: 'local', parent: 2 },
  { id: 6, name: 'Nowhere', level: 'local', parent: 99 },
];
const placeOptions = async () => places;
global.document = { createElement: () => ({ tag: 'input' }) };
const load = () => new Function('Api', 'esc', 'ME', 'money', 'placeLabel', 'makeSearchable', 'placeOptions', 'document',
  `${src.slice(from, to)}; return { allItems, wireItemField, wireRelFields, wireRegionField };`)(Api, esc, ME, money, placeLabel, makeSearchable, placeOptions, global.document);

(async () => {
  let { allItems, wireItemField, wireRelFields, wireRegionField } = load();
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

  /* ---- the region picker ---------------------------------------------- */

  const regionForm = (sel) => ({ querySelector: (q) => (q === '[data-region]' ? sel : null) });
  const region = async (current) => {
    const sel = { innerHTML: '', value: '', replaceWith(n) { this.replaced = n; } };
    searchable = [];
    await wireRegionField(regionForm(sel), current);
    return sel;
  };

  // Every local government reads as "LGA, State", sorted, with a blank to
  // leave the field on.
  let rsel = await region({});
  assert.ok(rsel.innerHTML.startsWith('<option value=""></option>'));
  assert.deepStrictEqual(rsel.innerHTML.match(/value="[^"]*"/g),
    ['value=""', 'value="Apapa, Lagos"', 'value="Ikeja, Lagos"', 'value="Offa, Kwara"']);
  // A local whose state is not in the tree is not a region anyone can pick.
  assert.ok(!rsel.innerHTML.includes('Nowhere'), 'an orphan local was offered');
  // The picker is handed the filled select, not the empty one.
  assert.deepStrictEqual(searchable, [rsel], 'the region select was not made searchable');

  // A value already on the record is selected, not re-offered.
  rsel = await region({ region: 'Ikeja, Lagos' });
  assert.ok(/<option value="Ikeja, Lagos" selected>/.test(rsel.innerHTML));
  assert.strictEqual((rsel.innerHTML.match(/Ikeja, Lagos/g) || []).length, 2, 'the row was duplicated');

  // Free text typed before this was a picker survives being opened and saved.
  rsel = await region({ region: 'Ikeja LGA' });
  assert.ok(/<option value="Ikeja LGA" selected>/.test(rsel.innerHTML),
            'an off-list value was dropped from the record');
  assert.ok(rsel.innerHTML.indexOf('Ikeja LGA') < rsel.innerHTML.indexOf('Apapa'),
            'the record value was buried down the list');

  // No tree seeded: a text box beats a picker with nothing in it.
  places = [];
  rsel = await region({ region: 'Somewhere' });
  assert.strictEqual(rsel.replaced.name, 'region', 'the field lost its name');
  assert.strictEqual(rsel.replaced.value, 'Somewhere');
  assert.strictEqual(rsel.replaced.type, 'text');
  assert.deepStrictEqual(searchable, [], 'an empty list was still made searchable');

  console.log('itemfield.test.js ok');
})();
