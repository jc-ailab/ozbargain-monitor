/* No browser or packages: execute app rendering and events against a small DOM stub. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');

async function check(monitor, storageUnavailable) {
  const page = fs.readFileSync(path.join(root, 'site', monitor === 'ozbargain' ? 'index.html' : 'hn.html'), 'utf8');
  const nodes = {};
  for (const [, id] of page.matchAll(/\bid="([^"]+)"/g)) nodes[id] = {value: id === 'sort' ? 'score' : '', textContent: '', innerHTML: '', hidden: false, checked: false, listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; }, setAttribute() {}, showModal() { this.open = true; }, close() { this.open = false; }, querySelector() { return {focus() {}}; }};
  const document = {body: {dataset: {monitor}}, getElementById(id) { assert.ok(nodes[id], `missing id ${id}`); return nodes[id]; }, listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; }};
  const source = JSON.parse(fs.readFileSync(path.join(process.argv[2], 'data', `${monitor}.json`), 'utf8'));
  const localStorage = {getItem() { if (storageUnavailable) throw Error('denied'); return null; }, setItem() { if (storageUnavailable) throw Error('denied'); }};
  let fail = false;
  const intervals = [];
  const context = vm.createContext({window: {location: {href: 'http://localhost/'}}, document, localStorage, URL, Intl, Date, console, setInterval(fn, ms) { intervals.push(ms); }, fetch: async () => { if (fail) throw Error('offline'); return {ok: true, json: async () => source}; }});
  vm.runInContext(fs.readFileSync(path.join(root, 'site/app.js'), 'utf8'), context);
  await vm.runInContext('load()', context);
  assert.equal(nodes.title.textContent, source.title);
  assert.equal(vm.runInContext('compactNumber(1620)', context), '1.6K');
  assert.equal(vm.runInContext('compactNumber(39.6)', context), '39.6');
  for (const rank of [0, 1]) {
    assert.match(vm.runInContext(`card({...data.items[0], watch_hit: [], in_current_feed: false}, ${rank})`, context), /已离开 feed · 数据截至/);
    assert.doesNotMatch(vm.runInContext(`card({...data.items[0], watch_hit: [], in_current_feed: true}, ${rank})`, context), /已离开 feed/);
  }
  assert.match(nodes['deal-list'].innerHTML, /<article/);
  assert.match(nodes['top-list'].innerHTML, /热度精选/);
  assert.equal(nodes['deal-list'].innerHTML.includes('去商家'), monitor === 'ozbargain');
  assert.ok(intervals.includes(600000));
  assert.ok(intervals.includes(60000));
  assert.equal(vm.runInContext('safeURL("javascript:alert(1)")', context), '');
  assert.equal(vm.runInContext('escapeHTML("<script>")', context), '&lt;script&gt;');
  assert.equal(vm.runInContext('parseKeywords("Apple, Apple，coffee\\nLEGO").join("|")', context), 'Apple|coffee|LEGO');
  nodes.search.value = 'no such fixture item qxvr';
  nodes.search.listeners.input();
  assert.equal(nodes.empty.hidden, false);
  nodes.search.value = '';
  nodes.search.listeners.input();
  const id = source.items[0].id;
  document.listeners.click({target: {closest() { return {dataset: {action: 'favourite', id}}; }}});
  assert.ok(vm.runInContext(`favourites.has(${JSON.stringify(id)})`, context));
  document.listeners.click({target: {closest() { return {dataset: {action: 'hide', id}}; }}});
  assert.equal(nodes['hidden-toggle'].hidden, false);
  assert.equal(vm.runInContext('baseItems().length', context), source.items.length - 1);
  nodes['hidden-toggle'].listeners.click();
  assert.equal(vm.runInContext('baseItems().length', context), source.items.length);
  nodes['settings-open'].listeners.click();
  assert.equal(nodes.settings.open, true);
  nodes.watch.value = 'Nintendo, AI';
  nodes.block.value = 'Nintendo';
  nodes['settings-form'].listeners.submit({preventDefault() {}});
  assert.equal(nodes.settings.open, false);
  assert.ok(vm.runInContext('baseItems().every(i => !i.title.toLowerCase().includes("nintendo") && !i.tags.join(" ").toLowerCase().includes("nintendo"))', context));
  nodes['settings-reset'].listeners.click();
  assert.equal(vm.runInContext('Object.keys(prefs).length', context), 0);
  const before = nodes['deal-list'].innerHTML;
  fail = true;
  await vm.runInContext('load()', context);
  assert.equal(nodes['deal-list'].innerHTML, before);
  assert.match(nodes.notice.textContent, /更新暂时失败/);
  if (storageUnavailable) assert.match(nodes.notice.textContent, /存储不可用/);
  console.log(`PASS ${monitor}: render, filters, settings, favourites, hide, error retention; storage=${!storageUnavailable}`);
}
(async () => { for (const m of ['ozbargain', 'hackernews']) for (const noStore of [false, true]) await check(m, noStore); })().catch(error => { console.error(error); process.exitCode = 1; });
