"""Read-only calendar APIs and Feishu's documented device registration flow."""
from base64 import b64encode, urlsafe_b64encode
from datetime import datetime, timezone
import gzip
import json
import time
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from resource_agenda_import import parse_rows

DING = 'https://api.dingtalk.com/v1.0'
FEISHU = 'https://open.feishu.cn/open-apis/calendar/v4'
FEISHU_ACCOUNT = 'https://accounts.feishu.cn/oauth'
FEISHU_SCOPES = ('calendar:calendar:read', 'calendar:calendar.event:read', 'offline_access')
MAX_RESPONSE = 4 * 1024 * 1024


class CalendarError(Exception):
    def __init__(self, message, kind='temporary', status=None):
        super().__init__(message)
        self.kind = kind
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request_json(url, *, headers=None, body=None, form=False, expected_errors=()):
    headers = dict(headers or {}, Accept='application/json')
    if body is not None:
        if form:
            body = urlencode(body).encode('ascii')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
    request = Request(url, data=body, headers=headers)
    status = 200
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        with error:
            status = error.code
            raw = error.read(32768)
    except OSError as error:
        raise CalendarError('暂时无法连接，稍后自动重试。') from error

    data = {}
    if len(raw) > MAX_RESPONSE:
        raise CalendarError('接口响应过大，已保留上次同步结果。')
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        if status == 200:
            raise CalendarError('接口响应无法读取，已保留上次同步结果。') from None
    if not isinstance(data, dict):
        raise CalendarError('接口响应格式有误。')
    code = str(data.get('error') or data.get('code', '0'))
    if status < 500 and code in expected_errors:
        return data
    if status == 429 or code in ('190004', '190005', '190010', '99991403'):
        raise CalendarError('平台调用已限流，稍后自动重试。', 'rate')
    if code in ('invalid_grant', 'invalid_client', '99991669', '20002', '20003', '20004', '20010'):
        raise CalendarError('授权凭证无效，请检查应用信息并重新授权。', 'login')
    if status == 401 or code in ('99991668', '99991677', '20005', '20006', 'InvalidAccessToken'):
        raise CalendarError('访问凭证已失效。', 'token')
    if status == 403 or code in ('99991672', '99991676', '99991679', '191002'):
        raise CalendarError('日历读取权限不足，请重新扫码或联系组织管理员。', 'login')
    if status >= 300 or code not in ('0', ''):
        raise CalendarError('接口读取失败，请检查开放平台中的权限和应用状态。', status=status)
    return data


def verification_url(source, url):
    hosts = {
        'dingtalk': ('login.dingtalk.com',),
        'feishu': ('open.feishu.cn', 'accounts.feishu.cn', 'applink.feishu.cn', 'open.larkoffice.com'),
        'tencent': ('meeting.tencent.com',),
    }[source]
    if isinstance(url, str) and 0 < len(url) <= 2048 and all(32 < ord(char) < 127 for char in url):
        try:
            parsed = urlsplit(url)
            if (parsed.scheme == 'https' and parsed.hostname in hosts and parsed.port in (None, 443)
                    and not parsed.username and not parsed.password and '\\' not in url
                    and (source != 'tencent' or parsed.path == '/marketplace/tencentmeeting-cli-auth.html')):
                return url
        except ValueError:
            pass
    raise CalendarError('平台返回的扫码链接无效，请重试。')


def poll_device(url, body, offer, completed_key, cancelled):
    # Honor the provider's timing and stop promptly if the user closes the dialog.
    interval = offer.get('interval', 5)
    expires = offer.get('expires_in', offer.get('expire_in', 600))
    interval = min(60, max(5, interval)) if type(interval) is int else 5
    expires = min(600, max(1, expires)) if type(expires) is int else 600
    deadline = time.monotonic() + expires
    expected = ('authorization_pending', 'slow_down', 'expired_token', 'access_denied')
    while time.monotonic() < deadline:
        if cancelled.wait(min(interval, max(0, deadline - time.monotonic()))):
            raise CalendarError('已取消扫码授权。')
        if time.monotonic() >= deadline:
            break
        response = request_json(url, body=body, form=True, expected_errors=expected)
        if response.get(completed_key):
            return response
        error = response.get('error')
        if error == 'slow_down':
            interval = min(60, interval + 5)
        elif error == 'access_denied':
            raise CalendarError('飞书未批准本次授权。', 'login')
        elif error == 'expired_token':
            break
    raise CalendarError('飞书二维码已过期，请重新扫码。')


def register_feishu(scan, cancelled):
    url = FEISHU_ACCOUNT + '/v1/app/registration'
    offer = request_json(url, form=True, body=dict(action='begin', archetype='PersonalAgent',
                                                  auth_method='client_secret', request_user_info='open_id'))
    device_code = offer.get('device_code')
    if not isinstance(device_code, str) or not device_code:
        raise CalendarError('飞书未返回应用注册凭证。')
    qr = urlsplit(verification_url('feishu', offer.get('verification_uri_complete')))
    addons = dict(preset=False, scopes=dict(user=list(FEISHU_SCOPES)))
    compact = json.dumps(addons, separators=(',', ':')).encode('ascii')
    preset = urlsafe_b64encode(gzip.compress(compact, mtime=0)).rstrip(b'=').decode('ascii')
    query = dict(parse_qsl(qr.query, keep_blank_values=True))
    query.update({'from': 'sdk', 'tp': 'sdk', 'source': 'BigFishDockpro', 'name': '大肥鱼 Dock 日程',
                  'desc': '在桌面胶囊显示飞书日程与提醒', 'addons': preset, 'createOnly': 'true'})
    scan('feishu-app', verification_url('feishu', qr._replace(query=urlencode(query)).geturl()))
    response = poll_device(url, dict(action='poll', device_code=device_code), offer, 'client_secret', cancelled)
    client, secret = response.get('client_id'), response.get('client_secret')
    if not all(isinstance(value, str) and 0 < len(value) <= 512 and value.isascii() for value in (client, secret)):
        raise CalendarError('飞书未返回有效的应用注册信息。')
    return dict(mode='feishu-device', client_id=client, secret=secret)


