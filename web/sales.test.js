/* Self-check for salesHeadline in app.js: the state-sales tiles show the latest
 * day, month and year in the payload, summed across every area. Run with:
 * node sales.test.js
 *
 * ponytail: source sliced out of app.js, same as dashboards.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const a = src.indexOf('function salesHeadline(data, now = null) {');
const b = src.indexOf('function statIndex(');
assert.ok(a > 0 && b > a, 'salesHeadline not found in app.js');

const salesHeadline = new Function('esc', 'label', 'fmtVal', 'money',
  `${src.slice(a, b)}; return salesHeadline;`)(
  String,
  (k) => k,
  (v) => String(v),
  (v) => 'N' + Number(v || 0).toFixed(2),
);

// Two states in the same period: the tile is the sum, not one of them.
const data = {
  level: 'state',
  daily: [
    { state: 'Kano', period: '2026-09-09', revenue: '100.00', sales: 2 },
    { state: 'Kano', period: '2026-09-10', revenue: '250.50', sales: 3 },
    { state: 'Kwara', period: '2026-09-10', revenue: '49.50', sales: 1 },
  ],
  monthly: [
    { state: 'Kano', period: '2026-08', revenue: '900.00', sales: 9 },
    { state: 'Kano', period: '2026-09', revenue: '350.50', sales: 5 },
  ],
  yearly: [{ state: 'Kano', period: '2026', revenue: '1250.50', sales: 14 }],
};
const html = salesHeadline(data);
assert.ok(html.includes('N300.00'), `daily total wrong: ${html}`);
assert.ok(html.includes('2026-09-10'), 'daily tile names the wrong day');
assert.ok(!html.includes('2026-09-09'), 'daily tile shows an older day too');
assert.ok(html.includes('N350.50'), 'monthly total wrong');
assert.ok(html.includes('N1250.50'), 'yearly total wrong');
assert.ok(html.includes('4 sale(s)'), 'daily sale count is not the two areas added');

// Nothing to show is empty, never a tile reading zero.
assert.strictEqual(salesHeadline({ level: 'state', daily: [], monthly: [], yearly: [] }), '');
assert.strictEqual(salesHeadline(null), '');

// Live (no window): the tiles are today, this month and this year — zero
// until the first sale lands, never the last day that had one.
const now = new Date('2026-09-13T08:00:00Z');
const live = salesHeadline(data, now);
assert.ok(live.includes('2026-09-13'), 'live daily tile is not today');
assert.ok(!live.includes('2026-09-10'), 'live daily tile shows the last day with sales');
assert.ok(live.includes('N0.00'), 'a day with no sales yet does not read zero');
assert.ok(live.includes('0 sale(s)'), 'a day with no sales yet does not count zero');
assert.ok(live.includes('N350.50'), 'live monthly total wrong');
assert.ok(live.includes('N1250.50'), 'live yearly total wrong');
assert.ok(salesHeadline({ level: 'state', daily: [], monthly: [], yearly: [] }, now).includes('2026-09-13'),
  'a live dashboard with no sales yet still shows today');

console.log('sales: ok');
