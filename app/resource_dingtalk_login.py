"""Run DingTalk's published device login and read-only calendar command."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from zipfile import ZipFile

from config_store import _atomic
from resource_agenda_import import parse_rows
from resource_calendar_api import CalendarError, verification_url
from resource_calendar_tool import download_bundle, install_program, run_tool, verified

VERSION = '1.0.67'
RELEASE = f'https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli/releases/tag/v{VERSION}'
ZIP_URL = RELEASE.replace('/tag/', '/download/') + '/dws-windows-amd64.zip'
ZIP_SIZE = 25_194_574
ZIP_HASH = '3cb839866497405581c8ba5ef069e635495e9ee8afa8ff736c11f66db726184e'
EXE_HASH = 'f8de6a7ac044af8641be6f9ca88a40f1a98cea9bb8012830fad1871cf2da570c'


def executable(directory):
    return Path(directory) / 'calendar-tools' / f'dws-{VERSION}' / 'dws.exe'


def tool_candidates(directory):
    paths = [executable(directory), Path.home() / '.local' / 'bin' / 'dws.exe']
    if installed := shutil.which('dws.exe'):
        paths.append(Path(installed).absolute())
    return tuple(dict.fromkeys(paths))


def installed_tool(directory):
    return next((path for path in tool_candidates(directory) if verified(path, EXE_HASH)), None)


def ensure_tool(job):
    installed = installed_tool(job.directory)
    if installed:
        return installed
    target = executable(job.directory)
    with tempfile.TemporaryFile() as download:
        download_bundle(job, download, ZIP_URL, ZIP_SIZE, ZIP_HASH, '钉钉')
        with ZipFile(download) as archive, archive.open('dws.exe') as source:
            target.parent.mkdir(parents=True, exist_ok=True)
            for name in ('LICENSE', 'NOTICE'):
                _atomic(target.parent / name, archive.read(name))
            install_program(job, source, target, EXE_HASH, '钉钉')
    job.progress.emit('ready', 0, 0)
    return target


def invoke(job, args, timeout=25, on_scan=None):
    program = getattr(job, 'verified_tool', None) or installed_tool(job.directory)
    if program is None:
        raise CalendarError('钉钉授权组件需要重新安装，请重新扫码。', 'login')
    job.verified_tool = program
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('DWS_')}
    env.update(DWS_CONFIG_DIR=str(job.directory / 'dingtalk-login'), DWS_LANG='zh')
    sent_url = False

    def publish(line):
        nonlocal sent_url
        if not sent_url and line.startswith('https://'):
            try:
                url = verification_url('dingtalk', line)
            except CalendarError:
                return
            on_scan('dingtalk', url)
            sent_url = True

    code, raw, diagnostics = run_tool(job, program, (*args, '--format', 'json'), env, timeout, '钉钉',
                                      scan=publish if on_scan else None)
    if code:
        if any(word in diagnostics for word in ('未开通', '管理员', 'authorization_required', 'scope')):
            raise CalendarError('钉钉日历权限未开通，请在钉钉确认授权或联系组织管理员。', 'login')
        if any(word in diagnostics.lower() for word in ('not logged in', 'unauthorized', '未登录', '重新登录', 'token expired')):
            raise CalendarError('钉钉登录已失效，请重新扫码。', 'login')
        raise CalendarError('钉钉操作失败，请检查网络和组织的 CLI 访问权限。')
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        raise CalendarError('钉钉返回了无法读取的数据。') from None
    if not isinstance(data, dict) or data.get('success') is not True:
        raise CalendarError('钉钉未返回完整结果。')
    return data


def login(job):
    job.verified_tool = ensure_tool(job)
    data = invoke(job, ('auth', 'login', '--device', '--no-browser'), timeout=600, on_scan=job.scan.emit)
    corp, user = data.get('corp_id'), data.get('user_id')
    if not all(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_@.=+/\-]{1,200}', value)
               for value in (corp, user)):
        raise CalendarError('未取得钉钉组织和账号标识，请重新扫码并选择组织。', 'login')
    return dict(mode='dingtalk-device', identity=f'{corp}:{user}')


def logout(job):
    invoke(job, ('auth', 'logout', f"--profile={job.account['identity']}"))


def read_calendar(job):
    start, end = (datetime.fromtimestamp(value, timezone.utc).isoformat()
                  for value in (job.now - 86400, job.now + 14 * 86400))
    args = ('calendar', 'event', 'list', f"--profile={job.account['identity']}",
            '--start', start, '--end', end, '--limit', '50', '--timeout', '12')
    events, seen, paging = {}, set(), ()
    for _ in range(20):
        data = invoke(job, (*args, *paging))
        result = data.get('result')
        rows = result.get('events') if isinstance(result, dict) else result
        if not isinstance(rows, list):
            break
        events.update((row['id'], row) for row in parse_rows('dingtalk', rows, strict=True)[0])
        cursor = data.get('nextCursor') or (result.get('nextCursor') if isinstance(result, dict) else None)
        if not cursor:
            return list(events.values())
        if not isinstance(cursor, str) or cursor in seen or len(cursor) > 4096:
            break
        seen.add(cursor)
        paging = (f'--cursor={cursor}',)
    raise CalendarError('钉钉日程未完整返回，已保留上次同步结果。')
