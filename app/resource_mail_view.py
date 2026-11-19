"""News-style recent mail list, filtered locally by account."""
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from mail_accounts import ACCOUNT_COLORS, account_label
from resource_content import Headline
from ui_style import ModernComboBox, button


class MailView(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.model = owner.service.get_mail()
        self.accounts = None
        self.entries = None
        body = QVBoxLayout(self)
        body.setContentsMargins(0,0,0,0)
        body.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(5)
        title = QLabel('邮箱通知')
        title.setObjectName('RankTitle')
        header.addWidget(title, 1)
        self.filter = ModernComboBox()
        self.filter.setAccessibleName('筛选邮箱')
        self.filter.setProperty('glassField', True)
        self.filter.setFixedSize(112, 22)
        self.filter.setStyleSheet('QComboBox{min-height:0;padding:1px 23px 1px 7px;border:0;background:transparent;font-size:11px}')
        header.addWidget(self.filter)
        self.reload = QToolButton()
        self.reload.setText('刷新')
        self.reload.setFixedHeight(22)
        self.reload.clicked.connect(self.model.refresh)
        header.addWidget(self.reload)
        body.addLayout(header)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        body.addLayout(self.rows)
        self.status = QLabel()
        self.status.setObjectName('Subtle')
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        self.manage = button('管理邮箱账号…', self.manage_accounts)
        body.addWidget(self.manage)
        self.filter.currentIndexChanged.connect(self.select)
        self.model.changed.connect(self.update_if_visible)

    def manage_accounts(self):
        from resource_mail_settings import edit_mail_accounts
        edit_mail_accounts(self.owner.service, self.window())

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    @pyqtSlot()
    def update_if_visible(self):
        if self.isVisible():
            self.refresh()

    def select(self, *_):
        self.model.selection = self.filter.currentData() or ''
        self.refresh()
        frame = self.parentWidget()
        while frame is not None:
            if hasattr(frame, 'verticalScrollBar'):
                frame.verticalScrollBar().setValue(0)
                break
            frame = frame.parentWidget()

    def refresh(self):
        model = self.model
        accounts = [row for row in model.accounts() if row['enabled']]
        signature = tuple((row['id'], account_label(row), row['color']) for row in accounts)
        if signature != self.accounts:
            self.accounts = signature
            self.filter.blockSignals(True)
            self.filter.clear()
            self.filter.addItem('全部邮箱', '')
            for identity, title, color in signature:
                swatch = QPixmap(9, 9)
                swatch.fill(QColor(ACCOUNT_COLORS[color]))
                self.filter.addItem(QIcon(swatch), title, identity)
            self.filter.setCurrentIndex(max(0, self.filter.findData(model.selection)))
            self.filter.blockSignals(False)
            model.selection = self.filter.currentData() or ''
        selected = model.selection
        lookup = {row['id']: row for row in accounts}
        entries = (signature, tuple(model.contents(selected)))
        if entries != self.entries:
            self.entries = entries
            while self.rows.count():
                widget = self.rows.takeAt(0).widget()
                widget.hide()
                widget.deleteLater()
            for identity, item in entries[1]:
                account = lookup[identity]
                entry = dict(title=item.title, stamp=item.stamp or None, url=item.url,
                             source=account_label(account) + ' · ' + item.sender)
                self.rows.addWidget(Headline(self.owner, entry, accent=ACCOUNT_COLORS[account['color']]))
        statuses = [model.status(row) for row in accounts if not selected or selected == row['id']]
        unavailable = sum(state in ('暂时离线', '需要授权') for state, _, _ in statuses)
        if not accounts:
            message = '请添加邮箱账号。' if not model.accounts() else '邮箱账号已暂停。'
        elif len(statuses) == 1 and statuses[0][1]:
            message = statuses[0][1]
        elif unavailable:
            message = f'{unavailable} 个邮箱暂时无法更新。'
        elif not entries[1]:
            message = '正在同步收件箱…' if any(state != '已连接' for state, _, _ in statuses) else '收件箱暂无邮件。'
        else:
            message = ''
        self.status.setText(message)
        self.status.setVisible(bool(message))
        self.manage.setVisible(not accounts or bool(unavailable))
        self.reload.setEnabled(bool(model.job))
        if self.isVisible():
            model.mark_seen(selected)
