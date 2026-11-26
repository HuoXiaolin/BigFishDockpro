"""Demand-driven mail synchronization and compact capsule notifications."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
from threading import Event
import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

from background_worker import BackgroundWorker
from mail_accounts import MAIL_LIMIT, account_binding, account_label, clean_accounts
from mail_messages import MailError


CODE_SECONDS = 90
MAX_CODE_AGE = 180


def desktop_unlocked():
    wts = C.WinDLL('wtsapi32', use_last_error=True)
    wts.WTSQuerySessionInformationW.argtypes = (W.HANDLE, W.DWORD, C.c_int,
                                                C.POINTER(C.c_void_p), C.POINTER(W.DWORD))
    wts.WTSQuerySessionInformationW.restype = W.BOOL
    wts.WTSFreeMemory.argtypes = (C.c_void_p,)
    buffer, length = C.c_void_p(), W.DWORD()
    if not wts.WTSQuerySessionInformationW(None, 0xffffffff, 25, C.byref(buffer), C.byref(length)):
        return False
    try:
        # WTSINFOEXW has an eight-byte aligned level-one data union.
        return (length.value >= 20 and W.DWORD.from_address(buffer.value).value == 1
                and W.DWORD.from_address(buffer.value + 16).value == 1)
    finally:
        wts.WTSFreeMemory(buffer)


def connection_error(error):
    import ssl
    from urllib.error import HTTPError, URLError
    if isinstance(error, MailError):
        return str(error), error.authorization
    if isinstance(error, ssl.SSLCertVerificationError) or (
            isinstance(error, URLError) and isinstance(error.reason, ssl.SSLCertVerificationError)):
        return '服务器证书校验失败。', False
    if isinstance(error, HTTPError) and error.code in (401, 403):
        return 'Gmail 拒绝读取，请检查 Gmail API 与授权。', True
    return '邮箱暂时无法连接，将自动重试。', False


class MailPoll(BackgroundWorker):
    received = pyqtSignal(str, object, object)
    failed = pyqtSignal(str, str, bool)

    def __init__(self, accounts, detect_codes, interval):
        super().__init__()
        self.accounts = accounts
        self.detect_codes = detect_codes
        self.interval = interval
        self.wake = Event()

    def refresh(self):
        self.wake.set()

    def requestInterruption(self):
        super().requestInterruption()
        self.wake.set()

    def run(self):
        from mail_credentials import load_bound
        from mail_transport import ImapSession, open_session
        sessions, retries, failures = {}, {}, {}
        try:
            while not self.cancelled.is_set():
                immediate = self.wake.is_set()
                self.wake.clear()
                for account in self.accounts:
                    if self.cancelled.is_set():
                        return
                    identity = account['id']
                    if not immediate and time.monotonic() < retries.get(identity, 0):
                        continue
                    client = sessions.get(identity)
                    try:
                        if client is None:
                            secret = load_bound(account)
                            client = sessions[identity] = open_session(account, secret, self.cancelled)
                        rows, new = client.snapshot(self.detect_codes)
                        retries.pop(identity, None)
                        failures.pop(identity, None)
                        if not self.cancelled.is_set():
                            self.received.emit(identity, rows, new)
                    except Exception as error:
                        if isinstance(client, ImapSession):
                            client.close()  # Preserve the UID cursor across a reconnect.
                        message, authorization = connection_error(error)
                        failures[identity] = failures.get(identity, 0) + 1
                        delay = min(900, max(30, self.interval) * 2 ** min(4, failures[identity] - 1))
                        retries[identity] = float('inf') if authorization else time.monotonic() + delay
                        if not self.cancelled.is_set():
                            self.failed.emit(identity, message, authorization)
                self.wake.wait(self.interval)
        finally:
            for client in sessions.values():
                client.close()


@dataclass(frozen=True)
class CodeNotice:
    account: str
    value: str
    expires: float


class MailInbox(QObject):
    changed = pyqtSignal()

    def __init__(self, service):
        super().__init__(service)
        self.service = service
        self.job = None
        self.request = None
        self.bindings = {}
        self.rows = {}
        self.states = {}
        self.unseen = {}
        self.codes = []
        self.selection = ''
        self.expiry = QTimer(self)
        self.expiry.setSingleShot(True)
        self.expiry.timeout.connect(self.expire_codes)

    @property
    def cfg(self):
        return self.service.cfg

    def accounts(self):
        return self.cfg['resource_mail_accounts']

    def account(self, identity):
        return next((row for row in self.accounts() if row['id'] == identity), None)

    def sync(self, force=False):
        runtime = self.service.runtime
        enabled = [row for row in self.accounts() if row['enabled']]
        bindings = {row['id']: account_binding(row) for row in enabled}
        removed = {identity for identity, old in self.bindings.items() if bindings.get(identity) != old}
        self.bindings = bindings
        for cache in (self.rows, self.states, self.unseen):
            for key in cache.keys() & removed:
                cache.pop(key)
        self.codes = [code for code in self.codes if code.account not in removed]
        allowed = (self.cfg['resource_mail'] and not self.service.closed and not runtime.session_ending
                   and not runtime.game_active)
        if not allowed or not self.cfg['resource_alert_mail_code']:
            self.codes.clear()
            self.expiry.stop()
        request = (tuple(bindings.items()),
                   self.cfg['resource_alert_mail_code']) if allowed and not runtime.dock.preview else None
        if self.request != request or force:
            self.request = request
            self.stop_job()
            if self.job is None:
                self.start_polling()
        elif self.job and self.job.interval != self.cfg['resource_mail_interval']:
            self.job.interval = self.cfg['resource_mail_interval']
            self.job.refresh()
        self.changed.emit()

    def start_polling(self):
        if not self.request or not self.request[0]:
            return
        enabled = [row for row in self.accounts() if row['enabled']]
        for row in enabled:
            self.states[row['id']] = ('正在连接', '', time.time())
        job = self.job = MailPoll(enabled, self.request[1], self.cfg['resource_mail_interval'])
        job.received.connect(self.receive)
        job.failed.connect(self.error)
        job.finished.connect(self.poll_finished)
        job.start()

    def stop_job(self):
        if self.job is not None:
            self.job.requestInterruption()

    @pyqtSlot()
    def poll_finished(self):
        job = self.sender()
        if self.job is job:
            self.job = None
            if job.cancelled.is_set():
                self.start_polling()
            self.changed.emit()
        job.deleteLater()

    def close(self):
        self.stop_job()
        self.expiry.stop()
        self.codes.clear()
        self.unseen.clear()
        self.request = None

    def refresh(self):
        if self.job:
            self.job.refresh()

    def status(self, row):
        if not row['enabled']:
            return '已暂停', '', 0
        if row['id'] in self.states:
            return self.states[row['id']]
        return '等待同步' if self.cfg['resource_mail'] else '邮件通知已关闭', '', 0

    def contents(self, selected=''):
        enabled = {row['id'] for row in self.accounts() if row['enabled']}
        stream = ((identity, item) for identity, rows in self.rows.items()
                  if identity in enabled and (not selected or selected == identity) for item in rows)
        return sorted(stream, key=lambda pair: pair[1].stamp, reverse=True)[:MAIL_LIMIT]

    def announce(self):
        self.changed.emit()
        window = self.service.window
        if window and self.service.compact:
            window.refresh_reminders()

    @pyqtSlot(str, str, bool)
    def error(self, identity, message, authorization):
        if self.sender() is self.job and not self.job.cancelled.is_set() and self.account(identity):
            self.states[identity] = ('需要授权' if authorization else '暂时离线', message, time.time())
            self.changed.emit()

    @pyqtSlot(str, object, object)
    def receive(self, identity, rows, new):
        if self.sender() is not self.job or self.job.cancelled.is_set():
            return
        self.accept_snapshot(identity, rows, new)

    def accept_snapshot(self, identity, rows, new):
        account = self.account(identity)
        if not account or not account['enabled'] or not self.cfg['resource_mail']:
            return
        rows = tuple(rows)[:MAIL_LIMIT]
        changed = self.rows.get(identity) != rows or self.status(account)[0] != '已连接'
        self.rows[identity] = rows
        self.states[identity] = ('已连接', '', time.time())
        if new:
            self.unseen[identity] = True
            if desktop_unlocked():
                self.notify(account, new)
        if changed or new:
            self.announce()

    def notify(self, account, new):
        runtime = self.service.runtime
        recent = []
        has_code=False
        now = time.time()
        for item, code in new:
            if code and self.cfg['resource_alert_mail_code'] and now - MAX_CODE_AGE <= item.stamp <= now + 30:
                has_code=True
                self.codes.append(CodeNotice(account['id'], code, time.monotonic() + CODE_SECONDS))
            elif not code:
                recent.append(item)
        self.codes = self.codes[-5:]
        self.expire_codes(announce=False)
        if has_code:
            code=self.current_code()
            if code:self.service.peek_reminder(('mail_code',code.value))
        elif recent and self.cfg['resource_mail_notifications']:
            self.service.peek_reminder(('mail_new',f'{len(recent)} 封新邮件'))
        if recent and self.cfg['resource_mail_notifications'] and not runtime.dock.preview:
            item = max(recent, key=lambda row: row.stamp)
            detail = item.sender + ' · ' + item.title if len(recent) == 1 else f'{len(recent)} 封新邮件 · {item.title}'
            runtime.tray.showMessage('新邮件 · ' + account_label(account), detail, runtime.tray.icon(), 5000)

    def mark_seen(self, selected=''):
        if selected:
            changed = self.unseen.pop(selected, False)
        else:
            changed = bool(self.unseen)
            self.unseen.clear()
        if changed:
            self.announce()

    def expire_codes(self, announce=True):
        now = time.monotonic()
        self.codes = [code for code in self.codes if code.expires > now]
        self.expiry.stop()
        if self.codes:
            self.expiry.start(max(1, round(1000 * (min(code.expires for code in self.codes) - now))))
        if announce:
            self.announce()

    def current_code(self):
        if self.cfg['resource_mail'] and self.cfg['resource_alert_mail_code']:
            return next((code for code in reversed(self.codes) if code.expires > time.monotonic()), None)
        return None

    def session_locked(self):
        if self.codes:
            self.codes.clear()
            self.expiry.stop()
            self.announce()

    def copy_code(self):
        notice = self.current_code()
        if not notice or not desktop_unlocked():
            return False
        QApplication.clipboard().setText(notice.value)
        self.codes.remove(notice)
        self.expire_codes()
        return True

    def save_account(self, row, secret=None):
        from mail_credentials import read, remove, save_bound, write
        accounts = [row if old['id'] == row['id'] else old for old in self.accounts()]
        if not self.account(row['id']):
            accounts.append(row)
        accounts = clean_accounts(accounts, strict=True)
        same_binding = self.bindings.get(row['id']) == account_binding(row)
        previous = read(row['id']) if secret else None
        if secret:
            save_bound(row, secret)
        try:
            if not self.service.set_options(resource_mail_accounts=accounts):
                raise OSError('保存邮箱账号失败。')
        except OSError:
            if previous is not None:
                if previous:
                    write(row['id'], previous)
                else:
                    remove(row['id'])
            raise
        if secret:
            self.unseen.pop(row['id'], None)
            self.codes = [code for code in self.codes if code.account != row['id']]
            self.expire_codes(announce=False)
            if same_binding:
                self.sync(force=True)
        self.announce()

    def remove_account(self, identity):
        from mail_credentials import remove
        if not self.service.set_options(resource_mail_accounts=[row for row in self.accounts() if row['id'] != identity]):
            raise OSError('移除账号失败，请重试。')
        self.announce()
        remove(identity)
