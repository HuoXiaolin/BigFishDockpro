"""Google desktop authorization and incremental Gmail mailbox reads."""
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import secrets
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from mail_accounts import GMAIL_SCOPE, MAIL_LIMIT, inbox_url
from mail_messages import MAX_TEXT, MailError, MailItem, plain_text, summary_subject, verification_code


API = 'https://gmail.googleapis.com/gmail/v1/users/me/'
TOKEN = 'https://oauth2.googleapis.com/token'
AUTHORIZE = 'https://accounts.google.com/o/oauth2/v2/auth'
MAX_RESPONSE = 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def json_request(url, *, token='', fields=None):
    data = urlencode(fields).encode('ascii') if fields is not None else None
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    request = Request(url, data=data, headers=headers)
    with build_opener(NoRedirect()).open(request, timeout=8) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise MailError('Google 返回的数据超过读取限制。')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise MailError('Google 返回的数据格式无效。')
    return result


def desktop_client(value):
    installed = value.get('installed') if isinstance(value, dict) else None
    if not isinstance(installed, dict):
        raise ValueError('请选择 Google OAuth 桌面应用的客户端 JSON。')
    client = installed.get('client_id', '')
    secret = installed.get('client_secret', '')
    if not isinstance(client, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,140}\.apps\.googleusercontent\.com', client):
        raise ValueError('Google OAuth 客户端 ID 无效。')
    if not isinstance(secret, str) or not 1 <= len(secret) <= 200 or not secret.isascii():
        raise ValueError('Google OAuth 客户端密钥无效。')
    return dict(client_id=client, client_secret=secret)


