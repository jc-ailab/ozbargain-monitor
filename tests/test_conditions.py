"""Condition chips from captured RSS titles and conservative synthetic cases."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from monitor_core.build import run
from monitors.ozbargain.adapter import Source, merge
from monitors.ozbargain.conditions import condition_chips

FIXTURES = Path(__file__).parent / 'fixtures'


class ConditionTests(unittest.TestCase):
    def test_real_fixture_titles(self):
        items = {i.id: i for i in Source(FIXTURES).fetch()}
        expected = {
            '984332': ['Prime 免运', '自提 C&C', '满 $59 免运'],
            '984324': ['Prime 免运', '满 $59 免运'],
            '984318': ['自提 C&C', '满 $130 免运'],
            '984306': ['满 $150 免运'],
            '984225': ['自提 C&C', '满 $59 免运'],
            '984331': ['即将开始', '返现'],
            '984316': ['需激活'],
            '984252': ['需激活', '返现'],
            '984246': ['会员/定向', '需激活'],
            '984075': ['会员/定向'],
            '984243': ['自提 C&C'],
            '984328': [],  # Command & Conquer is not Click & Collect.
            '984330': [],
        }
        for item_id, labels in expected.items():
            with self.subTest(item_id=item_id, title=items[item_id].title):
                item = items[item_id]
                self.assertEqual(condition_chips(item.title, flags=item.flags), labels)
                self.assertTrue(set(labels) <= set(item.extra['conditions']))

    def test_description_flags_and_deduplication(self):
        self.assertEqual(condition_chips('[Prime] Headphones'), ['需 Prime'])
        self.assertEqual(condition_chips('Members offer', 'Prime members only. Click and Collect. Activate cashback.', ['targeted', 'upcoming']),
                         ['需 Prime', '自提 C&C', '会员/定向', '即将开始', '需激活', '返现'])
        self.assertEqual(condition_chips('Delivery ($0 Prime/$59 Spend)',
                                         'Free shipping on orders over $59. Click & Collect.'),
                         ['Prime 免运', '自提 C&C', '满 $59 免运'])
        self.assertEqual(condition_chips('Members offer', 'Upcoming members offer', ['targeted', 'upcoming']),
                         ['会员/定向', '即将开始'])

    def test_no_shipping_inference_from_spend_or_product_names(self):
        for title in ('Cashback on $100 Spend', '$30 off $150 Spend Voucher',
                      'Metroid Prime 4 $59', 'Prime lens $150', 'Membership software',
                      'Reactive switch', '$0 Gift Card with $150 Order',
                      '+ Delivery ($0 Gift Card with $150 Order)',
                      'Delivery $10 with $150 Order'):
            with self.subTest(title=title):
                labels = condition_chips(title)
                self.assertFalse(any('免运' in label for label in labels))
                self.assertNotIn('需 Prime', labels)
        self.assertEqual(condition_chips('Free delivery', '$150 Order'), [])

    def test_merged_flags_recompute_conditions(self):
        item = Source(FIXTURES).fetch()[0]
        second = copy.deepcopy(item)
        second.flags = ['targeted', 'upcoming']
        result = merge([item, second])[0]
        self.assertIn('会员/定向', result.extra['conditions'])
        self.assertIn('即将开始', result.extra['conditions'])

    def test_conditions_published_with_ai_off(self):
        with tempfile.TemporaryDirectory() as temp, patch('monitor_core.summarize.urlopen') as opening:
            document = run('ozbargain', Path(temp) / 'state', Path(temp) / 'out', FIXTURES)
            opening.assert_not_called()
            rows = {i['id']: i for i in document['items']}
            self.assertIn('满 $59 免运', rows['984332']['conditions'])
            self.assertIsNone(rows['984332']['summary'])
