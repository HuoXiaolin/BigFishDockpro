"""On-demand account connections and background calendar snapshots."""
import json
from pathlib import Path
import time

from PyQt5.QtCore import QObject, QTimer, Qt, pyqtSignal

from background_worker import BackgroundWorker
from config_store import _atomic
from resource_agenda import SYNC_SOURCES as SOURCES, normalize_events
from resource_calendar_api import (CalendarError, authorize_feishu, exchange, primary_calendar,
                                   read_events, register_feishu, verification_url)
from resource_options import calendar_data_active
from resource_task_calendars import TOKEN_SOURCES, read_task_events, token_account

SYNC_SECONDS = 600
EVENT_LIMIT = 256
ACCOUNT_NAME_LIMIT = 40
STORAGE_LIMIT = 512 * 1024
STORAGE_ERROR = '日程同步数据保存失败，请检查本机数据目录。'


def connection_path(directory, source):
    return Path(directory) / f'resource-calendar-{source}.dat'


def protect(payload, encrypt):
    """Use current-user DPAPI, including for the downloaded schedule cache."""
    import ctypes as ct
    from ctypes import wintypes

    class Blob(ct.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ct.POINTER(ct.c_ubyte))]

    buffer = (ct.c_ubyte * len(payload)).from_buffer_copy(payload)
    source, result = Blob(len(payload), buffer), Blob()
    crypt = ct.WinDLL('crypt32', use_last_error=True)
    convert = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    convert.argtypes = [ct.POINTER(Blob), ct.c_void_p, ct.c_void_p, ct.c_void_p,
                        ct.c_void_p, wintypes.DWORD, ct.POINTER(Blob)]
    convert.restype = wintypes.BOOL
    if not convert(ct.byref(source), None, None, None, None, 1, ct.byref(result)):
        raise ct.WinError(ct.get_last_error())
    kernel = ct.WinDLL('kernel32')
    kernel.LocalFree.argtypes = [ct.c_void_p]
    kernel.LocalFree.restype = ct.c_void_p
    try:
        return ct.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def read_private(path):
    with path.open('rb') as stream:
        payload = stream.read(STORAGE_LIMIT + 1)
    if len(payload) > STORAGE_LIMIT:
        raise ValueError('Invalid calendar state size')
    return json.loads(protect(payload, False))


