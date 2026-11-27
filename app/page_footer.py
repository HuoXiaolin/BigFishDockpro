"""Transparent page navigation anchored inside capsule and collection cards."""
from PyQt5.QtCore import QEvent, QSize, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy, QToolButton
from flash_view import icon


PAGER_WIDTH = 110
PAGER_HEIGHT = 20
PAGER_TEXT = 11
PAGER_BOTTOM = 3


class FooterLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, rect.width())
        painter = QPainter(self)
        self.style().drawItemText(painter, rect, self.alignment() | Qt.TextSingleLine,
                                  self.palette(), self.isEnabled(), text, self.foregroundRole())


class CollectionHint(FooterLabel):
    drop_text = '拖入文件、文件夹或快捷方式'
    empty_text = '拖入内容，或等待桌面自动分类'

    def has_room(self):
        view = self.parentWidget()
        scroll = view.verticalScrollBar()
        if scroll.value() < scroll.maximum():
            return False
        if not view.count():
            return True
        last = view.visualItemRect(view.item(view.count() - 1))
        return view.viewport().y() + last.bottom() < self.y()

    def paintEvent(self, event):
        if self.text() not in (self.drop_text, self.empty_text) or self.has_room():
            super().paintEvent(event)


class PagePager(QFrame):
    def __init__(self, parent, step, *, bottom=PAGER_BOTTOM, leading=None):
        super().__init__(parent)
        self.setObjectName('FooterPager')
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAccessibleName('切换页面')
        self.setToolTip('滚轮上下切换页面')
        self.step = step
        self.bottom = bottom
        self.leading = leading
        self.wheel_units = 0
        self.appearance = None
        self.setFixedSize(PAGER_WIDTH, PAGER_HEIGHT)
        self.visibility_effect = QGraphicsOpacityEffect(self)
        self.visibility_effect.setOpacity(0)
        self.setGraphicsEffect(self.visibility_effect)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.previous = self.arrow(row, '上一页', -1)
        self.name = FooterLabel(parent=self)
        self.name.setObjectName('FooterPagerName')
        self.name.setAlignment(Qt.AlignCenter)
        self.name.installEventFilter(self)
        row.addWidget(self.name, 1)
        self.next = self.arrow(row, '下一页', 1)
        self.set_page('', False)
        parent.installEventFilter(self)

    def anchor(self):
        parent = self.parentWidget()
        x = max(0, (parent.width() - self.width()) // 2)
        y = max(0, parent.height() - self.height() - self.bottom)
        self.move(x, y)
        self.raise_()
        if self.leading is not None:
            edge = parent.width() if self.isHidden() else x
            self.leading.setGeometry(0, y, max(0, edge - 5), self.height())
            self.leading.raise_()

    def arrow(self, row, title, step):
        button = QToolButton(self)
        button.setObjectName('FooterPagerArrow')
        button.setToolTip(title)
        button.setAccessibleName(title)
        button.setFocusPolicy(Qt.StrongFocus)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda checked=False: self.step(step))
        button.installEventFilter(self)
        row.addWidget(button)
        return button

    def set_page(self, name, can_switch):
        if name != self.name.text():
            self.name.setText(name)
            self.name.setAccessibleName('当前页 ' + name)
            self.name.setToolTip(name + ' · 滚轮上下切换页面')
        self.previous.setEnabled(can_switch)
        self.next.setEnabled(can_switch)
        if not can_switch:
            self.wheel_units = 0
        self.anchor()

    def sync_appearance(self, ink):
        if self.appearance == ink:
            return
        self.appearance = ink
        for button, name in ((self.previous, 'back'), (self.next, 'fold')):
            button.setFixedSize(24, PAGER_HEIGHT)
            button.setIcon(icon(name, ink, 14))
            button.setIconSize(QSize(14, 14))
        self.setStyleSheet(f'''
            QFrame#FooterPager {{border:0;background:transparent;}}
            QToolButton#FooterPagerArrow {{color:{ink};background:transparent;border:0;
                padding:0;margin:0;border-radius:6px;}}
            QToolButton#FooterPagerArrow:hover,QToolButton#FooterPagerArrow:focus,
            QToolButton#FooterPagerArrow:pressed {{background:transparent;}}
            QToolButton#FooterPagerArrow:disabled {{color:rgba(128,140,153,150);}}
            QLabel#FooterPagerName {{color:{ink};background:transparent;border:0;font-size:{PAGER_TEXT}px;font-weight:600;}}
        ''')

    def scroll_page(self, event):
        if not self.previous.isEnabled():
            return False
        angle, pixel = event.angleDelta(), event.pixelDelta()
        units = angle.y() or angle.x() or 4 * (pixel.y() or pixel.x())
        if not units:
            return False
        self.wheel_units += -units
        steps = int(self.wheel_units / 120)
        if steps:
            self.wheel_units -= steps * 120
            self.step(steps)
        event.accept()
        return True

    def eventFilter(self, watched, event):
        if watched is self.parentWidget():
            if event.type() in (QEvent.Resize, QEvent.Show):
                self.anchor()
        else:
            if event.type() == QEvent.Wheel and self.scroll_page(event):
                return True
            if event.type() == QEvent.FocusIn and event.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason):
                self.visibility_effect.setOpacity(1)
            if event.type() == QEvent.FocusOut and not self.underMouse():
                self.visibility_effect.setOpacity(0)
        return super().eventFilter(watched, event)

    def wheelEvent(self, event):
        if not self.scroll_page(event):
            event.ignore()

    def enterEvent(self, event):
        self.visibility_effect.setOpacity(1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.wheel_units = 0
        self.visibility_effect.setOpacity(0)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self.wheel_units = 0
        self.visibility_effect.setOpacity(0)
        super().hideEvent(event)
