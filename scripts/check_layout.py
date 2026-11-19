#!/usr/bin/env python3
"""Offline Chrome layout regression check, deliberately separate from unittest.

Builds and serves isolated fixtures in exact-width same-origin iframes.
Screenshots default to .state/layoutcheck/screenshots/ozb-layout-*.png.
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
  root.dataset.overflow = String(root.scrollWidth > window.innerWidth);
  root.dataset.cards = String(document.querySelectorAll('.card').length);
  const inside = (node, parent) => {
    const a = node.getBoundingClientRect(), b = parent.getBoundingClientRect();
    return a.width > 0 && a.left >= b.left - 1 && a.right <= b.right + 1;
  };
  root.dataset.scores = String([...document.querySelectorAll('.score')].every(
    n => inside(n, n.closest('.card'))));
  root.dataset.stats = String([...document.querySelectorAll('.stat strong')].every(
    n => n.scrollWidth <= n.clientWidth));
  root.dataset.actions = String([...document.querySelectorAll('.card-actions')].every(n => {
    const children = [...n.children], gap = parseFloat(getComputedStyle(n).columnGap);
    const rects = children.map(c => c.getBoundingClientRect());
    const fit = rects.reduce((sum, r) => sum + r.width, 0) + gap * (rects.length - 1) <= n.getBoundingClientRect().width + 0.01;
    const valid = children.every(c => inside(c, n) && c.scrollWidth <= c.clientWidth + 1) &&
      (!fit || rects.every(r => Math.abs(r.top - rects[0].top) < 1)) &&
      rects.every((r, i) => rects.slice(i + 1).every(s =>
        r.right <= s.left + 1 || s.right <= r.left + 1 || r.bottom <= s.top + 1 || s.bottom <= r.top + 1));
    if (!valid) root.dataset.actionFailure = JSON.stringify({available: n.clientWidth, fit,
      children: children.map((c, i) => ({text: c.textContent, x: rects[i].x, y: rects[i].y,
        width: rects[i].width, scroll: c.scrollWidth, client: c.clientWidth}))});
    return valid;
  }));
  const thumbs = [...document.querySelectorAll('.top-card .thumbnail')];
  const states = thumbs.map(n => n.dataset.imageState).sort().join(',');
  root.dataset.images = String(states === 'failed,loaded,missing' && thumbs.every(n => {
    const letter = n.querySelector('.thumb-letter'), image = n.querySelector('img');
    return letter.textContent.trim() && (n.dataset.imageState === 'loaded'
      ? image.naturalWidth > 0 && getComputedStyle(letter).visibility === 'hidden'
      : getComputedStyle(letter).visibility === 'visible' && (!image || image.hidden));
  }));
}"""
PROBE = ('<style>*{animation:none!important;transition:none!important}</style><script>'
         + PROBE_JS + '; setTimeout(layoutProbe, 1000);</script>')


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


def wrapper_page(page, width):
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<style>html,body{margin:0}iframe{display:block;border:0}</style>'
            '</head><body>'
            f'<iframe src="{page}?layoutcheck=1" style="width:{width}px;height:2400px">'
            '</iframe></body></html>')


def check_result(dom, viewport, width, shot):
    # Check the live iframe window independently of the probe's DOM attributes.
    if viewport != width:
        raise ValueError(f'iframe innerWidth={viewport}, expected {width}')
    attrs = RootAttributes(dom).attrs
    expected = {'data-overflow': 'false', 'data-viewport': str(width),
                'data-scores': 'true', 'data-stats': 'true',
                'data-actions': 'true', 'data-saved-actions': 'true',
                'data-images': 'true'}
    if any(attrs.get(k) != v for k, v in expected.items()) or int(attrs.get('data-cards', 0)) < 4:
        raise ValueError(f'iframe layout assertions failed: {attrs}')
    png = shot.read_bytes() if shot.is_file() else b''
    if (len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n' or png[12:16] != b'IHDR'
            or struct.unpack('!I', png[16:20])[0] != width):
        raise ValueError(f'screenshot width does not match {width}')


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


