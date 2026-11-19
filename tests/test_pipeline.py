import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from xml.etree import ElementTree as ET

from monitor_core import scoring, store, summarize
from monitor_core.build import run, recover
from monitor_core.model import iso
from monitor_core.rss import FeedClient
from monitors.ozbargain.adapter import parse, merge, Source
from monitors.hackernews.adapter import Source as HNSource

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'
NOW = datetime(2026, 11, 20, 0, tzinfo=timezone.utc)
CONFIG = json.loads((ROOT / 'monitors/ozbargain/config.json').read_text())


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.deals = parse(ET.parse(FIXTURES / 'deals_feed.xml').getroot())
        self.front = parse(ET.parse(FIXTURES / 'front_feed.xml').getroot(), 'front')

    def test_fixture_parsing(self):
        self.assertEqual(len(self.deals), 30)
        self.assertEqual(len(self.front), 20)
        item = self.deals[0]
        self.assertEqual(item.id, '984332')
        self.assertEqual(item.metrics, {'votes_pos': 2, 'votes_neg': 0, 'comments': 0, 'clicks': 79})
        self.assertTrue(item.item_url.startswith('https://www.amazon.com.au/'))
        self.assertNotIn('/goto/', item.item_url)
        self.assertEqual(item.posted_at, '2026-11-19T19:48:32Z')
        self.assertEqual(item.extra['category'], 'Toys & Kids')
        self.assertIn('Black Friday', item.extra['events'])
        self.assertIn('upcoming', self.deals[1].flags)
        self.assertLessEqual(len(item.extra['description']), 300)
        self.assertNotIn('<', item.extra['description'])
        self.assertTrue(any(i.extra['is_free'] for i in self.deals + self.front))

    def test_merge(self):
        result = merge(self.deals + self.front)
        self.assertEqual(len(result), len({i.id for i in self.deals + self.front}))
        a, b = copy.deepcopy(self.deals[0]), copy.deepcopy(self.deals[0])
        b.metrics['votes_pos'] = 99
        b.extra['on_front_page'] = True
        merged = merge([a, b])[0]
        self.assertEqual(merged.metrics['votes_pos'], 99)
        self.assertTrue(merged.extra['on_front_page'])

    def test_bad_item_and_missing_metrics(self):
        root = ET.parse(FIXTURES / 'deals_feed.xml').getroot()
        first = root.find('./channel/item')
        first.find('pubDate').text = 'broken'
        self.assertEqual(len(parse(root)), 29)
        first.find('pubDate').text = 'Fri, 20 Nov 2026 06:48:32'
        self.assertEqual(len(parse(root)), 29)
        first.find('pubDate').text = 'Fri, 20 Nov 2026 06:48:32 +1100'
        first.remove(first.find('{https://www.ozbargain.com.au}meta'))
        self.assertEqual(parse(root)[0].metrics['clicks'], 0)

    def test_free_and_flags(self):
        root = ET.parse(FIXTURES / 'deals_feed.xml').getroot()
        for title in ('FREE Coffee', 'Coffee $0 Today', 'Coffee'):
            root.find('./channel/item/title').text = title
            self.assertEqual(parse(root)[0].extra['is_free'], title != 'Coffee')
        first = root.find('./channel/item')
        ET.SubElement(first, 'category', domain='https://www.ozbargain.com.au/cat/freebies').text = 'Freebies'
        ET.SubElement(first, '{https://www.ozbargain.com.au}title-msg', type='expired')
        self.assertTrue(parse(root)[0].extra['is_free'])
        self.assertIn('expired', parse(root)[0].flags)

    def test_hn(self):
        source = HNSource(FIXTURES)
        items = source.fetch()
        self.assertEqual(len(items), 20)
        self.assertTrue(all(i.id.isdigit() for i in items))
        self.assertTrue(any(i.metrics['votes_pos'] > 0 and i.metrics['comments'] > 0 for i in items))
        self.assertEqual(source.feeds, {'front': 'ok'})

    def test_feed_failure_isolated(self):
        with patch('monitor_core.rss.FeedClient.get', side_effect=[OSError('offline'), (FIXTURES / 'front_feed.xml').read_bytes()]):
            source = Source()
            self.assertEqual(len(source.fetch()), 20)
            self.assertTrue(source.feeds['deals'].startswith('error:'))
            self.assertEqual(source.feeds['front'], 'ok')

    def test_request_budget(self):
        client = FeedClient()
        with patch('monitor_core.rss.build_opener') as opener:
            opener.return_value.open.side_effect = OSError('offline')
            with self.assertRaises(RuntimeError):
                client.get('https://www.ozbargain.com.au/deals/feed')
            with self.assertRaises(RuntimeError):
                client.get('https://www.ozbargain.com.au/feed')
            self.assertEqual(opener.return_value.open.call_count, 2)
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 20)


