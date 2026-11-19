/* Shared, dependency-free monitor UI. Source text never enters HTML unescaped. */
'use strict';
const $ = id => document.getElementById(id);
const monitor = document.body.dataset.monitor;
const storageKey = `monitor:${monitor}:v1`;
const tiers = {viral: '爆火', hot: '热门', rising: '升温'};
const filterOptions = [['all', '全部'], ['viral', '爆火'], ['hot', '热门'], ['rising', '升温'], ['burst', '正在爆发'], ['free', '免费'], ['front', '首页'], ['favourites', '收藏'], ['watch', '关注词命中']];
let data = null, filter = 'all', showHidden = false, storageFailed = false;
let prefs = {}, favourites = new Set(), hidden = new Set();
let loadError = false;
try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || '{}');
  if (saved && typeof saved === 'object') {
    prefs = saved.settings && typeof saved.settings === 'object' ? saved.settings : {};
    favourites = new Set(Array.isArray(saved.favourites) ? saved.favourites.filter(x => typeof x === 'string') : []);
    hidden = new Set(Array.isArray(saved.hidden) ? saved.hidden.filter(x => typeof x === 'string') : []);
  }
} catch (_) { storageFailed = true; }

function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify({settings: prefs, favourites: [...favourites], hidden: [...hidden]})); }
  catch (_) { storageFailed = true; }
}
function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, x => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[x]));
}
function safeURL(value) {
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? escapeHTML(u.href) : ''; }
  catch (_) { return ''; }
}
function relative(value) {
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 60000));
  if (!Number.isFinite(minutes)) return '时间未知';
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} 小时前`;
  return `${Math.floor(minutes / 1440)} 天前`;
}
function compactNumber(value) {
  return new Intl.NumberFormat('en', {notation: 'compact', maximumFractionDigits: 1}).format(value);
}
function sydney(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return '尚无成功采样';
  return new Intl.DateTimeFormat('zh-CN', {timeZone: 'Australia/Sydney', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false}).format(new Date(value));
}
function settings() {
  const defaults = {watch: data?.config_public?.watch || [], block: data?.config_public?.block || [], frontOnly: false, showExpired: true, showBlocked: false};
  const result = {...defaults, ...prefs};
  for (const key of ['watch', 'block']) if (!Array.isArray(result[key])) result[key] = defaults[key];
  return result;
}
function hits(item, words) {
  const text = [item.title, ...(item.tags || [])].join(' ').toLowerCase();
  return words.filter(word => typeof word === 'string' && word && text.includes(word.toLowerCase()));
}
function isExpired(item) { return item.flags.includes('expired'); }
function bursting(item) { return !!item.burst?.is_burst; }
function baseItems() {
  const cfg = settings();
  return data.items.map(item => ({...item, watch_hit: hits(item, cfg.watch), blocked: hits(item, cfg.block).length > 0})).filter(item =>
    (showHidden || !hidden.has(item.id)) && (cfg.showBlocked || !item.blocked) &&
    (cfg.showExpired || !isExpired(item)) && (!cfg.frontOnly || item.on_front_page));
}
function selectItems(items, selected, query, order) {
  const matches = {all: () => true, viral: i => i.tier === 'viral', hot: i => i.tier === 'hot', rising: i => i.tier === 'rising', burst: bursting, free: i => i.is_free, front: i => i.on_front_page, favourites: i => favourites.has(i.id), watch: i => i.watch_hit.length > 0};
  const sorters = {score: i => i.score, latest: i => Date.parse(i.posted_at) || 0, votes: i => i.metrics.votes_pos - i.metrics.votes_neg, comments: i => i.metrics.comments, burst: i => i.burst?.raw ?? -Infinity};
  const metric = sorters[order] || sorters.score;
  return items.filter(i => (matches[selected] || matches.all)(i) && [i.title, ...i.tags].join(' ').toLowerCase().includes(query.toLowerCase())).sort((a, b) => Number(isExpired(a)) - Number(isExpired(b)) || metric(b) - metric(a) || a.id.localeCompare(b.id));
}
function sparkline(points) {
  if (!points || points.length < 2) return '<span class="muted">趋势采样中</span>';
  const values = points.map(p => p[1]);
  const low = Math.min(...values), span = Math.max(...values) - low || 1;
  const times = points.map(p => Date.parse(p[0]));
  const duration = times[times.length - 1] - times[0] || 1;
  const coords = values.map((v, n) => `${(2 + (times[n] - times[0]) / duration * 106).toFixed(1)},${(27 - (v - low) / span * 24).toFixed(1)}`).join(' ');
  return `<svg class="sparkline" viewBox="0 0 110 30" role="img" aria-label="净票数趋势：${escapeHTML(values[0])} 到 ${escapeHTML(values[values.length - 1])}"><polyline points="${coords}" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg><span>净票数趋势</span>`;
}
function card(item, rank = 0) {
  const h = escapeHTML, m = item.metrics, net = m.votes_pos - m.votes_neg;
  const chip = (text, css = '') => `<span class="chip ${css}">${h(text)}</span>`;
  const flagLabels = {expired: '过期', upcoming: '即将开始', targeted: '仅限部分用户', 'out-of-stock': '缺货'};
  const chips = (item.tier ? chip(tiers[item.tier], 'tier') : '') + (bursting(item) ? chip('正在爆发', 'burst') : '') + (item.is_free ? chip('免费', 'free') : '') + (item.on_front_page ? chip('首页') : '') + item.flags.map(f => chip(flagLabels[f] || f)).join('') + (item.blocked ? chip('已屏蔽') : '') + (hidden.has(item.id) ? chip('已隐藏') : '') + item.watch_hit.map(w => chip(`关注 · ${w}`, 'tier')).join('');
  const image = safeURL(item.image);
  const title = `<h3><a href="${safeURL(item.url)}" target="_blank" rel="noopener noreferrer">${h(item.title)}</a></h3><div class="chips">${chips}</div>`;
  const score = `<div class="score"><strong>${h(item.score)}</strong><small>热度分 / 100</small></div>`;
  const ai = item.summary ? `<div class="summary"><span class="ai-label">AI 摘要</span>${h(item.summary.one_liner)}${item.summary.caveat ? `<p class="caveat">留意：${h(item.summary.caveat)}</p>` : ''}</div>` : '';
  const jump = item.burst ? `<p class="burst-line">${bursting(item) ? '↗ 正在爆发' : '↗ 最近采样'} · 票数 ${item.burst.delta_votes >= 0 ? '+' : ''}${h(item.burst.delta_votes)} · 评论 ${item.burst.delta_comments >= 0 ? '+' : ''}${h(item.burst.delta_comments)}</p>` : '<p class="sampling">○ 爆发趋势采样中</p>';
  const lastObserved = item.in_current_feed === false ? `<p class="sampling">已离开 feed · 数据截至 ${h(sydney(item.last_seen))}（悉尼）</p>` : '';
  const names = {votes: '票数', comments: '评论', velocity: '增速', clicks: '点击', burst: '爆发'};
  const breakdown = `<details class="breakdown"><summary>这个分数怎么算？</summary><p>对数归一化后按权重相加，最高 100 分。</p>${Object.entries(item.breakdown).map(([key, value]) => `<div class="component"><span>${h(names[key] || key)}</span><progress max="${h(value.weight)}" value="${h(value.points)}" aria-label="${h(names[key] || key)}得分"></progress><span>${h(value.points)} / ${h(value.weight)}</span></div>`).join('')}</details>`;
  const merchant = monitor === 'ozbargain' && safeURL(item.item_url) ? `<a class="merchant" href="${safeURL(item.item_url)}" target="_blank" rel="noopener noreferrer">去商家 ↗</a>` : '';
  const article = monitor === 'hackernews' && safeURL(item.item_url) ? `<a href="${safeURL(item.item_url)}" target="_blank" rel="noopener noreferrer">读原文 ↗</a>` : '';
  return `<article class="card ${rank ? 'top-card' : ''} ${isExpired(item) ? 'expired' : ''}">${rank ? `<div class="card-top"><span class="rank"><b>${rank}</b> 热度精选</span>${score}</div>` : ''}<div class="card-main ${image ? 'has-image' : ''}">${image ? `<img class="thumb" src="${image}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}<div>${title}</div>${rank ? '' : score}</div><div class="metrics"><span>票数 <b>${h(net)}</b></span><span>评论 <b>${h(m.comments)}</b></span>${monitor === 'ozbargain' ? `<span>点击 <b>${h(m.clicks)}</b></span>` : ''}</div>${jump}${lastObserved}${ai}${rank ? '' : `<p class="posted">${h(relative(item.posted_at))}发布${item.category ? ` · ${h(item.category)}` : ''}${item.expiry ? ` · 截止 ${h(sydney(item.expiry))}（悉尼）` : ''}${item.starting ? ` · 开始 ${h(sydney(item.starting))}（悉尼）` : ''}</p><div class="trend-line">${sparkline(item.trend)}</div>${breakdown}`}<div class="card-actions">${merchant}${article}<a href="${safeURL(item.url)}" target="_blank" rel="noopener noreferrer">看帖子 ↗</a><button data-action="favourite" data-id="${h(item.id)}" aria-pressed="${favourites.has(item.id)}" aria-label="${favourites.has(item.id) ? '取消收藏' : '收藏'} ${h(item.title)}">${favourites.has(item.id) ? '★ 已收藏' : '☆ 收藏'}</button><button data-action="hide" data-id="${h(item.id)}">${hidden.has(item.id) ? '取消隐藏' : '隐藏'}</button></div></article>`;
}
function notice() {
  const warnings = [];
  if (loadError) warnings.push('更新暂时失败，继续显示上次读取的数据。');
  if (data && Object.values(data.stats.feeds).some(status => status !== 'ok')) warnings.push('部分数据源暂不可用，已保留上次成功数据。');
  if (data && (!data.generated_at || Date.now() - Date.parse(data.generated_at) > 90 * 60000)) warnings.push('数据已超过 90 分钟未更新或尚未成功采样，请查看原帖确认。');
  if (storageFailed) warnings.push('浏览器存储不可用；本次操作仍可使用，偏好可能无法保留。');
  $('notice').textContent = warnings.join(' ');
  $('notice').hidden = !warnings.length;
}
function render() {
  if (!data) return;
  $('title').textContent = data.title;
  document.title = data.title;
  $('updated').textContent = `更新于 ${sydney(data.generated_at)}（悉尼） · ${data.generated_at ? relative(data.generated_at) : '等待采样'}`;
  const stats = [['total', '帖子总数'], ['viral', '爆火'], ['hot', '热门'], ['rising', '升温'], ['free', '免费'], ['bursting', '正在爆发'], ['avg_score', '平均分'], ['total_votes', '总票数'], ['total_comments', '总评论']];
  $('stats').innerHTML = stats.map(([key, label]) => `<div class="stat ${['viral', 'bursting'].includes(key) ? 'accent' : ''}"><strong>${escapeHTML(compactNumber(data.stats[key]))}</strong><span>${label}</span></div>`).join('');
  $('digest-box').hidden = !data.digest?.text;
  $('digest-text').textContent = data.digest?.text || '';
  $('filters').innerHTML = filterOptions.map(([key, label]) => `<button data-filter="${key}" aria-pressed="${key === filter}">${label}</button>`).join('');
  const base = baseItems();
  const top = [...base].filter(i => !isExpired(i)).sort((a, b) => b.score - a.score).slice(0, 3);
  $('top-section').hidden = !top.length;
  $('top-list').innerHTML = top.map((i, n) => card(i, n + 1)).join('');
  const selected = selectItems(base, filter, $('search').value.trim(), $('sort').value);
  $('count').textContent = `${selected.length} 条`;
  $('deal-list').innerHTML = selected.map(i => card(i)).join('');
  $('empty').hidden = !!selected.length;
  $('empty-text').textContent = data.items.length ? '试试其他筛选，或调整关键词设置。' : '暂时没有可用数据，稍后会自动再试。';
  const hiddenCount = data.items.filter(i => hidden.has(i.id)).length;
  $('hidden-toggle').hidden = !hiddenCount;
  $('hidden-toggle').textContent = `已隐藏 ${hiddenCount} 条 · ${showHidden ? '收起' : '显示'}`;
  $('hidden-toggle').setAttribute('aria-pressed', String(showHidden));
  notice();
  if (new URL(window.location.href).searchParams.get('layoutcheck') === '1') {
    document.documentElement.dataset.overflow = String(document.documentElement.scrollWidth > window.innerWidth);
  }
}
async function load() {
  try {
    const response = await fetch(`data/${monitor}.json`, {cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP');
    const incoming = await response.json();
    if (incoming.monitor !== monitor || !Array.isArray(incoming.items) || !incoming.stats?.feeds || !incoming.config_public) throw new Error('schema');
    data = incoming;
    loadError = false;
    render();
  } catch (_) {
    loadError = true;
    if (data) notice();
    else { $('updated').textContent = '暂时无法读取数据'; $('notice').textContent = '数据尚未就绪，请稍后再试。页面每 10 分钟自动更新。'; $('notice').hidden = false; }
  }
}
function fillSettings() {
  const cfg = settings();
  $('watch').value = cfg.watch.join(', ');
  $('block').value = cfg.block.join(', ');
  $('front-only').checked = cfg.frontOnly;
  $('show-expired').checked = cfg.showExpired;
  $('show-blocked').checked = cfg.showBlocked;
}
function parseKeywords(value) { return [...new Set(value.split(/[,，\n]/).map(s => s.trim()).filter(Boolean))]; }
$('filters').addEventListener('click', event => {
  const button = event.target.closest('[data-filter]');
  if (!button) return;
  filter = button.dataset.filter;
  render();
  // Rendering replaces chip buttons; restore keyboard focus to the selected chip.
  $('filters').querySelector(`[data-filter="${filter}"]`)?.focus({preventScroll: true});
});
$('search').addEventListener('input', render);
$('sort').addEventListener('change', render);
$('hidden-toggle').addEventListener('click', () => { showHidden = !showHidden; render(); });
document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const id = button.dataset.id;
  const set = button.dataset.action === 'favourite' ? favourites : hidden;
  if (set.has(id)) set.delete(id); else set.add(id);
  persist();
  render();
  $('announcement').textContent = '偏好已更新';
});
$('settings-open').addEventListener('click', () => { fillSettings(); $('settings').showModal(); });
$('settings-close').addEventListener('click', () => $('settings').close());
$('settings-form').addEventListener('submit', event => {
  event.preventDefault();
  prefs = {watch: parseKeywords($('watch').value), block: parseKeywords($('block').value), frontOnly: $('front-only').checked, showExpired: $('show-expired').checked, showBlocked: $('show-blocked').checked};
  persist(); render(); $('settings').close();
});
$('settings-reset').addEventListener('click', () => { prefs = {}; showHidden = false; persist(); fillSettings(); render(); });
$('config-link').href = `https://github.com/jc-ailab/ozbargain-monitor/blob/main/monitors/${monitor}/config.json`;
// Retain the last rendered document on network errors. Never reload the full page.
load();
setInterval(load, 10 * 60 * 1000);
setInterval(() => { if (data) { $('updated').textContent = `更新于 ${sydney(data.generated_at)}（悉尼） · ${data.generated_at ? relative(data.generated_at) : '等待采样'}`; notice(); } }, 60 * 1000);
