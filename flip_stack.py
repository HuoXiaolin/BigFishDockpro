"""On-demand card flip; snapshots are released as soon as the transition ends."""
import math
from PyQt5.QtCore import QVariantAnimation,QEasingCurve,Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QStackedWidget


class FlipStack(QStackedWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.frames=None;self.progress=0
        self.animation=QVariantAnimation(self);self.animation.setDuration(240);self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.advance);self.animation.finished.connect(self.finish)
    def flip_to(self,index):
        if index==self.currentIndex() and not self.frames:return
        if self.frames:self.animation.stop();self.finish()
        self.target=index;front=self.currentWidget().grab();other=self.widget(index);other.resize(self.size());back=other.grab()
        self.frames=(front,back);self.currentWidget().hide();self.progress=0;self.animation.start()
    def advance(self,value):self.progress=float(value);self.update()
    def finish(self):
        if self.frames:self.setCurrentIndex(self.target);self.currentWidget().show()
        self.frames=None;self.update()
    def paintEvent(self,event):
        if not self.frames:return super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.SmoothPixmapTransform);painter.translate(self.width()/2,self.height()/2)
        painter.scale(max(.015,abs(math.cos(math.pi*self.progress))),1)
        image=self.frames[0 if self.progress<.5 else 1];painter.drawPixmap(-self.width()//2,-self.height()//2,self.width(),self.height(),image)
