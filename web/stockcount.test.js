/* Self-check for the stock-check counting sheet in app.js. No DOM: the builder
 * is a plain function over a plain record. Run with: node stockcount.test.js
 *
 * ponytail: source sliced out of app.js, same as preauth.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('function stockCountHtml');
const to = src.indexOf('async function wireStockCount');
assert.ok(from > 0 && to > from, 'counting sheet not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const { stockCountHtml, countRowsHtml } = new Function('esc',
  `${src.slice(from, to)}; return { stockCountHtml, countRowsHtml };`)(esc);

const items = [
  { id: 7, name: 'Paracetamol 500mg', store: 'retail', quantity_on_hand: 55 },
  { id: 9, name: 'Amoxil <caps>', store: 'retail', quantity_on_hand: 10 },
  { id: 11, name: 'Ciprofloxacin', store: 'retail', quantity_on_hand: 30 },
  { id: 13, name: 'Bulk Saline', store: 'wholesale', quantity_on_hand: 99 },
];
const lines = [
  { item: 7, expected_quantity: 40, actual_quantity: null, notes: '' },
  { item: 9, expected_quantity: 12, actual_quantity: 11, discrepancy: -1, notes: 'one broken' },
];
const check = { status: 'in_progress', store: 'retail', lines };

// Every item in the store gets a row, raised or not; another store's don't.
const rows = countRowsHtml(check, items);
for (const id of [7, 9, 11]) assert.ok(rows.includes(`data-item="${id}"`), `item ${id} has no count box`);
assert.ok(!rows.includes('data-item="13"'), "another store's item is on the sheet");
// A raised line counts against its snapshot; an unraised one against the shelf.
assert.ok(rows.includes('>40<'), 'snapshot expected not shown');
assert.ok(rows.includes('>30<'), 'shelf figure not shown for an unraised item');
assert.ok(rows.includes('value="11"') && rows.includes('>-1<'), 'count or gap lost');
assert.ok(rows.includes('Amoxil &lt;caps&gt;'), 'item name is not escaped');

// An open check always has a sheet, even with no lines raised; a closed one has none.
assert.ok(stockCountHtml({ status: 'pending', lines: [] }).includes('count-rows'));
assert.strictEqual(stockCountHtml({ status: 'completed', lines }), '');
assert.strictEqual(stockCountHtml({ status: 'cancelled', lines }), '');

console.log('stock count sheet: ok');
