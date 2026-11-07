"""Small, finite liquid interactions for the existing resource window."""
import math
import time
from PyQt5.QtCore import Qt,QPoint,QPointF,QRect,QRectF,QTimer,QPropertyAnimation,QEasingCurve
from PyQt5.QtGui import QColor,QPainter,QPen,QPainterPath,QCursor
from PyQt5.QtWidgets import QWidget,QApplication
from screen_layout import capture,screen_records
from resource_liquid_shape import body_path,edge_corners,neck_path,drip_path

from widget_face import FaceTracker

EDGES=('top','bottom','left','right')


def attached(rect,area,edge):
    rect=QRect(rect)
    rect.moveLeft(max(area.left(),min(rect.x(),area.right()-rect.width()+1)))
    rect.moveTop(max(area.top(),min(rect.y(),area.bottom()-rect.height()+1)))
    if edge=='top':rect.moveTop(area.top())
    elif edge=='bottom':rect.moveBottom(area.bottom())
    elif edge=='left':rect.moveLeft(area.left())
    elif edge=='right':rect.moveRight(area.right())
    return rect


def nearest(rect,area):
    distances=(abs(rect.top()-area.top()),abs(rect.bottom()-area.bottom()),
               abs(rect.left()-area.left()),abs(rect.right()-area.right()))
    return EDGES[min(range(4),key=distances.__getitem__)]


class LiquidBridge(QWidget):
    """A transient, click-through bridge, limited to its path's small bounds."""
    def __init__(self,owner):
        super().__init__(owner,Qt.Tool|Qt.FramelessWindowHint|Qt.NoDropShadowWindowHint|Qt.WindowTransparentForInput|Qt.WindowDoesNotAcceptFocus)
        self.owner=owner;self.path=QPainterPath();self.fade=0.;self.drip=None
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.tick)
    def draw(self,path):
        self.path=path
        if path.isEmpty():self.hide();return
        bounds=path.boundingRect().adjusted(-3,-3,3,3).toAlignedRect()
        self.setGeometry(bounds);self.show();self.update()
    def break_off(self,edge,line,center):
        self.drip=(edge,line,center);self.fade=time.monotonic();self.timer.start();self.tick()
    def tick(self):
        elapsed=time.monotonic()-self.fade
        if elapsed>=.32:self.stop();return
        self.draw(drip_path(*self.drip,10*(1-elapsed/.32)**2))
    def stop(self):
        self.timer.stop();self.drip=None;self.path=QPainterPath();self.hide()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.translate(-self.x(),-self.y())
        c=self.owner.colors;color=QColor(c.get('surface','#e7f2f5'))
        accent=self.owner.background.get('color')
        if accent:
            from flash_view import blend
            color=blend(QColor(accent),color,.78)
        color.setAlpha(215)
        border=QColor(c.get('ink','#405765'));border.setAlpha(45)
        p.setPen(QPen(border,.8));p.setBrush(color);p.drawPath(self.path)


