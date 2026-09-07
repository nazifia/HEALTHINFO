/* Self-check for the field type-aheads in app.js. No framework, no DOM:
 * the picker only ever touches `.value`, `.oninput`, `.textContent`,
 * `.innerHTML` and `.querySelectorAll`, so plain objects stand in for both
 * elements. Run with: node picker.test.js
 *
 * ponytail: the source is sliced out of app.js rather than split into a module
 * — the app is loaded with plain <script> tags and has no build step to add
 * one. Move it to its own file the day app.js needs importing anyway. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('const patientHitHtml');
const to = src.indexOf('function showFieldErrors');
assert.ok(from > 0 && to > from, 'picker block not found in app.js');

let listCalls = 0;
let lastPath = '';
let reply = [];              // rows the next lookup answers with
const esc = (v) => String(v ?? '');
const Api = { list: async (path) => (listCalls++, lastPath = path, { rows: await reply }) };
const load = new Function('esc', 'Api',
  `${src.slice(from, to)}; return { picker, PICKERS, carryPatientFields, patientHitHtml, userHitHtml };`);
const { picker, PICKERS, carryPatientFields, patientHitHtml, userHitHtml } = load(esc, Api);

const el = () => ({ value: '', textContent: '', innerHTML: '', querySelectorAll: () => [] });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const box = el(), out = el();
  let picked = 'unset';
  picker(box, out, PICKERS.patient, (p) => { picked = p; });

  // Typing does not fire a lookup per keystroke — only after the pause.
  box.value = 'ade';
  box.oninput(); box.oninput(); box.oninput();
  assert.strictEqual(listCalls, 0, 'lookup fired before the debounce elapsed');

  // One match binds itself.
  reply = [{ id: 7, full_name: 'Ade Bello', hospital_number: '08031234567' }];
  await wait(320);
  assert.strictEqual(listCalls, 1);
  assert.strictEqual(picked.id, 7);
  assert.ok(out.innerHTML.includes('Ade Bello'));

  // Several matches resolve nothing: the user has to pick.
  reply = [{ id: 7, full_name: 'Ade Bello' }, { id: 8, full_name: 'Ade Cole' }];
  box.value = 'ade b';
  box.oninput();
  await wait(320);
  assert.strictEqual(picked, null, 'an ambiguous lookup must not bind a patient');

  // A stale reply may not overwrite a newer one.
  let release;
  reply = new Promise((r) => { release = r; });
  box.value = 'slow';
  box.oninput();
  await wait(320);
  reply = [{ id: 9, full_name: 'Chi Eze' }];
  box.value = 'chi';
  box.oninput();
  await wait(320);
  release([{ id: 1, full_name: 'Stale Row' }]);
  await wait(20);
  assert.strictEqual(picked.id, 9, 'a stale lookup reply overwrote a newer one');

  // An emptied box clears the link rather than leaving the last patient on it.
  box.value = '';
  box.oninput();
  await wait(320);
  assert.strictEqual(picked, null);
  assert.strictEqual(out.textContent, '');

  // A linked patient fills what the registry already answers, and never
  // overwrites what was typed.
  const form = { elements: { region: { value: '', tagName: 'INPUT' } } };
  carryPatientFields(form, { region: 'Ikeja, Lagos' });
  assert.strictEqual(form.elements.region.value, 'Ikeja, Lagos');
  carryPatientFields(form, { region: 'Bauchi, Bauchi' });
  assert.strictEqual(form.elements.region.value, 'Ikeja, Lagos',
      'a value already on the form was overwritten');
  carryPatientFields({ elements: {} }, { region: 'Ikeja, Lagos' });  // no field: no throw

  // The hit line carries the details the form would otherwise ask for.
  const hit = patientHitHtml({
    full_name: 'Ade Bello', age: 34, sex: 'female', blood_group: 'O+',
    allergies: 'penicillin', chronic_condition_names: ['Asthma'],
  });
  assert.ok(hit.includes('34y') && hit.includes('O+'), 'details missing from the hit line');
  assert.ok(hit.includes('penicillin') && hit.includes('Asthma'));

  // The same picker over accounts: it searches /api/users/, and the hit line
  // names the account by something a person can read back to the patient.
  const ubox = el(), uout = el();
  let account = 'unset';
  picker(ubox, uout, PICKERS.user, (u) => { account = u; });
  reply = [{ id: 12, username: 'ade', phone: '08031234567', role: 'public' }];
  ubox.value = '0803';
  ubox.oninput();
  await wait(320);
  assert.strictEqual(lastPath, '/api/users/', 'the account picker searched the wrong list');
  assert.strictEqual(account.id, 12);
  assert.ok(uout.innerHTML.includes('ade') && uout.innerHTML.includes('08031234567'));

  // No match says so in the words of the field being filled.
  reply = [];
  ubox.value = 'nobody';
  ubox.oninput();
  await wait(320);
  assert.strictEqual(uout.textContent, 'No account found.');
  assert.strictEqual(account, null);

  // An account with no display name still reads as something.
  assert.ok(userHitHtml({ id: 3, phone: '08000000000' }).includes('08000000000'));

  console.log('field pickers: ok');
})();
