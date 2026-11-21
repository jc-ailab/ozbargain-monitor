"""Offline checks for tourist access, retention and robots compliance."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from monitors.europe.monitor import PlainText, PublicPages, build
from monitors.europe.sources import SOURCES, STOPS
from scripts.run_europe import run

NOW = datetime(2026, 11, 21, tzinfo=timezone.utc)
NEON = next(source for source in SOURCES if source.key == 'neon')
NEON_PAGE = '26 – 29 November 2026 | 9:00 pm FREE ENTRANCE Reservation required.'
PHARM = next(source for source in SOURCES if source.key == 'pharmacy295')


class EuropeTests(unittest.TestCase):
    def test_itinerary_dates_and_event_window(self):
        self.assertEqual([stop.key for stop in STOPS], [
            'athens', 'tarragona', 'barcelona', 'malaga', 'cadiz', 'valencia', 'palma', 'madrid'
        ])
        result = build(NOW, lambda url: NEON_PAGE, sources=[NEON])
        self.assertEqual(result['items'][0]['dates'], ['2026-11-26'])
        # It is already the 27th in Athens, although it is still the 26th UTC.
        result = build(datetime(2026, 11, 26, 23, tzinfo=timezone.utc),
                       lambda url: self.fail('Past sources must not be fetched'), sources=[NEON])
        self.assertEqual(result['sources'][0]['status'], 'past')
        self.assertEqual(result['items'], [])

    def test_failure_retains_recent_checks_but_changed_terms_drop(self):
        previous = build(NOW, lambda url: NEON_PAGE, sources=[NEON])

        def fail(url):
            raise ValueError('robots.txt HTTP 403')

        result = build(NOW + timedelta(hours=6), fail, previous, [NEON])
        self.assertEqual(result['updated_at'], previous['updated_at'])
        self.assertTrue(result['items'][0]['cached'])
        self.assertEqual(result['sources'][0]['status'], 'error')
        self.assertEqual(build(NOW + timedelta(hours=25), fail, previous, [NEON])['items'], [])
        result = build(NOW, lambda url: 'Event cancelled', previous, [NEON])
        self.assertEqual(result['items'], [])
        self.assertEqual(result['sources'][0]['status'], 'changed')

    def test_pharmacy_needs_guest_pickup_and_real_discount(self):
        offers = ('Άμεσα Διαθέσιμο APIVITA - PROMO PACK CLEANSING FOAM 300ml '
                  'Χαμηλ. τιμή 30 ημ.: 12.28€ Τιμή καταλόγου: 20.14€ 11.49€')
        pages = {
            PHARM.url: offers,
            PHARM.requirements[0][0]: 'δωρεάν Click & Collect στα 5 φαρμακεία μας στην Αττική',
            PHARM.requirements[1][0]: 'Μπορείτε ως επισκέπτης χωρίς να δημιουργήσετε λογαριασμό.',
        }
        data = build(NOW, pages.__getitem__, sources=[PHARM])
        self.assertEqual(data['items'][0]['price'], '€11.49（近 30 日参考低价 €12.28）')
        for url, replacement in [(PHARM.requirements[1][0], 'Account required'),
                                 (PHARM.url, offers.replace('11.49€', '12.28€')),
                                 (PHARM.url, offers.replace('Άμεσα Διαθέσιμο', 'Διαθέσιμο σε 24 με 48 ώρες'))]:
            with self.subTest(replacement=replacement):
                data = build(NOW, {**pages, url: replacement}.__getitem__, sources=[PHARM])
                self.assertEqual(data['items'], [])
                self.assertEqual(data['sources'][0]['status'], 'changed')

    @unittest.skipUnless(sys.version_info >= (3, 14),
                         'Europe production uses Python 3.14 robots wildcard semantics')
    def test_robots_wildcard_excludes_path_and_no_other_requests(self):
        with patch('monitors.europe.monitor.read_public', return_value='User-agent: *\nDisallow: /*/private$') as read:
            with self.assertRaisesRegex(ValueError, '禁止抓取'):
                PublicPages()('https://example.org/item/private')
            self.assertEqual(read.call_count, 1)
            self.assertEqual(read.call_args.args[0], 'https://example.org/robots.txt')

    def test_html_scripts_are_not_offer_evidence(self):
        self.assertEqual(PlainText('<p>Official &amp; public</p><script>FREE ENTRANCE</script>').text,
                         'Official & public')

    def test_runner_reuses_the_snapshot_for_six_hours(self):
        with tempfile.TemporaryDirectory() as root, patch('builtins.print'):
            a = run(root, NOW, fetch=lambda url: NEON_PAGE)
            b = run(root, NOW + timedelta(hours=3), fetch=lambda url: self.fail('Not due'))
            self.assertEqual(a, b)
            self.assertTrue(Path(root, 'data/europe.json').is_file())


if __name__ == '__main__':
    unittest.main()
