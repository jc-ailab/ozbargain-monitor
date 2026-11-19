"""Atomic JSON state with bounded, recent-dense snapshot history."""
import json
import logging
from pathlib import Path
from .model import iso, timestamp


def load(path):
    try:
        state = json.loads(Path(path).read_text())
        if not isinstance(state.get('items'), dict):
            raise ValueError('Invalid state schema')
        return state
    except FileNotFoundError:
        return {'items': {}}
    except (ValueError, OSError) as exc:
        # Do not overwrite an unreadable state file: it may be the only good copy.
        logging.getLogger(__name__).error('Cannot load state: %s', exc)
        raise


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
    temporary.replace(path)


def sample(points, limit):
    if len(points) <= limit:
        return points
    return [points[round(i * (len(points) - 1) / (limit - 1))] for i in range(limit)]


def thin(points):
    # Preserve 64 most recent points; evenly sample older history into 32 slots.
    return sample(points[:-64], 32) + points[-64:] if len(points) > 96 else points


def update(state, items, now, retention_days=7):
    ts = iso(now)
    for item in items:
        entry = state['items'].setdefault(item.id, {'first_seen': ts, 'snapshots': [], 'summary': None})
        entry['item'] = item.to_dict()
        entry['last_seen'] = ts
        m = item.metrics
        entry['snapshots'].append([ts] + [m.get(k, 0) for k in ('votes_pos', 'votes_neg', 'comments', 'clicks')])
        entry['snapshots'] = thin(entry['snapshots'])
    state['items'] = {key: entry for key, entry in state['items'].items()
                      if (now - timestamp(entry['last_seen'])).total_seconds() <= retention_days * 86400}
    return state
