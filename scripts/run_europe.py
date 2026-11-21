#!/usr/bin/env python3
"""Refresh the Europe page using the existing publication fallback directory."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitor_core.model import timestamp
from monitor_core.store import save
from monitors.europe.monitor import INTERVAL, PublicPages, build


def run(out, now, *, refresh=False, fallback=False, fetch=None):
    path = Path(out) / 'data/europe.json'
    try:
        previous = json.loads(path.read_text())
    except FileNotFoundError:
        previous = {}
    except (OSError, ValueError):
        if not fallback:
            raise
        previous = {}
    if previous.get('checked_at') and not (refresh or fallback):
        if now - timestamp(previous['checked_at']) < INTERVAL:
            print('Europe: six-hour refresh window has not elapsed.')
            return previous

    if not (fallback or fetch) and sys.version_info < (3, 14):
        raise RuntimeError('Live Europe refresh requires Python 3.14+ for robots wildcard handling')

    def failed(_):
        raise ValueError('欧洲更新程序失败，等待下一轮复查')

    result = build(now, failed if fallback else fetch or PublicPages(), previous)
    save(path, result)
    for source in result['sources']:
        print(f"Europe: {source['id']} {source['status']} {source['count']} {source.get('detail', '')}".rstrip())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('site'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--refresh', action='store_true', help='Run a single intentional live check')
    mode.add_argument('--fallback', action='store_true', help='Expose an unexpected pipeline failure')
    args = parser.parse_args()
    run(args.out, datetime.now(timezone.utc), refresh=args.refresh, fallback=args.fallback)
