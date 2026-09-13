/* Self-check for the live screens in app.js: which routes re-pull their
 * numbers on a timer, and which hold still. Run with: node live.test.js
 *
 * ponytail: source sliced out of app.js, same as dashboards.test.js. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const line = src.split('\n').find((l) => l.startsWith('const LIVE_RE = '));
assert.ok(line, 'LIVE_RE not found in app.js');
const LIVE_RE = new Function(`${line}; return LIVE_RE;`)();

// Every dashboard, register and report is live.
for (const p of ['/', '/clinical', '/facility', '/earnings', '/portal', '/insurer', '/gov',
  '/pharmacy', '/hmo', '/notifications', '/notifiable', '/r/patients', '/r/case-reports',
  '/analytics', '/analytics/sales', '/platform', '/platform/idsr', '/trading', '/trading/controlled']) {
  assert.ok(LIVE_RE.test(p), `${p} is not live`);
}
// Anything the user is filling in holds still.
for (const p of ['/login', '/profile', '/pharmacy/sell', '/r/patients/new', '/r/patients/3',
  '/r/patients/3/edit', '/search', '/differential', '/interaction-check', '/graph/disease/3']) {
  assert.ok(!LIVE_RE.test(p), `${p} refreshes under the user`);
}

// A refresh never fires while the user is typing, and never overlaps itself.
const refresh = src.slice(src.indexOf('async function refreshView'), src.indexOf('function route()'));
assert.ok(/if \(refreshing \|\| document\.activeElement\?\.matches\('input, textarea, select'\)\) return;/.test(refresh));

console.log('live.test.js: ok');
