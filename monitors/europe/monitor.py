"""Recheck public, visitable offers and keep per-source verification visible."""
from dataclasses import asdict
from datetime import date, timedelta
from functools import lru_cache
from html.parser import HTMLParser
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

from monitor_core.model import iso, timestamp
from .sources import SOURCES, STOPS, UNAVAILABLE

AGENT = 'EuropeDealsMonitor'
INTERVAL = timedelta(hours=6)
MAX_STALE = timedelta(hours=24)
STOPS_BY_KEY = {stop.key: stop for stop in STOPS}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirected URL would need its own robots and source admission check.
        return None


def read_public(url, media_type, limit):
    request = Request(url, headers={'User-Agent': AGENT, 'Accept': media_type})
    with build_opener(NoRedirect()).open(request, timeout=10) as response:
        content = response.read(limit + 1)
        if response.headers.get_content_type() != media_type or len(content) > limit:
            raise ValueError('响应类型或大小异常')
        return content.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')


class PublicPages:
    @lru_cache(maxsize=32)
    def robots(self, origin):
        rules = RobotFileParser()
        try:
            body = read_public(origin + '/robots.txt', 'text/plain', 512_000)
        except HTTPError as exc:
            if exc.code not in (404, 410):
                raise ValueError(f'robots.txt HTTP {exc.code}') from exc
            body = ''
        except (OSError, ValueError) as exc:
            raise ValueError('无法核验 robots.txt') from exc
        rules.parse(body.splitlines())
        return rules

    def __call__(self, url):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username:
            raise ValueError('来源必须是公开 HTTPS 页面')
        if not self.robots('https://' + parsed.netloc).can_fetch(AGENT, url):
            raise ValueError('robots.txt 禁止抓取')
        try:
            body = read_public(url, 'text/html', 2_500_000)
        except HTTPError as exc:
            raise ValueError(f'公开页面 HTTP {exc.code}') from exc
        except URLError as exc:
            raise ValueError('公开页面连接失败') from exc
        return PlainText(body).text


class PlainText(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ignored = []
        self.parts = []
        self.feed(html)
        self.close()
        self.text = ' '.join(' '.join(self.parts).split())

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'template', 'noscript'):
            self.ignored.append(tag)

    def handle_endtag(self, tag):
        if self.ignored and self.ignored[-1] == tag:
            self.ignored.pop()

    def handle_data(self, text):
        if not self.ignored and text.strip():
            self.parts.append(text)


def eligible_days(stop, offer, now):
    local = ZoneInfo('Europe/Athens' if stop.country == '希腊' else 'Europe/Madrid')
    today = now.astimezone(local).date()
    result = []
    for first, last in stop.dates():
        start = max(today, first, date.fromisoformat(offer.first))
        end = min(last, date.fromisoformat(offer.last))
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            if day.weekday() in offer.weekdays:
                result.append(day.isoformat())
    return result


def outlet_price(text, _):
    # Read one explicitly paired display price and the same item's RRP.
    # Avoid campaign banners, extra discounts with conditions, and inferred Australian prices.
    amount = r'(\d+(?:[.,]\d{1,2})?)\s*€'
    match = re.search(r'Village price\s*' + amount + r'\s*RRP\s*' + amount, text, re.I)
    if not match:
        return None
    village, rrp = (float(value.replace(',', '.')) for value in match.groups())
    if 0 < village < rrp:
        return f'官网示例 €{village:g}（原标价 €{rrp:g}）'
    return None


def pharmacy_price(text, evidence):
    amount = r'(\d+(?:[.,]\d{1,2})?)\s*€'
    match = re.search(evidence + r'[^€]{0,65}Χαμηλ\. τιμή 30 ημ\.:\s*' + amount
                      + r'\s*Τιμή καταλόγου:\s*' + amount + r'\s*' + amount, text, re.I)
    if not match:
        return None
    recent, _, price = (float(value.replace(',', '.')) for value in match.groups())
    if 0 < price < recent:
        return f'€{price:.2f}（近 30 日参考低价 €{recent:.2f}）'
    return None


PRICING = {'outlet': outlet_price, 'pharmacy': pharmacy_price}


def keep_recent(previous, source, now):
    for item in previous.get('items', []):
        if item['source'] != source.key or now - timestamp(item['verified_at']) > MAX_STALE:
            continue
        for offer in source.offers:
            if offer.title == item['title']:
                dates = eligible_days(STOPS_BY_KEY[source.stop], offer, now)
                if dates:
                    yield {**item, 'dates': dates, 'cached': True}


def build(now, fetch, previous=None, sources=SOURCES):
    previous = previous or {}
    items, health = [], []
    successful = False
    for source in sources:
        stop = STOPS_BY_KEY[source.stop]
        candidates = [(offer, eligible_days(stop, offer, now)) for offer in source.offers]
        candidates = [(offer, dates) for offer, dates in candidates if dates]
        row = {'id': source.key, 'stop': source.stop, 'name': source.name, 'url': source.url, 'count': 0, 'status': 'past'}
        health.append(row)
        if not candidates:
            continue
        try:
            content = fetch(source.url)
            requirements_met = all(re.search(pattern, fetch(url), re.I)
                                   for url, pattern in source.requirements)
        except (OSError, ValueError) as exc:
            cached = list(keep_recent(previous, source, now))
            items.extend(cached)
            row.update(status='error', detail=str(exc), count=len(cached))
            continue

        for offer, days in candidates:
            if not requirements_met or not re.search(offer.evidence, content, re.I):
                continue
            price = offer.price or PRICING[offer.pricing](content, offer.evidence)
            if price:
                items.append(dict(source=source.key, stop=source.stop, title=offer.title,
                                  category=offer.category, price=price, reason=offer.reason,
                                  access=offer.access, url=source.url, dates=days,
                                  verified_at=iso(now), priority=offer.priority, cached=False))
                row['count'] += 1
        if row['count'] != len(candidates):
            row.update(status='changed', detail='原页条件有变或无法确认，已隐藏相应条目')
        else:
            row['status'] = 'ok'
        successful |= bool(row['count'])

    return {
        'monitor': 'europe', 'checked_at': iso(now),
        'updated_at': iso(now) if successful else previous.get('updated_at'),
        'stops': [{**asdict(stop), 'windows': [list(window) for window in stop.windows]} for stop in STOPS],
        'items': items,
        'sources': health,
        'unavailable': [{'name': name, 'url': url, 'detail': detail} for name, url, detail in UNAVAILABLE],
    }
