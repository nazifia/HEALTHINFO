/* Self-check for the patient type-ahead in app.js. No framework, no DOM:
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
assert.ok(from > 0 && to > from, 'patient picker block not found in app.js');

let listCalls = 0;
let reply = [];              // rows the next /api/patients/ lookup answers with
const esc = (v) => String(v ?? '');
const Api = { list: async () => (listCalls++, { rows: await reply }) };
const load = new Function('esc', 'Api', `${src.slice(from, to)}; return { patientPicker };`);
const { patientPicker } = load(esc, Api);

const el = () => ({ value: '', textContent: '', innerHTML: '', querySelectorAll: () => [] });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const box = el(), out = el();
  let picked = 'unset';
  patientPicker(box, out, (p) => { picked = p; });

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

  console.log('patient picker: ok');
})();
