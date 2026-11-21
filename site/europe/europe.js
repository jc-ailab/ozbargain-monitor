'use strict';

const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
};

const link = (text, url, className) => {
  const anchor = element('a', text, className);
  if (/^(https:\/\/|#[a-z]+$)/.test(url)) anchor.href = url;
  return anchor;
};

const byId = (id) => document.getElementById(id);
const dayLabel = (day) => day.slice(5).replace(/^0/, '').replace(/-0?/, '/');
const windowLabel = ([first, last]) => first === last ? dayLabel(first) : `${dayLabel(first)}–${dayLabel(last)}`;
const localTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Europe/Madrid', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
});

function card(item) {
  const article = element('article', '', 'card');
  const meta = element('div', '', 'meta');
  meta.append(element('span', item.category), element('strong', item.price, 'price'));
  article.append(meta, element('h4', item.title), element('p', item.reason, 'reason'));
  article.append(element('p', `${item.dates.map(dayLabel).join('、')} · ${item.access}${item.cached ? ' · 上次核验' : ''}`, 'subtle'));
  article.append(link('查看原页 ↗', item.url, 'card-link'));
  return article;
}

function render(data) {
  const route = byId('route');
  const cities = byId('cities');
  route.replaceChildren();
  cities.replaceChildren();
  let country;
  let countryName;
  for (const stop of data.stops) {
    if (stop.country !== countryName) {
      countryName = stop.country;
      country = element('section', '', 'country');
      country.append(element('h2', countryName));
      route.append(country);
    }
    cities.append(link(stop.name, '#' + stop.key));
    const section = element('section', '', 'city');
    section.id = stop.key;
    const heading = element('div', '', 'city-head');
    heading.append(element('h3', stop.name), element('p', stop.windows.map(windowLabel).join('、')));
    section.append(heading);
    if (stop.note) section.append(element('p', stop.note, 'subtle'));
    const items = data.items.filter((item) => item.stop === stop.key)
      .sort((a, b) => b.priority - a.priority || a.dates[0].localeCompare(b.dates[0]));
    const grid = element('div', '', 'cards');
    const states = data.sources.filter((source) => source.stop === stop.key);
    const past = states.length && states.every((source) => source.status === 'past');
    if (items.length) grid.append(...items.map(card));
    else grid.append(element('p', past ? '这个城市的优惠窗口已过。' : '暂未核验到符合停留日期的优惠。', 'subtle'));
    section.append(grid);
    country.append(section);
  }

  const labels = {ok: '核验通过', changed: '条件待复核', error: '抓取失败', past: '没有余下适用日期'};
  const sources = byId('sources');
  sources.replaceChildren();
  for (const source of [...data.sources, ...data.unavailable]) {
    const line = element('li');
    line.append(link(source.name, source.url));
    const count = source.status ? ` · ${labels[source.status]} · ${source.count} 条` : '';
    line.append(document.createTextNode(count + (source.detail ? ' · ' + source.detail : '')));
    sources.append(line);
  }
  byId('source-health').hidden = false;

  const checked = localTime.format(new Date(data.checked_at));
  let update = `最近核验 ${checked}（西班牙时间） · 每 6 小时复查`;
  if (!data.updated_at) update = `最近尝试 ${checked}（西班牙时间） · 暂无成功核验`;
  else if (data.checked_at !== data.updated_at) {
    update = `最近尝试 ${checked} · 上次成功 ${localTime.format(new Date(data.updated_at))}（西班牙时间）`;
  }
  byId('updated').textContent = update;
  const warnings = [];
  if (data.sources.some((source) => ['error', 'changed'].includes(source.status))) {
    warnings.push('部分来源读取失败或条件有变。展开页面底部查看。');
  }
  if (Date.now() - Date.parse(data.checked_at) > 9 * 3600 * 1000) {
    warnings.push('页面超过 9 小时未刷新。请点原页确认。');
  }
  showNotice(warnings.join(' '));
}

function showNotice(message) {
  const notice = byId('notice');
  notice.textContent = message;
  notice.hidden = !message;
}

async function load() {
  try {
    const response = await fetch('../data/europe.json', {cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    render(await response.json());
  } catch {
    byId('updated').textContent = '暂时读不到新数据';
    showNotice('优惠数据加载失败，可能还没有首次发布。请稍后刷新。');
  }
}

load();
setInterval(load, 10 * 60 * 1000);
