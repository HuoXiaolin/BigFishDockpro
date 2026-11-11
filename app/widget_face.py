"""Shared, bounded face animation for resource and desktop collection cards."""
import time
from PyQt5.QtCore import QPointF,QRectF,QTimer,Qt
from PyQt5.QtGui import QCursor


IDLE_POLL=120
ACTIVE_POLL=42


class FaceTracker:
    def __init__(self,window,config,prefix,roles):
        self.window=window;self.config=config;self.prefix=prefix
        self.roles=roles
        self.face=None;self.face_until=0.;self.cursor=None;self.was_near=False
        self.last_tired=False;self.down=False;self.face_bounds=None
        self.watch=QTimer(window);self.watch.setInterval(IDLE_POLL);self.watch.timeout.connect(self.watch_face)
        self.frames=QTimer(window);self.frames.setInterval(33);self.frames.timeout.connect(self.face_frame)
        self.rotation = None
        self.face_preference = None

    def option(self,key):return self.config()[self.prefix+'_'+key]

    @property
    def interactive(self):
        return self.config().get('motion_enabled',True) and self.option('face') and self.option('face_interactive')

    def sync_face(self):
        if not self.window.isVisible() or not self.option('face'):
            self.hide_face();return
        if self.face is None:
            from resource_face import PetFace
            self.face=PetFace()
        old_mood=self.face.forced_mood
        mood = self.option('face_mood')
        auto_switch = self.option('face_auto_switch')
        if self.face_preference != (mood, auto_switch):
            self.face.forced_mood = None if mood == 'random' else mood
            self.face_preference = mood, auto_switch
        self.sync_rotation(auto_switch)
        if not self.interactive:self.stop_interaction()
        elif not self.watch.isActive():
            self.watch_face()
            self.watch.start()
            self.pulse(.5)
        elif self.face.forced_mood!=old_mood:self.pulse(.5)

    def sync_rotation(self, enabled):
        if not enabled:
            if self.rotation is not None:
                self.rotation.stop()
            return
        if self.rotation is None:
            self.rotation = QTimer(self.window)
            self.rotation.setTimerType(Qt.VeryCoarseTimer)
            self.rotation.timeout.connect(self.rotate_face)
        interval = self.option('face_switch_minutes') * 60_000
        if not self.rotation.isActive() or self.rotation.interval() != interval:
            self.rotation.start(interval)

    def rotate_face(self):
        self.face.change_mood()
        if self.face_bounds is not None:
            self.window.update(self.face_bounds)
        self.pulse(.5)

    def pulse(self,seconds=.6):
        if not self.interactive:return
        self.face_until=max(self.face_until,time.monotonic()+seconds)
        if self.face and self.window.isVisible() and not self.frames.isActive():self.frames.start()

    def press(self,down):
        self.down=down;self.pulse(.5)

    def watch_face(self):
        w=self.window
        if not w.isVisible() or not self.option('face'):
            self.hide_face()
            return
        if not self.interactive or self.face is None:
            self.stop_interaction()
            return
        pos=QCursor.pos();near=w.geometry().adjusted(-50,-40,50,40).contains(pos)
        now=time.monotonic()
        moved=self.cursor is not None and pos!=self.cursor
        if moved:self.face.last_attention=now
        tired=now-self.face.last_attention>60
        idle=self.face.blink_at<=now or tired!=self.last_tired
        if near!=self.was_near or moved or idle:self.pulse(.45)
        interval=ACTIVE_POLL if moved else IDLE_POLL
        if self.watch.interval()!=interval:self.watch.setInterval(interval)
        self.cursor=pos;self.was_near=near;self.last_tired=tired

    def face_frame(self):
        if time.monotonic()>self.face_until or not self.window.isVisible() or not self.interactive:
            self.frames.stop();return
        if self.face_bounds is not None:self.window.update(self.face_bounds)

    def paint_face(self,p,center,slot=40,colors=None):
        if self.face is None or not self.option('face'):return
        w=self.window;center=QPointF(center);cursor=w.mapFromGlobal(QCursor.pos());look=QPointF(cursor)-center
        active=self.interactive
        self.face_bounds=QRectF(center.x()-slot/2-3,center.y()-20,slot+6,40).toAlignedRect().intersected(w.rect())
        self.face.spread=6 if self.down and active else 0;self.face.tilt=14 if self.down and active else 0
        colors=colors or w.colors
        role_id=self.option('face_role')
        if role_id and (role:=self.roles().get(role_id)):
            available_height=2*min(center.y()-1,w.height()-center.y()-1)
            size=min(slot-3,26*self.option('face_scale')/100,available_height)
            if size>=6:
                self.paint_role(p,role,center,size,look,colors,active)
                return
        scale=min(.72*self.option('face_scale')/100,(w.height()-10)/28,max(.3,(slot-4)/46))
        self.face.paint(p,center.x(),center.y(),scale,1.,look,self.was_near if active else False,colors,animate=active)

    def paint_role(self,p,role,center,size,look,colors,active):
        rect=QRectF(center.x()-size/2,center.y()-size/2,size,size)
        anchors=tuple((rect.x()+size*x/100,rect.y()+size*y/100) for x,y in role.anchors)
        pixels=min(144,max(1,round(size*p.device().devicePixelRatioF())))
        if role.ink:
            colors=dict(colors,ink=role.ink)
        p.save()
        try:
            p.setClipRect(rect,Qt.IntersectClip)
            self.draw_layer(p,rect,pixels,role.digest+':back',role.back)
            self.face.paint(p,center.x(),center.y(),size/76,1.,look,self.was_near if active else False,
                            colors,animate=active,anchors=anchors)
            if role.front:
                self.draw_layer(p,rect,pixels,role.digest+':front',role.front)
        finally:
            p.restore()

    @staticmethod
    def draw_layer(p,rect,pixels,layer,svg):
        from PyQt5.QtCore import QByteArray
        from PyQt5.QtGui import QPainter,QPixmap,QPixmapCache
        key=f'face-role:{layer}:{pixels}'
        pixmap=QPixmapCache.find(key)
        if pixmap is None or pixmap.isNull():
            from PyQt5.QtSvg import QSvgRenderer
            renderer=QSvgRenderer(QByteArray(svg.encode('utf-8')))
            pixmap=QPixmap(pixels,pixels)
            pixmap.fill(Qt.transparent)
            painter=QPainter(pixmap)
            renderer.render(painter,QRectF(pixmap.rect()))
            painter.end()
            QPixmapCache.insert(key,pixmap)
        p.drawPixmap(rect,pixmap,QRectF(pixmap.rect()))

    def stop_interaction(self):
        self.watch.stop();self.frames.stop();self.down=False;self.cursor=None;self.was_near=False

    def hide_face(self):
        self.stop_interaction()
        if self.rotation is not None:
            self.rotation.stop()
