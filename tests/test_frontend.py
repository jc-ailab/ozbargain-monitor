from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.assets, self.external = [], [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'script' or tag == 'link' and attrs.get('rel') == 'stylesheet':
            src = attrs.get('src') or attrs.get('href', '')
            (self.external if urlsplit(src).scheme or src.startswith('//') else self.assets).append(src)


class FrontendTests(unittest.TestCase):
    def test_assets_ids_and_no_external_code(self):
        js = (ROOT / 'site/app.js').read_text()
        used = set(re.findall(r"\$\('([^']+)'\)", js))
        self.assertGreater(len(used), 20)
        for path in (ROOT / 'site').glob('*.html'):
            page = Page(path.read_text())
            self.assertEqual(page.external, [], path)
            self.assertEqual(len(page.ids), len(set(page.ids)), path)
            self.assertEqual(used - set(page.ids), set(), path)
            for asset in page.assets:
                self.assertTrue((path.parent / asset).is_file(), asset)
            self.assertIn('name="viewport"', path.read_text())
            self.assertIn('lang="zh-CN"', path.read_text())

    def test_europe_local_assets_and_navigation(self):
        path = ROOT / 'site/europe/index.html'
        page = Page(path.read_text())
        js = (path.parent / 'europe.js').read_text()
        self.assertEqual(page.external, [])
        self.assertEqual(len(page.ids), len(set(page.ids)))
        self.assertLessEqual(set(re.findall(r"byId\('([^']+)'\)", js)), set(page.ids))
        self.assertIn("fetch('../data/europe.json'", js)
        self.assertIn('name="viewport"', path.read_text())
        for asset in page.assets:
            self.assertTrue((path.parent / asset).is_file(), asset)
        for filename in ('index.html', 'hn.html'):
            self.assertIn('href="europe/"', (ROOT / 'site' / filename).read_text())

    def test_responsive_and_dark_styles(self):
        css = (ROOT / 'site/style.css').read_text()
        self.assertIn('prefers-color-scheme:dark', css)
        self.assertIn('max-width:480px', css)
        self.assertIn('repeat(3,minmax(0,1fr))', css)
        self.assertIn('min-height:36px', css)
        self.assertNotIn('@import', css)
        self.assertNotRegex(css, r'url\(\s*[\'"]?https?://')
