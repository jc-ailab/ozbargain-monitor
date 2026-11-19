"""Official RSS only; never follow merchant or OzBargain redirect links."""
import logging
import re
from urllib.parse import urlsplit
from monitor_core.model import Item
from monitor_core.rss import number, plain_text, pubdate, read_feeds, web_url
from .conditions import condition_chips

NS = {'ozb': 'https://www.ozbargain.com.au', 'dc': 'http://purl.org/dc/elements/1.1/'}
FEEDS = {
    'deals': ('https://www.ozbargain.com.au/deals/feed', 'deals_feed.xml'),
    'front': ('https://www.ozbargain.com.au/feed', 'front_feed.xml'),
}


def free_deal(title, free_category=False):
    if free_category:
        return True
    # Remove even nested parentheses, including alternate prices and pickup fees.
    main = title
    while re.search(r'\([^()]*\)', main):
        main = re.sub(r'\([^()]*\)', ' ', main)
    main = re.split(r'\+\s*(?:delivery|shipping|postage)\b', main, maxsplit=1, flags=re.I)[0]
    if re.search(r'\bfree\b(?![\s:–—-]*(?:delivery|shipping|postage|returns)\b)', main, re.I):
        return True
    # The first advertised price is the main price, not a later $0 add-on.
    price = re.search(r'\$(\d+(?:\.\d+)?)(?![\d.])', main)
    return bool(price and price.group(1) in ('0', '0.00'))


def parse(root, feed='deals'):
    result = []
    for node in root.findall('./channel/item'):
        try:
            url = web_url(node.findtext('link', ''))
            match = re.fullmatch(r'/node/(\d+)/?', urlsplit(url).path)
            if not match or urlsplit(url).hostname != 'www.ozbargain.com.au':
                raise ValueError('Invalid node URL')
            title = node.findtext('title', '').strip()
            if not title:
                raise ValueError('Missing title')
            meta = node.find('ozb:meta', NS)
            attrs = meta.attrib if meta is not None else {}
            category, tags, events, free_category = '', [], [], False
            for cat in node.findall('category'):
                domain, text = cat.get('domain', ''), cat.text or ''
                if '/cat/' in domain:
                    category = text
                    free_category |= domain.rstrip('/').endswith('/freebies') or text.strip().casefold() == 'freebies'
                elif '/tag/' in domain:
                    tags.append(text)
                elif '/event/' in domain:
                    events.append(text)
            result.append(Item(
                id=match[1], source='ozbargain', title=title, url=url,
                item_url=web_url(attrs.get('url', '')), image=web_url(attrs.get('image', '')),
                posted_at=pubdate(node.findtext('pubDate', '')),
                metrics={key: number(attrs.get(attr)) for key, attr in {
                    'votes_pos': 'votes-pos', 'votes_neg': 'votes-neg',
                    'comments': 'comment-count', 'clicks': 'click-count'}.items()},
                tags=tags, flags=[n.get('type') for n in node.findall('ozb:title-msg', NS) if n.get('type')],
                extra={'description': plain_text(node.findtext('description', ''))[:300],
                       'category': category, 'events': events,
                       'creator': node.findtext('dc:creator', '', NS),
                       'expiry': attrs.get('expiry', ''), 'starting': attrs.get('starting', ''),
                       'on_front_page': feed == 'front',
                       'is_free': free_deal(title, free_category)}))
            item = result[-1]
            item.extra['conditions'] = condition_chips(title, item.extra['description'], item.flags)
        except Exception as exc:
            logging.getLogger(__name__).warning('Skipping malformed RSS item: %s', exc)
    return result


def merge(items):
    merged = {}
    for item in items:
        if item.id not in merged:
            merged[item.id] = item
            continue
        old = merged[item.id]
        old.metrics = {key: max(old.metrics.get(key, 0), item.metrics.get(key, 0))
                       for key in old.metrics.keys() | item.metrics.keys()}
        old.extra['on_front_page'] |= item.extra['on_front_page']
        old.flags = sorted(set(old.flags + item.flags))
        old.tags = list(dict.fromkeys(old.tags + item.tags))
        old.extra['conditions'] = condition_chips(old.title, old.extra['description'], old.flags)
    return list(merged.values())


class Source:
    def __init__(self, fixture_dir=None):
        self.fixture_dir = fixture_dir
        self.feeds = {}

    def fetch(self):
        items, self.feeds = read_feeds(FEEDS, parse, self.fixture_dir)
        return merge(items)
