#!/usr/bin/env python3
"""Workflow-only fallback if a CLI run cannot publish its state-backed output."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor_core.model import iso, utcnow
from monitor_core.store import save


def publish(monitor, out):
    path = Path(out) / 'data' / (monitor + '.json')
    if path.exists():
        document = json.loads(path.read_text())
    else:
        config = json.loads((ROOT / 'monitors' / monitor / 'config.json').read_text())
        document = {'monitor': monitor, 'title': config['title'], 'generated_at': None,
                    'stats': dict.fromkeys(['total', 'viral', 'hot', 'rising', 'free', 'bursting', 'avg_score', 'total_votes', 'total_comments'], 0),
                    'digest': None, 'config_public': {k: config[k] for k in ('weights', 'thresholds', 'watch', 'block')}, 'items': []}
    document['stats']['feeds'] = {'pipeline': 'error: CLI failed; previous published data retained'}
    document['checked_at'] = iso(utcnow())
    save(path, document)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--monitor', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    publish(args.monitor, args.out)