def write_private(path, value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
    _atomic(path, protect(raw, True))


def check_fields(account, fields):
    for key, maximum in fields:
        value = account.get(key)
        if not isinstance(value, str) or not 0 < len(value) <= maximum:
            raise ValueError('Invalid calendar credential')
    return account


APP_FIELDS = (('client_id', 512), ('secret', 512))
TOOL_MODES = {'dingtalk': 'dingtalk-device', 'tencent': 'tencent-device'}


def uses_tool(source, account):
    return source in TOOL_MODES and account.get('mode') == TOOL_MODES[source]


def provider_tool(source):
    if source == 'dingtalk':
        import resource_dingtalk_login as provider
    else:
        import resource_tencent_login as provider
    return provider


def feishu_app_path(directory):
    return Path(directory) / 'resource-calendar-feishu-app.dat'


def account_name(value):
    if not isinstance(value, str):
        raise ValueError('账号名称无效。')
    value = value.strip()
    if len(value) > ACCOUNT_NAME_LIMIT:
        raise ValueError(f'账号名称最多 {ACCOUNT_NAME_LIMIT} 个字符。')
    if value and not value.isprintable():
        raise ValueError('请输入单行显示名称。')
    return value


def read_connection(path, source):
    state = read_private(path)
    account = check_fields(state['account'], (('identity', 512),))
    if source in TOKEN_SOURCES:
        check_fields(account, (('token', 8192),))
        if source == 'nexttodo':
            check_fields(account, (('endpoint', 2048),))
        normalized = token_account(source, account['token'], account.get('endpoint', ''))
        if any(account.get(key) != value for key, value in normalized.items() if key != 'identity'):
            raise ValueError('Invalid task calendar credential')
    elif not uses_tool(source, account):
        check_fields(account, APP_FIELDS + (('access', 8192), ('refresh', 8192)))
        if type(account.get('expires')) is not int or not 0 <= account['expires'] < 10**10:
            raise ValueError('Invalid calendar credential expiry')
    if type(state.get('updated')) is not int or not 0 <= state['updated'] < 10**10:
        raise ValueError('Invalid calendar timestamp')
    events = normalize_events(state['events'], strict=True, limit=EVENT_LIMIT)
    if any(row['source'] != source for row in events):
        raise ValueError('Invalid calendar source')
    result = dict(account=account, updated=state['updated'], events=events,
                  truncated=state.get('truncated') is True)
    try:
        label = account_name(state.get('label', ''))
    except ValueError:
        label = ''
    if label:
        result['label'] = label
    if state.get('needs_auth') is True:
        result['needs_auth'] = True
    return result


def reconcile(incoming, existing, now):
    previous = {row['id']: row for row in existing}
    # If a busy account exceeds the cache limit, retain ongoing and closest
    # future events before retaining history.
    ordered = sorted(incoming, key=lambda row: (row['end'] <= now, row['start'], row['id']))
    events = []
    for row in ordered[:EVENT_LIMIT]:
        old = previous.get(row['id'])
        if old:
            row = dict(row, lead=old['lead'], ack=old['ack'] if old['start'] == row['start'] else row['ack'])
        events.append(row)
    return sorted(events, key=lambda row: (row['start'], row['id']))


class CalendarJob(BackgroundWorker):
    scan = pyqtSignal(str, str)
    progress = pyqtSignal(str, int, int)
    authorized = pyqtSignal(object)
    refreshed = pyqtSignal(object)

    def __init__(self, source, account, connecting, now, directory, disconnecting=False):
        super().__init__()
        self.source = source
        self.account = dict(account)
        self.connecting = connecting
        self.disconnecting = disconnecting
        self.signed_in = False
        self.previous_login_removed = False
        self.now = now
        self.directory = directory
        self.result = None
        self.error = None

    def renew(self):
        try:
            self.account = exchange(self.source, self.account)
        except CalendarError as error:
            if error.kind == 'token':
                raise CalendarError('续期凭证已失效，请重新授权。', 'login') from error
            raise
        if not self.cancelled.is_set():
            self.refreshed.emit(self.account)

    def connect_feishu(self):
        path = feishu_app_path(self.directory)
        if self.account.get('mode') != 'feishu-device':
            try:
                self.account = check_fields(read_private(path), APP_FIELDS)
            except FileNotFoundError:
                self.account = register_feishu(self.scan.emit, self.cancelled)
                # The app already exists after the first scan. Keep its
                # credentials if the second scan is interrupted.
                write_private(path, self.account)
        if self.cancelled.is_set():
            return
        self.account = authorize_feishu(self.account, self.scan.emit, self.cancelled)
        self.account['identity'] = primary_calendar('feishu', self.account['access'])

    def download(self):
        if uses_tool(self.source, self.account):
            return provider_tool(self.source).read_calendar(self)
        try:
            return read_events(self.source, self.account, self.now, self.cancelled)
        except CalendarError as error:
            if self.connecting or error.kind != 'token' or self.cancelled.is_set():
                raise
            self.renew()
            return read_events(self.source, self.account, self.now, self.cancelled)

    def run(self):
        try:
            if self.source in TOKEN_SOURCES:
                if not self.cancelled.is_set():
                    self.result = read_task_events(self.source, self.account, self.now)
                return
            if self.disconnecting:
                provider_tool(self.source).logout(self)
                self.result = []
                return
            if self.connecting:
                if self.source in TOOL_MODES:
                    self.account = provider_tool(self.source).login(self)
                else:
                    self.connect_feishu()
                if self.cancelled.is_set():
                    return
                self.authorized.emit(self.account)
            elif not uses_tool(self.source, self.account) and self.account['expires'] <= self.now + 60:
                self.renew()
            if not self.cancelled.is_set():
                self.result = self.download()
        except CalendarError as error:
            self.error = error
        except (OSError, ValueError, KeyError, AttributeError, TypeError, RecursionError):
            self.error = CalendarError('暂时无法读取日程，已保留上次同步结果。')


class CalendarSync(QObject):
    changed = pyqtSignal()
    events_changed = pyqtSignal()

    def __init__(self, owner, clock=time.time):
        super().__init__(owner)
        self.owner = owner
        self.clock = clock
        self.directory = Path(owner.runtime.api.CONFIG_DIR)
        self.states = {}
        self.errors = {}
        self.next_sync = {}
        self.reauthorize = set()
        self.unreadable = set()
        self.job = None
        self.scan_info = None
        self.transfer = None
        self.projection = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)
        for source in SOURCES:
            try:
                self.states[source] = read_connection(connection_path(self.directory, source), source)
            except FileNotFoundError:
                continue
            except (OSError, ValueError, AttributeError, KeyError, TypeError, RecursionError):
                self.errors[source] = '本机授权记录无法读取，请重新授权。'
                self.unreadable.add(source)
                continue
            if self.states[source].get('needs_auth'):
                self.reauthorize.add(source)
            self.next_sync[source] = 0

    def pending_registration(self, source):
        return source == 'feishu' and source not in self.states and feishu_app_path(self.directory).is_file()

    def account_sources(self):
        return tuple(source for source in SOURCES
                     if source in self.states or source in self.unreadable or self.pending_registration(source))

    def events_for(self, local):
        if not self.states:
            return local
        if self.projection is None or self.projection[0] is not local:
            synced = {source for source, state in self.states.items() if state['updated']}
            rows = [row for row in local if row['source'] not in synced]
            for state in self.states.values():
                rows.extend(dict(row, synced=True) for row in state['events'])
            self.projection = local, sorted(rows, key=lambda row: (row['start'], row['id']))
        return self.projection[1]

    def change_events(self):
        self.projection = None
        self.events_changed.emit()

    def store(self, source, state):
        previous = self.states.get(source)
        state = dict(state)
        label = state.pop('label', (previous or {}).get('label'))
        if label:
            state['label'] = label
        try:
            write_private(connection_path(self.directory, source), state)
        except (OSError, ValueError):
            self.errors[source] = STORAGE_ERROR
            return False
        self.states[source] = state
        self.unreadable.discard(source)
        if (previous is None or previous['events'] != state['events'] or
                bool(previous['updated']) != bool(state['updated'])):
            self.change_events()
        return True

    def rename_account(self, source, label):
        label = account_name(label)
        state = self.states.get(source)
        if state is None:
            return False
        if state.get('label', '') == label:
            return True
        saved = self.store(source, dict(state, label=label))
        if saved and self.errors.get(source) == STORAGE_ERROR:
            self.errors.pop(source)
        self.changed.emit()
        return saved

    def require_authorization(self, source):
        self.reauthorize.add(source)
        state = self.states.get(source)
        if state and not state.get('needs_auth'):
            self.store(source, dict(state, needs_auth=True))

    def connect_account(self, source, *, token='', endpoint=''):
        if source not in SOURCES or self.job or self.owner.runtime.dock.preview:
            return False
        if source in TOKEN_SOURCES:
            try:
                account = token_account(source, token, endpoint)
            except ValueError as error:
                self.errors[source] = str(error)
                self.changed.emit()
                return False
        else:
            account = self.states.get(source, {}).get('account', {})
        self.start(source, account, connecting=True)
        return True

    def disconnect(self, source):
        if source not in SOURCES or self.job or self.owner.runtime.dock.preview:
            return
        account = self.states.get(source, {}).get('account', {})
        if uses_tool(source, account):
            self.start(source, account, disconnecting=True)
        else:
            self.forget(source)
            self.schedule()
            self.changed.emit()

    def forget(self, source):
        try:
            if source == 'feishu':
                feishu_app_path(self.directory).unlink(missing_ok=True)
            connection_path(self.directory, source).unlink(missing_ok=True)
        except OSError:
            self.errors[source] = '无法清除本机授权，请稍后重试。'
        else:
            self.errors.pop(source, None)
            self.next_sync.pop(source, None)
            self.reauthorize.discard(source)
            self.unreadable.discard(source)
            if self.states.pop(source, None) is not None:
                self.change_events()

    def active(self):
        cfg = self.owner.cfg
        return not (self.job or self.owner.closed or self.owner.runtime.dock.preview) and calendar_data_active(cfg)

    def schedule(self):
        self.timer.stop()
        if not self.active():
            return
        deadlines = [when for source, when in self.next_sync.items() if source not in self.reauthorize]
        if deadlines:
            self.timer.start(max(1, min(3600000, int((min(deadlines) - self.clock()) * 1000))))

    def poll(self):
        if not self.active():
            return
        now = self.clock()
        for source, when in sorted(self.next_sync.items(), key=lambda item: item[1]):
            if source not in self.reauthorize and when <= now:
                self.sync_now(source)
                return
        self.schedule()

    def sync_now(self, source):
        if not self.job and source in self.states and not self.owner.runtime.dock.preview:
            self.start(source, self.states[source]['account'])

    def start(self, source, account, connecting=False, disconnecting=False):
        self.timer.stop()
        self.errors.pop(source, None)
        self.scan_info = None
        self.transfer = None
        self.job = CalendarJob(source, account, connecting, int(self.clock()), self.directory, disconnecting)
        self.job.finished.connect(self.finished, Qt.QueuedConnection)
        self.job.scan.connect(self.show_scan, Qt.QueuedConnection)
        self.job.progress.connect(self.show_progress, Qt.QueuedConnection)
        self.job.authorized.connect(self.save_authorized, Qt.QueuedConnection)
        self.job.refreshed.connect(self.save_refresh, Qt.QueuedConnection)
        self.job.start()
        self.changed.emit()

    def show_scan(self, phase, url):
        if self.sender() is self.job and not self.job.cancelled.is_set():
            self.scan_info = (self.job.source, phase, verification_url(self.job.source, url))
            self.transfer = None
            self.changed.emit()

    def show_progress(self, phase, received, size):
        if self.sender() is self.job and not self.job.cancelled.is_set():
            self.transfer = (self.job.source, phase, received, size) if phase != 'ready' else None
            self.changed.emit()

    def cancel_authorization(self):
        if self.job and self.job.connecting and not self.job.signed_in:
            self.scan_info = None
            self.transfer = None
            self.job.requestInterruption()
            self.changed.emit()

    def save_authorized(self, account):
        job = self.sender()
        if job is not self.job or job.cancelled.is_set():
            return
        job.signed_in = True
        self.scan_info = None
        self.transfer = None
        old = self.states.get(job.source)
        if old and old['account']['identity'] == account['identity']:
            state = dict(old, account=account)
            state.pop('needs_auth', None)
        else:
            state = dict(account=account, events=[], updated=0, truncated=False)
        if self.store(job.source, state):
            self.reauthorize.discard(job.source)
        self.changed.emit()

    def save_refresh(self, account):
        job = self.sender()
        if job is not self.job or job.cancelled.is_set():
            return
        # A rotated refresh token must survive even when the calendar request fails.
        state = dict(self.states[job.source], account=account)
        if not self.store(job.source, state):
            self.states[job.source] = state

    def finished(self):
        job = self.sender()
        if job is not self.job:
            return
        self.job = None
        self.scan_info = None
        self.transfer = None
        job.deleteLater()
        source = job.source
        if job.previous_login_removed and not job.signed_in:
            self.require_authorization(source)
        if not job.cancelled.is_set():
            if job.error is not None:
                if source not in self.errors:
                    self.errors[source] = str(job.error)
                replacing_token = job.connecting and source in TOKEN_SOURCES
                if not (job.disconnecting or replacing_token) and job.error.kind in ('login', 'token'):
                    self.require_authorization(source)
            elif job.disconnecting:
                self.forget(source)
            elif job.result is not None:
                old = self.states.get(source)
                previous = self.owner.cfg['resource_agenda_events']
                if old and old['updated'] and old['account']['identity'] == job.account['identity']:
                    previous = old['events']
                events = reconcile(job.result, previous, job.now)
                state = dict(account=job.account, events=events, updated=int(self.clock()),
                             truncated=len(job.result) > EVENT_LIMIT)
                if self.store(source, state):
                    self.errors.pop(source, None)
                    self.reauthorize.discard(source)
                    if source == 'feishu' and job.account.get('mode') == 'feishu-device':
                        try:
                            feishu_app_path(self.directory).unlink(missing_ok=True)
                        except OSError:
                            pass
            if source in self.states:
                delay = 1800 if job.error and job.error.kind == 'rate' else SYNC_SECONDS
                self.next_sync[source] = self.clock() + delay
        self.schedule()
        self.changed.emit()

    def set_reminder(self, key, *, lead=None, ack=False):
        for source, state in self.states.items():
            for row in state['events']:
                if row['id'] == key:
                    updated = dict(row)
                    if lead is not None:
                        updated['lead'] = lead
                    updated['ack'] = ack
                    events = [updated if item is row else item for item in state['events']]
                    return events == state['events'] or self.store(source, dict(state, events=events))
        return False

    def close(self):
        self.timer.stop()
        if self.job:
            self.job.requestInterruption()
            self.job.deleteLater()
            self.job = None
