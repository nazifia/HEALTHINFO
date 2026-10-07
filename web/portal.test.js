/* Self-check for the patient portal's table builders in app.js. No DOM: the
 * block is plain functions over plain rows. Run with: node portal.test.js
 *
 * ponytail: source sliced out of app.js, same as columns.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('function portalMedsHtml');
const to = src.indexOf('// What a patient may change');
assert.ok(from > 0 && to > from, 'portal block not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const cellHtml = (k, v) => `<span class="pill">${esc(v)}</span>`;
const fmtVal = (v) => (v == null || v === '' ? '—' : String(v));
const label = (k) => k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
const load = new Function('esc', 'cellHtml', 'fmtVal', 'label',
  `${src.slice(from, to)};
   return { portalMedsHtml };`);
const { portalMedsHtml } = load(esc, cellHtml, fmtVal, label);

const meds = portalMedsHtml([
  { medication: 7, medication_name: 'Amoxicillin', dose: '500 mg',
    frequency: 'twice daily', duration_days: 5, status: 'dispensed' },
]);
assert.ok(meds.includes('Amoxicillin'));
// The list is dispensed drugs only, so empty means nothing collected.
assert.ok(portalMedsHtml([]).includes('not collected any medication'));

console.log('portal: ok');
