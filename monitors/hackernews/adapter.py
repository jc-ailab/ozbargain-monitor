"""HN adapter using the public hnrss frontpage feed."""
import logging
import re
from urllib.parse import parse_qs, urlsplit
from monitor_core.model import Item
from monitor_core.rss import number, plain_text, pubdate, read_feeds, web_url

FEEDS = {'front': ('https://hnrss.org/frontpage', 'hn_frontpage.xml')}


def parse(root, feed='front'):
    result = []
    for node in root.findall('./channel/item'):
        try:
            discussion = web_url(node.findtext('comments', ''))
            item_id = parse_qs(urlsplit(discussion).query)['id'][0]
            if not item_id.isdigit():
                raise ValueError('Invalid id')
            description = plain_text(node.findtext('description', ''))
            def metric(pattern):
                matches = re.findall(pattern, description)
                return number(matches[-1]) if matches else 0
            title = node.findtext('title', '').strip()
            if not title:
                raise ValueError('Missing title')
            result.append(Item(
                id=item_id, source='hackernews', title=title, url=discussion,
                item_url=web_url(node.findtext('link', '')), image='',
                posted_at=pubdate(node.findtext('pubDate', '')),
                metrics={'votes_pos': metric(r'Points:\s*(\d+)'), 'votes_neg': 0,
                         'comments': metric(r'# Comments:\s*(\d+)'), 'clicks': 0},
                extra={'description': description[:300], 'category': 'Hacker News',
                       'events': [], 'on_front_page': True, 'is_free': False,
                       'creator': node.findtext('{http://purl.org/dc/elements/1.1/}creator', '')}))
        except Exception as exc:
            logging.getLogger(__name__).warning('Skipping malformed HN item: %s', exc)
    return result


class Source:
    def __init__(self, fixture_dir=None):
        self.fixture_dir = fixture_dir
        self.feeds = {}

    def fetch(self):
        items, self.feeds = read_feeds(FEEDS, parse, self.fixture_dir)
        return list({item.id: item for item in items}.values())
