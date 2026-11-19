"""Non-secret mailbox settings and the provider endpoints used by the Dock."""
import re
from hashlib import sha256
from urllib.parse import quote, urlsplit


PROVIDERS = {'qq': 'QQ 邮箱', 'gmail': 'Gmail', 'netease': '网易邮箱', 'imap': '自定义 IMAP'}
ACCOUNT_COLORS = ('#287ec9', '#7961c5', '#119179', '#bd6434', '#b74c83', '#59802f',
                  '#276e8a', '#ac535a', '#866a31', '#4265b5', '#8d5495', '#497351')
MAIL_LIMIT = 20
ACCOUNT_LIMIT = len(ACCOUNT_COLORS)
GMAIL_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'


def account_label(row):
    return row['name'] or row['address']


def inbox_url(row, message_id=''):
    provider = row['provider']
    if provider == 'qq':
        return 'https://mail.qq.com/'
    if provider == 'gmail':
        mailbox = 'https://mail.google.com/mail/?authuser=' + quote(row['address'], safe='')
        if re.fullmatch(r'[a-fA-F0-9]{8,32}', message_id):
            return mailbox + '#all/' + message_id
        return mailbox + '#inbox'
    if provider == 'netease':
        return 'https://mail.' + row['address'].rsplit('@', 1)[1].lower() + '/'
    return row['webmail']


def imap_endpoint(row):
    if row['provider'] == 'qq':
        return 'imap.qq.com', 993
    if row['provider'] == 'gmail':
        return 'imap.gmail.com', 993
    if row['provider'] == 'netease':
        return 'imap.' + row['address'].rsplit('@', 1)[1].lower(), 993
    return row['server'], row['port']


def account_binding(row):
    address = row['address'].casefold()
    endpoint = imap_endpoint(row) if row['method'] == 'imap' else ('gmail.googleapis.com', 443)
    return sha256(repr((row['provider'], row['method'], address, endpoint)).encode('utf-8')).hexdigest()


def clean_account(raw):
    identity = raw.get('id') if isinstance(raw, dict) else None
    if not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{32}', identity):
        raise ValueError('邮箱账号标识无效。')
    provider = raw.get('provider')
    address = str(raw.get('address', '')).strip()
    if not isinstance(provider, str) or provider not in PROVIDERS or len(address) > 254 or not re.fullmatch(r'[^@\s\x00-\x1f]+@[^@\s\x00-\x1f]+\.[^@\s\x00-\x1f]+', address):
        raise ValueError('请选择邮箱类型并填写完整的邮箱地址。')
    if provider == 'netease' and address.rsplit('@', 1)[1].lower() not in ('163.com', '126.com', 'yeah.net'):
        raise ValueError('网易邮箱支持 163.com、126.com 和 yeah.net。')
    method = raw.get('method', 'google' if provider == 'gmail' else 'imap')
    if method not in ('imap', 'google') or method == 'google' and provider != 'gmail':
        raise ValueError('邮箱授权方式无效。')
    color = raw.get('color', 0)
    if type(color) is not int or not 0 <= color < ACCOUNT_LIMIT:
        color = 0
    result = dict(id=identity, provider=provider, method=method, address=address,
                  name=' '.join(str(raw.get('name', '')).split())[:40], enabled=raw.get('enabled', True) is True, color=color)
    if provider == 'imap':
        server = str(raw.get('server', '')).strip().lower()
        port = raw.get('port', 993)
        webmail = str(raw.get('webmail', '')).strip()
        if len(server) > 253 or not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)*', server) or type(port) is not int or not 1 <= port < 65536:
            raise ValueError('请输入 IMAP 服务器名称和 TLS 端口。')
        try:
            parsed = urlsplit(webmail)
            valid = (parsed.scheme == 'https' and parsed.hostname and parsed.username is None
                     and parsed.password is None and not any(ord(c) <= 32 for c in webmail))
        except ValueError:
            valid = False
        if not valid or len(webmail) > 2048:
            raise ValueError('请填入以 https:// 开头的邮箱网页地址。')
        result.update(server=server, port=port, webmail=webmail)
    return result


def clean_accounts(raw, strict=False):
    if not isinstance(raw, list):
        if strict:
            raise ValueError('邮箱账号列表无效。')
        return []
    if strict and len(raw) > ACCOUNT_LIMIT:
        raise ValueError(f'最多添加 {ACCOUNT_LIMIT} 个邮箱账号。')
    result, ids, addresses, colors = [], set(), set(), set()
    for item in raw[:ACCOUNT_LIMIT]:
        try:
            row = clean_account(item)
            key = (row['provider'], row['address'].casefold())
            if row['id'] in ids or key in addresses:
                raise ValueError('这个邮箱账号已经添加。')
        except ValueError:
            if strict:
                raise
            continue
        if row['color'] in colors:
            row['color'] = next(i for i in range(ACCOUNT_LIMIT) if i not in colors)
        result.append(row)
        ids.add(row['id'])
        addresses.add(key)
        colors.add(row['color'])
    return result
