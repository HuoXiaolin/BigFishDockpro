"""Account balances reported by AI providers and custom usage endpoints."""
from decimal import Decimal, InvalidOperation
from typing import NamedTuple
from urllib.parse import urlsplit


class BalanceService(NamedTuple):
    kind: str
    path: str
    currency: str


SERVICES = {
    'api.deepseek.com': BalanceService('deepseek', '/user/balance', ''),
    'api.moonshot.cn': BalanceService('kimi', '/v1/users/me/balance', 'CNY'),
    'api.moonshot.ai': BalanceService('kimi', '/v1/users/me/balance', 'USD'),
    'openrouter.ai': BalanceService('openrouter', '/api/v1/credits', 'USD'),
}
PRESETS = {service.kind: f'https://{host}{service.path}' for host, service in SERVICES.items()
           if host != 'api.moonshot.ai'}
BALANCE_KEYS = ('available_balance', 'availableBalance', 'remaining_balance', 'remainingBalance',
                'account_balance', 'accountBalance', 'total_balance', 'totalBalance', 'balance')
SYMBOLS = {'CNY': '¥', 'USD': '$', 'EUR': '€', 'GBP': '£'}


def money(value):
    if type(value) not in (str, int, float) or len(str(value)) > 80:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if amount.is_finite() and amount.copy_abs() < 10**18:
        return amount
    return None


def currency_of(row, default=''):
    value = row.get('currency') or row.get('currency_code') or row.get('currencyCode') or row.get('unit')
    if isinstance(value, str):
        code = value.strip().upper()
        if code == 'RMB':
            return 'CNY'
        if code in ('¥', '￥', '$', '€', '£'):
            return '¥' if code == '￥' else code
        if code in ('%', 'PERCENT', 'TOKENS', 'TOKEN', 'REQUESTS', 'POINTS', '额度', '积分', '次'):
            return None
        if (code.isascii() and code.isalpha() and len(code) == 3) or code in ('USDC', 'USDT'):
            return code
    return default


def balance_metric(amount, currency):
    magnitude = amount.copy_abs()
    # Preserve sub-cent credit. Ordinary readings use the card's two decimal places.
    if 0 < magnitude < Decimal('0.01'):
        value = format(magnitude, ',.8f').rstrip('0') if magnitude >= Decimal('1e-8') else format(magnitude.normalize(), 'E')
    else:
        value = format(magnitude, ',.2f')
    prefix = SYMBOLS.get(currency, currency + ' ' if currency.isalpha() else currency)
    sign = '−' if amount < 0 else ''
    return dict(id='account-balance:' + (currency or 'unknown'), label='账户余额',
                kind='balance', value=sign + prefix + value)


def balance_metrics(payload, url, *, balance_endpoint=False):
    if not isinstance(payload, dict) or payload.get('error') or payload.get('success') is False:
        return []
    if payload.get('status') is False or payload.get('status') in ('error', 'failed'):
        return []
    data = payload.get('data', payload)
    if not isinstance(data, dict):
        return []
    parts = urlsplit(url)
    service = SERVICES.get(parts.hostname)
    default = currency_of(data, currency_of(payload, service.currency if service else ''))
    path = parts.path.rstrip('/')
    if service and service.kind == 'openrouter' and path == service.path:
        purchased = money(data.get('total_credits'))
        used = money(data.get('total_usage'))
        return [] if purchased is None or used is None or default is None else [balance_metric(purchased - used, default)]

    amounts = {}

    def add(row, keys, currency):
        for key in keys:
            value = row.get(key)
            unit = currency
            if isinstance(value, dict):
                unit = currency_of(value, currency)
                value = next((value[k] for k in ('amount', 'remaining', 'available', 'value') if value.get(k) is not None), None)
            amount = money(value)
            if amount is not None and unit is not None:
                amounts.setdefault(unit, amount)
                return

    # A service can maintain independent wallets. Never add different currencies or
    # count grants and top-ups a second time when a total is present.
    wallets = data.get('balance_infos', data.get('balances'))
    if isinstance(wallets, list):
        for wallet in wallets[:32]:
            if isinstance(wallet, dict):
                add(wallet, (*BALANCE_KEYS, 'amount'), currency_of(wallet, default))
    if not amounts:
        keys = BALANCE_KEYS
        if balance_endpoint:
            keys += ('total_available', 'amount')
            if default:
                keys += ('available', 'remaining')
        add(data, keys, default)
    metrics = [balance_metric(amount, unit) for unit, amount in amounts.items()]
    if len(metrics) > 1:
        for metric, unit in zip(metrics, amounts):
            if unit:
                metric['label'] += f'（{unit}）'
    return metrics
