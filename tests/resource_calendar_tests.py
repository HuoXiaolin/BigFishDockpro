"""Exercise QR login, token rotation and authoritative snapshots."""
from base64 import urlsafe_b64decode
from datetime import datetime, timedelta, timezone
import gzip
from hashlib import sha256
from io import BytesIO
import json
from os import environ
from threading import Event
from time import monotonic, sleep, time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

from PyQt5.QtCore import QObject


def check_device_poll(api):
    cancelled = Mock()
    cancelled.wait.return_value = False
    responses = [{'error':'authorization_pending'}, {'error':'slow_down'}, {'access_token':'fixture'}]
    with patch.object(api,'request_json',side_effect=responses):
        result=api.poll_device('https://accounts.feishu.cn/oauth/v3/token',{},dict(interval=5,expires_in=120),
                               'access_token',cancelled)
    waits=[call.args[0] for call in cancelled.wait.call_args_list]
    assert result==responses[-1] and waits==[5,5,10]
    for url in ('http://accounts.feishu.cn/verify','https://login.dingtalk.com@other.invalid/'):
        try:
            api.verification_url('feishu',url)
        except api.CalendarError:
            pass
        else:
            raise AssertionError('untrusted QR destination')


def check_dingtalk_download(directory, api, dingtalk):
    import resource_calendar_tool as tool

    binary = b'fixture program'
    stream = BytesIO()
    with ZipFile(stream, 'w') as archive:
        archive.writestr('dws.exe', binary)
        archive.writestr('LICENSE', 'fixture')
        archive.writestr('NOTICE', 'fixture')
    contents = stream.getvalue()
    job = SimpleNamespace(directory=directory, cancelled=Event(), progress=Mock())
    local = directory / 'installed' / 'dws.exe'
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(binary)
    managed = dingtalk.executable(directory)
    managed.unlink(missing_ok=True)
    with patch.multiple(dingtalk, ZIP_SIZE=len(contents), ZIP_HASH=sha256(contents).hexdigest(),
                        EXE_HASH=sha256(binary).hexdigest()), patch.object(dingtalk,'tool_candidates',return_value=(managed,local)):
        with patch.object(tool, 'urlopen') as open_download:
            assert dingtalk.ensure_tool(job) == local
            open_download.assert_not_called()
        local.unlink()
        with patch.object(tool, 'urlopen', return_value=BytesIO(contents)):
            assert dingtalk.ensure_tool(job) == managed
            assert managed.read_bytes() == binary
        assert [call.args for call in job.progress.emit.call_args_list] == [
            ('download',0,len(contents)),('download',len(contents),len(contents)),
            ('install',len(contents),len(contents)),('ready',0,0)]
        managed.unlink()
        with patch.object(tool, 'urlopen', return_value=BytesIO(contents[:-1])):
            try:
                dingtalk.ensure_tool(job)
            except api.CalendarError:
                pass
            else:
                raise AssertionError('partial package installed')
        assert not managed.exists()
        job.progress.emit.side_effect = lambda *_: job.cancelled.set()
        with patch.object(tool, 'urlopen', return_value=BytesIO(contents)):
            try:
                dingtalk.ensure_tool(job)
            except api.CalendarError:
                pass
            else:
                raise AssertionError('cancelled download installed')
        assert not managed.exists()


