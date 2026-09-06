/* Self-check for the notification list in app.js. No DOM: the renderer is a
 * plain function over plain rows. Run with: node notify.test.js
 *
 * ponytail: source sliced out of app.js, same as portal.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('function notificationsHtml');
const to = src.indexOf('async function viewNotifications');
assert.ok(from > 0 && to > from, 'notification block not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const load = new Function('esc', `${src.slice(from, to)}; return notificationsHtml;`);
const notificationsHtml = load(esc);

assert.ok(notificationsHtml([]).includes('Nothing waiting.'));

const html = notificationsHtml([
  { id: 7, title: 'PA123 authorised', message: 'Dispense against PA123.', priority: 'high',
    created_at: '2026-09-06T10:00:00Z', is_read: false },
  { id: 8, title: 'PA999 declined', message: '', priority: 'high',
    created_at: '2026-09-05T10:00:00Z', is_read: true },
]);
// Unread is what the bell counts, so it has to read differently from the rest.
assert.strictEqual((html.match(/card unread/g) || []).length, 1);
assert.ok(html.includes('Dispense against PA123.'));
// Only an unread row can be marked read, and the button carries its own id.
assert.strictEqual((html.match(/class="ghost mark-read"/g) || []).length, 1);
assert.ok(html.includes('data-id="7"'));
// An empty message leaves no empty paragraph behind.
assert.ok(!html.includes('<p></p>'));

// A title is data from the API, not markup.
assert.ok(notificationsHtml([{ title: '<img src=x>', priority: 'low', created_at: '' }])
  .includes('&lt;img src=x&gt;'), 'notification title is not escaped');

console.log('notify.test.js ok');
