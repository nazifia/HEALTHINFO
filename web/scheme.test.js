/* Self-check for the dispense screen's scheme label in app.js. No DOM: the
 * function is plain over a plain row. Run with: node scheme.test.js
 *
 * ponytail: source sliced out of app.js, same as portal.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('  const schemeLabel = (r) =>');
const to = src.indexOf('  const schemeOptions = ()');
assert.ok(from > 0 && to > from, 'scheme label block not found in app.js');

const money = (v) => '₦' + Number(v || 0).toFixed(2);
const load = new Function('money', `${src.slice(from, to)}; return schemeLabel;`);
const schemeLabel = load(money);

// A capped plan: what is left of the year's benefit decides whether the
// counter should expect the patient to pay the balance.
assert.strictEqual(
  schemeLabel({ hmo_name: 'Hygeia', member_number: 'HY-1', effective_coverage: '90.00',
                remaining_benefit: '2500.00' }),
  'Hygeia · HY-1 (90.00%, ₦2500.00 left this year)');

// Uncapped (null) and an API that predates the field (undefined) both say
// nothing rather than showing ₦0.00 left, which would read as exhausted.
for (const remaining_benefit of [null, undefined]) {
  assert.strictEqual(
    schemeLabel({ hmo_name: 'NHIA', member_number: 'N-9', effective_coverage: '100.00',
                  remaining_benefit }),
    'NHIA · N-9 (100.00%)');
}

console.log('scheme.test.js ok');