class ScoreTests(unittest.TestCase):
    def item(self, votes=0):
        item = Source(FIXTURES).fetch()[0].to_dict()
        item['metrics'] = {'votes_pos': votes, 'votes_neg': 0, 'comments': 0, 'clicks': 0}
        item['posted_at'] = iso(NOW - timedelta(hours=1))
        return item

    def test_bounds_monotonicity(self):
        values = [scoring.score(self.item(v), [], CONFIG, NOW)['score'] for v in (0, 1, 10, 100, 1000)]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(0 <= v <= 100 for v in values))
        self.assertEqual(scoring.score(self.item(-10), [], CONFIG, NOW)['score'], 0)
        item = self.item(10**9)
        item['metrics'].update(comments=10**9, clicks=10**9)
        self.assertLessEqual(scoring.score(item, [], CONFIG, NOW)['score'], 100)

    def test_all_score_threshold_tiers(self):
        for votes, comments, clicks, expected in [(35, 150, 5000, 'viral'), (10, 30, 5000, 'hot'), (1, 150, 5000, 'rising')]:
            item = self.item(votes)
            item['metrics'].update(comments=comments, clicks=clicks)
            self.assertEqual(scoring.score(item, [], CONFIG, NOW)['tier'], expected)
        self.assertIsNone(scoring.score(self.item(), [], CONFIG, NOW)['tier'])

    def test_tiers_and_keywords(self):
        self.assertEqual(scoring.score(self.item(200), [], CONFIG, NOW)['tier'], 'viral')
        self.assertEqual(scoring.score(self.item(60), [], CONFIG, NOW)['tier'], 'hot')
        item = self.item(1)
        item['title'] = 'Apple MacBook'
        item['tags'] = ['Student']
        config = copy.deepcopy(CONFIG)
        config.update(watch=['apple', 'STUDENT'], block=['macbook'])
        result = scoring.score(item, [], config, NOW)
        self.assertEqual(result['watch_hit'], ['apple', 'STUDENT'])
        self.assertTrue(result['blocked'])
        self.assertIsNone(scoring.score(self.item(), [], CONFIG, NOW)['burst'])

    def points(self, values, step=30):
        return [[iso(NOW - timedelta(minutes=(len(values) - n - 1) * step)), v, 0, 0, 0] for n, v in enumerate(values)]

    def test_burst(self):
        self.assertIsNone(scoring.burst([], CONFIG['thresholds']))
        self.assertTrue(scoring.burst(self.points([0, 1, 2, 40]), CONFIG['thresholds'])['is_burst'])
        self.assertFalse(scoring.burst(self.points([0, 10, 20, 30]), CONFIG['thresholds'])['is_burst'])
        self.assertIsNone(scoring.burst(self.points([1, 50], 100), CONFIG['thresholds']))
        self.assertIsNone(scoring.burst(self.points([1, 50], 10), CONFIG['thresholds']))

    def test_store_prune_and_unseen(self):
        state = {'items': {}}
        item = Source(FIXTURES).fetch()[0]
        store.update(state, [item], NOW - timedelta(days=8))
        store.update(state, [], NOW)
        self.assertEqual(state['items'], {})
        store.update(state, [item], NOW)
        store.update(state, [], NOW + timedelta(minutes=30))
        self.assertEqual(len(state['items'][item.id]['snapshots']), 1)
        for n in range(120):
            store.update(state, [item], NOW + timedelta(minutes=30 * (n + 1)))
        points = state['items'][item.id]['snapshots']
        self.assertEqual(len(points), 96)
        self.assertEqual(points[0][0], iso(NOW))
        self.assertEqual(points[-1][0], iso(NOW + timedelta(hours=60)))
        self.assertEqual(len(store.sample(points, 24)), 24)


