"""Connect calendar providers from the resource settings."""
from io import BytesIO
from math import ceil

from PyQt5.QtCore import QDateTime, Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QPixmap, QTextDocument, QTextOption
from PyQt5.QtWidgets import (QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QMessageBox,
                             QPlainTextEdit, QProgressBar, QSizePolicy, QVBoxLayout, QWidget)

from resource_agenda import SOURCES
from resource_calendar_sync import ACCOUNT_NAME_LIMIT, EVENT_LIMIT
from resource_dingtalk_login import tool_candidates
from resource_tencent_login import executable as tencent_executable
from resource_task_calendars import TOKEN_SOURCES
from ui_style import ModernComboBox, SettingsHeader, button, compact_dialog, exec_dialog


GUIDE = {
    'dingtalk': (
        'https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli/blob/main/README_zh.md#开始使用',
        '通过官方组件直接用钉钉扫码授权，免去手动创建应用和填写密钥。缺少组件时按需下载约 24 MB。组织需要允许 CLI 访问。',
    ),
    'feishu': (
        'https://github.com/larksuite/oapi-sdk-go/tree/v3_main/scene/registration',
        '首次用飞书扫码，由飞书创建日程授权应用。第二次扫码确认读取日历和日程。此后 Dock 自动续期。',
    ),
    'tencent': (
        'https://cloud.tencent.com/document/product/1095/133827',
        '通过官方组件扫码登录，免去手动创建应用和填写密钥。缺少组件时按需下载约 14 MB。重新授权会先退出 Dock 当前的腾讯会议登录。',
    ),
    'dida': (
        'https://help.dida365.com/articles/7464976698707017728',
        '在滴答清单网页版打开「设置 → 账户与安全 → API 口令」，创建口令并粘贴到下方。同步有日期的未完成任务。',
    ),
    'nexttodo': (
        'https://juniexd.github.io/NextTodo/guide/agent',
        '在 NextTodo「设置 → 令牌」生成只读令牌。连接本机版时填 local，并保持 NextTodo 运行。连接自建版时填写服务器地址。',
    ),
}
SCAN_PROMPTS = {
    'dingtalk': '请用钉钉扫码，在手机上选择组织并确认授权。',
    'feishu-app': '第 1 步 · 请用飞书扫码创建日程授权应用。',
    'feishu-user': '请用飞书扫码确认日历读取权限。',
    'tencent': '请扫码打开腾讯会议授权页，在官方页面完成授权。',
}


def connection_status(sync, source):
    state = sync.states.get(source)
    job = sync.job
    if job and job.source == source:
        if job.disconnecting:
            label = '正在移除'
        elif job.connecting and not job.signed_in:
            label = '正在授权'
        else:
            label = '正在同步'
    elif source in sync.reauthorize or source in sync.unreadable:
        label = '需要重新授权'
    elif sync.pending_registration(source):
        label = '待完成扫码授权'
    elif state is None:
        label = '尚未连接'
    elif source in sync.errors:
        label = '操作异常'
    else:
        label = '已连接' if state['updated'] else '已授权，等待首次同步'
    if state and state['updated']:
        stamp = QDateTime.fromSecsSinceEpoch(state['updated']).toString('MM-dd HH:mm')
        label += f"  ·  上次同步 {stamp}  ·  {len(state['events'])} 项"
        if state['truncated']:
            label += f'（已保留最近 {EVENT_LIMIT} 项）'
    return label


