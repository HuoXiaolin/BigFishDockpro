"""Independent AI quota tray. It shares the bridge and never starts hardware probes."""
from PyQt5.QtCore import Qt, QPointF, QRectF, QObject
from PyQt5.QtGui import QPainter, QPainterPath, QPixmap, QIcon, QColor, QPen, QCursor, QFont
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QToolButton,QLabel,QSystemTrayIcon,QApplication
from ui_style import AlignedMenu
from flash_view import palette_for
from resource_options import AI_PROVIDER_NAMES, background
from resource_pages import SCROLL_STYLE, reset_text
from resource_quota import quota_color, tray_balance_text, tray_label, tray_readings
from resource_status import TRAY_RING_SIZES, draw_tray_rings, ring_dimensions
from taskbar_text import foreground_ink, system_mode


def quota_icon(levels, light):
    gray = '#566b7b' if light else '#a8bac8'
    rings = [(value, gray if stale else quota_color(value, light), stale) for value, stale in levels]
    # The diagonal meets the clockwise arc at three eighths of a turn.
    tail_ink = rings[0][1] if rings and (rings[0][0] or 0) >= 37.5 else gray
    icon = QIcon()
    for size in TRAY_RING_SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        draw_tray_rings(painter, QRectF(0, 0, size, size), rings, dark=not light)
        radius, stroke, _ = ring_dimensions(size, len(rings))
        # Keep the Q's diagonal tail within the outer ring's lane when there are inner rings.
        start = radius - stroke * .45 if len(rings) > 1 else radius * .39
        end = radius + max(stroke * .55, radius * .19)
        start = size / 2 + start / (2 ** .5)
        end = size / 2 + end / (2 ** .5)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(tail_ink), stroke * .75, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(start, start), QPointF(end, end))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def amount_icon(amount, ink):
    icon = QIcon()
    font = QFont('Segoe UI')
    font.setWeight(QFont.Bold)
    font.setPixelSize(32)
    glyphs = QPainterPath()
    glyphs.addText(0, 0, font, amount)
    bounds = glyphs.boundingRect()
    if bounds.isEmpty():
        return quota_icon((), ink == '#000000')
    color = QColor(ink)
    for size in TRAY_RING_SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        # Fit the entire amount in a single tray slot. Slight condensation keeps the digits taller.
        height_scale = size * .62 / bounds.height()
        scale_x = min((size - 1) / bounds.width(), height_scale)
        scale_y = min(scale_x * 1.55, height_scale)
        center = bounds.center()
        painter.translate(size / 2, size / 2)
        painter.scale(scale_x, scale_y)
        painter.translate(-center.x(), -center.y())
        painter.fillPath(glyphs, color)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def tooltip_line(reading):
    period = reading.label.removesuffix(' · 已用')
    period = {'每小时额度': '小时额度', '每周额度': '周额度', '每月额度': '月额度',
              '每周': '周额度', '每月': '月额度'}.get(period, period)
    parts = [reading.name]
    if reading.amount:
        parts.append(f'{period} {reading.amount}')
    else:
        parts.append(f'{period}剩余 {reading.remaining:.0f}%')
    if reading.stale:
        parts.append('上次读数')
    if reset := reset_text(reading.reset, compact=True):
        parts.append(reset)
    return ' · '.join(parts)


class AiPopup(QWidget):
    def __init__(self,service):
        super().__init__(None,Qt.Popup|Qt.FramelessWindowHint);self.service=service;self.page_key='ai';self.colors={}
        self.setAttribute(Qt.WA_TranslucentBackground);self.setWindowTitle('AI 用量 · 大肥鱼Dock')
        from resource_pages import AiView
        lay=QVBoxLayout(self);lay.setContentsMargins(10,8,10,10);lay.setSpacing(5);head=QHBoxLayout();head.addWidget(QLabel('AI 用量'),1);self.tabs={}
        close=QToolButton();close.setText('×');close.setAccessibleName('关闭 AI 用量');close.clicked.connect(self.hide);head.addWidget(close);lay.addLayout(head)
        self.ai_view=AiView(self);self.stats_view=self.ai_view.statistics;lay.addWidget(self.ai_view,1);self.refresh()
    def select_page(self,key,focus=None):
        self.page_key='ai'
        self.stats_view.focus_quota(focus)
        self.refresh()
        self.stats_view.scroll.verticalScrollBar().setValue(0)
    def refresh(self):
        colors=palette_for(self.service,background(self.service.cfg))
        if colors!=self.colors:
            self.colors=colors;self.setStyleSheet('QWidget{background:transparent;color:%(ink)s;font-size:10px} QLabel#Subtle{color:%(muted)s;font-size:9px} QToolButton{border:0;padding:3px 7px;border-radius:5px;color:%(muted)s} QToolButton:hover,QToolButton:checked{background:%(hover)s;color:%(ink)s} QTableWidget{border:0;background:transparent} QHeaderView::section{background:%(hover)s;color:%(muted)s;border:0;padding:4px}'%colors+SCROLL_STYLE)
        self.ai_view.refresh();self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setBrush(QColor(self.colors['surface']));p.setPen(QPen(QColor(self.colors['line']),1));p.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),12,12)


