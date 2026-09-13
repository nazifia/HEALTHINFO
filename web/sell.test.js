/* Self-check for the dispense screen's prescription helpers in app.js: what a
 * patient's number turns up is one list the counter fills from, and the sale
 * carries a counter script in `rx` and a clinician's drug order in
 * `prescription`, either from another facility, with the number as proof.
 * Run with: node sell.test.js
 *
 * ponytail: source sliced out of app.js, same as sales.test.js. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const a = src.indexOf('function sellRxRows(found) {');
const b = src.indexOf('/* Dispensing counter.');
assert.ok(a > 0 && b > a, 'sell helpers not found in app.js');
const { sellRxRows, sellRxLabel, sellFillBody, sellMatchItem } = new Function(
  `${src.slice(a, b)}; return { sellRxRows, sellRxLabel, sellFillBody, sellMatchItem };`)();

assert.deepStrictEqual(sellRxRows(null), []);
const found = {
  scripts: [{ id: 3, prescriber_name: 'Dr Ada', consultation_category: 'B',
    lines: [{ name: 'Amoxicillin', quantity: 10 }, { name: 'Paracetamol', quantity: 6 }] }],
  orders: [{ id: 7, medication_name: 'Artemether', dose: '80 mg', frequency: 'twice daily' }],
  orders_elsewhere: [{ id: 9, medication_name: 'Amoxicillin', dose: '500 mg',
    duration_days: 5, facility: 'Ikeja Clinic', consultation_category: 'B' }],
  scripts_elsewhere: [{ id: 4, prescriber_name: 'Dr Bala', facility: 'Corner Pharmacy',
    lines: [{ name: 'ORS', quantity: 3 }] }],
};
const rows = sellRxRows(found);
assert.deepStrictEqual(rows.map((r) => r.key), ['script:3', 'order:7', 'order:9', 'script:4']);
assert.deepStrictEqual(rows.map((r) => r.facility),
  ['Counter script', 'Here', 'Ikeja Clinic', 'Corner Pharmacy']);

assert.strictEqual(sellRxLabel(rows[0]), 'Amoxicillin ×10, Paracetamol ×6 — Dr Ada');
assert.strictEqual(sellRxLabel(rows[1]), 'Artemether · 80 mg · twice daily');
assert.strictEqual(sellRxLabel(rows[2]), 'Amoxicillin · 500 mg · 5 days');

assert.deepStrictEqual(sellFillBody(null, '0803'), {});
assert.strictEqual(sellRxLabel(rows[3]), 'ORS ×3 — Dr Bala');
assert.deepStrictEqual(sellFillBody(rows[0], '0803'), { rx: 3, patient_number: '0803' });
assert.deepStrictEqual(sellFillBody(rows[2], '08031234567'),
  { prescription: 9, patient_number: '08031234567' });
assert.deepStrictEqual(sellFillBody(rows[3], '08031234567'),
  { rx: 4, patient_number: '08031234567' });

const stock = [{ id: 1, name: 'Amoxicillin 250mg' }, { id: 2, name: 'Paracetamol 500mg' },
  { id: 5, name: 'Amoxicillin 500mg' }];
assert.strictEqual(sellMatchItem(stock, rows[2]).id, 5);   // 'Amoxicillin' + '500 mg'
assert.strictEqual(sellMatchItem(stock, rows[1]), null);
assert.strictEqual(sellMatchItem(stock, { medication_name: 'Amoxicillin', dose: '1g' }).id, 1);
assert.strictEqual(sellMatchItem(stock, { medication_name: 'Paracetamol 1g' }).id, 2);
assert.strictEqual(sellMatchItem(stock, { medication_name: 'paracetamol 500mg' }).id, 2);
assert.strictEqual(sellMatchItem(stock, rows[3]), null);
assert.strictEqual(sellMatchItem(stock, {}), null);
console.log('sell helpers ok');
