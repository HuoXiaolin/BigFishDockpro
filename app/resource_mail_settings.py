"""Mailbox account management in the existing capsule settings."""
import json
from html import escape
from pathlib import Path
from uuid import uuid4

from PyQt5.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout)

from background_worker import BackgroundWorker
from mail_accounts import ACCOUNT_LIMIT, PROVIDERS, account_binding, account_label, clean_account, clean_accounts
from resource_mail import connection_error
from ui_style import ModernComboBox, ModernSpinBox, SettingsHeader, button, compact_dialog, exec_dialog


class MailLogin(BackgroundWorker):
    authorization_url = pyqtSignal(str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str, bool)

    def __init__(self, account, secret, authorize_google=False):
        super().__init__()
        self.account = account
        self.secret = secret
        self.authorize_google = authorize_google

    def run(self):
        from mail_transport import open_session
        client = None
        try:
            if self.authorize_google:
                from gmail_mail import authorize
                secret = authorize(self.secret, self.account['address'], self.cancelled, self.authorization_url.emit)
            else:
                secret = self.secret
            if self.cancelled.is_set():
                return
            client = open_session(self.account, secret, self.cancelled)
            client.test()
            if not self.cancelled.is_set():
                self.succeeded.emit(secret)
        except Exception as error:
            if not self.cancelled.is_set():
                self.failed.emit(*connection_error(error))
        finally:
            if client:
                client.close()
            self.secret = {}