def remove_account(parent, sync, source):
    answer = QMessageBox.question(parent, '移除日程账号',
                                 f'移除{SOURCES[source]}在本机的授权和已同步日程？',
                                 QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
    if answer == QMessageBox.Yes:
        sync.disconnect(source)


def edit_account(parent, sync, source):
    state = sync.states.get(source)
    if state is None:
        return
    dialog = QDialog(parent)
    dialog.setWindowTitle('编辑日程账号')
    dialog.resize(425, 167)
    layout = QVBoxLayout(dialog)
    layout.addWidget(SettingsHeader(dialog, dialog.windowTitle()))
    form = QFormLayout()
    form.addRow('日程来源', QLabel(SOURCES[source]))
    label = QLineEdit(state.get('label', ''))
    label.setAccessibleName('账号显示名称')
    label.setMaxLength(ACCOUNT_NAME_LIMIT)
    label.setPlaceholderText(SOURCES[source])
    form.addRow('显示名称', label)
    layout.addLayout(form)
    error = QLabel()
    error.setWordWrap(True)
    error.hide()
    layout.addWidget(error)

    def save():
        try:
            if sync.rename_account(source, label.text()):
                dialog.accept()
                return
            message = sync.errors.get(source, '账号已移除。')
        except ValueError as exc:
            message = str(exc)
        error.setText(message)
        error.show()

    actions = QHBoxLayout()
    actions.addStretch()
    actions.addWidget(button('取消', dialog.reject))
    actions.addWidget(button('保存', save, 'primary'))
    layout.addLayout(actions)
    label.returnPressed.connect(save)
    compact_dialog(dialog)
    label.setFocus()
    label.selectAll()
    exec_dialog(dialog)


class CalendarAccountRow(QFrame):
    def __init__(self, service, sync, source):
        super().__init__()
        self.setObjectName('CalendarAccountRow')
        self.setStyleSheet('QFrame#CalendarAccountRow {background: palette(base); border: 1px solid palette(midlight); border-radius: 7px;}')
        self.setAccessibleName(f'{SOURCES[source]}日程账号')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 7)
        details = QVBoxLayout()
        details.setSpacing(3)
        self.title = QLabel()
        self.title.setTextFormat(Qt.PlainText)
        self.title.setProperty('role', 'group-title')
        self.title.setWordWrap(True)
        details.addWidget(self.title)
        self.status = QLabel()
        self.status.setObjectName('Subtle')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        details.addWidget(self.status)
        layout.addLayout(details, 1)
        self.edit = button('编辑', lambda: edit_account(self.window(), sync, source))
        self.edit.setToolTip('编辑本机显示名称')
        self.authorize = button('重新授权', lambda: show_connections(self.window(), service, source))
        self.remove = button('移除', lambda: remove_account(self.window(), sync, source))
        for control in (self.edit, self.authorize, self.remove):
            control.setAccessibleName(f'{SOURCES[source]} · {control.text()}')
            layout.addWidget(control, 0, Qt.AlignVCenter)

    def refresh(self, sync, source):
        label = sync.states.get(source, {}).get('label')
        self.title.setText(f'{SOURCES[source]} · {label}' if label else SOURCES[source])
        summary = connection_status(sync, source)
        error = sync.errors.get(source)
        self.status.setText(summary + ('\n' + error if error else ''))
        self.edit.setVisible(source in sync.states)
        self.authorize.setEnabled(sync.job is None)
        self.remove.setEnabled(sync.job is None)


class CalendarAccounts(QWidget):
    def __init__(self, service):
        super().__init__()
        self.service = service
        self.sync = service.get_calendar_sync()
        self.rows = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.empty = QLabel('暂无已授权账号')
        self.empty.setObjectName('Subtle')
        layout.addWidget(self.empty)
        self.sync.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        sources = self.sync.account_sources()
        for source in tuple(self.rows):
            if source not in sources:
                row = self.rows.pop(source)
                self.layout().removeWidget(row)
                row.hide()
                row.deleteLater()
        self.empty.setVisible(not sources)
        for index, source in enumerate(sources):
            row = self.rows.get(source)
            if row is None:
                row = self.rows[source] = CalendarAccountRow(self.service, self.sync, source)
                self.layout().insertWidget(index, row)
            row.refresh(self.sync, source)


