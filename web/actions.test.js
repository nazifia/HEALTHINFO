/* Self-check for which module-action buttons a record is offered, and for the
 * registry entries that lean on it. No DOM: the function is plain over a plain
 * record. Run with: node actions.test.js
 *
 * ponytail: source sliced out of app.js, same as scheme.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('const visibleActions = (res, obj) =>');
const to = src.indexOf(';', src.indexOf('!obj[a.hideWhen]'));
assert.ok(from > 0 && to > from, 'visibleActions not found in app.js');

const load = (admin, staff) => new Function('isPharmacyAdmin', 'isPharmacyStaff',
  `const canActRes = (res) => res.group !== 'Pharmacy' || isPharmacyStaff();
   ${src.slice(from, to + 1)}; return visibleActions;`)(() => admin, () => staff);

const notify = { name: 'notify', label: 'Mark notified', hideWhen: 'notified_at' };
const cases = { group: 'Reports', actions: [notify] };
const anyone = load(false, false);

// A case still owed its notification offers the button; one already sent does
// not — the stamp is the record of it, and a second call moves nothing.
assert.deepStrictEqual(anyone(cases, { notified_at: null }), [notify]);
assert.deepStrictEqual(anyone(cases, {}), [notify]);
assert.deepStrictEqual(anyone(cases, { notified_at: '2026-09-09T10:00:00Z' }), []);

// A pharmacy record is offered nothing to anyone but pharmacy staff, and the
// admin-only half of the list only to the admin.
const correct = { name: 'adjust', label: 'Correct counted quantity', ask: 'quantity,reason', adminOnly: true };
const writeOff = { name: 'adjust', label: 'Write this batch off', ask: 'reason', adminOnly: true,
                   body: { quantity: 0, write_off: true } };
const batches = { group: 'Pharmacy', actions: [correct, writeOff] };
assert.deepStrictEqual(anyone(batches, {}), [], 'a non-pharmacy seat was offered stock actions');
assert.deepStrictEqual(load(false, true)(batches, {}), [], 'a counter hand was offered the admin actions');
assert.deepStrictEqual(load(true, true)(batches, {}), [correct, writeOff]);

// ``when`` still gates on the record's state: an approved claim is paid, not
// re-submitted.
const claims = { group: 'Pharmacy', actions: [{ name: 'submit', when: ['draft', 'rejected'] },
                                              { name: 'pay', when: ['approved'] }] };
assert.deepStrictEqual(load(true, true)(claims, { status: 'approved' }).map((a) => a.name), ['pay']);

// The registry entries these buttons come from, so a rename in app.js fails
// here rather than silently dropping the button.
assert.ok(/'case-reports':[\s\S]{0,400}hideWhen: 'notified_at'/.test(src),
          'the case report notify action lost its hideWhen');
assert.ok(/'pharmacy-batches':[\s\S]{0,600}write_off: true/.test(src),
          'the batch write-off action is gone');

console.log('actions.test.js ok');
