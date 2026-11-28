"""Reveal an edge-docked desktop window without changing its saved geometry."""
import time
from math import ceil

from PyQt5.QtCore import QEvent, QEasingCurve, QObject, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QColor, QCursor, QLinearGradient, QPainter, QPainterPath, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from card_snap import touching_edge


_UNCHANGED=object()


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
        self.glass=None
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
        if self.property('ball'):
            from capsule_glass import CapsuleGlass
            from resource_compact import paint_halo
            from window_backdrop import component_backdrop
            p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
            if self.glass is None:self.glass=CapsuleGlass()
            cfg=owner.service.cfg
            if not owner.testAttribute(Qt.WA_TransparentForMouseEvents):
                # Windows hit-tests layered windows by pixel alpha. Keep even a
                # clear, faded ball clickable with one displayed alpha level.
                transition=getattr(owner,'_fold_surface',None)
                opacity=transition.opacity if transition else owner.windowOpacity()
                p.setPen(Qt.NoPen);p.setBrush(QColor(0,0,0,ceil(1/max(.05,opacity))))
                p.drawEllipse(rect.adjusted(.5,.5,-.5,-.5))
            self.glass.paint(p,self,owner.service.runtime.dock,rect.height()/2,
                             appearance=owner.background,inset=4 if cfg['resource_halo'] else 0,
                             backdrop_mode=component_backdrop(cfg,'resource'))
            paint_halo(owner,p,event.region(),'ball',ball_widget=self)
            if cfg['resource_face']:
                p.translate(-self.pos())
                owner.liquid.paint_face(p,rect.center()+self.pos(),rect.width()*.64)
            else:
                p.setPen(Qt.NoPen);p.setBrush(accent)
                p.drawEllipse(rect.center(),rect.width()*.14,rect.width()*.14)
            return
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
        self.edge_enabled=False;self.app_mode='off';self.over_app=False;self.hidden_shape='light';self.previous_fold=_UNCHANGED
        self.light=None;self.peek_until=0.;self.manual_hover=False;self.notice=None;self.as_pill=False
        self.hovered_strip=None
        self.idle=QTimer(self);self.idle.setSingleShot(True);self.idle.timeout.connect(self.settle)
        self.app_timer=QTimer(self);self.app_timer.setInterval(450);self.app_timer.timeout.connect(self.check_application)
        self.animation=QVariantAnimation(self)
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.set_fraction)
        window.installEventFilter(self)

    def configure(self,enabled,app_mode='off'):
        if (enabled,app_mode)==(self.edge_enabled,self.app_mode):return
        self.edge_enabled=enabled;self.app_mode=app_mode
        self.enabled=enabled or app_mode!='off'
        if self.app_mode=='off':self.over_app=False
        self.watch_application()
        if self.enabled:
            if self.over_app and self.fraction<1.:
                self.edge=self.hiding_position();self.hidden_shape=app_mode;self.set_fraction(self.fraction)
            self.idle.start(200)
        else:self.reset()

    def watch_application(self):
        if self.app_mode!='off' and self.window.isVisible():
            if not self.app_timer.isActive():self.app_timer.start()
        else:self.app_timer.stop()

    def check_application(self):
        from ctypes.wintypes import POINT
        from window_layers import application_under,client_frame,is_topmost
        w=self.window
        if w.press is not None or w.liquid.landing or getattr(w,'_fold_surface',None):return
        active=False
        if self.app_mode!='off' and w.isVisible() and not w.isMinimized() and w.taskbar_slot() is None:
            hwnd=int(w.winId())
            if is_topmost(hwnd):
                frame=client_frame(hwnd)
                if frame:
                    x,y,width,height=frame
                    middle=w.rect().center()
                    if not w.service.compact:
                        shared=w.geometry().intersected(w.floating_rect(True))
                        if not shared.isEmpty():middle=w.mapFromGlobal(shared.center())
                    active=application_under(hwnd,POINT(x+round((middle.x()+.5)*width/w.width()),y+round((middle.y()+.5)*height/w.height())))
        if active==self.over_app:return
        self.over_app=active
        self.runtime.click_policy.apply(w)
        self.settle()

    def hiding_position(self):
        if self.over_app and self.app_mode=='light':return 'app-top'
        edge=self.find_edge() if self.edge_enabled else 'free'
        return 'center' if self.over_app and edge=='free' else edge

    @property
    def presenting_marker(self):
        return self.target==0. or self.fraction<1. or self.hovered_strip is not None

    @property
    def visible_ball(self):
        return self.light if self.hidden_shape=='ball' and self.light is not None and not self.light.isHidden() else None

    def reset(self,refresh=True):
        self.idle.stop();self.animation.stop();self.peek_until=0.;self.manual_hover=False
        self.hovered_strip=None
        self.notice=None;self.as_pill=False
        self.target=1.;self.set_fraction(1.);self.edge='free'
        self.restore_fold(refresh)

    def restore_fold(self,refresh):
        if self.previous_fold is _UNCHANGED:return
        service=self.window.service
        previous,self.previous_fold=self.previous_fold,_UNCHANGED
        if service.auto_compact is True:
            service.auto_compact=previous
            if refresh and self.window.isVisible():service.sync()

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
        w=self.window;edge=self.hiding_position()
        if edge=='free':
            if self.previous_fold is not _UNCHANGED or self.peek_until:self.reset()
            else:
                self.manual_hover=False;self.move_to(1.)
            return
        if self.edge!=edge:
            self.edge=edge
            if self.fraction<1.:self.set_fraction(self.fraction)
        wait=self.peek_until-time.monotonic()
        if wait>0:
            self.idle.start(max(1,round(wait*1000)));return
        settings_dialog = w.service.options_dialog if self.capsule else None
        if popup_blocks_folding(settings_dialog) or QApplication.mouseButtons():
            self.idle.start(650);return
        automatic_peek=bool(self.peek_until)
        self.peek_until=0.
        interactive=not self.over_app or self.runtime.click_policy.accepts_input(w)
        if interactive and self.visible_at_cursor() and (self.manual_hover or self.fraction>=1. and not automatic_peek):
            self.manual_hover=True;return
        if self.capsule and not w.service.compact:
            if self.over_app and self.previous_fold is _UNCHANGED:self.previous_fold=w.service.auto_compact
            w.service.fold(True,automatic=True)
            if self.hiding_position()=='free':return
        surface=getattr(w,'_fold_surface',None)
        if surface:
            self.idle.start(max(1,surface.animation.duration()-surface.animation.currentTime()+1))
            return
        shape=self.app_mode if self.over_app else 'light'
        if self.hidden_shape!=shape:
            self.hidden_shape=shape
            if self.fraction<1.:self.set_fraction(self.fraction)
        self.move_to(0.)

    def visible_at_cursor(self):
        point=self.window.mapFromGlobal(QCursor.pos())
        mask=self.window.mask()
        return self.window.rect().contains(point) if mask.isEmpty() else mask.contains(point)

    def notify(self,notice=None):
        if not self.capsule or not self.enabled or self.hiding_position()=='free':return
        w=self.window
        if self.fraction>=1. and self.target==1. and not w.service.compact:return
        if not w.service.compact:
            if self.over_app and self.previous_fold is _UNCHANGED:self.previous_fold=w.service.auto_compact
            w.service.fold(True,automatic=True)
        with w.service.fold_transition(content_change=bool(notice)):
            self.peek_until=time.monotonic()+5.;self.manual_hover=False;self.as_pill=True;self.notice=notice
            w.clear_notice();w.enter_timer.stop()
            w._compact_cache=None;w.reposition();self.move_to(1.);w.update()
        self.idle.start(5000)
        return True

    def move_to(self,value):
        if self.target==value:return
        self.target=value;self.animation.stop()
        if self.capsule and value==0.:
            self.window.resize_edges.sync()
        if self.runtime.dock.cfg.get('motion_enabled',True):
            self.animation.setDuration(max(1,round(210*abs(self.fraction-value))))
            self.animation.setStartValue(self.fraction);self.animation.setEndValue(value);self.animation.start()
        else:self.set_fraction(value)

    def light_rect(self):
        rect=self.window.rect();vertical=self.edge in ('left','right')
        if self.hidden_shape=='ball':
            side=min(38,rect.width(),rect.height())
            ball=QRect(0,0,side,side);ball.moveCenter(rect.center())
            if self.edge=='left':ball.moveLeft(0)
            elif self.edge=='right':ball.moveRight(rect.right())
            elif self.edge=='top':ball.moveTop(0)
            elif self.edge=='bottom':ball.moveBottom(rect.bottom())
            return ball
        length=min(58,rect.height() if vertical else rect.width());breadth=6
        if self.edge in ('center','free'):
            bar=QRect(0,0,length,min(breadth,rect.height()));bar.moveCenter(rect.center());return bar
        if vertical:
            return QRect(0 if self.edge=='left' else rect.width()-breadth,(rect.height()-length)//2,breadth,length)
        return QRect((rect.width()-length)//2,0 if self.edge in ('top','app-top') else rect.height()-breadth,length,breadth)

    def set_fraction(self,value):
        self.fraction=float(value);w=self.window
        if value>=1.:
            if self.light:
                self.light.hide();w.clearMask()
                if self.light.glass:self.light.glass.clear()
        else:
            if self.light is None:self.light=EdgeLight(w)
            target=self.light_rect();rect=w.rect()
            scaled=QRectF(*(a+(b-a)*value for a,b in zip(target.getRect(),rect.getRect())))
            ball=self.hidden_shape=='ball'
            radius=min(scaled.width(),scaled.height())/2 if ball else min(6,scaled.width()/2,scaled.height()/2)
            path=QPainterPath();path.addRoundedRect(scaled,radius,radius)
            w.setMask(QRegion(path.toFillPolygon().toPolygon()))
            self.light.setProperty('ball',ball)
            self.light.setAccessibleName('收起圆球' if ball else '收起光条')
            self.light.setGeometry(target);self.light.setVisible(value<.6)
            self.light.update()
            if value<.6:self.light.raise_()
        if value in (0.,1.):
            if self.capsule and hasattr(w,'resize_edges'):w.resize_edges.sync()
            self.runtime.click_policy.apply(w)
            if self.capsule and self.target==0. and value==0. and not self.peek_until:
                if self.as_pill or self.notice:
                    self.as_pill=False;self.notice=None;w._compact_cache=None;w.reposition()
            if self.capsule:w.sync_rotation()

    def eventFilter(self,w,event):
        if not self.enabled:return False
        kind=event.type()
        if kind in (QEvent.Hide,QEvent.ParentChange):
            self.app_timer.stop();self.over_app=False;self.reset(refresh=False)
        elif kind in (QEvent.Resize,QEvent.Move,QEvent.Show):
            if kind==QEvent.Show:self.watch_application()
            if self.fraction<1.:self.set_fraction(self.fraction)
            # Live compact width may change while peeking. Keep its original deadline.
            if not self.idle.isActive():self.idle.start(650)
        elif kind==QEvent.Enter and self.target==0.:
            if (not self.over_app or self.runtime.click_policy.accepts_input(w)) and self.visible_at_cursor():
                if self.capsule and self.hidden_shape=='light':
                    bar=self.light_rect()
                    self.hovered_strip=QRect(w.mapToGlobal(bar.topLeft()),bar.size())
                self.manual_hover=True;self.idle.stop();self.move_to(1.)
        elif kind==QEvent.MouseMove and self.hovered_strip is not None:
            if not self.hovered_strip.contains(event.globalPos()):
                self.hovered_strip=None;w.resize_edges.sync()
        elif kind==QEvent.Leave:
            if self.hovered_strip is not None:
                self.hovered_strip=None;w.resize_edges.sync()
            self.manual_hover=False
            if not self.peek_until or self.peek_until<=time.monotonic():self.idle.start(650)
        elif kind==QEvent.MouseButtonPress:
            self.peek_until=0.;self.manual_hover=True
        elif kind==QEvent.MouseButtonRelease:self.idle.start(650)
        return False
