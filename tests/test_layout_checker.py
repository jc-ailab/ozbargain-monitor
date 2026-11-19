"""Offline checks that layout evidence fails closed; no Chrome or server needed."""
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.check_layout import check_result


class LayoutCheckerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.shot = Path(self.directory.name) / 'capture.png'
        # Only the PNG header is needed for the width assertion.
        self.shot.write_bytes(b'\x89PNG\r\n\x1a\n' + struct.pack('!I', 13) + b'IHDR'
                              + struct.pack('!II', 375, 2400))
        self.dom = ('<html data-viewport="375" data-overflow="false" data-cards="4" '
                    'data-scores="true" data-stats="true" data-actions="true" '
                    'data-saved-actions="true" data-images="true"></html>')

    def test_actual_iframe_width_overrides_plausible_dom_and_png(self):
        check_result(self.dom, 375, 375, self.shot)
        with self.assertRaisesRegex(ValueError, 'innerWidth=500, expected 375'):
            check_result(self.dom, 500, 375, self.shot)
        with self.assertRaisesRegex(ValueError, 'layout assertions failed'):
            check_result(self.dom.replace('data-viewport="375"', 'data-viewport="500"'),
                         375, 375, self.shot)

    def test_iframe_overflow_and_missing_evidence_fail(self):
        for old, new in [('data-overflow="false"', 'data-overflow="true"'),
                         ('data-overflow="false"', ''),
                         ('data-saved-actions="true"', 'data-saved-actions="false"'),
                         ('data-cards="4"', 'data-cards="0"')]:
            with self.subTest(change=new), self.assertRaisesRegex(ValueError, 'layout assertions failed'):
                check_result(self.dom.replace(old, new), 375, 375, self.shot)

    def test_missing_corrupt_or_wrong_width_screenshot_fails(self):
        png = self.shot.read_bytes()
        for contents in (b'', b'not a PNG', png[:16] + struct.pack('!II', 500, 2400)):
            self.shot.write_bytes(contents)
            with self.subTest(contents=contents), self.assertRaisesRegex(ValueError, 'screenshot width'):
                check_result(self.dom, 375, 375, self.shot)
        self.shot.unlink()
        with self.assertRaisesRegex(ValueError, 'screenshot width'):
            check_result(self.dom, 375, 375, self.shot)
