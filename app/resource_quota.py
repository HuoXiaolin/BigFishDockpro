"""Keep currency amounts separate from rate-limited AI quota windows."""
from dataclasses import dataclass
from math import isfinite
import re

from resource_status import band_ink


_COMMON_PLAN_NAMES = {
    'free': 'Free',
    'go': 'Go',
    'plus': 'Plus',
    'pro': 'Pro',
    'max': 'Max',
    'team': '团队版',
    'business': '商业版',
    'enterprise': '企业版',
    'edu': '教育版',
    'education': '教育版',
}
_CODEX_PLAN_NAMES = {
    **_COMMON_PLAN_NAMES,
    'prolite': 'Pro 100',
    'pro100': 'Pro 100',
    'pro': 'Pro 200',
    'pro200': 'Pro 200',
    'promax': 'Pro 500',
    'pro500': 'Pro 500',
}


def provider_plan_name(provider):
    plan = provider.get('plan')
    if not isinstance(plan, str) or not (plan := plan.strip()):
        return ''
    if provider.get('id', '').casefold() != 'codex':
        return _COMMON_PLAN_NAMES.get(plan.casefold(), plan)
    # The account usage response supplies the plan code independently of the quota windows.
    code = re.sub(r'[\s_-]+', '', plan.casefold())
    return _CODEX_PLAN_NAMES.get(code, '套餐未识别')


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


def tray_balance_text(amount):
    if not isinstance(amount, str):
        return None
    # Bridge and gateway currency strings use an invariant decimal point.
    match = re.fullmatch(r'([^\d.]*)([0-9]+(?:,[0-9]{3})*)(?:\.[0-9]+)?', amount.strip())
    if not match:
        return None
    prefix, whole = match.groups()
    digits = whole.replace(',', '').lstrip('0') or '0'
    sign = '−' if digits != '0' and ('−' in prefix or '-' in prefix) else ''
    currency = prefix.lstrip('≥ ').replace('−', '').replace('-', '').lstrip()
    return sign + currency + digits


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


TRAY_PERIODS = {
    'hour': '小时额度', 'day': '日额度', 'week': '周额度',
    'month': '月额度', 'balance': '账户余额',
}
_TRAY_PERIOD_RANGES = {'hour': (1, 1439), 'day': (1440, 1440), 'week': (10080, 10080), 'month': (40320, 44640)}
_WINDOW_UNITS = {
    '分钟': 1, '小时': 60, '天': 1440, '周': 10080, '月': 43200, '个月': 43200,
    'minute': 1, 'min': 1, 'hour': 60, 'hr': 60, 'h': 60,
    'day': 1440, 'week': 10080, 'month': 43200,
}
_WINDOW_LABELS = (
    (re.compile(r'每小时|小时额度|hourly', re.I), 60),
    (re.compile(r'每日|每天|日额度|daily', re.I), 1440),
    (re.compile(r'每周|周额度|周限额|weekly', re.I), 10080),
    (re.compile(r'每月|月额度|月度|monthly', re.I), 43200),
)
_WINDOW_RE = re.compile(r'(\d{1,5})\s*[-‐]?\s*(分钟|小时|天|周|个月|月|minutes?\b|mins?\b|hours?\b|hrs?\b|h\b|days?\b|weeks?\b|months?\b)', re.I)


def quota_window(metric):
    minutes = metric.get('window')
    if type(minutes) is int and minutes > 0:
        return minutes
    label = metric.get('label') or ''
    match = _WINDOW_RE.search(label)
    if match and (count := int(match[1])):
        return count * _WINDOW_UNITS[match[2].casefold().rstrip('s')]
    return next((minutes for pattern, minutes in _WINDOW_LABELS if pattern.search(label)), None)


def tray_metric_key(metric):
    label = metric.get('label') or ''
    identity = metric.get('id')
    return 'id:' + identity if identity and identity != label else 'label:' + label


def _tray_balance(metric):
    return None if metric.get('kind') == 'spend' else amount_text(metric)


def tray_metric_options(provider):
    choices = {}
    for metric in provider.get('quotas', []):
        label = metric.get('label')
        if label and (_tray_balance(metric) is not None or used_percent(metric) is not None or
                      (metric.get('kind') in (None, 'percent') and quota_window(metric))):
            choices[tray_metric_key(metric)] = label
    return choices


@dataclass(frozen=True, slots=True)
class TrayReading:
    provider: str
    name: str
    metric: str
    label: str
    window: int | None
    remaining: float | None
    amount: str | None
    reset: str | None
    stale: bool


def _tray_reading(row, metric):
    name = ' '.join(filter(None, (row['name'], provider_plan_name(row))))
    return TrayReading(row['id'], name, tray_metric_key(metric), metric.get('label') or '额度', quota_window(metric),
                       remaining_percent(used_percent(metric)), _tray_balance(metric),
                       metric.get('reset'), bool(row.get('stale')))


def _by_window(metric):
    return quota_window(metric) or float('inf'), -used_percent(metric), tray_metric_key(metric)


def _fixed_tray_metric(metrics, target):
    if target == 'balance':
        amounts = [q for q in metrics if _tray_balance(q) not in (None, '—')]
        return next((q for q in amounts if q.get('label') == '账户余额'), amounts[0] if amounts else None)
    if target in _TRAY_PERIOD_RANGES:
        low, high = _TRAY_PERIOD_RANGES[target]
        return min((q for q in metrics if used_percent(q) is not None
                    and low <= (quota_window(q) or 0) <= high), key=_by_window, default=None)
    return next((q for q in metrics if tray_metric_key(q) == target and (
        used_percent(q) is not None or _tray_balance(q) not in (None, '—'))), None)


def tray_readings(rows, mode, provider, target):
    if mode == 'fixed':
        row = next((row for row in rows if row['id'] == provider), None)
        if row and (metric := _fixed_tray_metric(row.get('quotas', []), target)):
            return (_tray_reading(row, metric),)
        return ()

    readings, balances = [], []
    for row in rows:
        metrics = row.get('quotas', [])
        metric = min((q for q in metrics if used_percent(q) is not None), key=_by_window, default=None)
        if metric:
            readings.append(_tray_reading(row, metric))
        elif (balance := _fixed_tray_metric(metrics, 'balance')):
            balances.append(_tray_reading(row, balance))
    if readings:
        return tuple(sorted(readings, key=lambda reading: (
            reading.stale, reading.window or float('inf'), reading.remaining, reading.provider))[:3])
    return tuple(sorted(balances, key=lambda reading: reading.stale)[:1])


def tray_label(metric):
    return TRAY_PERIODS.get(metric) or (metric[6:] if metric.startswith('label:') else '')