class SummaryTests(unittest.TestCase):
    def rows(self):
        row = Source(FIXTURES).fetch()[0].to_dict()
        row.update(row.pop('extra'))
        row.update(score=75, tier='viral', watch_hit=[], blocked=False, summary=None, burst=None, category='Toys')
        state = {'items': {row['id']: {'summary': None}}}
        return [row], state

    def test_success_and_digest_cache(self):
        rows, state = self.rows()
        with patch('monitor_core.summarize.complete', side_effect=[{'one_liner': '玩具好价', 'caveat': '需会员'}, {'text': '本期玩具值得关注'}]) as call:
            summarize.enrich(rows, state, CONFIG, 'token')
            self.assertEqual(call.call_count, 2)
            self.assertEqual(state['items'][rows[0]['id']]['summary']['one_liner'], '玩具好价')
            summarize.enrich(rows, state, CONFIG, 'token')
            self.assertEqual(call.call_count, 2)

    def test_failures_and_absent_token(self):
        for failure in (ValueError('bad JSON'), HTTPError('url', 429, 'limit', {}, None)):
            rows, state = self.rows()
            with patch('monitor_core.summarize.complete', side_effect=failure):
                summarize.enrich(rows, state, CONFIG, 'token')
            self.assertIsNone(state['items'][rows[0]['id']]['summary'])
            if hasattr(failure, 'close'):
                failure.close()
        rows, state = self.rows()
        with patch('monitor_core.summarize.complete') as call:
            summarize.enrich(rows, state, CONFIG, '')
            call.assert_not_called()
        self.assertFalse(summarize.valid_summary({'one_liner': '长' * 41, 'caveat': ''}))

    def test_limits_fallback_and_invalid_json(self):
        rows, state = self.rows()
        config = copy.deepcopy(CONFIG)
        config['summary']['summary_max_per_run'] = 1
        second = copy.deepcopy(rows[0])
        second['id'] = 'another'
        state['items']['another'] = {'summary': None}
        rows.append(second)
        with patch('monitor_core.summarize.complete', side_effect=[ValueError('model unavailable'), {'one_liner': '好价', 'caveat': ''}, {'text': '今日速览'}]) as call:
            summarize.enrich(rows, state, config, 'token')
            self.assertEqual(call.call_count, 3)
            self.assertEqual(sum(bool(row['summary']) for row in rows), 1)
            self.assertEqual(call.call_args_list[1].args[1], config['summary']['fallback_models'][0])
        rows, state = self.rows()
        with patch('monitor_core.summarize.complete', return_value={'one_liner': '长' * 41, 'caveat': ''}):
            summarize.enrich(rows, state, CONFIG, 'token')
        self.assertIsNone(state['items'][rows[0]['id']]['summary'])
        self.assertNotIn('digest', state)

    def test_http_transport(self):
        response = {'choices': [{'message': {'content': '{"one_liner":"好价","caveat":""}'}}]}
        with patch('monitor_core.summarize.urlopen') as opening:
            opening.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            result = summarize.complete('secret', 'model', 'prompt')
            self.assertEqual(result['one_liner'], '好价')
            request = opening.call_args.args[0]
            self.assertEqual(json.loads(request.data)['temperature'], 0.2)


class PipelineTests(unittest.TestCase):
    def test_end_to_end_schema_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'GITHUB_TOKEN': ''}):
            state_dir, out = Path(temp) / 'state', Path(temp) / 'out'
            document = run('ozbargain', state_dir, out, FIXTURES, NOW)
            self.assertTrue({'monitor', 'title', 'generated_at', 'stats', 'digest', 'config_public', 'items'} <= document.keys())
            self.assertTrue({'first_seen', 'category', 'events', 'flags', 'score', 'tier', 'trend', 'summary', 'breakdown', 'burst', 'watch_hit', 'blocked'} <= document['items'][0].keys())
            self.assertTrue(all(len(i['trend']) <= 24 for i in document['items']))
            destination = out / 'data/ozbargain.json'
            self.assertLess(destination.stat().st_size, 1_500_000)
            self.assertEqual(json.loads(destination.read_text())['stats']['feeds'], {'deals': 'ok', 'front': 'ok'})
            with patch('monitor_core.rss.FeedClient.get', side_effect=OSError('offline')):
                fallback = run('ozbargain', state_dir, out, now=NOW + timedelta(minutes=30))
            self.assertEqual(len(fallback['items']), len(document['items']))
            self.assertEqual(fallback['generated_at'], document['generated_at'])
            self.assertTrue(all(v.startswith('error:') for v in fallback['stats']['feeds'].values()))
            recovered = recover('ozbargain', state_dir, out, ValueError())
            self.assertIn('pipeline', recovered['stats']['feeds'])

    def test_ai_exception_and_invalid_stored_item_are_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('monitor_core.summarize.enrich', side_effect=RuntimeError('AI unavailable')):
                document = run('ozbargain', temp + '/state', temp + '/out', FIXTURES, NOW)
            self.assertEqual(document['stats']['total'], 48)
            state_path = Path(temp) / 'state/state.json'
            state = store.load(state_path)
            invalid = copy.deepcopy(next(iter(state['items'].values())))
            invalid['item']['posted_at'] = 'broken'
            invalid['item']['id'] = 'invalid'
            state['items']['invalid'] = invalid
            store.save(state_path, state)
            document = run('ozbargain', temp + '/state', temp + '/out', FIXTURES, NOW)
            self.assertEqual(document['stats']['total'], 48)

    def test_fixture_api_offline_even_with_token(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'GITHUB_TOKEN': 'must-not-be-used'}), patch('monitor_core.summarize.complete') as call:
            run('ozbargain', temp + '/state', temp + '/out', FIXTURES, NOW)
            call.assert_not_called()

    def test_cli_fixtures(self):
        with tempfile.TemporaryDirectory() as temp:
            for monitor in ('ozbargain', 'hackernews'):
                command = [sys.executable, str(ROOT / 'scripts/run.py'), '--monitor', monitor, '--fixtures', '--state-dir', temp + '/' + monitor, '--out', temp + '/out']
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads((Path(temp) / 'out/data' / (monitor + '.json')).read_text())
                self.assertGreater(data['stats']['total'], 0)


if __name__ == '__main__':
    unittest.main()