def check_task_accounts(sync, agenda, finish, now):
    from calendar_markers import MARKER_TONES, month_markers
    import resource_calendar_api as api
    import resource_calendar_sync as calendar
    import resource_task_calendars as tasks

    cutoff = datetime.fromtimestamp(now[0]).replace(hour=23, minute=59, second=45, microsecond=0)
    tomorrow = cutoff.date() + timedelta(days=1)
    dida = dict(id='dida-id', title='有截止时间的任务', status=0, dueDate=cutoff.astimezone().isoformat())
    dida_rows = [dida, dict(id='dida-start', title='只有开始时间', status=0, startDate=dida['dueDate']),
                 dict(id='ignored', title='无日期', status=0), dict(dida, id='finished', status=2)]
    nexttodo = dict(id='next-id', title='等待前置任务', status='waiting', done_at=None,
                    due=dict(date=tomorrow.isoformat(), time='09:30', remind_before=25))
    all_day = dict(id='next-all-day', title='全天任务', due=dict(date=tomorrow.isoformat()))
    next_rows = [nexttodo, all_day, dict(nexttodo, id='finished', done_at=1), dict(nexttodo, id='undated', due=None)]
    snapshot = dict(user='nexttodo-test-user', tasks=next_rows)
    next_error = ''

    def request(http, timeout):
        assert timeout == 8
        auth = http.get_header('Authorization')
        if http.full_url == tasks.DIDA_FILTER:
            assert http.get_method() == 'POST' and json.loads(http.data) == {'status': [0]}
            if auth == 'Bearer rejected-fixture':
                raise HTTPError(http.full_url, 401, 'Unauthorized', {}, BytesIO(b'[]'))
            assert auth == 'Bearer fixture-dida'
            data = dida_rows
        else:
            assert http.get_method() == 'GET' and http.data is None and auth == 'Bearer fixture-next'
            assert http.get_header('User-agent') == 'BigFishDockpro'
            assert http.full_url in ('https://next.invalid/todo/api/v1/snapshot',
                                     'https://127.0.0.1:44007/api/v1/snapshot',
                                     'https://127.0.0.1:44008/api/v1/snapshot')
            if next_error == 'edge':
                body = b'{"cloudflare_error":true,"error_code":1010}'
                raise HTTPError(http.full_url, 403, 'Forbidden', {}, BytesIO(body))
            if next_error == 'expired':
                raise HTTPError(http.full_url, 401, 'Unauthorized', {}, BytesIO(b'{}'))
            data = snapshot
        return BytesIO(json.dumps(data).encode('utf-8'))

    opener = Mock()
    opener.open.side_effect = request
    with patch.object(api, 'build_opener', return_value=opener):
        assert sync.connect_account('dida', token='Bearer fixture-dida')
        finish()
        assert 'dida' not in sync.errors and sync.timer.isActive()
        state = sync.states['dida']
        assert len(state['events']) == 2 and all(row['timing'] == 'deadline' for row in state['events'])
        assert month_markers(state['events'], (), cutoff.date(), 2) == {cutoff.date(): {'dida'}}
        path = calendar.connection_path(sync.directory, 'dida')
        assert b'fixture-dida' not in path.read_bytes() and calendar.read_connection(path, 'dida') == state
        assert sync.connect_account('dida', token='rejected-fixture')
        finish()
        assert sync.states['dida'] == state and 'dida' not in sync.reauthorize
        assert '缺少待办读取权限' in sync.errors['dida']

        assert sync.connect_account('nexttodo', token='fixture-next', endpoint='https://next.invalid/todo/mcp')
        finish()
        assert sync.rename_account('nexttodo', '  项目待办  ')
        state = sync.states['nexttodo']
        assert state['label'] == '项目待办'
        assert state['account']['endpoint'] == 'https://next.invalid/todo'
        records = {row['title']: row for row in state['events']}
        all_day_record = records[all_day['title']]
        deadline = records[nexttodo['title']]
        assert all_day_record['timing'] == 'all_day' and all_day_record['ack']
        assert deadline['timing'] == 'deadline' and deadline['lead'] == 25
        assert MARKER_TONES['dida'] != MARKER_TONES['nexttodo']

        next_error = 'edge'
        sync.sync_now('nexttodo')
        finish()
        assert 'Cloudflare' in sync.errors['nexttodo'] and '1010' in sync.errors['nexttodo']
        assert 'nexttodo' not in sync.reauthorize and sync.states['nexttodo'] == state
        next_error = 'expired'
        sync.sync_now('nexttodo')
        finish()
        path = calendar.connection_path(sync.directory, 'nexttodo')
        reopened = calendar.read_connection(path, 'nexttodo')
        assert 'nexttodo' in sync.reauthorize and reopened['needs_auth'] and reopened['label'] == '项目待办'
        assert '项目待办'.encode('utf-8') not in path.read_bytes()
        next_error = ''
        assert sync.connect_account('nexttodo', token='fixture-next', endpoint='https://next.invalid/todo')
        finish()
        assert 'nexttodo' not in sync.reauthorize and 'needs_auth' not in sync.states['nexttodo']
        assert sync.states['nexttodo']['label'] == '项目待办'

        cfg = sync.owner.cfg
        cfg.update(resource_enabled=False, resource_component_locations={'agenda': 'desktop'})
        sync.schedule()
        assert sync.timer.isActive()
        cfg['resource_agenda'] = False
        sync.schedule()
        assert not sync.timer.isActive()
        cfg.update(resource_enabled=True, resource_agenda=True)

        assert agenda.synced_reminder(deadline['id'], lead=15, ack=True)
        nexttodo['due']['time'] = '10:00'
        sync.sync_now('nexttodo')
        finish()
        moved = next(row for row in sync.states['nexttodo']['events'] if row['id'] == deadline['id'])
        assert moved['start'] == deadline['start'] + 1800 and moved['lead'] == 15 and not moved['ack']
        snapshot['tasks'] = {'invalid': True}
        sync.sync_now('nexttodo')
        finish()
        assert 'nexttodo' in sync.errors and moved in sync.states['nexttodo']['events']
        snapshot['tasks'] = next_rows

        appdata = sync.directory / 'nexttodo-local-fixture'
        address = appdata / 'cn.juniexd.nexttodo' / 'local' / 'address'
        address.parent.mkdir(parents=True, exist_ok=True)
        context = Mock()
        test_ssl = SimpleNamespace(SSLContext=Mock(return_value=context), PROTOCOL_TLS_CLIENT=tasks.ssl.PROTOCOL_TLS_CLIENT)
        with patch.dict(environ, APPDATA=str(appdata)), patch.object(tasks, 'ssl', test_ssl), \
                patch.object(tasks, 'build_opener', return_value=opener):
            address.write_text(json.dumps(dict(url='https://127.0.0.1:44007', ca='fixture CA')), encoding='utf-8')
            assert sync.connect_account('nexttodo', token='fixture-next', endpoint='local')
            finish()
            context.load_verify_locations.assert_called_once_with(cadata='fixture CA')
            assert sync.states['nexttodo']['account']['endpoint'] == 'local'
            address.write_text(json.dumps(dict(url='https://127.0.0.1:44008', ca='rotated CA')), encoding='utf-8')
            sync.sync_now('nexttodo')
            finish()
            assert ':44008/' in opener.open.call_args.args[0].full_url
            calls = opener.open.call_count
            address.write_text(json.dumps(dict(url='https://next.invalid:44008', ca='rotated CA')), encoding='utf-8')
            sync.sync_now('nexttodo')
            finish()
            assert opener.open.call_count == calls and moved in sync.states['nexttodo']['events']

        dida_rows.clear()
        sync.next_sync['dida'] = now[0]
        sync.poll()
        finish()
        assert not sync.states['dida']['events']
        path = calendar.connection_path(sync.directory, 'nexttodo')
        assert b'fixture-next' not in path.read_bytes()
        assert calendar.read_connection(path, 'nexttodo') == sync.states['nexttodo']
        assert sync.rename_account('nexttodo', '') and 'label' not in sync.states['nexttodo']
        for source in tasks.TOKEN_SOURCES:
            sync.disconnect(source)
            assert source not in sync.states and not calendar.connection_path(sync.directory, source).exists()


