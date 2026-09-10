/* Self-check for the mobile drawer's state helper in app.js. No DOM: the
 * elements are stubs with the properties setNav writes. Run: node nav.test.js
 *
 * ponytail: source sliced out of app.js, same as scheme.test.js — the app is
 * loaded with <script> tags and has no build step to import from. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('function setNav(open, refocus) {');
const to = src.indexOf('function render(html) {');
assert.ok(from > 0 && to > from, 'setNav block not found in app.js');

function harness() {
  const el = (name) => ({
    name,
    open: false,
    aria: null,
    focused: 0,
    classList: {
      toggle(_c, on) { el.open = on; },
    },
  });
  const sidebar = {
    open: false,
    link: { name: 'link', focused: 0, focus() { this.focused++; } },
    classList: { toggle(c, on) { assert.strictEqual(c, 'open'); sidebar.open = on; } },
    querySelector(sel) { assert.strictEqual(sel, 'a, summary'); return sidebar.link; },
  };
  const toggle = {
    aria: null,
    focused: 0,
    setAttribute(k, v) { assert.strictEqual(k, 'aria-expanded'); toggle.aria = v; },
    focus() { toggle.focused++; },
  };
  const $ = (sel) => ({ '#sidebar': sidebar, '#nav-toggle': toggle }[sel]);
  const setNav = new Function('$', `${src.slice(from, to)}; return setNav;`)($);
  return { sidebar, toggle, setNav };
}

// Opening deliberately (the button, a keypress) slides the drawer in, tells
// assistive tech it is open, and puts the focus inside it.
let h = harness();
h.setNav(true, true);
assert.strictEqual(h.sidebar.open, true);
assert.strictEqual(h.toggle.aria, 'true');           // the string, not the boolean
assert.strictEqual(h.sidebar.link.focused, 1);
assert.strictEqual(h.toggle.focused, 0);

// Dismissing it deliberately (Escape, the scrim) hands the focus back to the
// button that opened it, rather than leaving it on a hidden link.
h.setNav(false, true);
assert.strictEqual(h.sidebar.open, false);
assert.strictEqual(h.toggle.aria, 'false');
assert.strictEqual(h.toggle.focused, 1);

// The automatic close on navigation must not move the focus: the user is
// reading the page that just rendered, not the menu.
h = harness();
h.setNav(true, true);
h.setNav(false);
assert.strictEqual(h.sidebar.open, false);
assert.strictEqual(h.toggle.aria, 'false');
assert.strictEqual(h.toggle.focused, 0);

// The insurance desk is its own sidebar group, but the gate above it still
// reads ``group`` — so a resource flagged ``hmo`` that left the Pharmacy group
// would show up for staff the API refuses.
const hmoLines = src.split(String.fromCharCode(10)).filter((l) => l.includes('hmo: true'));
assert.ok(hmoLines.length >= 6, 'no hmo-flagged resources found');
for (const line of hmoLines) assert.ok(line.includes("group: 'Pharmacy'"), line.trim());
assert.ok(src.includes("groups[r.hmo ? 'HMO' : r.group]"), 'HMO links not split out');
assert.ok(src.includes("navGroup('HMO'"), 'HMO nav group not rendered');
// The HMO group's own dashboard: the sidebar link and the route must agree,
// or the section's front door lands on "Page not found".
assert.ok(src.includes('href="#/hmo"'), 'no HMO dashboard link in the sidebar');
assert.ok(src.includes('/hmo$/, viewHmo'), 'no /hmo route');
assert.ok(src.includes('async function viewHmo()'), 'viewHmo not defined');

// A desk admin's Users link moves into their own section, so the Admin group
// must not be the only place it renders.
assert.ok(src.includes("deskUsers ? usersLink : ''"), 'Users link not shown in the desk section');
assert.ok(src.includes("groups.Admin.filter((a) => a !== usersLink)"), 'Users link left in Admin too');

console.log('nav.test.js ok');
