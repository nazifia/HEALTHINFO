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
const to = src.indexOf('function wireStockCount');
assert.ok(from > 0 && to > from, 'counting sheet not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const stockCountHtml = new Function('esc',
  `${src.slice(from, to)}; return stockCountHtml;`)(esc);

const lines = [
  { item: 7, item_name: 'Paracetamol 500mg', expected_quantity: 40, actual_quantity: null, notes: '' },
  { item: 9, item_name: 'Amoxil <caps>', expected_quantity: 12, actual_quantity: 11, notes: 'one broken' },
];

// A check still open shows every line, with what the shelf said beside it.
const open = stockCountHtml({ status: 'in_progress', lines });
assert.ok(open.includes('data-item="7"'), 'uncounted line is missing an input');
assert.ok(open.includes('value="11"'), 'a counted line keeps the number already entered');
assert.ok(open.includes('>40<'), 'expected quantity is not shown');
assert.ok(open.includes('Amoxil &lt;caps&gt;'), 'item name is not escaped');

// A count with nothing on it, and one that is over, have no sheet to fill in.
assert.strictEqual(stockCountHtml({ status: 'pending', lines: [] }), '');
assert.strictEqual(stockCountHtml({ status: 'completed', lines }), '');
assert.strictEqual(stockCountHtml({ status: 'cancelled', lines }), '');

console.log('stock count sheet: ok');