class ConnectionErrorText(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setAccessibleName('连接错误详情')
        self.setReadOnly(True)
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(1)
        self.hide()

    def set_message(self, message):
        message = message or ''
        if message != self.toPlainText():
            self.setPlainText(message)
        self.setVisible(bool(message))

    def fit_height(self, width):
        if self.isHidden():
            return
        frame = self.frameWidth() * 2
        measure = QTextDocument()
        measure.setDefaultFont(self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        measure.setDefaultTextOption(option)
        measure.setDocumentMargin(self.document().documentMargin())
        measure.setPlainText(self.toPlainText())
        measure.setTextWidth(max(1, width - frame))
        required = ceil(measure.size().height()) + frame + 2
        maximum = 7 * self.fontMetrics().lineSpacing() + frame + 2 * ceil(measure.documentMargin())
        height = min(required, maximum)
        if self.minimumHeight() != height or self.maximumHeight() != height:
            self.setFixedHeight(height)


def qr_image(url):
    from segno import make_qr

    code = make_qr(url, error='M')
    width, _ = code.symbol_size(border=4)
    image = BytesIO()
    code.save(image, kind='png', scale=max(3, 213 // width), border=4)
    pixmap = QPixmap()
    pixmap.loadFromData(image.getvalue(), 'PNG')
    return pixmap


class CalendarConnections(QDialog):
    def __init__(self, owner, service, selected_source=None):
        super().__init__(owner)
        self.service = service
        self.sync = service.get_calendar_sync()
        self.scan_url = ''
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(lambda: self.fit_content(True))
        self.setWindowTitle('重新授权日程账号' if selected_source else '日程账号接入')
        self.resize(520, 256)
        self.setMinimumWidth(478)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(SettingsHeader(self, self.windowTitle()))
        providers = QHBoxLayout()
        self.source = ModernComboBox()
        self.source.setAccessibleName('日程来源')
        for source in GUIDE:
            self.source.addItem(SOURCES[source], source)
        accounts = self.sync.account_sources()
        preferred = selected_source or next((source for source in GUIDE if source not in accounts), accounts[0] if accounts else None)
        if preferred:
            self.source.setCurrentIndex(self.source.findData(preferred))
        self.source.setEnabled(selected_source is None)
        if selected_source:
            self.source.hide()
            provider = QLabel(SOURCES[selected_source])
            provider.setProperty('role', 'group-title')
            providers.addWidget(provider, 1)
        else:
            providers.addWidget(self.source, 1)
        providers.addWidget(button('授权说明', self.open_guide))
        layout.addLayout(providers)

        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName('同步状态')
        layout.addWidget(self.status)
        self.error = ConnectionErrorText()
        layout.addWidget(self.error)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(10)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet('QProgressBar {background: rgba(115,140,158,50); border: 0; border-radius: 3px;}'
                                    'QProgressBar::chunk {background: #3289d2; border-radius: 3px;}')
        self.progress.setAccessibleName('授权组件下载进度')
        self.progress.hide()
        layout.addWidget(self.progress)
        self.steps = QLabel()
        self.steps.setTextFormat(Qt.PlainText)
        self.steps.setWordWrap(True)
        layout.addWidget(self.steps)
        self.token_fields = QWidget()
        form = QVBoxLayout(self.token_fields)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(4)
        form.setSizeConstraint(QLayout.SetMinimumSize)
        self.endpoint_label = QLabel('服务器地址')
        self.endpoint = QLineEdit()
        self.endpoint.setMaxLength(2048)
        self.endpoint.setAccessibleName(self.endpoint_label.text())
        self.endpoint.setPlaceholderText('local 或 https://todo.example.com')
        form.addWidget(self.endpoint_label)
        form.addWidget(self.endpoint)
        self.token_label = QLabel()
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setMaxLength(8200)
        self.token.setPlaceholderText('粘贴口令或令牌')
        form.addWidget(self.token_label)
        form.addWidget(self.token)
        layout.addWidget(self.token_fields)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setAccessibleName('官方扫码授权二维码')
        self.qr.hide()
        layout.addWidget(self.qr)
        self.browser = button('在浏览器打开授权页', self.open_scan)
        self.browser.hide()
        layout.addWidget(self.browser, 0, Qt.AlignHCenter)
        hint = QLabel('连接后每 10 分钟同步。日程改期、取消、完成或删除后，本机会更新提醒。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

        actions = QHBoxLayout()
        if selected_source is None:
            actions.addWidget(button('手动导入…', self.manual_import))
        actions.addStretch()
        self.disconnect = button('移除', lambda: remove_account(self, self.sync, self.source.currentData()))
        self.refresh = button('立即同步', lambda: self.sync.sync_now(self.source.currentData()))
        self.connect_account = button('扫码登录', self.authorize, 'primary')
        for action in (self.disconnect, self.refresh, self.connect_account):
            actions.addWidget(action)
        actions.addWidget(button('关闭', self.reject))
        layout.addLayout(actions)
        self.source.currentIndexChanged.connect(self.change_source)
        self.sync.changed.connect(self.update_status)
        self.change_source()
        compact_dialog(self)
        self.fit_content()
        if selected_source in TOKEN_SOURCES:
            self.token.setFocus()

    def fit_content(self, shrink=False):
        if not self.property('densityApplied'):
            return
        layout = self.layout()
        margins = layout.contentsMargins()
        sheet = self.error.parentWidget()
        sheet_layout = sheet.layout()
        sheet_width = self.width() - margins.left() - margins.right()
        sheet_margins = sheet_layout.contentsMargins()
        self.error.fit_height(sheet_width - sheet_margins.left() - sheet_margins.right())
        sheet_layout.invalidate()
        sheet_layout.activate()
        sheet_height = max(sheet_layout.minimumSize().height(), sheet_layout.totalHeightForWidth(sheet_width))
        if sheet.minimumHeight() != sheet_height:
            sheet.setMinimumHeight(sheet_height)
        layout.invalidate()
        layout.activate()
        required = min(max(layout.minimumSize().height(), layout.totalHeightForWidth(self.width())),
                       self.screen().availableGeometry().height() - 24)
        if required > 0:
            if required != self.minimumHeight():
                self.setMinimumHeight(required)
            if shrink:
                self.resize(self.width(), required)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self.fit_content()

    def change_source(self):
        source = self.source.currentData()
        state = self.sync.states.get(source, {})
        self.token.clear()
        self.endpoint.setText(state.get('account', {}).get('endpoint', 'local'))
        self.token_fields.setVisible(source in TOKEN_SOURCES)
        self.endpoint_label.setVisible(source == 'nexttodo')
        self.endpoint.setVisible(source == 'nexttodo')
        self.token_label.setText('API 口令' if source == 'dida' else '只读令牌')
        self.token.setAccessibleName(self.token_label.text())
        self.update_status()
        self.fit_timer.start(0)

    def update_status(self):
        source = self.source.currentData()
        token_source = source in TOKEN_SOURCES
        state = self.sync.states.get(source)
        self.steps.setText(GUIDE[source][1])
        job = self.sync.job
        scan = self.sync.scan_info
        waiting = bool(job and job.source == source and job.connecting and not job.signed_in)
        show_scan = bool(waiting and scan and scan[0] == source)
        transfer = self.sync.transfer if waiting and self.sync.transfer and self.sync.transfer[0] == source else None
        downloading = transfer and transfer[1] == 'download'
        url = scan[2] if show_scan else ''
        shrink = bool(self.scan_url and not url or not self.progress.isHidden() and not transfer)
        if url != self.scan_url:
            self.scan_url = url
            if url:
                self.qr.setPixmap(qr_image(url))
            else:
                self.qr.clear()
        self.qr.setVisible(show_scan)
        self.browser.setVisible(show_scan)
        self.progress.setVisible(bool(transfer))
        if transfer:
            if downloading:
                self.progress.setRange(0, transfer[3])
                self.progress.setValue(transfer[2])
            else:
                self.progress.setRange(0, 0)

        if show_scan:
            label = SCAN_PROMPTS[scan[1]]
        elif downloading:
            received, size = (value / 1024**2 for value in transfer[2:])
            percent = round(100 * transfer[2] / transfer[3])
            label = f'正在下载{SOURCES[source]}官方组件  ·  {received:.1f} / {size:.1f} MB  ·  {percent}%'
        elif transfer:
            label = f'正在校验并准备{SOURCES[source]}组件…'
        elif waiting:
            if job.cancelled.is_set():
                label = '正在取消连接…'
            else:
                label = '正在验证并同步待办…' if token_source else '正在连接官方授权服务…'
        else:
            label = connection_status(self.sync, source)
        self.status.setText(label)
        self.error.set_message(self.sync.errors.get(source))

        self.disconnect.setVisible(source in self.sync.account_sources())
        self.disconnect.setEnabled(not job)
        self.refresh.setVisible(bool(state))
        self.refresh.setEnabled(not job)
        self.connect_account.setEnabled(not job or waiting and not job.cancelled.is_set())
        self.token_fields.setEnabled(not job)
        if waiting:
            caption = '取消连接' if token_source else '取消下载' if transfer else '取消授权'
        elif token_source:
            caption = '更新令牌并同步' if state else '连接并同步'
        elif ((source == 'dingtalk' and not any(path.is_file() for path in tool_candidates(self.sync.directory)))
              or (source == 'tencent' and not tencent_executable(self.sync.directory).is_file())):
            caption = '下载组件并扫码'
        else:
            caption = '重新扫码' if state else '扫码登录'
        self.connect_account.setText(caption)
        self.fit_content()
        if shrink:
            self.fit_timer.start(0)

    def open_guide(self):
        QDesktopServices.openUrl(QUrl(GUIDE[self.source.currentData()][0]))

    def open_scan(self):
        if self.scan_url:
            QDesktopServices.openUrl(QUrl(self.scan_url))

    def authorize(self):
        source = self.source.currentData()
        if self.sync.job:
            self.sync.cancel_authorization()
        elif source in TOKEN_SOURCES:
            if self.sync.connect_account(source, token=self.token.text(), endpoint=self.endpoint.text()):
                self.token.clear()
        else:
            self.sync.connect_account(source)

    def manual_import(self):
        from resource_agenda_import import show_import
        show_import(self, self.service)


def show_connections(owner, service, source=None):
    dialog = CalendarConnections(owner, service, source)
    try:
        exec_dialog(dialog)
    finally:
        dialog.sync.cancel_authorization()
