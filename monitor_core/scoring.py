"""Config-driven engagement scoring, keyword matching and self-relative bursts."""
import math
from .model import timestamp


def keywords(item, words):
    text = ' '.join([item['title']] + item.get('tags', [])).casefold()
    return [word for word in words if word.casefold() in text]


def burst(snapshots, config):
    if len(snapshots) < 2:
        return None
    latest = snapshots[-1]
    ts = timestamp(latest[0])
    options = [(abs((ts - timestamp(p[0])).total_seconds() / 60 - config['burst_window_minutes']), p)
               for p in snapshots[:-1] if 20 <= (ts - timestamp(p[0])).total_seconds() / 60 <= 90]
    if not options:
        return None
    previous = min(options, key=lambda pair: pair[0])[1]
    delta_votes, delta_comments = latest[1] - previous[1], latest[3] - previous[3]
    raw = delta_votes + 0.7 * delta_comments
    hours = (ts - timestamp(previous[0])).total_seconds() / 3600
    rate = raw / hours
    first = snapshots[0]
    # Average across the complete observed history, including the current window.
    duration = (ts - timestamp(first[0])).total_seconds() / 3600
    average = ((latest[1] - first[1]) + 0.7 * (latest[3] - first[3])) / duration if duration else 0
    return {'delta_votes': delta_votes, 'delta_comments': delta_comments, 'raw': round(raw, 2),
            'per_hour': round(rate, 2), 'average_per_hour': round(average, 2),
            'is_burst': raw >= config['burst_min'] and rate >= average * config['burst_ratio']}


def score(item, history, config, now):
    m = item['metrics']
    net = m.get('votes_pos', 0) - m.get('votes_neg', 0)
    hours = max(0.5, (now - timestamp(item['posted_at'])).total_seconds() / 3600)
    jump = burst(history, config['thresholds'])
    raw = {'votes': net, 'comments': m.get('comments', 0), 'velocity': net / hours,
           'clicks': m.get('clicks', 0), 'burst': jump['raw'] if jump else 0}
    breakdown = {key: {'raw': round(value, 3), 'weight': config['weights'][key],
                       'points': config['weights'][key] * min(1, math.log1p(max(value, 0)) / math.log1p(config['caps'][key]))}
                 for key, value in raw.items()}
    total = max(0, min(100, round(sum(x['points'] for x in breakdown.values()))))
    for component in breakdown.values():
        component['points'] = round(component['points'], 2)
    t = config['thresholds']
    tier = ('viral' if total >= t['viral_score'] or net >= t['viral_votes'] else
            'hot' if total >= t['hot_score'] or net >= t['hot_votes'] else
            'rising' if (jump and jump['is_burst']) or total >= t['rising_score'] else None)
    return {'score': total, 'breakdown': breakdown, 'tier': tier, 'burst': jump,
            'watch_hit': keywords(item, config['watch']), 'blocked': bool(keywords(item, config['block']))}
