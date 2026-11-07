"""Shared, bounded face animation for resource and desktop collection cards."""
import time
from PyQt5.QtCore import QPointF,QRectF,QTimer
from PyQt5.QtGui import QCursor


class FaceTracker:
    def __init__(self,window,config,lite,prefix):
        self.window=window;self.config=config;self.lite=lite;self.prefix=prefix
        self.face=None;self.face_until=0.;self.cursor=None;self.was_near=False
        self.last_tired=False;self.down=False;self.face_bounds=None
        self.watch=QTimer(window);self.watch.setInterval(250);self.watch.timeout.connect(self.watch_face)
        self.frames=QTimer(window);self.frames.setInterval(33);self.frames.timeout.connect(self.face_frame)

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
        self.face.forced_mood=None if self.option('face_mood')=='random' else self.option('face_mood')
        if self.interactive:self.watch.start();self.pulse(.5)
        else:self.hide_face()

    def pulse(self,seconds=.6):
        if not self.interactive:return
        self.face_until=max(self.face_until,time.monotonic()+seconds)
        if self.face and self.window.isVisible():self.frames.start()

    def press(self,down):
        self.down=down;self.pulse(.5)

    def watch_face(self):
        w=self.window
        if not w.isVisible() or not self.interactive or self.face is None:self.hide_face();return
        pos=QCursor.pos();near=w.geometry().adjusted(-50,-40,50,40).contains(pos)
        now=time.monotonic();tired=now-self.face.last_attention>60
        idle=not self.lite() and (self.face.blink_at<=now or tired!=self.last_tired)
        if near!=self.was_near or (near and pos!=self.cursor) or idle:self.pulse(.45)
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
        scale=min(.72*self.option('face_scale')/100,(w.height()-10)/28,max(.3,(slot-4)/46))
        self.face.paint(p,center.x(),center.y(),scale,1.,look,self.was_near if active else False,colors or w.colors,animate=active)

    def hide_face(self):
        self.watch.stop();self.frames.stop();self.down=False
