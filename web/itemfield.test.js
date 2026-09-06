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
const Api = {
  list: async (path, params) => {
    calls.push(params.page);
    if (fail) throw new Error('offline');
    // Two pages, so a catalogue past the first page is still pickable.
    return params.page === 1
      ? { rows: [{ id: 1, name: 'Coartem' }], next: 'p2' }
      : { rows: [{ id: 2, name: 'Panadol <500mg>' }], next: null };
  },
};
const load = () => new Function('Api', 'esc',
  `${src.slice(from, to)}; return { allItems, wireItemField };`)(Api, esc);

(async () => {
  let { allItems, wireItemField } = load();
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
  ({ allItems, wireItemField } = load());
  fail = true;
  await wireItemField(form, null);
  assert.ok(sel.innerHTML.includes('unavailable'), 'failure not reported');
  fail = false;
  await wireItemField(form, null);
  assert.ok(sel.innerHTML.includes('>Coartem<'), 'failure was cached');

  console.log('itemfield.test.js ok');
})();
