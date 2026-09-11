/* Self-check for the related-field controls in app.js: a foreign key comes up
 * as something to pick, not a box for a raw id.
 * Run with: node relfield.test.js
 *
 * ponytail: source sliced out of app.js, same as itemfield.test.js — the app
 * is loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('/* Whether a field takes several values.');
const to = src.indexOf('/* ---------------------------------------------------------- field type-ahead */');
assert.ok(from > 0 && to > from, 'field block not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const label = (n) => n.replace(/_/g, ' ');
const FIELD_HINTS = {};
const PICKERS = { patient: { placeholder: 'Name…' } };
const M2M_FIELDS = new Set(['symptoms']);
const STR_LIST_FIELDS = new Set(['privileges']);
let searchable = [];
const makeSearchable = (sel) => { searchable.push(sel); };

const { isMultiField, wireChoiceFields, fieldHtml, collectForm } =
  new Function('esc', 'label', 'FIELD_HINTS', 'PICKERS', 'M2M_FIELDS',
    'STR_LIST_FIELDS', 'makeSearchable',
    `${src.slice(from, to)}; return { isMultiField, wireChoiceFields, fieldHtml, collectForm };`)(
    esc, label, FIELD_HINTS, PICKERS, M2M_FIELDS, STR_LIST_FIELDS, makeSearchable);

const choices = (n) => Array.from({ length: n }, (_, i) =>
  ({ value: i + 1, display_name: `Row <${i + 1}>` }));

// A relation the server could list is a select of names, not a number box.
const one = fieldHtml('supplier', { type: 'field', required: true, choices: choices(2) }, 2);
assert.ok(one.includes('<select'), 'listed relation still a raw id box');
assert.ok(!one.includes('multiple'), 'to-one relation rendered as multi-select');
assert.ok(one.includes('value="2"  selected') || /value="2"\s+selected/.test(one),
  'current value not selected');
assert.ok(one.includes('Row &lt;1&gt;'), 'option label not escaped');
assert.ok(one.includes('<option value=""></option>'), 'to-one select has no blank row');

// The server saying "multiple" is enough — no need to name the field in app.js.
const many = fieldHtml('claims', { type: 'field', multiple: true, choices: choices(2) }, [1]);
assert.ok(/multiple/.test(many), 'declared to-many not a multi-select');
assert.ok(!many.includes('<option value=""></option>'), 'multi-select has a blank row');
assert.strictEqual(isMultiField('claims', { multiple: true }), true);
assert.strictEqual(isMultiField('symptoms', {}), true, 'named M2M field lost');
assert.strictEqual(isMultiField('supplier', {}), false);

// A to-many the server could not list still takes ids, and still reads as one.
const wide = fieldHtml('claims', { type: 'field', multiple: true }, [1, 2]);
assert.ok(wide.includes('placeholder="ids, comma-separated"'), 'unlisted to-many lost its hint');

// A field with its own type-ahead keeps it, listed or not.
assert.ok(fieldHtml('patient', { type: 'field', choices: choices(2) }, '').includes('type="hidden"'),
  'patient picker overridden by choices');

// Long closed lists become type-aheads; short ones stay plain selects.
// A multi-select is picked over by makeMultiPicker instead, whatever its size.
const sels = (n) => [{ options: { length: n }, multiple: false }];
const formOf = (n) => ({ querySelectorAll: (q) => (q.endsWith('[multiple]') ? [] : sels(n)) });
searchable = [];
wireChoiceFields(formOf(13));
assert.strictEqual(searchable.length, 1, 'long list not made searchable');
searchable = [];
wireChoiceFields(formOf(12));
assert.strictEqual(searchable.length, 0, 'short list needlessly swapped');

// What a picked select sends: an id, and a list of ids for a to-many.
const form = {
  elements: {
    supplier: { value: ' 7 ' },
    claims: Object.assign(Object.create({ multiple: true }), {
      multiple: true, value: '', selectedOptions: [{ value: '3' }, { value: '4' }],
    }),
  },
};
// collectForm branches on HTMLSelectElement, absent outside a browser.
global.HTMLSelectElement = function () {};
Object.setPrototypeOf(form.elements.claims, global.HTMLSelectElement.prototype);
form.elements.claims.multiple = true;
const body = collectForm(form, {
  supplier: { type: 'field' }, claims: { type: 'field', multiple: true },
});
assert.deepStrictEqual(body, { supplier: 7, claims: [3, 4] });

console.log('relfield.test.js ok');