class AiTray(QObject):
    def __init__(self,service):
        super().__init__(service);self.service=service;self.popup=None;self.key=None;self.tray=QSystemTrayIcon(self);self.menu=AlignedMenu()
        self.readings=()
        self.balance=None
        self.taskbar_ink=None
        self.data_key=None
        self.appearance=None
        self.menu.addAction('AI',lambda:self.open('ai'))
        self.menu.addAction('刷新',lambda:service.deck.refresh() if service.deck else None);self.menu.addAction('设置',lambda:service.settings(page=3))
        self.menu.addSeparator();self.menu.addAction('关闭 AI 用量托盘图标',lambda:service.set_options(resource_ai_tray=False));self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason:self.open('stats') if reason==QSystemTrayIcon.Trigger else None)
        service.ai_data_changed.connect(self.refresh)
        self.refresh()
        if not service.runtime.dock.preview:self.tray.show()

    def refresh(self):
        bridge = self.service.deck
        cfg = self.service.cfg
        mode, provider, target = (cfg['resource_ai_tray_' + field] for field in ('mode', 'provider', 'metric'))
        prefs = mode, provider, target
        data_key = (id(bridge), bridge.ai_revision if bridge else 0, prefs)
        light = self.service.runtime.dock.is_light()
        style = background(cfg)
        appearance = light, style, self.service.runtime.dock._sys_light if style['theme'] == 'auto' else None
        if data_key == self.data_key and appearance == self.appearance:
            return
        if data_key != self.data_key:
            rows = bridge.providers if bridge else []
            self.readings = tray_readings(rows, *prefs)
            self.balance = tray_balance_text(self.readings[0].amount) if self.readings else None
            tip = self.tooltip(rows, mode, provider, target)
            if tip != self.tray.toolTip():
                self.tray.setToolTip(tip)
        self.data_key, self.appearance = data_key, appearance
        self.update_icon()
        if self.popup and self.popup.isVisible():
            self.popup.refresh()

    def sync_taskbar_text(self):
        if self.balance:
            self.taskbar_ink = foreground_ink(system_mode())
            self.update_icon()

    def update_icon(self):
        light = self.appearance[0]
        levels = ()
        if self.balance:
            if self.taskbar_ink is None:
                self.taskbar_ink = foreground_ink(system_mode())
            key = (self.balance, self.taskbar_ink)
        else:
            self.taskbar_ink = None
            levels = tuple((row.remaining, row.stale) for row in self.readings if row.remaining is not None)
            key = (light, levels)
        if key != self.key:
            icon = amount_icon(self.balance, self.taskbar_ink) if self.balance else quota_icon(levels, light)
            self.tray.setIcon(icon)
            self.key = key

    def tooltip(self, rows, mode, provider, target):
        if self.readings:
            return '\n'.join(map(tooltip_line, self.readings))
        if mode == 'fixed' and provider:
            name = next((row['name'] for row in rows if row['id'] == provider), '')
            if not name:
                name = AI_PROVIDER_NAMES.get(provider, provider)
                if provider.startswith('gateway-'):
                    name = '自定义用量接口'
            return ' · '.join(filter(None, (name, tray_label(target), '暂无读数')))
        return 'AI 用量 · 等待读数'

    def open(self,page='stats'):
        if self.popup is None:self.popup=AiPopup(self.service)
        first = self.readings[0] if self.readings else None
        cfg = self.service.cfg
        focus = (first.provider, first.metric) if first else (
            (cfg['resource_ai_tray_provider'], cfg['resource_ai_tray_metric']) if cfg['resource_ai_tray_mode'] == 'fixed' else None)
        self.popup.select_page(page, focus);point=self.tray.geometry().center() if not self.tray.geometry().isEmpty() else QCursor.pos()
        screen=QApplication.screenAt(point) or QApplication.primaryScreen();area=screen.availableGeometry();width=min(360,area.width());height=min(540,area.height())
        self.popup.resize(width,height);self.popup.move(max(area.left(),min(point.x()-width//2,area.right()-width+1)),max(area.top(),min(point.y()-height-5,area.bottom()-height+1)))
        self.popup.show();self.popup.raise_()
    def close(self):
        self.service.ai_data_changed.disconnect(self.refresh)
        self.tray.hide();self.tray.setContextMenu(None);self.tray.deleteLater();self.menu.close();self.menu.deleteLater()
        if self.popup:self.popup.hide();self.popup.deleteLater();self.popup=None
        self.deleteLater()
