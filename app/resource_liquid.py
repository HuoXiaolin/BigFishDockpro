"""Small, finite liquid interactions for the existing resource window."""
import time
from PyQt5.QtCore import Qt,QRect,QRectF,QTimer,QPropertyAnimation,QEasingCurve
from PyQt5.QtGui import QColor,QBrush,QLinearGradient,QPainter,QPainterPath,QPen
from PyQt5.QtWidgets import QWidget,QApplication
from card_snap import edge_gaps,resolve,touching_edge
from screen_layout import capture,screen_records
from resource_liquid_shape import body_path,edge_corners,neck_path,drip_path
from capsule_glass import CapsuleGlass
from card_design import blend
from window_backdrop import component_backdrop

from widget_face import FaceTracker

def attached(rect,area,edge):
    rect=QRect(rect)
    rect.moveLeft(max(area.left(),min(rect.x(),area.right()-rect.width()+1)))
    rect.moveTop(max(area.top(),min(rect.y(),area.bottom()-rect.height()+1)))
    if edge=='top':rect.moveTop(area.top())
    elif edge=='bottom':rect.moveBottom(area.bottom())
    elif edge=='left':rect.moveLeft(area.left())
    elif edge=='right':rect.moveRight(area.right())
    return rect


class LiquidBridge(QWidget):
    """A transient, click-through bridge, limited to its path's small bounds."""
    def __init__(self,owner):
        super().__init__(owner,Qt.Tool|Qt.FramelessWindowHint|Qt.NoDropShadowWindowHint|Qt.WindowTransparentForInput|Qt.WindowDoesNotAcceptFocus)
        self.owner=owner;self.path=QPainterPath();self.fade=0.;self.drip=None
        self.glass=CapsuleGlass()
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self.tick)
    def draw(self,path,edge,tension):
        self.path=path
        if path.isEmpty():self.hide();return
        self.edge=edge;self.tension=tension
        bounds=path.boundingRect().adjusted(-3,-3,3,3).toAlignedRect()
        self.setGeometry(bounds);self.show();self.update()
    def break_off(self,edge,line,center):
        self.drip=(edge,line,center);self.fade=time.monotonic();self.timer.start();self.tick()
    def tick(self):
        elapsed=time.monotonic()-self.fade
        if elapsed>=.32:self.stop();return
        remaining=1-elapsed/.32
        self.draw(drip_path(*self.drip,10*remaining**2),self.drip[0],remaining)
    def stop(self):
        self.timer.stop();self.drip=None;self.path=QPainterPath();self.glass.clear();self.hide()
    def paintEvent(self,event):
        if self.path.isEmpty():return
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        origin=self.mapToGlobal(self.rect().topLeft())
        path=self.path.translated(-origin.x(),-origin.y())
        if self.drip is None:
            # The neck enters the body to keep its silhouette continuous.
            # Stop both material layers at the join so it has no end cap.
            _,inset,corners=self.owner.glass_shape()
            inset+=.8
            body=QRectF(self.owner.frameGeometry().translated(-origin)).adjusted(inset,inset,-inset,-inset)
            exposed=QPainterPath();exposed.addRect(QRectF(self.rect()))
            p.setClipPath(exposed.subtracted(body_path(body,corners)))
        style=self.owner.background
        self.glass.paint(p,self,self.owner.service.runtime.dock,0,appearance=style,
                         backdrop_mode=component_backdrop(self.owner.service.cfg,'resource'),
                         outline=path)
        self.paint_refraction(p,path,style)

    def paint_refraction(self,p,path,style):
        bounds=path.boundingRect()
        across=bounds.topRight() if self.edge in ('top','bottom') else bounds.bottomLeft()
        tint=QColor(style['color'] or '#82b9ca')
        pearl=blend(tint,QColor('#edfdff'),.82)
        shade=blend(tint,QColor('#132d48'),.74)
        water=blend(tint,QColor('#63b7ca'),.34)
        # Reflections follow the normal across the stretched surface. Even
        # clear glass has a narrow light and dark rim around its empty centre.
        strength=(.65+.35*self.tension)*(.82+.18*style['opacity']/100)
        shine=.73+.27*min(1,style['highlight']/65)
        if style['material'] in ('paper','paper_glass','solid','mica','obsidian','celadon','velvet'):
            shine*=.82
        def tone(color,alpha):
            result=QColor(color)
            result.setAlpha(round(alpha*strength))
            return result
        p.save()
        p.setClipPath(path,Qt.IntersectClip)
        if style['material']!='clear':
            wash=QLinearGradient(bounds.topLeft(),across)
            wash.setColorAt(0,tone(pearl,70*shine))
            wash.setColorAt(.26,tone(water,46))
            wash.setColorAt(.54,tone(water,0))
            wash.setColorAt(1,tone(shade,68))
            p.fillPath(path,QBrush(wash))
        rim=QLinearGradient(bounds.topLeft(),across)
        rim.setColorAt(0,tone(pearl,255*shine))
        rim.setColorAt(.38,tone(pearl,245*shine))
        rim.setColorAt(.62,tone(shade,218))
        rim.setColorAt(1,tone(shade,245))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QBrush(rim),3.2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        p.drawPath(path)
        p.restore()


