/* Self-check for the multi-drug prescription payload in app.js. No framework,
 * no DOM: prescriptionPayload is pure. Run with: node prescription.test.js
 *
 * ponytail: the source is sliced out of app.js, same as picker.test.js — the
 * app is loaded with plain <script> tags and has no build step to import. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf("const RX_DRUG_FIELDS");
const to = src.indexOf('function fieldHtml');
assert.ok(from > 0 && to > from, 'drug row block not found in app.js');
const head = src.slice(from, src.indexOf('\n', from) + 1);
const block = src.slice(src.indexOf('function prescriptionPayload'), to);
const { prescriptionPayload, collapseByGroup, cancelButtonHtml } = new Function(
  `${head}${block}; return { prescriptionPayload, collapseByGroup, cancelButtonHtml };`)();

const form = {
  patient: 4, case_report: 9, region: 'Kano', notes: 'take after food',
  medication: 1, dose: '80 mg', frequency: 'twice daily', duration_days: 3,
};

// No extra drugs: one order, posted as the object the form built.
assert.deepStrictEqual(prescriptionPayload(form, []), form);

// Untouched blank rows are dropped, not posted as empty orders.
assert.deepStrictEqual(prescriptionPayload(form, [{}, { dose: '1 g' }]), form);

// Several drugs: one row each, all carrying the patient and the diagnosis.
const rows = prescriptionPayload(form, [{ medication: 2, dose: '1 g' }]);
assert.strictEqual(rows.length, 2);
assert.deepStrictEqual(rows[0], form);
assert.deepStrictEqual(rows[1], {
  patient: 4, case_report: 9, region: 'Kano', notes: 'take after food',
  medication: 2, dose: '1 g',
});
// A drug field left blank on an extra row stays blank: it must not inherit the
// first drug's directions, which belong to a different drug.
assert.ok(!('frequency' in rows[1]) && !('duration_days' in rows[1]));

/* The list shows one row per prescription, not per drug. */
const listed = collapseByGroup([
  { id: 1, group: 'g1', medication_name: 'Artemether', dose: '80 mg', frequency: 'bd', status: 'prescribed' },
  { id: 2, group: 'g1', medication_name: 'Paracetamol', dose: '1 g', frequency: 'prn', status: 'prescribed' },
  { id: 3, group: null, medication_name: 'Zinc', dose: '20 mg', frequency: 'od', status: 'dispensed' },
  { id: 4, group: 'g2', medication_name: 'Metformin', dose: '500 mg', frequency: 'bd', status: 'prescribed' },
]);
assert.deepStrictEqual(listed.map((r) => r.id), [1, 3, 4]);
assert.strictEqual(listed[0].medication_name,
  'Artemether 80 mg bd; Paracetamol 1 g prn');
// One drug's directions are not the prescription's, so they go.
assert.strictEqual(listed[0].dose, '');
assert.strictEqual(listed[0].frequency, '');
// An order on no prescription keeps everything it had.
assert.strictEqual(listed[1].medication_name, 'Zinc');
assert.strictEqual(listed[1].dose, '20 mg');

// Drugs at different stages: the row says so rather than picking one.
const mixed = collapseByGroup([
  { id: 5, group: 'g3', medication_name: 'Artemether', status: 'dispensed' },
  { id: 6, group: 'g3', medication_name: 'Zinc', status: 'prescribed' },
]);
assert.strictEqual(mixed.length, 1);
assert.strictEqual(mixed[0].status, 'part-dispensed');

// A row of objects reads as nothing in a table, so the drugs come off it.
assert.ok(!('drugs' in listed[0]) && !('drugs' in listed[1]));

// Cancel is offered while something on the prescription can still be stopped.
assert.ok(cancelButtonHtml({ id: 1, status: 'prescribed' }).includes('data-cancel="1"'));
assert.ok(cancelButtonHtml({ id: 1, status: 'part-dispensed' }).includes('Cancel'));
assert.strictEqual(cancelButtonHtml({ id: 1, status: 'dispensed' }), '');
assert.strictEqual(cancelButtonHtml({ id: 1, status: 'cancelled' }), '');

console.log('prescription payload: ok');
