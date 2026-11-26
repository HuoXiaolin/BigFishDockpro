"""Reveal an edge-docked desktop window without changing its saved geometry."""
import time

from PyQt5.QtCore import QEvent, QEasingCurve, QObject, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QColor, QCursor, QLinearGradient, QPainter, QPainterPath, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from card_snap import touching_edge


def popup_blocks_folding(settings_dialog=None):
    modal = QApplication.activeModalWidget()
    return QApplication.activePopupWidget() is not None or (modal is not None and modal is not settings_dialog)


def option(key):
    if key=='resource':return 'resource_edge_hide'
    if key in ('clock','calendar','picture','spectrum') or str(key).split(':')[0] in ('panel','custom','note','resource'):
        return 'card_edge_hide'


class EdgeLight(QWidget):
    def __init__(self,window):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAccessibleName('贴边光条')
        self.hide()

    def paintEvent(self,event):
        owner=self.parentWidget();colors=getattr(owner,'colors',None) or {}
        style=getattr(owner,'background',None)
        accent=QColor(style.get('color') or '#64bafa') if isinstance(style,dict) else QColor('#64bafa')
        if not accent.isValid():accent=QColor('#64bafa')
        rect=QRectF(self.rect());horizontal=self.width()>self.height()
        gradient=QLinearGradient(rect.topLeft(),rect.topRight() if horizontal else rect.bottomLeft())
        for pos,ink in ((0,accent.darker(145)),(.24,accent),(.55,accent.lighter(155)),(1,accent.darker(130))):
            gradient.setColorAt(pos,ink)
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen);p.setBrush(QColor(colors.get('surface','#23344a')) if isinstance(colors,dict) else QColor('#23344a'))
        p.drawRoundedRect(rect,3,3);p.setBrush(gradient);p.drawRoundedRect(rect.adjusted(1,1,-1,-1),2,2)


