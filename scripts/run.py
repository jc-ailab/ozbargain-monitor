#!/usr/bin/env python3
"""CLI for the generic monitor pipeline; fixture mode never uses the network."""
import argparse
import logging
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor_core.build import run, recover


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--monitor', choices=sorted(p.parent.name for p in (ROOT / 'monitors').glob('*/config.json')), required=True)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT / 'site')
    parser.add_argument('--fixtures', nargs='?', const=str(ROOT / 'tests' / 'fixtures'), help='Offline fixtures directory')
    args = parser.parse_args()
    # Keep offline history separate from live samples, including in default local usage.
    state_dir = args.state_dir or ROOT / '.state' / ('fixtures' if args.fixtures else 'live') / args.monitor
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if args.fixtures:
        os.environ.pop('GITHUB_TOKEN', None)
    try:
        run(args.monitor, state_dir, args.out, args.fixtures)
    except Exception as exc:
        logging.error('Pipeline failed (%s); trying last-good output', type(exc).__name__)
        try:
            recover(args.monitor, state_dir, args.out, exc)
        except Exception:
            logging.error('No recovery available')
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