class CapsuleMotion(FaceTracker):
    def __init__(self,window):
        super().__init__(window,lambda:window.service.cfg,'resource',lambda:window.service.runtime.face_roles)
        self.bridge=None;self.drag_edge='free';self.broken=False;self.landing=False
        self.snap=QPropertyAnimation(window,b'pos',window);self.snap.setDuration(240);self.snap.setEasingCurve(QEasingCurve.OutCubic)
        self.snap.finished.connect(self.landed)
        self.presentation=None
    @property
    def enabled(self):
        return self.config().get('motion_enabled',True)
    @property
    def edge_snap(self):
        cfg = self.config()
        return cfg['card_snap'] and cfg['resource_edge_snap'] and self.window.taskbar_slot() is None
    @property
    def can_stretch(self):
        cfg = self.config()
        return self.edge_snap and cfg['resource_liquid'] and cfg.get('motion_enabled',True)
    def prepare(self):
        w=self.window;cfg=w.service.cfg
        presentation=(w.service.compact,cfg['resource_fold'],cfg['resource_compact_width'],cfg['resource_compact_height'],
                      cfg['resource_expanded_width'],cfg['resource_expanded_height'],cfg['card_snap'],
                      cfg['resource_edge_snap'],cfg['resource_peer_snap'],cfg['resource_geometry_locked'])
        if self.presentation!=presentation:
            self.snap.stop();self.landing=False;self.presentation=presentation
            self.drag_edge='free';self.stop_bridge()
    def sync(self):
        w=self.window
        if not self.enabled:
            landing=self.landing;self.snap.stop();self.landing=False
            if landing:w.reposition()
        if not self.can_stretch:
            self.drag_edge='free';self.stop_bridge()
        elif self.bridge and self.bridge.isVisible():
            self.bridge.update()
        self.sync_face()
    def radii(self,radius):
        w=self.window;cfg=w.service.cfg
        edge=self.drag_edge if self.drag_edge!='free' else cfg['resource_edge']
        if not cfg['resource_liquid'] or not self.edge_snap or edge=='free':return (radius,)*4
        rect=w.geometry()
        screen=QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
        area=self.drag_area if self.drag_edge!='free' else screen.availableGeometry()
        gap=edge_gaps(rect,area)[edge]
        corner=max(3,min(radius,3+max(0,gap)*.55))
        return tuple(corner if at_edge else radius for at_edge in edge_corners(edge))
    def shape(self,rect,radius):return body_path(rect,self.radii(radius))
    def begin(self):
        was_landing = self.landing
        self.snap.stop();self.landing=False;self.press(True)
        self.broken=False;self.drag_edge='free'
        self.stop_bridge()
        if not self.can_stretch:return
        cfg = self.config()
        self.drag_rect = QRect(self.window.geometry())
        screen = QApplication.screenAt(self.drag_rect.center()) or QApplication.primaryScreen()
        if screen is None:return
        self.drag_area = screen.availableGeometry()
        tolerance = cfg['card_snap_distance'] if was_landing else 2
        self.drag_edge = touching_edge(self.drag_rect, self.drag_area, cfg['resource_edge'], tolerance=tolerance)
    def moved(self):
        w=self.window;edge=self.drag_edge
        if edge=='free' or self.broken or not self.can_stretch:return
        rect=w.geometry();area=self.drag_area;horizontal=edge in ('top','bottom')
        gap=edge_gaps(rect,area)[edge]
        if gap<=0:
            self.drag_rect=rect;self.stop_bridge();return
        line={'top':area.top(),'bottom':area.bottom()+1,'left':area.left(),'right':area.right()+1}[edge]
        center=rect.center().x() if horizontal else rect.center().y()
        original=self.drag_rect.center().x() if horizontal else self.drag_rect.center().y()
        if self.bridge is None:self.bridge=LiquidBridge(w)
        if gap>85 or abs(center-original)>100:
            self.broken=True;self.bridge.break_off(edge,line,original);return
        length=min(120,rect.width() if horizontal else rect.height())
        tension=gap/85
        self.bridge.draw(neck_path(edge,line,center,length,gap,tension,1,12,10),edge,tension)
        self.pulse(.25)
    def released(self):
        self.down=False;self.pulse(.6);self.drag_edge='free'
        if not self.broken:self.stop_bridge()
    def drop(self,point):
        w=self.window;cfg=w.service.cfg
        match = resolve(w, w.service.runtime, point, snap_edges=self.edge_snap, snap_peers=cfg['resource_peer_snap'])
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
        self.hide_face();self.snap.stop();self.landing=False;self.drag_edge='free';self.stop_bridge()
    def close(self):
        self.hide()
        if self.bridge:self.bridge.deleteLater();self.bridge=None
