"""Keep currency amounts separate from rate-limited AI quota windows."""
from math import isfinite

from resource_status import band_ink


def amount_text(metric):
    value = metric.get('value') or ''
    if metric.get('kind') == 'spend':
        return value.removeprefix('≥').lstrip() or '—'
    if metric.get('kind') == 'balance':
        return value or '—'
    # Older local bridges already send the formatted value without a kind.
    if value.lstrip('≥−- ').startswith(('¥', '￥', '$', '€', '£')):
        return value
    return None


def amount_label(metric):
    label = metric['label']
    if metric.get('kind') == 'spend' and (metric.get('value') or '').startswith('≥'):
        return label + '（已知金额）'
    return label


def used_percent(metric):
    percent = metric.get('percent')
    return percent if type(percent) in (int, float) and isfinite(percent) and amount_text(metric) is None else None


def remaining_percent(used):
    return None if used is None else max(0, min(100, 100 - used))


def quota_color(remaining, light=False):
    if remaining is None:
        return '#84939e'
    if remaining >= 70:
        return band_ink(remaining, 100, 70, 'green', light)
    if remaining >= 40:
        return band_ink(remaining, 70, 40, 'yellow', light)
    if remaining > 10:
        return band_ink(remaining, 40, 10, 'orange', light)
    return band_ink(remaining, 10, 0, 'red', light)


def quota_text(metric):
    amount = amount_text(metric)
    if amount is not None:
        return amount
    remaining = remaining_percent(used_percent(metric))
    return '—' if remaining is None else f'剩余 {remaining:.0f}%'
