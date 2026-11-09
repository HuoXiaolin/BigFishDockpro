"""Scan official device authorization codes from the resource settings."""
from io import BytesIO

from PyQt5.QtCore import QDateTime, Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from resource_agenda import SOURCES
from resource_calendar_sync import feishu_app_path
from resource_dingtalk_login import tool_candidates
from resource_tencent_login import executable as tencent_executable
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
        '通过官方组件直接扫码登录腾讯会议，免去手动创建应用和填写密钥。缺少组件时按需下载约 14 MB。授权后可同步待办和进行中的会议。',
    ),
}
SCAN_PROMPTS = {
    'dingtalk': '请用钉钉扫码，在手机上选择组织并确认授权。',
    'feishu-app': '第 1 步 · 请用飞书扫码创建日程授权应用。',
    'feishu-user': '请用飞书扫码确认日历读取权限。',
    'tencent': '请扫码打开腾讯会议授权页，在官方页面完成授权。',
}


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
    def __init__(self, owner, service):
        super().__init__(owner)
        self.service = service
        self.sync = service.get_calendar_sync()
        self.scan_url = ''
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(lambda: self.fit_content(True))
        self.setWindowTitle('日程账号接入')
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
        if self.sync.states:
            self.source.setCurrentIndex(self.source.findData(next(iter(self.sync.states))))
        providers.addWidget(self.source, 1)
        providers.addWidget(button('授权说明', self.open_guide))
        layout.addLayout(providers)

        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setAccessibleName('同步状态')
        layout.addWidget(self.status)
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
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setAccessibleName('官方扫码授权二维码')
        self.qr.hide()
        layout.addWidget(self.qr)
        self.browser = button('在浏览器打开授权页', self.open_scan)
        self.browser.hide()
        layout.addWidget(self.browser, 0, Qt.AlignHCenter)
        hint = QLabel('登录后，每 10 分钟同步。日程改期、取消或删除后，本机会更新提醒。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.addWidget(button('手动导入…', self.manual_import))
        actions.addStretch()
        self.disconnect = button('断开', lambda: self.sync.disconnect(self.source.currentData()))
        self.refresh = button('立即同步', lambda: self.sync.sync_now(self.source.currentData()))
        self.connect_account = button('扫码登录', self.authorize, 'primary')
        for action in (self.disconnect, self.refresh, self.connect_account):
            actions.addWidget(action)
        actions.addWidget(button('关闭', self.reject))
        layout.addLayout(actions)
        self.source.currentIndexChanged.connect(self.update_status)
        self.sync.changed.connect(self.update_status)
        self.update_status()
        compact_dialog(self)
        self.fit_content()

    def fit_content(self, shrink=False):
        if not self.property('densityApplied'):
            return
        layout = self.layout()
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

    def update_status(self):
        source = self.source.currentData()
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
            label = '正在结束授权…' if job.cancelled.is_set() else '正在连接官方授权服务…'
        elif job and job.source == source:
            label = '正在断开…' if job.disconnecting else '正在同步日程…'
        elif state and state['updated']:
            stamp = QDateTime.fromSecsSinceEpoch(state['updated']).toString('MM-dd HH:mm')
            label = f"已登录  ·  上次同步 {stamp}  ·  {len(state['events'])} 项"
            if state['truncated']:
                label += '（已保留最近 256 项）'
        elif state:
            label = '已登录，等待首次同步'
        else:
            label = '尚未登录'
        error = self.sync.errors.get(source)
        self.status.setText(label + ('\n' + error if error else ''))

        pending = source == 'feishu' and feishu_app_path(self.sync.directory).is_file()
        self.disconnect.setVisible(bool(state or pending))
        self.disconnect.setEnabled(not job)
        self.refresh.setVisible(bool(state))
        self.refresh.setEnabled(not job)
        self.connect_account.setVisible(source != 'tencent' or not state or waiting or bool(error))
        self.connect_account.setEnabled(not job or waiting and not job.cancelled.is_set())
        if waiting:
            caption = '取消下载' if transfer else '取消授权'
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
        if self.sync.job:
            self.sync.cancel_authorization()
        else:
            self.sync.connect_account(self.source.currentData())

    def manual_import(self):
        from resource_agenda_import import show_import
        show_import(self, self.service)


def show_connections(owner, service):
    dialog = CalendarConnections(owner, service)
    try:
        exec_dialog(dialog)
    finally:
        dialog.sync.cancel_authorization()
