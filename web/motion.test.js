/* Self-check for the stat count-up in app.js: a formatted number keeps its
 * prefix, suffix, grouping and decimals while it ticks; anything else is left
 * alone. Run with: node motion.test.js */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const a = src.indexOf('const NUM_RE'), b = src.indexOf('function countUp(');
assert.ok(a > 0 && b > a);
const countFmt = new Function(`${src.slice(a, b)}; return countFmt;`)();

assert.strictEqual(countFmt('₦1,200.50', 987.654), '₦987.65');
assert.strictEqual(countFmt('₦12,345', 12345), '₦12,345');
assert.strictEqual(countFmt('42%', 21), '21%');
assert.strictEqual(countFmt('7', 3.2), '3');
assert.strictEqual(countFmt('2024-01-05', 0), '2024-01-05');
assert.strictEqual(countFmt('—', 0), '—');
console.log('motion ok');
