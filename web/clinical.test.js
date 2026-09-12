/* Self-check for the clinical-records helpers in app.js: the patient rules
 * checked before the round trip, and the visit rows the list reads. No DOM:
 * both are pure. Run with: node clinical.test.js
 *
 * ponytail: source sliced out of app.js, same as prescription.test.js. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('function patientFormError');
const to = src.indexOf('/* Whether a field takes several values');
assert.ok(from > 0 && to > from, 'clinical block not found in app.js');
const { patientFormError, visitRows } = new Function(
  `${src.slice(from, to)}; return { patientFormError, visitRows };`)();

// The two cross-field rules the API enforces, said before the round trip.
assert.strictEqual(patientFormError({ first_name: 'Amina', last_name: null }), 'First and last name are required.');
assert.strictEqual(patientFormError({ first_name: 'Amina', last_name: 'Bello', patient_type: 'nhia', nhis_number: ' ' }),
  'NHIS number is required for NHIA patients.');
assert.strictEqual(patientFormError({ first_name: 'Amina', last_name: 'Bello', patient_type: 'nhia', nhis_number: 'NH-1' }), null);
assert.strictEqual(patientFormError({ first_name: 'Amina', last_name: 'Bello', patient_type: 'regular' }), null);

// A visit row: catalog name beats the written text, readings on one line, and
// the out-of-band list named by label rather than field.
const [row] = visitRows([{
  id: 7, status: 'open', patient_name: 'Amina Bello', chief_complaint: 'Fever',
  case_report_disease: 'Malaria', case_report_notes: 'malaria?',
  temperature_c: 39.2, pulse_bpm: 110, blood_pressure: '120/80', oxygen_saturation: 97, bmi: null,
  abnormal_vitals: ['temperature_c', 'pulse_bpm'], disposition: '', follow_up_on: null,
}]);
assert.strictEqual(row.diagnosis, 'Malaria');
assert.strictEqual(row.vitals, '39.2 C · P 110 · BP 120/80 · SpO2 97%');
assert.strictEqual(row.outside_band, '⚠ Temp, Pulse');

// No case matched: the written text is still what the visit found. Nothing
// abnormal reads as blank, not as a warning with no readings.
const [bare] = visitRows([{ id: 8, status: 'closed', case_report_notes: 'sprain', abnormal_vitals: [] }]);
assert.strictEqual(bare.diagnosis, 'sprain');
assert.strictEqual(bare.vitals, '');
assert.strictEqual(bare.outside_band, '');

// The sheet's order: pairs share a row, a name the form lacks is skipped, and
// what the layout never named still follows.
const { layoutHtml } = new Function(`${src.slice(src.indexOf('function layoutHtml'),
  src.indexOf('function wireFormRules'))}; return { layoutHtml };`)();
assert.strictEqual(layoutHtml([['a', 'b'], 'zz', ['c', 'missing']], { c: '<c>', a: '<a>', b: '<b>', d: '<d>' }),
  '<div class="row2"><a><b></div><c><d>');
assert.strictEqual(layoutHtml(undefined, { a: '<a>' }), '<a>');

console.log('clinical.test.js OK');