class CapsuleMotion(FaceTracker):
    def __init__(self,window):
        super().__init__(window,lambda:window.service.cfg,lambda:window.service.runtime.lite,'resource')
        self.bridge=None;self.live=None;self.drag_edge='free';self.broken=False;self.landing=False
        self.snap=QPropertyAnimation(window,b'pos',window);self.snap.setDuration(240);self.snap.setEasingCurve(QEasingCurve.OutCubic)
        self.snap.finished.connect(self.landed)
        self.presentation=None
    @property
    def enabled(self):
        w=self.window;return w.service.cfg.get('motion_enabled',True) and not w.service.runtime.lite
    def prepare(self):
        w=self.window;cfg=w.service.cfg
        presentation=(w.service.compact,cfg['resource_fold'],cfg['resource_compact_width'],cfg['resource_compact_height'],
                      cfg['resource_expanded_width'],cfg['resource_expanded_height'],cfg['resource_edge_snap'])
        if self.presentation!=presentation:
            self.snap.stop();self.landing=False;self.presentation=presentation
    def sync(self):
        w=self.window;cfg=w.service.cfg
        if not self.enabled:
            landing=self.landing;self.snap.stop();self.landing=False;self.stop_bridge()
            if landing:w.reposition()
        self.sync_face()
        use_live=w.isVisible() and cfg['resource_live_glass'] and not w.service.runtime.lite and w.background['material'] not in ('clear','solid')
        if use_live and self.live is None:
            from resource_live_glass import LiveGlass
            self.live=LiveGlass(w)
        if self.live:self.live.sync(use_live)
    def radii(self,radius):
        w=self.window;cfg=w.service.cfg;edge=cfg['resource_edge']
        if not cfg['resource_liquid'] or not cfg['resource_edge_snap'] or not cfg['card_snap'] or edge=='free':return (radius,)*4
        area=(QApplication.screenAt(w.geometry().center()) or QApplication.primaryScreen()).availableGeometry()
        rect=w.geometry();gap={'top':rect.top()-area.top(),'bottom':area.bottom()-rect.bottom(),
                              'left':rect.left()-area.left(),'right':area.right()-rect.right()}[edge]
        corner=max(3,min(radius,3+max(0,gap)*.55))
        return tuple(corner if at_edge else radius for at_edge in edge_corners(edge))
    def shape(self,rect,radius):return body_path(rect,self.radii(radius))
    def begin(self):
        self.snap.stop();self.landing=False;self.down=True;self.pulse(.5)
        cfg = self.window.service.cfg
        self.drag_edge = cfg['resource_edge'] if cfg['resource_edge_snap'] and cfg['card_snap'] else 'free'
        self.broken=False
        self.drag_rect=QRect(self.window.geometry())
        self.drag_area=(QApplication.screenAt(self.drag_rect.center()) or QApplication.primaryScreen()).availableGeometry()
        self.stop_bridge()
    def moved(self):
        w=self.window;edge=self.drag_edge
        if edge not in EDGES or not w.service.cfg['resource_liquid'] or not self.enabled or self.broken:return
        rect=w.geometry();area=self.drag_area;horizontal=edge in ('top','bottom')
        line={'top':area.top(),'bottom':area.bottom()+1,'left':area.left(),'right':area.right()+1}[edge]
        gap={'top':rect.top()-line,'bottom':line-rect.bottom()-1,'left':rect.left()-line,'right':line-rect.right()-1}[edge]
        center=rect.center().x() if horizontal else rect.center().y()
        original=self.drag_rect.center().x() if horizontal else self.drag_rect.center().y()
        if self.bridge is None:self.bridge=LiquidBridge(w)
        if gap>85 or abs(center-original)>100 or gap<-15:
            self.broken=True;self.bridge.break_off(edge,line,original);return
        length=min(120,rect.width() if horizontal else rect.height())
        self.bridge.draw(neck_path(edge,line,center,length,max(0,gap),max(0,gap)/85,1,12,10))
        self.pulse(.25)
    def released(self):
        self.down=False;self.pulse(.6);self.stop_bridge()
    def drop(self,point):
        w=self.window;cfg=w.service.cfg
        if not cfg['resource_edge_snap']:return False
        from card_snap import resolve
        match = resolve(w, w.service.runtime, point)
        if match is None:
            return False
        target, edge = match
        start=w.pos();self.landing=True
        ok=w.service.set_options(resource_edge=edge,resource_layout=capture(list(target.getRect()),screen_records()))
        if not ok:self.landing=False;w.reposition();return True
        if self.enabled and start!=target.topLeft():
            self.snap.setStartValue(start);self.snap.setEndValue(target.topLeft());self.snap.start()
        else:self.landed()
        return True
    def landed(self):
        self.landing=False;self.window.reposition();self.window.update()
    def stop_bridge(self):
        if self.bridge:self.bridge.stop()
    def hide(self):
        self.hide_face();self.snap.stop();self.landing=False;self.stop_bridge()
        if self.live:self.live.sync(False)
    def close(self):
        self.hide()
        if self.live:self.live.close();self.live=None
        if self.bridge:self.bridge.deleteLater();self.bridge=None
