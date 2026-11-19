"""Shared RSS, safe text extraction and bounded HTTP transport."""
import logging
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener
from xml.etree import ElementTree as ET
from .model import iso

LOG = logging.getLogger(__name__)
USER_AGENT = 'ozbargain-monitor/1.0 (+https://github.com/jc-ailab/ozbargain-monitor)'
MAX_FEED_BYTES = 4_000_000


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = TextParser()
    parser.feed(value)
    return ' '.join(' '.join(parser.parts).split())


def web_url(value):
    parts = urlsplit(value or '')
    return value if parts.scheme in ('http', 'https') and parts.netloc else ''


def pubdate(value):
    return iso(parsedate_to_datetime(value))


def number(value):
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError):
        return 0


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect must never silently spend another feed request or hit /goto/.
        return None


class FeedClient:
    def __init__(self, budget=2):
        self.remaining = budget

    def get(self, url):
        error = None
        for _ in range(2):
            if self.remaining <= 0:
                break
            self.remaining -= 1
            try:
                request = Request(url, headers={'User-Agent': USER_AGENT})
                with build_opener(NoRedirect).open(request, timeout=20) as response:
                    data = response.read(MAX_FEED_BYTES + 1)
                if len(data) > MAX_FEED_BYTES:
                    raise ValueError('Feed exceeds size limit')
                return data
            except Exception as exc:
                error = exc
                LOG.warning('Feed request failed: %s (%s)', url, type(exc).__name__)
        raise RuntimeError(type(error).__name__ if error else 'request budget exhausted')


def read_feeds(feeds, parser, fixture_dir=None):
    from pathlib import Path
    client = FeedClient(budget=2)
    items, health = [], {}
    for name, (url, fixture) in feeds.items():
        try:
            raw = (Path(fixture_dir) / fixture).read_bytes() if fixture_dir else client.get(url)
            parsed = parser(ET.fromstring(raw), name)
            if not parsed:
                raise ValueError('No valid RSS items')
            items.extend(parsed)
            health[name] = 'ok'
        except Exception as exc:
            LOG.warning('Feed %s unavailable: %s', name, exc)
            health[name] = 'error: ' + str(exc)[:120]
    return items, health