def run(app, output, checks):
    import resource_calendar_api as api
    import resource_calendar_sync as calendar
    import resource_dingtalk_login as dingtalk
    import resource_tencent_login as tencent
    from resource_agenda import Agenda

    check_device_poll(api)
    now = [int(time())]
    start = now[0] + 8 * 60
    folder = output / 'calendar-sync-fixture'
    folder.mkdir(exist_ok=True)
    for source in calendar.SOURCES:
        calendar.connection_path(folder, source).unlink(missing_ok=True)
    calendar.feishu_app_path(folder).unlink(missing_ok=True)
    check_dingtalk_download(folder / 'tool-test', api, dingtalk)
    cli_folder = tencent.config_folder(folder)
    cli_folder.mkdir(exist_ok=True)
    cli_metadata=cli_folder / 'config.json'
    cli_metadata.unlink(missing_ok=True)

    class Owner(QObject):
        def __init__(self):
            super().__init__()
            self.closed = False
            self.cfg = dict(resource_enabled=True, resource_agenda=True, resource_alert_agenda=True,
                            resource_agenda_events=[
                                dict(id='a'*32, title='本地记录', start=start+2400, end=start+4800, lead=5, ack=False, source='local'),
                                dict(id='b'*32, title='旧导入', start=start+2400, end=start+4800, lead=5, ack=False, source='dingtalk'),
                            ])
            self.runtime = SimpleNamespace(api=SimpleNamespace(CONFIG_DIR=folder),
                                           dock=SimpleNamespace(preview=False), tray=Mock(), game_active=False)
            self.play_reminder_sound = Mock()
            self.calendar_sync = calendar.CalendarSync(self, lambda: now[0])
            self.agenda = Agenda(self, lambda: now[0])
            self.calendar_sync.events_changed.connect(self.agenda.sync)

    owner = Owner()
    sync = owner.calendar_sync
    agenda = owner.agenda
    ding = dict(start=start, title='初次同步', cancelled=False, second=True, partial=False)
    feishu = dict(fail=False, revoked=False)
    scans = []
    sync.changed.connect(lambda: scans.append(sync.scan_info) if sync.scan_info and sync.scan_info not in scans else None)
    close_after_scan = []

    def close_authorization_window():
        if sync.job and sync.job.connecting and sync.job.signed_in:
            sync.cancel_authorization()
            close_after_scan.append(not sync.job.cancelled.is_set())

    sync.changed.connect(close_authorization_window)

    def dt(stamp):
        return dict(dateTime=datetime.fromtimestamp(stamp, timezone.utc).isoformat())

    def mock_cli(job, args, timeout=25, on_scan=None):
        if args[:2] == ('auth','login'):
            assert args[2:] == ('--device','--no-browser') and on_scan
            on_scan('dingtalk','https://login.dingtalk.com/oauth2/device/verify.htm?fixture=1')
            return dict(success=True,corp_id='ding-org',user_id='ding-account')
        if args[:2] == ('auth','logout'):
            assert args[2]=='--profile=ding-org:ding-account'
            return dict(success=True)
        assert args[:4] == ('calendar','event','list','--profile=ding-org:ding-account')
        if '--cursor=next' in args:
            if ding['partial']:
                raise api.CalendarError('模拟分页失败')
            return dict(success=True,result=dict(events=[dict(id='second',summary='第二页',start=dt(start+4800),end=dt(start+5400))]))
        row = dict(id='ding-event',summary=ding['title'],start=dt(ding['start']),end=dt(ding['start']+3600))
        if ding['cancelled']:
            row = dict(id='ding-event',status='cancelled')
        return dict(success=True,result=dict(events=[row]),nextCursor='next' if ding['second'] else '')

    meeting_state = dict(start=start+3600, cancelled=False, partial=False, cancel_login=False)

    def mock_tencent(job, args, timeout=25, on_scan=None):
        if args[:2] == ('auth','login'):
            assert args[2:] == ('--no-browser',) and on_scan
            assert not cli_metadata.exists()
            on_scan('tencent','https://meeting.tencent.com/marketplace/tencentmeeting-cli-auth.html?code=fixture')
            if meeting_state['cancel_login']:
                job.cancelled.set()
                return b''
            cli_metadata.write_text('{"active_open_id":"tencent_fixture"}',encoding='utf-8')
            return b''
        if args == ('auth','logout'):
            cli_metadata.unlink()
            return b''
        assert args[:3] == ('meeting','list','--start')
        assert args[4:8] == ('--page-size','20','--show-all-sub','1')
        assert args[8:] in ((), ('--page-token=next',))
        if args[-1]=='--page-token=next':
            if meeting_state['partial']:
                raise api.CalendarError('腾讯会议分页暂时失败。')
            data=dict(meeting_info_list=[])
        elif meeting_state['cancelled']:
            data=dict(meeting_info_list=[dict(status='MEETING_STATE_CANCELLED')])
        else:
            begins=meeting_state['start']
            data=dict(meeting_info_list=[dict(meeting_id='12345',subject='周期例会',
                sub_meetings=[dict(sub_meeting_id='a',start_time=dt(begins)['dateTime'],end_time=begins+1800),
                              dict(sub_meeting_id='b',status=1)])], next_page_token='next')
        return json.dumps(dict(data=data)).encode()

    def mock_request(url, *, headers=None, body=None, form=False, expected_errors=()):
        if url.endswith('/app/registration'):
            assert form and body['archetype']=='PersonalAgent' and body['action']=='begin'
            return dict(device_code='registration-fixture',verification_uri_complete='https://open.feishu.cn/page/launcher?fixture=1')
        if url.endswith('/device_authorization'):
            assert form and body['client_id']=='fei-fixture'
            assert set(body['scope'].split())==set(api.FEISHU_SCOPES) and headers['Authorization'].startswith('Basic ')
            return dict(device_code='device-fixture',verification_uri_complete='https://accounts.feishu.cn/oauth/v1/device/verify?fixture=1')
        if url.endswith('/oauth/v3/token'):
            if feishu['revoked']:
                raise api.CalendarError('授权已撤销，请重新授权。', 'login')
            assert body['refresh_token'] == 'fei-refresh'
            return dict(access_token='fei-access-new', refresh_token='fei-refresh-new', expires_in=7200)
        if url.endswith('/calendars/primary'):
            assert body == {} and headers == {'Authorization': 'Bearer fei-access'}
            return dict(code=0, data=dict(calendars=[dict(calendar=dict(calendar_id='fei@calendar'))]))
        assert '/fei%40calendar/events/instance_view?' in url
        assert 'start_time' in url and 'end_time' in url
        if feishu['fail']:
            assert headers == {'Authorization': 'Bearer fei-access-new'}
            raise api.CalendarError('模拟断网')
        return dict(code=0, data=dict(items=[
            dict(event_id='fei-event_0', summary='飞书日程', start_time=dict(timestamp=str(start+7200)),
                 end_time=dict(timestamp=str(start+9000)))]))

    def mock_poll(url, body, offer, completed, cancelled):
        if url.endswith('/app/registration'):
            assert body==dict(action='poll',device_code='registration-fixture') and completed=='client_secret'
            return dict(client_id='fei-fixture',client_secret='fei-fixture-secret')
        assert body['device_code']=='device-fixture' and body['grant_type']=='urn:ietf:params:oauth:grant-type:device_code'
        if feishu.get('cancel_user'):
            raise api.CalendarError('模拟第二步取消')
        return dict(access_token='fei-access',refresh_token='fei-refresh',expires_in=7200)

    def finish():
        deadline = monotonic() + 5
        while sync.job is not None and monotonic() < deadline:
            app.processEvents()
            sleep(.01)
        assert sync.job is None

    try:
        with patch.object(dingtalk,'ensure_tool'),patch.object(dingtalk,'invoke',side_effect=mock_cli), \
                patch.object(tencent,'ensure_tool'),patch.object(tencent,'invoke',side_effect=mock_tencent), \
                patch.object(api,'poll_device',side_effect=mock_poll),patch.object(api,'request_json',side_effect=mock_request):
            sync.connect_account('dingtalk')
            finish()
            assert not sync.errors
            assert sync.timer.isActive()
            assert {row['title'] for row in agenda.events} == {'本地记录', '初次同步', '第二页'}
            key = next(row['id'] for row in agenda.events if row['title'] == '初次同步')
            assert not agenda.due()
            assert agenda.synced_reminder(key, lead=15)
            assert agenda.due()[0]['id'] == key
            assert agenda.dismiss(key) and not agenda.due()
            assert agenda.set_reminder(key,enabled=True) and agenda.due()[0]['id']==key
            assert agenda.dismiss(key) and not agenda.due()

            feishu['cancel_user']=True
            sync.connect_account('feishu')
            finish()
            assert 'feishu' not in sync.states and calendar.feishu_app_path(folder).is_file()
            assert 'feishu' in sync.account_sources() and sync.pending_registration('feishu')
            assert b'fei-fixture-secret' not in calendar.feishu_app_path(folder).read_bytes()
            app_scan=next(url for _,phase,url in scans if phase=='feishu-app')
            encoded=parse_qs(urlsplit(app_scan).query)['addons'][0]
            config=json.loads(gzip.decompress(urlsafe_b64decode(encoded+'='*(-len(encoded)%4))))
            assert config=={'preset':False,'scopes':{'user':list(api.FEISHU_SCOPES)}}
            scans.clear()
            feishu['cancel_user']=False
            sync.connect_account('feishu')
            finish()
            assert len(sync.states) == 2 and not sync.errors
            assert close_after_scan==[True,True]
            assert [phase for _,phase,_ in scans]==['feishu-user']
            assert not calendar.feishu_app_path(folder).exists()
            ding.update(start=start+1800, title='改期后', partial=True)
            sync.sync_now('dingtalk')
            finish()
            assert 'dingtalk' in sync.errors
            assert any(row['title'] == '初次同步' for row in agenda.events)
            assert not agenda.due()

            ding['partial'] = False
            now[0] += calendar.SYNC_SECONDS
            sync.poll()
            finish()
            moved = next(row for row in agenda.events if row['id'] == key)
            assert moved['title'] == '改期后' and moved['start'] == ding['start']
            assert moved['lead'] == 15 and not moved['ack'] and not agenda.due()
            now[0] = ding['start'] - 15*60
            agenda.sync()
            assert agenda.due()[0]['id'] == key

            ding.update(cancelled=True, second=False)
            sync.sync_now('dingtalk')
            finish()
            assert not agenda.due() and not any(row['source'] == 'dingtalk' for row in agenda.events)

            state = sync.states['feishu']
            assert sync.store('feishu', dict(state, account=dict(state['account'], expires=now[0])))
            feishu['fail'] = True
            sync.sync_now('feishu')
            finish()
            path = calendar.connection_path(folder, 'feishu')
            assert b'fei-refresh' not in path.read_bytes()
            restored = calendar.read_connection(path, 'feishu')
            assert restored['account']['refresh'] == 'fei-refresh-new'
            assert restored['events'] == state['events'] and 'feishu' in sync.errors
            assert all('secret' not in name for name in owner.cfg)
            assert sync.store('feishu', dict(restored, account=dict(restored['account'], expires=now[0])))
            feishu['revoked'] = True
            sync.sync_now('feishu')
            finish()
            assert 'feishu' in sync.reauthorize

            sync.disconnect('dingtalk')
            finish()
            assert not calendar.connection_path(folder, 'dingtalk').exists()
            assert any(row['title'] == '旧导入' for row in agenda.events)

            sync.connect_account('tencent')
            finish()
            assert any(phase == 'tencent' for _,phase,_ in scans)
            record, = sync.states['tencent']['events']
            assert record['title']=='周期例会' and record['start']==meeting_state['start']
            meeting_state['cancel_login']=True
            assert sync.connect_account('tencent')
            finish()
            assert 'tencent' in sync.reauthorize and not cli_metadata.exists()
            assert sync.states['tencent']['events']==[record]
            meeting_state['cancel_login']=False
            assert sync.connect_account('tencent')
            finish()
            assert 'tencent' not in sync.reauthorize and cli_metadata.is_file()
            assert agenda.synced_reminder(record['id'], lead=25)
            meeting_state.update(start=record['start']+1800,partial=True)
            sync.sync_now('tencent')
            finish()
            assert sync.states['tencent']['events'][0]['start']==record['start']
            meeting_state['partial']=False
            sync.sync_now('tencent')
            finish()
            moved, = sync.states['tencent']['events']
            assert moved['id']==record['id'] and moved['lead']==25 and moved['start']==meeting_state['start']
            meeting_state['cancelled']=True
            sync.sync_now('tencent')
            finish()
            assert not sync.states['tencent']['events']
            restored_tencent=calendar.read_connection(calendar.connection_path(folder,'tencent'),'tencent')
            assert restored_tencent['account']['mode']=='tencent-device' and not restored_tencent['events']
            sync.disconnect('tencent')
            finish()
            assert 'tencent' not in sync.states and not cli_metadata.exists()
            sync.close()
            reopened = calendar.CalendarSync(owner, lambda: now[0])
            try:
                assert set(reopened.states) == {'feishu'}
                assert reopened.states['feishu']['account']['refresh'] == 'fei-refresh-new'
                assert 'feishu' in reopened.reauthorize
                reopened.schedule()
                assert not reopened.timer.isActive()
            finally:
                reopened.close()
            owner.cfg.update(resource_enabled=True, resource_agenda=True)
            check_task_accounts(sync, agenda, finish, now)
    finally:
        sync.close()
        agenda.timer.stop()
        owner.deleteLater()
    checks.extend([
        'DingTalk verified component reuse, download progress, cancellation and rejection of partial downloads. Three official authorization paths are exercised against fixture responses.',
        'Calendar sync works in standalone mode, preserves reminders across reschedules and incomplete pages, removes cancellations, and clears authorization on disconnect.',
        'Dida and NextTodo sync dated tasks read-only, preserve good credentials after a failed replacement, reload encrypted snapshots, and follow NextTodo local address and CA rotation.',
        'Calendar account names and required authorization survive reload. Tencent renewal requests a new scan, and NextTodo sends its exact client name and distinguishes Cloudflare denial from an expired token.',
    ])