def authorize_feishu(account, scan, cancelled):
    basic = b64encode((account['client_id'] + ':' + account['secret']).encode('ascii')).decode('ascii')
    offer = request_json(FEISHU_ACCOUNT + '/v1/device_authorization', headers={'Authorization': 'Basic ' + basic},
                         body=dict(client_id=account['client_id'], scope=' '.join(FEISHU_SCOPES)), form=True)
    device_code = offer.get('device_code')
    if not isinstance(device_code, str) or not device_code:
        raise CalendarError('飞书未返回日历授权凭证。')
    scan('feishu-user', verification_url('feishu', offer.get('verification_uri_complete')))
    params = dict(client_id=account['client_id'], client_secret=account['secret'], device_code=device_code,
                  grant_type='urn:ietf:params:oauth:grant-type:device_code')
    token = poll_device(FEISHU_ACCOUNT + '/v3/token', params, offer, 'access_token', cancelled)
    return with_tokens(account, token.get('access_token'), token.get('refresh_token'), token.get('expires_in'))


def token_response(url, body):
    try:
        return request_json(url, body=body)
    except CalendarError as error:
        if error.status == 400:
            raise CalendarError('授权凭证无效，请检查应用信息并重新授权。', 'login') from error
        raise


def exchange(source, account):
    if source == 'dingtalk':
        params = dict(clientId=account['client_id'], clientSecret=account['secret'],
                      grantType='refresh_token', refreshToken=account['refresh'])
        data = token_response(DING + '/oauth2/userAccessToken', params)
        access, refresh, seconds = data.get('accessToken'), data.get('refreshToken'), data.get('expireIn')
    else:
        params = dict(client_id=account['client_id'], client_secret=account['secret'],
                      grant_type='refresh_token', refresh_token=account['refresh'])
        data = token_response(FEISHU_ACCOUNT + '/v3/token', params)
        access, refresh, seconds = data.get('access_token'), data.get('refresh_token'), data.get('expires_in')
    return with_tokens(account, access, refresh or account['refresh'], seconds)


def with_tokens(account, access, refresh, seconds):
    if not isinstance(refresh, str) or not 0 < len(refresh) <= 8192:
        raise CalendarError('未获得续期凭证，请检查权限并重新授权。', 'login')
    if not isinstance(access, str) or not 0 < len(access) <= 8192 or type(seconds) is not int or not 0 < seconds <= 86400:
        raise CalendarError('授权响应缺少有效期或访问凭证。')
    return dict(account, access=access, refresh=refresh, expires=int(time.time()) + seconds)


def auth_headers(source, access):
    if source == 'dingtalk':
        return {'x-acs-dingtalk-access-token': access}
    return {'Authorization': 'Bearer ' + access}


def primary_calendar(source, access):
    headers = auth_headers(source, access)
    try:
        if source == 'dingtalk':
            identity = request_json(DING + '/contact/users/me', headers=headers)['unionId']
        else:
            data = request_json(FEISHU + '/calendars/primary', headers=headers, body={})
            identity = data['data']['calendars'][0]['calendar']['calendar_id']
        if isinstance(identity, str) and 0 < len(identity) <= 512:
            return identity
    except (KeyError, TypeError, IndexError):
        pass
    raise CalendarError('找不到当前账号的主日历，请检查应用权限。', 'login')


def read_events(source, account, now, cancelled):
    headers = auth_headers(source, account['access'])
    identity = quote(account['identity'], safe='')
    start, end = now - 86400, now + 14 * 86400
    if source == 'feishu':
        query = urlencode(dict(start_time=start, end_time=end))
        response = request_json(f'{FEISHU}/calendars/{identity}/events/instance_view?{query}', headers=headers)
        data = response.get('data')
        rows = data.get('items', []) if isinstance(data, dict) else None
        if isinstance(rows, list):
            return parse_rows(source, rows, strict=True)[0]
    else:
        url = f'{DING}/calendar/users/{identity}/calendars/primary/eventsview?'
        query = dict(timeMin=datetime.fromtimestamp(start, timezone.utc).isoformat(),
                     timeMax=datetime.fromtimestamp(end, timezone.utc).isoformat(), maxResults=50)
        events, seen = {}, set()
        for _ in range(20):
            if cancelled.is_set():
                raise CalendarError('同步已取消。')
            response = request_json(url + urlencode(query), headers=headers)
            rows = response.get('events')
            if not isinstance(rows, list):
                break
            events.update((row['id'], row) for row in parse_rows(source, rows, strict=True)[0])
            next_page = response.get('nextToken')
            if not next_page:
                return list(events.values())
            if not isinstance(next_page, str) or next_page in seen:
                break
            seen.add(next_page)
            query['nextToken'] = next_page
    raise CalendarError('日程列表未完整返回，已保留上次同步结果。')
