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
const fmtVal = (v) => (v == null || v === '' ? '—' : String(v));
const label = (k) => k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
const load = new Function('esc', 'cellHtml', 'fmtVal', 'label',
  `${src.slice(from, to)};
   return { portalMedsHtml, pharmaciesHtml, visitsHtml, labsHtml, visitDetailHtml };`);
const { portalMedsHtml, pharmaciesHtml, visitsHtml, labsHtml, visitDetailHtml } =
  load(esc, cellHtml, fmtVal, label);

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

// A visit shows what the patient said and what was found. The findings run
// together from four optional sources, and a visit with none of them still
// lists its complaint.
const visits = visitsHtml([
  { id: 4, created_at: '2026-09-01 09:30', chief_complaint: 'Headache for 3 days',
    case_report_disease: 'Malaria', case_report_notes: 'RDT positive',
    abnormal_vitals: ['high_temperature'], notes: 'Rest advised',
    reporter_name: 'nurse.ada' },
  { id: 5, created_at: '2026-08-02 10:00', chief_complaint: 'Cough' },
]);
assert.ok(visits.includes('Headache for 3 days'));
assert.ok(visits.includes('Malaria · RDT positive · High Temperature · Rest advised'),
  'findings not joined');
assert.ok(visits.includes('nurse.ada'));
assert.strictEqual(visits.match(/<td>2026-/g).length, 2, 'one row per visit');
assert.ok(visitsHtml([]).includes('No visit has been written up'));
// A complaint is free text a clinician typed, so it is escaped too.
assert.ok(visitsHtml([{ chief_complaint: '<b>x' }]).includes('&lt;b&gt;x'));

// Each visit row opens its own page.
assert.ok(visits.includes("location.hash='#/portal/visit/4'"), 'visit row not linked');

// A culture names the bug and the drug tested against it; a plain reading
// shows only its flag.
const labs = labsHtml([
  { created_at: '2026-09-01', lab_test_name: 'Blood culture', value: 'Positive',
    flag: 'critical', organism: 'S. aureus', antibiotic: 'Ampicillin',
    susceptibility: 'resistant', notes: 'Repeat in 5 days' },
  { created_at: '2026-08-01', disease_name: 'Malaria', value: '12.3 g/dL', flag: 'normal' },
]);
assert.ok(labs.includes('S. aureus / Ampicillin resistant'), 'AST line missing');
assert.ok(labs.includes('Malaria'), 'test falls back to the disease name');
assert.ok(labsHtml([]).includes('No test result has been filed'));
assert.ok(labsHtml([{ notes: '<b>x' }]).includes('&lt;b&gt;x'));

// The detail page shows a measured vital and leaves out the ones nobody took.
const detail = visitDetailHtml({
  id: 4, created_at: '2026-09-01 09:30', chief_complaint: 'Headache for 3 days',
  case_report_disease: 'Malaria', notes: 'Rest advised', reporter_name: 'nurse.ada',
  temperature_c: '38.4', blood_pressure: '120/80', pulse_bpm: null,
  abnormal_vitals: ['high_temperature'], status: 'closed',
  disposition: 'follow_up', follow_up_on: '2026-09-08',
});
assert.ok(detail.includes('38.4 °C'));
assert.ok(detail.includes('120/80'));
assert.ok(!detail.includes('Pulse'), 'a vital nobody took got a row');
assert.ok(detail.includes('Follow Up'), 'disposition not labelled');
assert.ok(detail.includes('High Temperature'));
// A visit with nothing measured still says so rather than showing an empty box.
assert.ok(visitDetailHtml({ id: 5, chief_complaint: 'Cough' }).includes('Not taken'));

console.log('portal: ok');
