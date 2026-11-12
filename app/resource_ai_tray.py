"""Independent AI quota tray. It shares the bridge and never starts hardware probes."""
from PyQt5.QtCore import Qt,QRectF,QPointF,QPoint,QObject
from PyQt5.QtGui import QPainter,QPixmap,QIcon,QColor,QPen,QCursor
from PyQt5.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QToolButton,QLabel,QSystemTrayIcon,QApplication
from ui_style import AlignedMenu
from flash_view import palette_for
from resource_options import background
from resource_pages import SCROLL_STYLE
from resource_quota import amount_text, quota_color, remaining_percent, used_percent


def quota_icon(used,light=False):
    """Draw the same rounded Q silhouette at Windows tray resolutions."""
    remaining = remaining_percent(used)
    ink = QColor(quota_color(remaining, light))
    track = QColor(ink)
    track.setAlpha(115)
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size / 32, size / 32)
        circle = QRectF(4.5, 4, 22, 22)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(track, 4.8, Qt.SolidLine, Qt.RoundCap))
        painter.drawEllipse(circle)
        painter.setPen(QPen(ink, 4.8, Qt.SolidLine, Qt.RoundCap))
        if remaining:
            painter.drawArc(circle, 90 * 16, -round(remaining * 57.6))
        painter.drawLine(QPointF(19, 21), QPointF(27.5, 28.5))
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class AiPopup(QWidget):
    def __init__(self,service):
        super().__init__(None,Qt.Popup|Qt.FramelessWindowHint);self.service=service;self.page_key='ai';self.colors={}
        self.setAttribute(Qt.WA_TranslucentBackground);self.setWindowTitle('AI 用量 · 大肥鱼Dock')
        from resource_pages import AiView
        lay=QVBoxLayout(self);lay.setContentsMargins(10,8,10,10);lay.setSpacing(5);head=QHBoxLayout();head.addWidget(QLabel('AI 用量'),1);self.tabs={}
        close=QToolButton();close.setText('×');close.setAccessibleName('关闭 AI 用量');close.clicked.connect(self.hide);head.addWidget(close);lay.addLayout(head)
        self.ai_view=AiView(self);self.stats_view=self.ai_view.statistics;lay.addWidget(self.ai_view,1);self.refresh()
    def select_page(self,key):self.page_key='ai';self.refresh()
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
        self.menu.addAction('AI',lambda:self.open('ai'))
        self.menu.addAction('刷新',lambda:service.deck.refresh() if service.deck else None);self.menu.addAction('设置',service.settings)
        self.menu.addSeparator();self.menu.addAction('关闭 AI 用量托盘图标',lambda:service.set_options(resource_ai_tray=False));self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason:self.open('stats') if reason==QSystemTrayIcon.Trigger else None);self.refresh()
        if not service.runtime.dock.preview:self.tray.show()
    def refresh(self):
        bridge=self.service.deck;rows=bridge.providers if bridge else []
        levels=[(value,row['name']) for row in rows for q in row.get('quotas',[]) if (value:=used_percent(q)) is not None]
        used,name=max(levels,default=(None,''),key=lambda value:value[0]);light=self.service.runtime.dock.is_light();key=(used,light)
        if key!=self.key:self.tray.setIcon(quota_icon(used,light));self.key=key
        balance = next((f" · {row['name']} {value}" for row in rows for q in row.get('quotas',[])
                        if q.get('kind')!='spend' and (value := amount_text(q)) not in (None, '—')), '')
        remaining = remaining_percent(used)
        self.tray.setToolTip('AI 用量'+(f' · {name} 剩余 {remaining:.0f}%' if remaining is not None else balance or ' · 等待读数'))
        if self.popup and self.popup.isVisible():self.popup.refresh()
    def open(self,page='stats'):
        if self.popup is None:self.popup=AiPopup(self.service)
        self.popup.select_page(page);point=self.tray.geometry().center() if not self.tray.geometry().isEmpty() else QCursor.pos()
        screen=QApplication.screenAt(point) or QApplication.primaryScreen();area=screen.availableGeometry();width=min(360,area.width());height=min(360,area.height())
        self.popup.resize(width,height);self.popup.move(max(area.left(),min(point.x()-width//2,area.right()-width+1)),max(area.top(),min(point.y()-height-5,area.bottom()-height+1)))
        self.popup.show();self.popup.raise_()
    def close(self):
        self.tray.hide();self.tray.setContextMenu(None);self.tray.deleteLater();self.menu.close();self.menu.deleteLater()
        if self.popup:self.popup.hide();self.popup.deleteLater();self.popup=None
        self.deleteLater()
