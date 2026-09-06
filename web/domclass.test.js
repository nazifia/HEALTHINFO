/* Self-check for domClass in app.js: every tile route lands on the module its
 * colour claims. Run with: node domclass.test.js
 *
 * ponytail: source sliced out of app.js, same as columns.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('const RESOURCES = {');
const to = src.indexOf('function domClass');
const end = src.indexOf('\n}', to) + 2;
assert.ok(from > 0 && to > from, 'RESOURCES or domClass not found in app.js');
const domClass = new Function(`${src.slice(from, to)}${src.slice(to, end)}; return domClass;`)();

assert.strictEqual(domClass('#/r/pharmacy-sales'), ' dom-pharmacy');
assert.strictEqual(domClass('#/r/patients'), ' dom-clinical');
assert.strictEqual(domClass('#/r/case-reports'), ' dom-reports');
assert.strictEqual(domClass('#/r/diseases'), ' dom-catalog');
assert.strictEqual(domClass('#/r/users'), ' dom-admin');
assert.strictEqual(domClass('#/pharmacy/sell'), ' dom-pharmacy');
assert.strictEqual(domClass('#/clinical'), ' dom-clinical');
assert.strictEqual(domClass('#/analytics'), ' dom-analytics');
assert.strictEqual(domClass('#/platform'), ' dom-analytics');
assert.strictEqual(domClass('#/search'), ' dom-tools');
// An unknown slug carries no class, so the tile falls back to the brand colour.
assert.strictEqual(domClass('#/r/nope'), '');

console.log('domClass: ok');
