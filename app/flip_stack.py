"""On-demand card flip; snapshots are released as soon as the transition ends."""
import math
from PyQt5.QtCore import QVariantAnimation,QEasingCurve,Qt,QPoint
from PyQt5.QtGui import QPainter,QPixmap,QRegion
from PyQt5.QtWidgets import QStackedWidget,QWidget,QFrame


class FlipStack(QStackedWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.frames=None;self.progress=0
        self.setObjectName('NoteFlipStack');self.setFrameShape(QFrame.NoFrame);self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAttribute(Qt.WA_NoSystemBackground)
        self.setStyleSheet('QStackedWidget#NoteFlipStack {background:transparent;border:0;}')
        self.animation=QVariantAnimation(self);self.animation.setDuration(240);self.animation.setStartValue(0.0);self.animation.setEndValue(1.0);self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.valueChanged.connect(self.advance);self.animation.finished.connect(self.finish)
    def flip_to(self,index):
        if index==self.currentIndex() and not self.frames:return
        if getattr(self,'frames',None):self.animation.stop();self.finish()
        self.target=index
        def snapshot(page):
            page.resize(self.size());ratio=self.devicePixelRatioF();image=QPixmap(max(1,round(self.width()*ratio)),max(1,round(self.height()*ratio)))
            image.setDevicePixelRatio(ratio);image.fill(Qt.transparent);painter=QPainter(image)
            try:page.render(painter,QPoint(),QRegion(),QWidget.DrawChildren)
            finally:painter.end()
            return image
        front=snapshot(self.currentWidget());back=snapshot(self.widget(index));self.frames=(front,back)
        for i in range(self.count()):self.widget(i).hide()
        self.progress=0;self.animation.start()
    def advance(self,value):self.progress=float(value);self.update()
    def finish(self):
        target=self.target if self.frames else None;self.frames=None
        if target is not None:self.setCurrentIndex(target);self.currentWidget().show()
        self.update()
    def resizeEvent(self,event):
        if getattr(self,'frames',None):self.animation.stop();self.finish()
        super().resizeEvent(event)
    def hideEvent(self,event):
        if getattr(self,'frames',None):self.animation.stop();self.finish()
        super().hideEvent(event)
    def paintEvent(self,event):
        if not self.frames:return super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.SmoothPixmapTransform);painter.translate(self.width()/2,self.height()/2)
        painter.scale(max(.015,abs(math.cos(math.pi*self.progress))),1)
        image=self.frames[0 if self.progress<.5 else 1];painter.drawPixmap(-self.width()//2,-self.height()//2,self.width(),self.height(),image)


class ContentTransition(QWidget):
    """Crisp, integer-pixel slide; never blend two pages or scale their text."""
    def __init__(self,view):
        super().__init__(view);self.frame=None;self.back=None;self.progress=0;self.direction=1;self.hide()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.animation=QVariantAnimation(self);self.animation.setDuration(180)
        self.animation.setStartValue(0.0);self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self.advance);self.animation.finished.connect(self.cancel)
    def capture(self):
        view=self.parentWidget().viewport();ratio=view.devicePixelRatioF()
        image=QPixmap(max(1,round(view.width()*ratio)),max(1,round(view.height()*ratio)))
        image.setDevicePixelRatio(ratio);image.fill(Qt.transparent)
        painter=QPainter(image);view.render(painter,QPoint(),QRegion(),QWidget.DrawChildren);painter.end()
        return image
    def begin(self,frame,direction=1):
        self.cancel()
        if frame is None or frame.isNull():return
        self.back=self.capture();self.frame=frame;self.progress=0;self.direction=1 if direction>=0 else -1
        viewport=self.parentWidget().viewport();self.setGeometry(viewport.geometry())
        viewport.hide();self.show();self.raise_();self.animation.start()
    def advance(self,value):self.progress=float(value);self.update()
    def cancel(self):
        self.animation.stop();self.frame=None;self.back=None;self.hide()
        self.parentWidget().viewport().show()
    def paintEvent(self,event):
        if self.frame is None or self.back is None:return
        painter=QPainter(self);painter.setClipRect(self.rect())
        painter.setRenderHint(QPainter.SmoothPixmapTransform,False)
        distance=round(self.width()*self.progress)*self.direction
        painter.drawPixmap(-distance,0,self.frame)
        painter.drawPixmap(self.direction*self.width()-distance,0,self.back)
