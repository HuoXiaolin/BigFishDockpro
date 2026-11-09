"""Tencent Meeting's published device login and pending-meeting command."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile

from config_store import _atomic
from resource_agenda_import import event_time, parse_rows
from resource_calendar_api import CalendarError, verification_url
from resource_calendar_tool import download_bundle, install_program, run_tool, verified

VERSION = '1.0.14'
PACKAGE_URL = f'https://registry.npmjs.org/@tencentcloud/tmeet/-/tmeet-{VERSION}.tgz'
PACKAGE_SIZE = 14_508_532
PACKAGE_HASH = ('295f5f208e0054f51e8cb5b40d71a4e033d9744acf21eb2df8662be9570fd8e32b'
                '986388b33f143a1c0d7f48377ac1504ea6cd3de0f50b86a2732be9eee2afda')
EXE_HASH = '744c50643b7a3c25325249e7c910a6847390ae538cf48ecd5c5def4542e6b285'
INACTIVE = {'MEETING_STATE_CANCELLED', 'MEETING_STATE_DELETED', 'MEETING_STATE_RECYCLED',
            'Cancelled', 'Canceled', 'Deleted', 'Recycled', '已取消', '已删除', '已回收'}


def executable(directory):
    return Path(directory) / 'calendar-tools' / f'tmeet-{VERSION}' / 'tmeet.exe'


def config_folder(directory):
    return Path(directory) / 'tencent-meeting-login'


def active_identity(folder):
    # This file holds the CLI's active account ID. Its tokens stay in the
    # official Windows keychain and are never read by Dock.
    try:
        with (folder / 'config.json').open('rb') as file:
            value = json.loads(file.read(4096)).get('active_open_id')
        if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_]{1,512}', value):
            return value
    except (OSError, ValueError, AttributeError, RecursionError):
        pass
    return None


def ensure_tool(job):
    target = executable(job.directory)
    if verified(target, EXE_HASH):
        return target
    with tempfile.TemporaryFile() as download:
        download_bundle(job, download, PACKAGE_URL, PACKAGE_SIZE, PACKAGE_HASH, '腾讯会议')
        with tarfile.open(fileobj=download, mode='r:gz') as archive:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile('package/LICENSE') as license_file:
                _atomic(target.parent / 'LICENSE', license_file.read())
            with archive.extractfile('package/dist/tmeet-Windows-x86_64.exe') as source:
                install_program(job, source, target, EXE_HASH, '腾讯会议')
    job.progress.emit('ready', 0, 0)
    return target


def invoke(job, args, timeout=25, on_scan=None):
    program = getattr(job, 'verified_tool', None)
    if program is None:
        program = executable(job.directory)
        if not verified(program, EXE_HASH):
            raise CalendarError('腾讯会议授权组件需要重新安装，请重新扫码。', 'login')
        job.verified_tool = program
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('TMEET_')}
    folder = config_folder(job.directory)
    env.update(TMEET_CLI_CONFIG_DIR=str(folder), TMEET_CLI_DATA_DIR=str(folder / 'private'))
    sent_url = False

    def publish(line):
        nonlocal sent_url
        if sent_url or not line.startswith('authorize url: '):
            return
        try:
            url = verification_url('tencent', line.removeprefix('authorize url: '))
        except CalendarError:
            return
        on_scan('tencent', url)
        sent_url = True

    code, output, diagnostics = run_tool(job, program, (*args, '--format', 'json'), env, timeout,
                                         '腾讯会议', scan=publish if on_scan else None, watch_stdout=bool(on_scan))
    if code:
        detail = diagnostics.lower()
        if any(word in detail for word in ('already logged in', 'already initialized', 'has been initialized')):
            if on_scan and active_identity(folder):
                return b''
        if '500246' in detail or 'rate limit' in detail or 'too many requests' in detail:
            raise CalendarError('腾讯会议查询暂时受限，稍后自动重试。', 'rate')
        if any(word in detail for word in ('auth login', 'token expired', 'identity expired',
                                          'refresh token failed', 'unauthorized')):
            raise CalendarError('腾讯会议授权已失效，请重新扫码。', 'login')
        raise CalendarError('腾讯会议操作失败，请检查网络和账号的会议访问权限。')
    return output


def login(job):
    job.verified_tool = ensure_tool(job)
    invoke(job, ('auth', 'login', '--no-browser'), timeout=330, on_scan=job.scan.emit)
    identity = active_identity(config_folder(job.directory))
    if not identity:
        raise CalendarError('未取得腾讯会议登录账号，请重新扫码。', 'login')
    return dict(mode='tencent-device', identity=identity)


def logout(job):
    folder = config_folder(job.directory)
    identity = job.account['identity']
    if active_identity(folder) != identity:
        return
    # On Windows the official CLI shares its secure store by account ID.
    # Keep another official CLI session if it points to the same account.
    other = [Path.home() / '.tmeet']
    if external := os.environ.get('TMEET_CLI_CONFIG_DIR'):
        other.append(Path(external))
    if any(path.resolve() != folder.resolve() and active_identity(path) == identity for path in other):
        (folder / 'config.json').unlink(missing_ok=True)
    else:
        invoke(job, ('auth', 'logout'))


def meeting_rows(rows, start, end):
    records = []
    for meeting in rows:
        if not isinstance(meeting, dict):
            raise ValueError('Invalid meeting')
        if meeting.get('status') in INACTIVE:
            continue
        key = meeting['meeting_id']
        if not isinstance(key, str) or not key:
            raise ValueError('Invalid meeting ID')
        occurrences = meeting.get('sub_meetings') or ()
        if occurrences and not isinstance(occurrences, list):
            raise ValueError('Invalid meeting occurrences')
        for row in occurrences or (meeting,):
            if occurrences and row.get('status') in (1, '1', 'Deleted', '已删除'):
                continue
            occurrence_id = row['sub_meeting_id'] if occurrences else ''
            if occurrences and (not isinstance(occurrence_id, str) or not occurrence_id):
                raise ValueError('Invalid meeting occurrence ID')
            times = []
            for field in ('start_time', 'end_time'):
                value = row[field]
                numeric = type(value) is int or isinstance(value, str) and value.isascii() and value.isdigit()
                times.append(event_time({'timestamp' if numeric else 'dateTime': value}))
            begins, ends = times
            if not 0 <= begins < ends < 10**10:
                raise ValueError('Invalid meeting times')
            if ends > start and begins < end:
                records.append(dict(id=f'{key}:{occurrence_id}', summary=meeting.get('subject'),
                                    start=dict(timestamp=begins), end=dict(timestamp=ends)))
    return parse_rows('tencent', records, strict=True)[0]


def read_calendar(job):
    if active_identity(config_folder(job.directory)) != job.account['identity']:
        raise CalendarError('腾讯会议登录已失效，请重新扫码。', 'login')
    start, end = job.now - 86400, job.now + 14 * 86400
    since = datetime.fromtimestamp(start, timezone.utc).isoformat()
    args = ('meeting', 'list', '--start', since, '--page-size', '20', '--show-all-sub', '1')
    events, seen, paging = {}, set(), ()
    for _ in range(20):
        data = json.loads(invoke(job, (*args, *paging)))['data']
        rows = data.get('meeting_info_list')
        if rows is None and data.get('meeting_number') == 0:
            rows = []
        if not isinstance(rows, list):
            break
        events.update((row['id'], row) for row in meeting_rows(rows, start, end))
        cursor = data.get('next_page_token')
        if not cursor and data.get('remaining') in (None, 0, '0'):
            return list(events.values())
        if not isinstance(cursor, str) or not cursor or cursor in seen or len(cursor) > 4096:
            break
        seen.add(cursor)
        paging = (f'--page-token={cursor}',)
    raise CalendarError('腾讯会议列表未完整返回，已保留上次同步结果。')