def authorize(client, address, cancelled, browser):
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = urlsafe_b64encode(sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    callback = '/oauth2/callback'
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            target = urlsplit(self.path)
            origin = f'127.0.0.1:{self.server.server_port}'
            query = parse_qs(target.query)
            key = query.get('state', [''])[0]
            if target.path != callback or self.headers.get('Host') != origin or not secrets.compare_digest(key.encode(), state.encode()):
                self.send_response(400)
                self.end_headers()
                return
            result['code'] = query.get('code', [''])[0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write('授权流程已结束，请返回大肥鱼Dock。'.encode('utf-8'))

    class LoopbackServer(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(1.0)
            return connection, address

    with LoopbackServer(('127.0.0.1', 0), Handler) as server:
        server.timeout = .25
        server.socket.settimeout(.25)
        redirect = f'http://127.0.0.1:{server.server_port}' + callback
        query = dict(client_id=client['client_id'], redirect_uri=redirect, scope=GMAIL_SCOPE, state=state,
                     code_challenge=challenge, code_challenge_method='S256', response_type='code',
                     access_type='offline', prompt='consent', login_hint=address)
        browser(AUTHORIZE + '?' + urlencode(query))
        deadline = time.monotonic() + 150
        while not result and not cancelled.is_set() and time.monotonic() < deadline:
            server.handle_request()
    if cancelled.is_set():
        raise MailError('已取消授权。')
    if not result.get('code'):
        raise MailError('Google 授权未完成，请重试。', authorization=True)
    try:
        token = json_request(TOKEN, fields=dict(client, grant_type='authorization_code', code=result['code'],
                                               code_verifier=verifier, redirect_uri=redirect))
    except HTTPError:
        raise MailError('Google 授权凭据无效或已过期，请重新授权。', authorization=True) from None
    if not isinstance(token.get('refresh_token'), str) or not token['refresh_token']:
        raise MailError('Google 未授予后台收件所需的权限，请重新授权。', authorization=True)
    scopes = token.get('scope', '').split()
    if GMAIL_SCOPE not in scopes:
        raise MailError('请同意 Gmail 读取权限。', authorization=True)
    return dict(client, refresh_token=token['refresh_token'])


def gmail_code(payload):
    pending = [payload]
    while pending:
        part = pending.pop()
        if not isinstance(part, dict) or part.get('filename'):
            continue
        children = part.get('parts', [])
        if isinstance(children, list):
            pending.extend(reversed(children))
        mime = part.get('mimeType')
        if mime not in ('text/plain', 'text/html'):
            continue
        data = part.get('body', {}).get('data', '')
        if isinstance(data, str) and data and len(data) < MAX_RESPONSE:
            try:
                text = urlsafe_b64decode(data + '=' * (-len(data) % 4))[:MAX_TEXT].decode('utf-8', errors='replace')
            except ValueError:
                continue
            code = verification_code('', plain_text(text, mime))
            if code:
                return code
    return ''


class GmailSession:
    def __init__(self, account, secret, cancelled):
        self.account = account
        self.secret = secret
        self.cancelled = cancelled
        self.items = {}
        self.history_id = None
        self.token = ''
        self.expires = 0.
        if any(not isinstance(secret.get(key), str) or not secret[key] for key in ('client_id', 'client_secret', 'refresh_token')):
            raise MailError('需要重新授权 Gmail。', authorization=True)

    def close(self):
        self.token = ''
        self.secret = {}

    def api(self, route, fields=None):
        if time.monotonic() >= self.expires or not self.token:
            try:
                renewed = json_request(TOKEN, fields=dict(self.secret, grant_type='refresh_token'))
            except HTTPError as error:
                if error.code in (400, 401, 403):
                    raise MailError('Gmail 授权已失效，请重新授权。', authorization=True) from None
                raise
            self.token = renewed.get('access_token', '')
            if not isinstance(self.token, str) or not self.token:
                raise MailError('Gmail 授权已失效，请重新授权。', authorization=True)
            self.expires = time.monotonic() + max(1, int(renewed.get('expires_in', 3600)) - 45)
        return json_request(API + route + ('?' + urlencode(fields, doseq=True) if fields else ''), token=self.token)

    def test(self):
        profile = self.api('profile', {'fields': 'emailAddress,historyId'})
        if profile.get('emailAddress', '').casefold() != self.account['address'].casefold():
            raise MailError('Google 授权的地址与输入的邮箱不同。', authorization=True)
        return str(profile.get('historyId', ''))

    def latest_history(self):
        added = set()
        cursor = self.history_id
        token = ''
        for _ in range(8):
            if self.cancelled.is_set():
                return set(), self.history_id
            params = dict(startHistoryId=self.history_id, labelId='INBOX', historyTypes='messageAdded', maxResults=250)
            if token:
                params['pageToken'] = token
            try:
                snapshot = self.api('history', params)
            except HTTPError as error:
                if error.code == 404:
                    return set(), self.test()
                raise
            for event in snapshot.get('history', ()):
                cursor = str(event.get('id', cursor))
                for entry in event.get('messagesAdded', ()):
                    added.add(entry.get('message', {}).get('id'))
            token = snapshot.get('nextPageToken')
            if not token:
                return added, str(snapshot.get('historyId', cursor))
        return added, cursor

    def snapshot(self, detect_codes):
        arrivals, cursor = self.latest_history() if self.history_id else (set(), self.test())
        recent = self.api('messages', dict(labelIds='INBOX', maxResults=MAIL_LIMIT, fields='messages(id)'))
        items, new = {}, []
        for entry in recent.get('messages', ())[:MAIL_LIMIT]:
            if self.cancelled.is_set():
                return (), ()
            uid = entry.get('id', '')
            if not isinstance(uid, str) or not re.fullmatch(r'[a-fA-F0-9]{8,32}', uid):
                continue
            if uid in self.items and uid not in arrivals:
                items[uid] = self.items[uid]
                continue
            route = 'messages/' + quote(uid, safe='')
            try:
                message = self.api(route, {'format': 'metadata', 'metadataHeaders': ('From', 'Subject'),
                                           'fields': 'internalDate,payload(headers)'})
            except HTTPError as error:
                if error.code == 404:
                    continue
                raise
            headers = {h['name'].lower(): h['value'] for h in message.get('payload', {}).get('headers', ())}
            subject = headers.get('subject', '')
            sender = ' '.join(headers.get('from', '').split())[:180] or '未知发件人'
            item = MailItem(uid, summary_subject(subject), sender, int(message.get('internalDate', 0)) / 1000,
                            inbox_url(self.account, uid))
            items[uid] = item
            if uid in arrivals:
                code = verification_code(subject)
                if detect_codes and not code:
                    try:
                        message = self.api(route, {'format': 'full', 'fields': 'payload(mimeType,body(data),parts)'})
                        code = gmail_code(message.get('payload', {}))
                    except (MailError, HTTPError, OSError, ValueError):
                        pass
                new.append((item, code))
        self.items = items
        self.history_id = cursor
        return tuple(items.values()), new
