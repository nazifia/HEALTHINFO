/* Self-check for the jurisdiction type-ahead in app.js. No framework, no DOM
 * library: the picker only ever touches a handful of element properties, so
 * plain objects stand in for the select, the box, the menu and the events.
 * Run with: node places.test.js
 *
 * ponytail: the source is sliced out of app.js rather than split into a module
 * — the app is loaded with plain <script> tags and has no build step to add
 * one. Same trick, and same reason, as picker.test.js. */
'use strict';
const assert = require('assert');
const { readFileSync } = require('fs');

const src = readFileSync(`${__dirname}/app.js`, 'utf8');
const from = src.indexOf('function placeLabel');
const to = src.indexOf('async function paintStatePicker');
assert.ok(from > 0 && to > from, 'place picker block not found in app.js');

const esc = (v) => String(v ?? '').replace(/[&<>"]/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const made = [];
const node = (tag) => {
  const attrs = {};
  return {
    tag, attrs, id: '', value: '', name: '', className: '', innerHTML: '',
    placeholder: '', type: '', required: false, autocomplete: '', hidden: false,
    children: [],
    setAttribute: (k, v) => { attrs[k] = String(v); },
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
    hasAttribute: (k) => k in attrs,
    append(...n) { this.children.push(...n); },
    dispatchEvent(e) { if (e.type === 'change') this.onchange?.(); return true; },
  };
};
global.document = { createElement: (tag) => { const n = node(tag); made.push(n); return n; } };
global.Event = class { constructor(type) { this.type = type; } };

const { placeLabel, optionIndex, rankMatches, matchScore, makeSearchable } =
  new Function('esc', `${src.slice(from, to)};
    return { placeLabel, optionIndex, rankMatches, matchScore, makeSearchable };`)(esc);

/* ---- labels ------------------------------------------------------------ */

const PLACES = [
  { id: 1, name: 'Kwara', level: 'state', parent: null },
  { id: 2, name: 'Osun', level: 'state', parent: null },
  { id: 3, name: 'Ifelodun', level: 'local', parent: 1 },
  { id: 4, name: 'Ifelodun', level: 'local', parent: 2 },
  { id: 5, name: 'Orphan', level: 'local', parent: 99 },
];

// A state reads by level; a local reads by its state, because the two
// Ifeloduns must not come out as the same string.
assert.strictEqual(placeLabel(PLACES[0], PLACES), 'Kwara · state');
assert.strictEqual(placeLabel(PLACES[2], PLACES), 'Ifelodun · Kwara');
assert.notStrictEqual(placeLabel(PLACES[2], PLACES), placeLabel(PLACES[3], PLACES));
// A local whose state is missing from the list still gets a label.
assert.strictEqual(placeLabel(PLACES[4], PLACES), 'Orphan · local');

/* ---- ranking ----------------------------------------------------------- */

// Exact, then prefix, then word start, then mid-word, then subsequence.
assert.strictEqual(matchScore('Kwara · state', 'kwara · state'), 0);
assert.strictEqual(matchScore('Kwara · state', 'kwa'), 1);
assert.strictEqual(matchScore('Ifelodun · Kwara', 'kwara'), 2, 'after a separator is a word start');
assert.strictEqual(matchScore('Ifelodun · Kwara', 'elo'), 3, 'mid-word is worse than a word start');
assert.strictEqual(matchScore('Ifelodun · Kwara', 'ifkw'), 4, 'fuzzy is the last resort');
assert.strictEqual(matchScore('Ifelodun · Kwara', 'zzz'), null);

const LBLS = ['Kwara · state', 'Ifelodun · Kwara', 'Osun · state',
  'Ifelodun · Osun', 'Ikeja · Lagos'];

// An empty query lists everything, untouched.
assert.deepStrictEqual(rankMatches(LBLS, '   '), LBLS);
// The state itself outranks the local governments that merely mention it.
assert.deepStrictEqual(rankMatches(LBLS, 'kwara'), ['Kwara · state', 'Ifelodun · Kwara']);
// Case and stray spaces do not matter.
assert.deepStrictEqual(rankMatches(LBLS, '  IFELODUN '), ['Ifelodun · Kwara', 'Ifelodun · Osun']);
// Typing the state after the local narrows to the one row.
assert.deepStrictEqual(rankMatches(LBLS, 'ifelodun · osun'), ['Ifelodun · Osun']);
// Fuzzy still finds it, and never above a literal match.
assert.deepStrictEqual(rankMatches(LBLS, 'ikj'), ['Ikeja · Lagos']);
assert.strictEqual(rankMatches(LBLS, 'osun')[0], 'Osun · state');
assert.deepStrictEqual(rankMatches(LBLS, 'zzz'), []);

/* ---- the box ----------------------------------------------------------- */

// The blank row is not a choice, and a label is indexed once.
const opts = [
  { value: '', textContent: '' },
  { value: '1', textContent: ' Kwara · state ' },
  { value: '3', textContent: 'Ifelodun · Kwara' },
  { value: '4', textContent: 'Ifelodun · Osun' },
];
assert.deepStrictEqual([...optionIndex({ options: opts })],
  [['Kwara · state', '1'], ['Ifelodun · Kwara', '3'], ['Ifelodun · Osun', '4']]);

const build = (selected = '') => {
  made.length = 0;
  let replaced = null;
  const sel = {
    options: opts, value: selected, name: 'jurisdiction', className: 'badge',
    required: false, attrs: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    hasAttribute(k) { return k in this.attrs; },
    replaceWith: (n) => { replaced = n; },
  };
  sel.setAttribute('aria-label', 'State to work in');
  return { ...makeSearchable(sel, { placeholder: 'All Nigeria' }), replaced };
};

let p = build();
assert.strictEqual(p.box.value, '');
assert.strictEqual(p.hidden.name, 'jurisdiction', 'FormData must read the same name as before');
assert.strictEqual(p.box.className, 'badge');
assert.strictEqual(p.box.placeholder, 'All Nigeria');
assert.strictEqual(p.box.getAttribute('aria-label'), 'State to work in');
assert.strictEqual(p.replaced.className, 'search-select');
assert.deepStrictEqual(p.replaced.children, [p.box, p.menu, p.hidden]);
// The menu stays shut until the box is used.
assert.strictEqual(p.menu.hidden, true);
assert.strictEqual(p.box.getAttribute('aria-expanded'), 'false');

// An id the field already carries comes back as a name, not a number.
assert.strictEqual(build('4').box.value, 'Ifelodun · Osun');

// Typing opens the menu and narrows it; the id waits for a whole label.
p = build();
let changes = 0;
p.hidden.onchange = () => { changes++; };
p.box.value = 'ifelo'; p.box.oninput();
assert.strictEqual(p.menu.hidden, false);
assert.strictEqual(p.box.getAttribute('aria-expanded'), 'true');
assert.strictEqual((p.menu.innerHTML.match(/role="option"/g) || []).length, 2);
assert.ok(!p.menu.innerHTML.includes('Kwara · state'), 'a row that does not match was listed');
assert.strictEqual(p.hidden.value, '', 'a half-typed name resolved to an id');

// Fuzzy typing still finds the row.
p.box.value = 'ifkw'; p.box.oninput();
assert.strictEqual((p.menu.innerHTML.match(/role="option"/g) || []).length, 1);
assert.ok(p.menu.innerHTML.includes('Ifelodun · Kwara'));

// Nothing matches: the menu says so instead of going blank.
p.box.value = 'zzz'; p.box.oninput();
assert.ok(p.menu.innerHTML.includes('No match'));

// Arrow keys walk the matches and Enter takes the one under the cursor.
const key = (k) => p.box.onkeydown({ key: k, preventDefault() {} });
p.box.value = 'ifelo'; p.box.oninput();
key('Enter');
assert.strictEqual(p.hidden.value, '', 'Enter picked a row before one was highlighted');
key('ArrowDown');
assert.ok(p.menu.innerHTML.includes('class="search-opt active"'), 'nothing was highlighted');
key('ArrowDown');
key('Enter');
assert.strictEqual(p.box.value, 'Ifelodun · Osun', 'Enter took the wrong row');
assert.strictEqual(p.hidden.value, '4');
assert.strictEqual(p.menu.hidden, true, 'the menu stayed open after a pick');

// ArrowUp from nothing wraps to the last row.
p.box.value = 'ifelo'; p.box.oninput();
key('ArrowUp'); key('Enter');
assert.strictEqual(p.hidden.value, '4');

// Escape shuts the menu without changing the pick.
p.box.oninput(); key('Escape');
assert.strictEqual(p.menu.hidden, true);

// A label pasted in full resolves without touching the menu.
p.box.value = ' Kwara · state '; p.box.oninput();
assert.strictEqual(p.hidden.value, '1');
// Clearing the box clears the pick rather than keeping the last one.
p.box.value = ''; p.box.oninput();
assert.strictEqual(p.hidden.value, '');
assert.ok(changes > 0, 'the caller was never told the pick had moved');

console.log('places.test.js ok');
