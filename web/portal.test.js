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
const to = src.indexOf('async function loadPharmacies');
assert.ok(from > 0 && to > from, 'portal block not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const cellHtml = (k, v) => `<span class="pill">${esc(v)}</span>`;
const load = new Function('esc', 'cellHtml',
  `${src.slice(from, to)}; return { portalMedsHtml, pharmaciesHtml };`);
const { portalMedsHtml, pharmaciesHtml } = load(esc, cellHtml);

// A prescription carries the medication id the pharmacy list filters on, so
// "where to get it" asks about the drug in that row and not the first one.
const meds = portalMedsHtml([
  { medication: 7, medication_name: 'Amoxicillin', dose: '500 mg',
    frequency: 'twice daily', duration_days: 5, status: 'prescribed' },
]);
assert.ok(meds.includes('data-medication="7"'), 'medication id missing');
assert.ok(meds.includes('Amoxicillin'));
assert.ok(portalMedsHtml([]).includes('Nothing has been prescribed'));

// A branch nobody has geocoded is still listed and still phoneable — it just
// has no distance and no directions link.
const rows = pharmaciesHtml([
  { name: 'Ikeja', pharmacy: 'Near Pharmacy', address: '1 Allen', phone: '08031234567',
    latitude: '6.60', longitude: '3.35', distance_km: 2.4 },
  { name: 'Main', pharmacy: 'Clinic', address: '', phone: '', distance_km: null },
]);
assert.ok(rows.includes('2.4 km'));
assert.ok(rows.includes('query=6.60,3.35'), 'map link missing');
assert.ok(rows.includes('tel:08031234567'));
assert.strictEqual(rows.match(/Directions/g).length, 1, 'un-geocoded row got a map link');
assert.ok(pharmaciesHtml([]).includes('No pharmacy listed'));

// Names come from other tenants' rows, so they are escaped like anything else.
assert.ok(pharmaciesHtml([{ name: '<script>', pharmacy: 'x' }]).includes('&lt;script&gt;'));

console.log('portal: ok');