def capture(command, profile, shot):
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
                    return ({}, stderr_file.read()), process.returncode or 1
                if time.monotonic() > deadline:
                    raise OSError('Chrome CDP startup timed out')
                time.sleep(0.05)
            port, path = active.read_text().splitlines()[:2]
            cdp = DevTools(int(port), path)
            try:
                # Native Chrome windows clamp at 500px on macOS. The wrapper
                # stays wide; the iframe supplies the actual phone viewport.
                target_id = cdp.call('Target.createTarget', {'url': 'about:blank'})['targetId']
                session = cdp.call('Target.attachToTarget', {'targetId': target_id, 'flatten': True})['sessionId']
                cdp.call('Page.navigate', {'url': next(a for a in command if a.startswith('http://'))}, session)
                deadline = time.monotonic() + 15
                while True:
                    result = cdp.call('Runtime.evaluate', {'expression':
                        "document.querySelector('iframe')?.contentDocument?.documentElement.dataset.cards || ''",
                        'returnByValue': True}, session)
                    if result['result'].get('value'):
                        break
                    if time.monotonic() > deadline:
                        raise OSError('Iframe fixture rendering timed out')
                    time.sleep(0.05)
                probe = (
                    "(async () => { layoutProbe(); const normalActions = document.documentElement.dataset.actions; "
                    "data.items.forEach(i => { favourites.add(i.id); hidden.add(i.id); }); "
                    "showHidden = true; render(); layoutProbe(); "
                    "const savedActions = document.documentElement.dataset.actions; "
                    "favourites.clear(); hidden.clear(); showHidden = false; render(); "
                    "await Promise.all([...document.querySelectorAll('.top-card img')].map(i => i.decode().catch(() => {}))); "
                    "await new Promise(resolve => setTimeout(resolve, 50)); layoutProbe(); "
                    "document.documentElement.dataset.savedActions = String(normalActions === 'true' && savedActions === 'true'); "
                    'return document.documentElement.outerHTML; })()')
                measured = cdp.call('Runtime.evaluate', {'expression':
                    '(async () => { const frame = document.querySelector("iframe"); '
                    f'const dom = await frame.contentWindow.eval({json.dumps(probe)}); '
                    'const rect = frame.getBoundingClientRect(); '
                    'return {dom, viewport: frame.contentWindow.innerWidth, '
                    'clip: {x: rect.x, y: rect.y, width: rect.width, height: rect.height, scale: 1}}; })()',
                    'returnByValue': True, 'awaitPromise': True}, session)
                if 'exceptionDetails' in measured or 'value' not in measured.get('result', {}):
                    raise OSError(f'Iframe probe failed: {measured}')
                result = measured['result']['value']
                screenshot = cdp.call('Page.captureScreenshot', {'format': 'png',
                    'clip': result.pop('clip'), 'captureBeyondViewport': True}, session)
                shot.write_bytes(base64.b64decode(screenshot['data']))
                cdp.call('Browser.close')
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
                stdout_file.seek(0)
                stderr_file.seek(0)
                return (result, stderr_file.read()), 0
            finally:
                cdp.socket.close()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome', default=CHROME)
    parser.add_argument('--screenshots', type=Path, default=ROOT / '.state/layoutcheck/screenshots')
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
            # Top 3 (and list) exercise successful, corrupt and absent images.
            for n, item in enumerate(document['items']):
                item['image'] = ('http://127.0.0.1:PORT/thumb.svg',
                                 'http://127.0.0.1:PORT/broken.png', '')[n % 3]
            store.save(site / 'data' / f'{monitor}.json', document)
        (site / 'thumb.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="58" height="58"><rect width="58" height="58" fill="#ddd"/></svg>')
        (site / 'broken.png').write_text('Deliberately corrupt image fixture')
        for page in site.glob('*.html'):
            page.write_text(page.read_text().replace('</body>', PROBE + '</body>'))
        try:
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(site)))
        except OSError as exc:
            print(f'BLOCKED local fixture server: {exc}', file=sys.stderr)
            return 1
        port = server.server_port
        for data in (site / 'data').glob('*.json'):
            data.write_text(data.read_text().replace(':PORT/', f':{port}/'))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for page in ('index.html', 'hn.html'):
                for width in WIDTHS:
                    wrapper = f'layout-{page[:-5]}-{width}.html'
                    (site / wrapper).write_text(wrapper_page(page, width))
                    shot = args.screenshots / f'ozb-layout-{page[:-5]}-{width}.png'
                    shot.unlink(missing_ok=True)
                    command = [args.chrome, '--headless=new', '--window-size=1400,2600',
                               f'--user-data-dir={work / "chrome-profile"}', '--no-first-run',
                               '--no-default-browser-check', '--disable-background-networking',
                               '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
                               f'http://127.0.0.1:{port}/{wrapper}']
                    (result, stderr), code = capture(command, work / 'chrome-profile', shot)
                    if code:
                        print(f'BLOCKED Chrome failed to launch/run (exit {code}): {stderr[-2000:]}', file=sys.stderr)
                        return 1
                    try:
                        check_result(result['dom'], result['viewport'], width, shot)
                    except ValueError as exc:
                        print(f'FAIL {page} width={width}: {exc}', file=sys.stderr)
                        return 1
                    print(f'PASS {page} width={width} iframe.innerWidth={result["viewport"]}: overflow=false; scores/stats/actions fit (default + saved); images=loaded/failed/missing OK; screenshot={shot}')
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