class EdgeReveal(QObject):
    def __init__(self,window,runtime,capsule):
        super().__init__(window)
        self.window=window;self.runtime=runtime;self.capsule=capsule
        self.enabled=False;self.edge='free';self.fraction=1.;self.target=1.
        self.light=None;self.peek_until=0.;self.manual_hover=False;self.notice=None;self.as_pill=False
        self.idle=QTimer(self);self.idle.setSingleShot(True);self.idle.timeout.connect(self.settle)
        self.animation=QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.set_fraction)
        window.installEventFilter(self)

    def configure(self,enabled):
        if enabled==self.enabled:return
        self.enabled=enabled
        if enabled:self.idle.start(650)
        else:self.reset()

    def reset(self):
        self.idle.stop();self.animation.stop();self.peek_until=0.;self.manual_hover=False
        self.notice=None;self.as_pill=False
        self.target=1.;self.set_fraction(1.);self.edge='free'

    def find_edge(self):
        w=self.window
        if not w.isWindow() or not w.isVisible() or w.isMinimized():return 'free'
        if self.capsule and w.taskbar_slot() is not None:return 'free'
        screen=QApplication.screenAt(w.geometry().center())
        if not screen:return 'free'
        preferred=w.service.cfg['resource_edge'] if self.capsule else self.edge
        return touching_edge(w.geometry(),screen.availableGeometry(),preferred,tolerance=3)

    def settle(self):
        if not self.enabled:return
        w=self.window;edge=self.find_edge()
        if edge=='free':
            self.reset();return
        self.edge=edge
        wait=self.peek_until-time.monotonic()
        if wait>0:
            self.idle.start(max(1,round(wait*1000)));return
        settings_dialog = w.service.options_dialog if self.capsule else None
        if popup_blocks_folding(settings_dialog) or QApplication.mouseButtons():
            self.idle.start(650);return
        automatic_peek=bool(self.peek_until)
        self.peek_until=0.
        if self.visible_at_cursor() and (self.manual_hover or self.fraction>=1. and not automatic_peek):
            self.manual_hover=True;return
        if self.capsule and not w.service.compact:
            w.service.fold(True,automatic=True)
            if self.find_edge()=='free':return
        surface=getattr(w,'_fold_surface',None)
        if surface:
            self.idle.start(max(1,surface.animation.duration()-surface.animation.currentTime()+1))
            return
        self.move_to(0.)

    def visible_at_cursor(self):
        point=self.window.mapFromGlobal(QCursor.pos())
        mask=self.window.mask()
        return self.window.rect().contains(point) if mask.isEmpty() else mask.contains(point)

    def notify(self,notice=None):
        if not self.capsule or not self.enabled or self.find_edge()=='free':return
        w=self.window
        if self.fraction>=1. and self.target==1. and not w.service.compact:return
        if not w.service.compact:w.service.fold(True,automatic=True)
        with w.service.fold_transition(content_change=bool(notice)):
            self.peek_until=time.monotonic()+5.;self.manual_hover=False;self.as_pill=True;self.notice=notice
            w.clear_notice();w.enter_timer.stop()
            w._compact_cache=None;w.reposition();self.move_to(1.);w.update()
        self.idle.start(5000)
        return True

    def move_to(self,value):
        if self.target==value:return
        self.target=value;self.animation.stop()
        if self.runtime.dock.cfg.get('motion_enabled',True):
            self.animation.setDuration(max(1,round(210*abs(self.fraction-value))))
            self.animation.setStartValue(self.fraction);self.animation.setEndValue(value);self.animation.start()
        else:self.set_fraction(value)

    def light_rect(self):
        rect=self.window.rect();vertical=self.edge in ('left','right')
        length=min(58,rect.height() if vertical else rect.width());breadth=6
        if vertical:
            return QRect(0 if self.edge=='left' else rect.width()-breadth,(rect.height()-length)//2,breadth,length)
        return QRect((rect.width()-length)//2,0 if self.edge=='top' else rect.height()-breadth,length,breadth)

    def set_fraction(self,value):
        self.fraction=float(value);w=self.window
        if value>=1.:
            if self.light:
                self.light.hide();w.clearMask()
        else:
            if self.light is None:self.light=EdgeLight(w)
            target=self.light_rect();rect=w.rect()
            scaled=QRectF(*(a+(b-a)*value for a,b in zip(target.getRect(),rect.getRect())))
            path=QPainterPath();path.addRoundedRect(scaled,min(6,scaled.width()/2),min(6,scaled.height()/2))
            w.setMask(QRegion(path.toFillPolygon().toPolygon()))
            self.light.setGeometry(target);self.light.setVisible(value<.6)
            if value<.6:self.light.raise_()
        if value in (0.,1.):
            self.runtime.click_policy.apply(w)
            if self.capsule and self.target==0. and value==0. and not self.peek_until:
                self.as_pill=False;self.notice=None;w._compact_cache=None;w.reposition()

    def eventFilter(self,w,event):
        if not self.enabled:return False
        kind=event.type()
        if kind in (QEvent.Hide,QEvent.ParentChange):
            self.reset()
        elif kind in (QEvent.Resize,QEvent.Move,QEvent.Show):
            if self.fraction<1.:self.set_fraction(self.fraction)
            # Live compact width may change while peeking. Keep its original deadline.
            if not self.idle.isActive():self.idle.start(650)
        elif kind==QEvent.Enter and self.target==0.:
            if self.visible_at_cursor():
                self.manual_hover=True;self.idle.stop();self.move_to(1.)
        elif kind==QEvent.Leave:
            self.manual_hover=False
            if not self.peek_until or self.peek_until<=time.monotonic():self.idle.start(650)
        elif kind==QEvent.MouseButtonPress:
            self.peek_until=0.;self.manual_hover=True
        elif kind==QEvent.MouseButtonRelease:self.idle.start(650)
        return False