class MailAccountEditor(QDialog):
    def __init__(self, inbox, parent, account=None, reauthorize=False):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint)
        self.inbox, self.account, self.reauthorize = inbox, account, reauthorize
        self.job = None
        self.google_client = None
        self.pending_account = None
        self.setProperty('simpleForms', True)
        self.setWindowTitle('邮箱账号')
        self.resize(480, 360)
        body = QVBoxLayout(self)
        body.addWidget(SettingsHeader(self, '重新授权' if reauthorize else '编辑邮箱账号' if account else '添加邮箱账号'))
        self.form = form = QFormLayout()
        body.addLayout(form)
        self.provider = ModernComboBox()
        for key, title in PROVIDERS.items():
            self.provider.addItem(title, key)
        form.addRow('邮箱服务', self.provider)
        self.address = QLineEdit(account['address'] if account else '')
        self.address.setMaxLength(254)
        self.address.setPlaceholderText('完整邮箱地址')
        form.addRow('邮箱地址', self.address)
        self.name = QLineEdit(account['name'] if account else '')
        self.name.setPlaceholderText('可选')
        self.name.setMaxLength(40)
        form.addRow('显示名称', self.name)
        self.method = ModernComboBox()
        self.method.addItem('应用专用密码', 'imap')
        self.method.addItem('通过 Google 授权', 'google')
        form.addRow('授权方式', self.method)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setMaxLength(256)
        form.addRow('客户端授权码', self.password)
        self.import_google = button('导入 Google 桌面客户端 JSON…', self.import_client)
        form.addRow('Google 客户端', self.import_google)
        self.server = QLineEdit(account.get('server', '') if account else '')
        self.server.setPlaceholderText('imap.example.com')
        form.addRow('IMAP 服务器', self.server)
        self.port = ModernSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(account.get('port', 993) if account else 993)
        form.addRow('TLS 端口', self.port)
        self.webmail = QLineEdit(account.get('webmail', '') if account else '')
        self.webmail.setPlaceholderText('https://mail.example.com/')
        form.addRow('邮箱网页', self.webmail)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setObjectName('Subtle')
        body.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button('取消', self.reject))
        self.save = button('验证并保存', self.commit, 'primary')
        actions.addWidget(self.save)
        body.addLayout(actions)
        self.provider.setCurrentIndex(self.provider.findData(account['provider'] if account else 'qq'))
        self.method.setCurrentIndex(self.method.findData(account['method'] if account else 'imap'))
        self.provider.currentIndexChanged.connect(self.sync_fields)
        self.method.currentIndexChanged.connect(self.sync_fields)
        self.sync_fields()
        compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self, self.inbox.cfg)

    def sync_fields(self):
        provider = self.provider.currentData()
        google = provider == 'gmail' and self.method.currentData() == 'google'
        self.form.labelForField(self.password).setText('应用专用密码' if provider == 'gmail' else '客户端授权码')
        self.password.setPlaceholderText('留空沿用已保存授权' if self.account and not self.reauthorize else '')
        custom = provider == 'imap'
        for widget, visible in ((self.method, provider == 'gmail'), (self.password, not google), (self.import_google, google),
                                (self.server, custom), (self.port, custom), (self.webmail, custom)):
            widget.setVisible(visible)
            self.form.labelForField(widget).setVisible(visible)
        self.adjustSize()
        self.status.setText({
            'qq': '在 QQ 邮箱网页版启用 IMAP，再生成客户端授权码。',
            'netease': '在网易邮箱设置的 POP3/SMTP/IMAP 页新增授权密码。',
            'gmail': '在 Google 账号开启两步验证后生成应用专用密码。' if not google else '导入 Google Cloud 已启用 Gmail API 的桌面客户端文件后，在浏览器完成授权。',
            'imap': '使用加密 IMAP 连接和邮箱服务提供的客户端授权码。',
        }[provider])

    def import_client(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 Google 桌面客户端', '', 'Google OAuth 客户端 (*.json)')
        if not path:
            return
        try:
            from gmail_mail import desktop_client
            file = Path(path)
            if file.stat().st_size > 64 * 1024:
                raise ValueError('Google 客户端文件超过 64 KB。')
            self.google_client = desktop_client(json.loads(file.read_text(encoding='utf-8-sig')))
        except (OSError, UnicodeError, ValueError) as error:
            # A JSON parsing error can quote text from the credentials file.
            self.status.setText(str(error) if type(error) is ValueError else '无法读取 Google 桌面客户端文件。')
            return
        self.import_google.setText('已导入 · 更换客户端…')
        self.status.setText('点击「验证并保存」后将打开 Google 授权页面。')

    def commit(self):
        if self.job:
            return
        account = self.account
        provider = self.provider.currentData()
        method = self.method.currentData() if provider == 'gmail' else 'imap'
        try:
            row = clean_account(dict(id=account['id'] if account else uuid4().hex, provider=provider, method=method,
                                     address=self.address.text(), name=self.name.text(),
                                     enabled=account['enabled'] if account else True, color=account['color'] if account else 0,
                                     server=self.server.text(), port=self.port.value(), webmail=self.webmail.text()))
            clean_accounts([old for old in self.inbox.accounts() if old['id'] != row['id']] + [row], strict=True)
            same = account and account_binding(row) == account_binding(account)
            credential_changed = bool(self.google_client if method == 'google' else self.password.text().strip())
            if same and not self.reauthorize and not credential_changed:
                self.inbox.save_account(row)
                self.accept()
                return
            if method == 'google':
                secret = self.google_client
                if secret is None and same:
                    from mail_credentials import load_bound
                    stored = load_bound(account)
                    if stored.get('client_id') and stored.get('client_secret'):
                        secret = {key: stored[key] for key in ('client_id', 'client_secret')}
                if not secret:
                    raise ValueError('请先导入 Google 桌面客户端 JSON。')
            else:
                entered = ''.join(self.password.text().split()) if provider in ('qq', 'gmail', 'netease') else self.password.text()
                if not entered:
                    raise ValueError('请输入邮箱客户端授权码或应用专用密码。')
                secret = {'password': entered}
        except (ValueError, OSError) as error:
            self.status.setText(str(error))
            return
        self.pending_account = row
        job = self.job = MailLogin(row, secret, authorize_google=method == 'google')
        job.authorization_url.connect(self.open_authorization)
        job.succeeded.connect(self.verified)
        job.failed.connect(self.failed)
        job.finished.connect(self.finished)
        self.set_busy(True)
        self.status.setText('等待浏览器授权…' if method == 'google' else '正在验证与收件箱的连接…')
        job.start()

    def set_busy(self, busy):
        for control in (self.provider, self.method, self.address, self.name, self.password, self.import_google,
                        self.server, self.port, self.webmail, self.save):
            control.setEnabled(not busy)

    @pyqtSlot(str)
    def open_authorization(self, url):
        if self.sender() is self.job and not QDesktopServices.openUrl(QUrl(url)):
            self.job.requestInterruption()
            self.status.setText('无法打开默认浏览器，请检查浏览器设置后重试。')

    @pyqtSlot(object)
    def verified(self, secret):
        if self.sender() is self.job:
            try:
                self.inbox.save_account(self.pending_account, secret)
            except (OSError, ValueError) as error:
                self.status.setText(str(error))
                return
            self.accept()

    @pyqtSlot(str, bool)
    def failed(self, text, _authorization):
        if self.sender() is self.job:
            self.status.setText(text)

    @pyqtSlot()
    def finished(self):
        job = self.sender()
        if job is self.job:
            self.job = None
            self.set_busy(False)
        job.deleteLater()

    def done(self, result):
        if self.job:
            self.job.requestInterruption()
            self.job.deleteLater()
            self.job = None
        self.password.clear()
        self.google_client = None
        super().done(result)


class MailAccountsDialog(QDialog):
    def __init__(self, inbox, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint)
        self.inbox = inbox
        self.job = None
        self.setWindowTitle('邮箱账号管理')
        self.resize(650, 410)
        body = QVBoxLayout(self)
        body.addWidget(SettingsHeader(self, '邮箱账号管理'))
        self.list = QListWidget()
        self.list.setAccessibleName('已添加邮箱账号')
        body.addWidget(self.list, 1)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setObjectName('Subtle')
        body.addWidget(self.status)
        actions = QHBoxLayout()
        self.add = button('添加账号…', self.add_account)
        actions.addWidget(self.add)
        self.edit = button('编辑…', lambda: self.edit_account(False))
        self.test = button('测试连接', self.test_account)
        self.renew = button('重新授权…', lambda: self.edit_account(True))
        self.toggle = button('暂停', self.toggle_account)
        self.remove = button('移除', self.remove_account)
        self.account_actions = (self.edit, self.test, self.renew, self.toggle, self.remove)
        for action in self.account_actions:
            actions.addWidget(action)
        body.addLayout(actions)
        self.list.currentRowChanged.connect(self.sync_actions)
        self.list.itemDoubleClicked.connect(lambda _: self.edit_account(False))
        self.inbox.changed.connect(self.refresh)
        self.refresh()
        compact_dialog(self)
        from settings_layout import fit_auxiliary_dialog
        fit_auxiliary_dialog(self, self.inbox.cfg)

    def selected(self):
        item = self.list.currentItem()
        return self.inbox.account(item.data(Qt.UserRole)) if item else None

    def refresh(self):
        selected = self.selected()
        wanted = selected['id'] if selected else ''
        self.list.blockSignals(True)
        self.list.clear()
        for row in self.inbox.accounts():
            status, detail, _ = self.inbox.status(row)
            title = f"{account_label(row)} · {PROVIDERS[row['provider']]} · {status}"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, row['id'])
            item.setToolTip('<qt>' + escape(row['address']) + ('<br>' + escape(detail) if detail else '') + '</qt>')
            self.list.addItem(item)
            if row['id'] == wanted:
                self.list.setCurrentItem(item)
        if not self.list.currentItem() and self.list.count():
            self.list.setCurrentRow(0)
        self.list.blockSignals(False)
        self.sync_actions()

    def sync_actions(self, *_):
        row = self.selected()
        for action in self.account_actions:
            action.setEnabled(row is not None and self.job is None)
        self.toggle.setText('启用' if row and not row['enabled'] else '暂停')
        self.add.setEnabled(len(self.inbox.accounts()) < ACCOUNT_LIMIT and self.job is None)

    def add_account(self):
        exec_dialog(MailAccountEditor(self.inbox, self))

    def edit_account(self, reauthorize):
        row = self.selected()
        if row and not self.job:
            exec_dialog(MailAccountEditor(self.inbox, self, row, reauthorize))

    def toggle_account(self):
        row = self.selected()
        if row:
            try:
                self.inbox.save_account(dict(row, enabled=not row['enabled']))
            except (OSError, ValueError) as error:
                self.status.setText(str(error))

    def remove_account(self):
        row = self.selected()
        if not row:
            return
        confirm = QMessageBox(QMessageBox.Question, '移除邮箱账号', f"移除「{account_label(row)}」的本机接入？",
                              QMessageBox.Yes | QMessageBox.No, self)
        confirm.setTextFormat(Qt.PlainText)
        confirm.setDefaultButton(QMessageBox.No)
        if confirm.exec_() != QMessageBox.Yes:
            return
        try:
            self.inbox.remove_account(row['id'])
            self.status.setText('已移除该账号。')
        except OSError as error:
            self.status.setText(str(error))

    def test_account(self):
        row = self.selected()
        if not row or self.job:
            return
        from mail_credentials import load_bound
        try:
            secret = load_bound(row)
        except OSError as error:
            self.status.setText(str(error))
            return
        if not secret:
            self.status.setText('请先重新授权。')
            return
        job = self.job = MailLogin(row, secret)
        job.succeeded.connect(self.connected)
        job.failed.connect(self.failed)
        job.finished.connect(self.finished)
        self.status.setText('正在测试连接…')
        self.sync_actions()
        job.start()

    @pyqtSlot(object)
    def connected(self, _):
        if self.sender() is self.job:
            self.status.setText('已连接，可以读取收件箱。')

    @pyqtSlot(str, bool)
    def failed(self, message, _authorization):
        if self.sender() is self.job:
            self.status.setText(message)

    @pyqtSlot()
    def finished(self):
        job = self.sender()
        if job is self.job:
            self.job = None
            self.sync_actions()
        job.deleteLater()

    def done(self, result):
        if self.job:
            self.job.requestInterruption()
            self.job.deleteLater()
            self.job = None
        super().done(result)


def edit_mail_accounts(service, parent=None):
    return exec_dialog(MailAccountsDialog(service.get_mail(), parent))
