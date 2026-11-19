#!/usr/bin/env python3
"""Offline Chrome layout regression check, deliberately separate from unittest.

Builds and serves isolated fixtures; screenshots default to /tmp/ozb-layout-*.png.
No external images or feed/API requests are used.
"""
import argparse
import base64
from functools import partial
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
from threading import Thread
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor_core.build import run
from monitor_core import store

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
WIDTHS = (360, 375, 390, 1300)

# Report component containment too: root width alone can miss clipped content.
PROBE_JS = """function layoutProbe() {
  const root = document.documentElement;
  root.dataset.viewport = String(window.innerWidth);
  root.dataset.cards = String(document.querySelectorAll('.card').length);
  const inside = (node, parent) => {
    const a = node.getBoundingClientRect(), b = parent.getBoundingClientRect();
    return a.width > 0 && a.left >= b.left - 1 && a.right <= b.right + 1;
  };
  root.dataset.scores = String([...document.querySelectorAll('.score')].every(
    n => inside(n, n.closest('.card'))));
  root.dataset.stats = String([...document.querySelectorAll('.stat strong')].every(
    n => n.scrollWidth <= n.clientWidth));
}"""
PROBE = '<script>' + PROBE_JS + '; setTimeout(layoutProbe, 1000);</script>'


class RootAttributes(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.attrs = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == 'html':
            self.attrs = dict(attrs)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class DevTools:
    """Minimal local WebSocket transport for Chrome CDP, standard library only."""
    def __init__(self, port, path):
        self.socket = socket.create_connection(('127.0.0.1', port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall((f'GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
                             f'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                             f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        header = b''
        while not header.endswith(b'\r\n\r\n'):
            header += self.read(1)
        if not header.startswith(b'HTTP/1.1 101 '):
            raise OSError(f'CDP handshake failed: {header!r}')
        self.sequence = 0

    def read(self, size):
        result = b''
        while len(result) < size:
            chunk = self.socket.recv(size - len(result))
            if not chunk:
                raise OSError('Chrome closed CDP connection')
            result += chunk
        return result

    def call(self, method, params=None, session=None):
        self.sequence += 1
        request = {'id': self.sequence, 'method': method, 'params': params or {}}
        if session:
            request['sessionId'] = session
        payload = json.dumps(request).encode()
        mask = os.urandom(4)
        size = len(payload)
        header = bytes([0x81, 0x80 | size]) if size < 126 else bytes([0x81, 0xfe]) + struct.pack('!H', size)
        self.socket.sendall(header + mask + bytes(x ^ mask[n % 4] for n, x in enumerate(payload)))
        while True:
            opcode, length = self.read(2)
            length &= 127
            if length == 126:
                length = struct.unpack('!H', self.read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self.read(8))[0]
            if opcode & 15 != 1:
                raise OSError(f'Unexpected CDP WebSocket opcode: {opcode}')
            response = json.loads(self.read(length))
            if response.get('id') == self.sequence:
                if 'error' in response:
                    raise OSError(f'CDP {method}: {response["error"]}')
                return response.get('result', {})


def capture(command, profile, width, shot):
    active = profile / 'DevToolsActivePort'
    active.unlink(missing_ok=True)
    with (profile.parent / 'chrome.stdout').open('w+') as stdout_file, (profile.parent / 'chrome.stderr').open('w+') as stderr_file, subprocess.Popen(command + ['--remote-debugging-port=0'], stdout=stdout_file,
                          stderr=stderr_file, text=True) as process:
        try:
            deadline = time.monotonic() + 12
            while not active.exists():
                if process.poll() is not None:
                    stdout_file.seek(0)
                    stderr_file.seek(0)
                    return (stdout_file.read(), stderr_file.read()), process.returncode
                if time.monotonic() > deadline:
                    raise OSError('Chrome CDP startup timed out')
                time.sleep(0.05)
            port, path = active.read_text().splitlines()[:2]
            cdp = DevTools(int(port), path)
            try:
                target = None
                while target is None:
                    targets = cdp.call('Target.getTargets')['targetInfos']
                    target = next((t for t in targets if t['type'] == 'page'
                                   and t['url'].startswith('http://127.0.0.1:')), None)
                    if time.monotonic() > deadline:
                        raise OSError(f'Chrome page target startup timed out: {targets}')
                    if target is None:
                        time.sleep(0.05)
                session = cdp.call('Target.attachToTarget', {'targetId': target['targetId'], 'flatten': True})['sessionId']
                cdp.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 2400,
                         'deviceScaleFactor': 1, 'mobile': False}, session)
                deadline = time.monotonic() + 30
                while True:
                    stdout_file.seek(0)
                    if '</html>' in stdout_file.read() and shot.is_file():
                        break
                    if time.monotonic() > deadline:
                        raise OSError('Chrome DOM/screenshot capture timed out')
                    time.sleep(0.05)
                # Chrome closes its CLI capture tab and clamps native windows
                # to 500px. Use a fresh tab at the exact CSS viewport for the
                # final DOM and PNG, keeping the requested CLI capture above.
                target_id = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
                session = cdp.call('Target.attachToTarget', {'targetId': target_id, 'flatten': True})['sessionId']
                cdp.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 2400,
                         'deviceScaleFactor': 1, 'mobile': False}, session)
                cdp.call('Page.navigate', {'url': next(a for a in command if a.startswith('http://'))}, session)
                deadline = time.monotonic() + 15
                while True:
                    result = cdp.call('Runtime.evaluate', {'expression':
                        "document.documentElement.dataset.cards || ''", 'returnByValue': True}, session)
                    if result['result'].get('value'):
                        break
                    if time.monotonic() > deadline:
                        raise OSError('Exact-width fixture rendering timed out')
                    time.sleep(0.05)
                measured = cdp.call('Runtime.evaluate', {'expression':
                    'layoutProbe(); document.documentElement.outerHTML',
                    'returnByValue': True}, session)
                dom = measured['result'].get('value', '')
                screenshot = cdp.call('Page.captureScreenshot', {'format': 'png'}, session)
                shot.write_bytes(base64.b64decode(screenshot['data']))
                # A debugging port keeps Chrome alive after its CLI capture.
                cdp.call('Browser.close')
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
                stdout_file.seek(0)
                stderr_file.seek(0)
                return (dom, stderr_file.read()), 0
            finally:
                cdp.socket.close()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome', default=CHROME)
    parser.add_argument('--screenshots', type=Path, default=Path('/tmp'))
    args = parser.parse_args()
    if not Path(args.chrome).is_file():
        print(f'BLOCKED Chrome executable not found: {args.chrome}', file=sys.stderr)
        return 1
    scratch = ROOT / '.state' / 'layoutcheck'
    scratch.mkdir(parents=True, exist_ok=True)
    args.screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        work = Path(directory)
        site = work / 'site'
        shutil.copytree(ROOT / 'site', site, ignore=shutil.ignore_patterns('data'))
        for monitor in ('ozbargain', 'hackernews'):
            document = run(monitor, work / monitor, site, ROOT / 'tests/fixtures')
            # Replace external images with a local, deterministic fixture asset.
            for item in document['items']:
                if item['image']:
                    item['image'] = 'http://127.0.0.1:PORT/thumb.svg'
            store.save(site / 'data' / f'{monitor}.json', document)
        (site / 'thumb.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="58" height="58"><rect width="58" height="58" fill="#ddd"/></svg>')
        for page in site.glob('*.html'):
            page.write_text(page.read_text().replace('</body>', PROBE + '</body>'))
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(site)))
        port = server.server_port
        for data in (site / 'data').glob('*.json'):
            data.write_text(data.read_text().replace(':PORT/', f':{port}/'))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for page in ('index.html', 'hn.html'):
                for width in WIDTHS:
                    shot = args.screenshots / f'ozb-layout-{page[:-5]}-{width}.png'
                    shot.unlink(missing_ok=True)
                    command = [args.chrome, '--headless=new', f'--window-size={width},2400',
                               '--virtual-time-budget=5000', '--dump-dom', f'--screenshot={shot}',
                               f'--user-data-dir={work / "chrome-profile"}', '--no-first-run',
                               '--no-default-browser-check', '--disable-background-networking',
                               '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
                               f'http://127.0.0.1:{port}/{page}?layoutcheck=1']
                    (stdout, stderr), code = capture(command, work / 'chrome-profile', width, shot)
                    if code:
                        print(f'BLOCKED Chrome failed to launch/run (exit {code}): {stderr[-2000:]}', file=sys.stderr)
                        return 1
                    attrs = RootAttributes(stdout).attrs
                    expected = {'data-overflow': 'false', 'data-viewport': str(width),
                                'data-scores': 'true', 'data-stats': 'true'}
                    if any(attrs.get(k) != v for k, v in expected.items()) or int(attrs.get('data-cards', 0)) < 4 or not shot.is_file():
                        print(f'FAIL {page} width={width}: {attrs}', file=sys.stderr)
                        return 1
                    if struct.unpack('!I', shot.read_bytes()[16:20])[0] != width:
                        print(f'FAIL screenshot width does not match {width}', file=sys.stderr)
                        return 1
                    print(f'PASS {page} width={width}: overflow=false; scores/stats fit; screenshot={shot}')
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f'BLOCKED Chrome check: {exc}', file=sys.stderr)
            return 1
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
