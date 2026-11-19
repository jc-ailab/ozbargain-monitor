#!/usr/bin/env python3
"""Verify served pages, local assets, JSON and every literal JS element reference."""
import argparse
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlsplit
from urllib.request import urlopen


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids, self.assets = [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'script' or tag == 'link' and attrs.get('rel') == 'stylesheet':
            src = attrs.get('src') or attrs.get('href', '')
            assert not urlsplit(src).scheme and not src.startswith('//'), 'External script/style: ' + src
            self.assets.append(src)


def check(base):
    def read(path):
        with urlopen(base.rstrip('/') + '/' + path, timeout=10) as response:
            assert response.status == 200, path
            return response.read().decode('utf-8')
    js = read('app.js')
    used = set(re.findall(r"\$\('([^']+)'\)", js))
    for filename, monitor in [('index.html', 'ozbargain'), ('hn.html', 'hackernews')]:
        page = Page(read(filename))
        assert len(page.ids) == len(set(page.ids)), 'Duplicate IDs'
        assert not used - set(page.ids), 'Missing IDs: ' + repr(used - set(page.ids))
        for asset in page.assets:
            read(asset)
        document = json.loads(read('data/' + monitor + '.json'))
        assert document['monitor'] == monitor and isinstance(document['items'], list)
        assert document['stats']['total'] == len(document['items'])
        print(f'PASS {filename}: assets and JSON load; {len(document["items"])} items; all {len(used)} JS IDs exist')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    check(parser.parse_args().base_url)
