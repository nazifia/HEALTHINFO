/* Self-check for the table/detail column picker in app.js. No DOM: the block
 * is plain functions over plain rows. Run with: node columns.test.js
 *
 * ponytail: source sliced out of app.js, same as picker.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('const namedElsewhere');
const to = src.indexOf('/* ------------------------------------------------------------- auth views */');
assert.ok(from > 0 && to > from, 'column picker block not found in app.js');

const label = (k) => k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
const load = new Function('label', `${src.slice(from, to)}; return { pickColumns, colLabel, namedElsewhere };`);
const { pickColumns, colLabel } = load(label);

// The users list: a super-admin belongs to no organization, so DRF drops
// tenant_name from their row. Sampling only that row would show the bare pk
// column for the whole table.
const users = [
  { id: 1, phone: '08032194090', username: 'superuser', role: 'super_admin', tenant: null, is_active: true },
  { id: 2, phone: '+2348000000001', username: 'tenant_admin', role: 'tenant_admin', tenant: 1, tenant_name: 'Demo Clinic', is_active: true },
];
const cols = pickColumns(users);
assert.ok(!cols.includes('tenant'), 'bare tenant pk survived a null first row');
assert.ok(cols.includes('tenant_name'), 'tenant name column missing');

// A name standing in for a hidden pk is headed by the thing itself.
const keys = ['tenant', 'tenant_name', 'symptoms', 'symptoms_names', 'full_name'];
assert.strictEqual(colLabel(keys, 'tenant_name'), 'Tenant');
assert.strictEqual(colLabel(keys, 'symptoms_names'), 'Symptoms');
// No `full` column for full_name to stand in for: it keeps its own heading.
assert.strictEqual(colLabel(keys, 'full_name'), 'Full Name');

// Nothing resolves a pk here, so it stays: an id beats no column at all.
assert.ok(pickColumns([{ id: 3, patient: 41, status: 'open' }]).includes('patient'));

console.log('columns.test.js OK');
