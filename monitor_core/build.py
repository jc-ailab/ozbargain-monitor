"""Run any adapter through the shared state, score, summary and publication path."""
import importlib
import json
import logging
from pathlib import Path
from . import scoring, store, summarize
from .model import iso, timestamp, utcnow

ROOT = Path(__file__).resolve().parents[1]


def run(monitor, state_dir, out, fixtures=None, now=None):
    now = now or utcnow()
    config = json.loads((ROOT / 'monitors' / monitor / 'config.json').read_text())
    adapter = importlib.import_module(f'monitors.{monitor}.adapter')
    source = adapter.Source(fixtures)
    state_path = Path(state_dir) / 'state.json'
    state = store.load(state_path)
    seen = source.fetch()
    store.update(state, seen, now, config.get('retention_days', 7))
    if seen:
        state['last_success'] = iso(now)
    output = []
    for entry in state['items'].values():
        item = entry['item']
        row = {**item, **item['extra'], 'first_seen': entry['first_seen'],
               'last_seen': entry['last_seen'], 'summary': entry.get('summary'),
               'trend': [[p[0], p[1] - p[2], p[3]] for p in store.sample(entry['snapshots'], 24)]}
        row.pop('extra', None)
        expiry = row.get('expiry')
        if expiry:
            try:
                if timestamp(expiry) <= now and 'expired' not in row['flags']:
                    row['flags'] = row['flags'] + ['expired']
            except ValueError:
                logging.getLogger(__name__).warning('Ignoring invalid expiry for %s', row['id'])
        row.update(scoring.score(item, entry['snapshots'], config, now))
        # Historical bursts are not current bursts when an item disappears from feeds.
        if entry['last_seen'] != iso(now):
            row['burst'] = None
            row['breakdown']['burst']['raw'] = 0
            row['breakdown']['burst']['points'] = 0
            fresh_score = scoring.score(item, [], config, now)
            row.update(fresh_score)
        output.append(row)
    output.sort(key=lambda x: ('expired' in x['flags'], -x['score'], x['id']))
    if seen:
        summarize.enrich(output, state, config)
    stats = {'total': len(output), **{tier: sum(i['tier'] == tier for i in output) for tier in ('viral', 'hot', 'rising')},
             'free': sum(bool(i['is_free']) for i in output),
             'bursting': sum(bool(i['burst'] and i['burst']['is_burst']) for i in output),
             'avg_score': round(sum(i['score'] for i in output) / len(output), 1) if output else 0,
             'total_votes': sum(i['metrics']['votes_pos'] - i['metrics']['votes_neg'] for i in output),
             'total_comments': sum(i['metrics']['comments'] for i in output), 'feeds': source.feeds}
    digest = state.get('digest')
    top_ids = sorted(i['id'] for i in [i for i in output if not i['blocked'] and 'expired' not in i['flags']][:3])
    published_digest = ({'text': digest['text'], 'ai': True}
                        if digest and digest.get('top_ids') == top_ids else None)
    document = {'monitor': monitor, 'title': config['title'], 'generated_at': state.get('last_success'),
                'checked_at': iso(now), 'stats': stats, 'digest': published_digest,
                'config_public': {key: config[key] for key in ('weights', 'thresholds', 'watch', 'block')}, 'items': output}
    # Trends are optional detail; preserve all records if a busy feed approaches the size budget.
    if len(json.dumps(document, ensure_ascii=False).encode()) >= 1_500_000:
        for item in output:
            item['trend'] = store.sample(item['trend'], 2)
    if len(json.dumps(document, ensure_ascii=False, separators=(',', ':')).encode()) >= 1_500_000:
        raise ValueError('Output exceeds 1.5 MB; last good output preserved')
    state['last_output'] = document
    store.save(state_path, state)
    destination = Path(out) / 'data' / f'{monitor}.json'
    store.save(destination, document)
    logging.getLogger(__name__).info('%s: %s items; feeds=%s; output=%s', monitor, len(output), source.feeds, destination)
    return document


def recover(monitor, state_dir, out, error):
    """Publish the previous successful document on unexpected pipeline failure."""
    state = store.load(Path(state_dir) / 'state.json')
    document = state.get('last_output')
    if not document:
        raise RuntimeError('No last-good output available') from error
    document['stats']['feeds'] = {'pipeline': 'error: ' + type(error).__name__}
    document['checked_at'] = iso(utcnow())
    store.save(Path(out) / 'data' / f'{monitor}.json', document)
    return document
