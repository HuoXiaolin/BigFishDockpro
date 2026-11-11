"""Read dated tasks from Dida365 and NextTodo with user-provided tokens."""
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import ssl
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, build_opener

from resource_calendar_api import CalendarError, NoRedirect, request_json


TOKEN_SOURCES = ('dida', 'nexttodo')
DIDA_FILTER = 'https://api.dida365.com/open/v1/task/filter'


def token_account(source, token, endpoint=''):
    token = token.strip().removeprefix('Bearer ').strip()
    if not 0 < len(token) <= 8192 or not all(32 < ord(char) < 127 for char in token):
        raise ValueError('请输入有效的 API 口令或令牌。')
    account = dict(mode='token', token=token, identity=source)
    if source == 'nexttodo':
        endpoint = endpoint.strip().rstrip('/') or 'local'
        if endpoint.lower() == 'local':
            endpoint = 'local'
        else:
            try:
                parsed = urlsplit(endpoint)
                if (not 0 < len(endpoint) <= 2048 or not all(32 < ord(char) < 127 for char in endpoint)
                        or any(char in endpoint for char in '\\?#') or parsed.scheme not in ('https', 'http')
                        or not parsed.hostname or '@' in parsed.netloc or parsed.port == 0):
                    raise ValueError()
                endpoint = endpoint.removesuffix('/mcp').removesuffix('/api/v1/snapshot').removesuffix('/api/v1')
                if not urlsplit(endpoint).hostname:
                    raise ValueError()
            except ValueError:
                raise ValueError('请输入 NextTodo 的服务器地址，或填写 local 连接本机版。') from None
        account['endpoint'] = endpoint
    return account


def local_nexttodo():
    appdata = os.environ.get('APPDATA')
    if not appdata:
        raise CalendarError('找不到 NextTodo 本机连接，请先打开 NextTodo 本机版。')
    path = Path(appdata) / 'cn.juniexd.nexttodo' / 'local' / 'address'
    try:
        with path.open('rb') as stream:
            raw = stream.read(32769)
        if len(raw) > 32768:
            raise ValueError()
        data = json.loads(raw)
        url = data['url']
        if not isinstance(url, str):
            raise ValueError()
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != '127.0.0.1' or not parsed.port
                or url != f'https://127.0.0.1:{parsed.port}'):
            raise ValueError()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=data['ca'])
    except FileNotFoundError:
        raise CalendarError('找不到 NextTodo 本机连接，请先打开 NextTodo 本机版。') from None
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise CalendarError('NextTodo 本机连接信息无效，请重新打开 NextTodo。') from None
    return url, build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())


def midnight(day):
    return int(datetime.combine(day, time.min).timestamp())


def dida_time(row):
    if row.get('status', 0) != 0 or row.get('completedTime'):
        return None
    first, last = row.get('startDate'), row.get('dueDate')
    if not (first or last):
        return None
    start_date = datetime.fromisoformat(first or last)
    end_date = datetime.fromisoformat(last or first)
    if row.get('isAllDay') is True:
        return midnight(start_date.date()), midnight(end_date.date() + timedelta(days=1)), 5, 'all_day'
    start, end = int(start_date.timestamp()), int(end_date.timestamp())
    if start == end:
        return start, end + 60, 5, 'deadline'
    return start, end, 5, ''


def nexttodo_time(row):
    due = row.get('due')
    if due is None or row.get('done_at') is not None:
        return None
    day = date.fromisoformat(due['date'])
    if not due.get('time'):
        return midnight(day), midnight(day + timedelta(days=1)), 5, 'all_day'
    clock = time.fromisoformat(due['time'])
    start = int(datetime.combine(day, clock).timestamp())
    lead = due.get('remind_before')
    lead = min(180, max(0, lead)) if type(lead) is int else 5
    return start, start + 60, lead, 'deadline'


def task_events(source, rows, window_start, window_end):
    if not isinstance(rows, list):
        raise CalendarError('接口未返回待办列表，已保留上次同步结果。')
    get_time = dida_time if source == 'dida' else nexttodo_time
    events = {}
    try:
        for row in rows:
            timing_data = get_time(row)
            if timing_data is None:
                continue
            start, end, lead, timing = timing_data
            key = row['id']
            title = ' '.join(row['title'].split())[:120] or '未命名待办'
            if (not isinstance(key, str) or not 0 < len(key) <= 512 or not key.isprintable()
                    or not title.isprintable() or not 0 <= start < end < 10**10):
                raise ValueError()
            if end <= window_start or start >= window_end:
                continue
            identity = sha256(f'{source}:{key}'.encode('utf-8')).hexdigest()[:32]
            event = dict(id=identity, title=title, start=start, end=end, lead=lead,
                         ack=timing == 'all_day', source=source)
            if timing:
                event['timing'] = timing
            events[identity] = event
    except (AttributeError, KeyError, OSError, OverflowError, TypeError, ValueError):
        raise CalendarError('待办时间或标题格式有误，已保留上次同步结果。') from None
    return list(events.values())


def read_task_events(source, account, now):
    headers = {'Authorization': 'Bearer ' + account['token']}
    start, end = now - 86400, now + 14 * 86400
    try:
        if source == 'dida':
            # The API's date filters are based on dueDate and would omit start-only tasks.
            rows = request_json(DIDA_FILTER, headers=headers, body={'status': [0]}, allow_list=True)
        else:
            endpoint = account['endpoint']
            opener = None
            if endpoint == 'local':
                endpoint, opener = local_nexttodo()
            headers['User-Agent'] = 'BigFishDockpro'
            data = request_json(endpoint + '/api/v1/snapshot', headers=headers, opener=opener)
            identity = data.get('user')
            if not isinstance(identity, str) or not 0 < len(identity) <= 512 or not identity.isprintable():
                raise CalendarError('NextTodo 未返回有效的账号信息，已保留上次同步结果。')
            account['identity'] = identity
            rows = data.get('tasks')
    except CalendarError as error:
        if error.kind == 'edge':
            raise
        if error.kind in ('token', 'login'):
            raise CalendarError('口令或令牌无效，或缺少待办读取权限。请检查后重新连接。', error.kind) from None
        if error.status:
            raise CalendarError(f'待办接口读取失败（HTTP {error.status}），请检查连接设置。') from None
        raise
    return task_events(source, rows, start, end)
