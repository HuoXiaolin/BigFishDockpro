"""Bounded background capture for one visible capsule. No desktop-sized image."""
import ctypes as C
from ctypes import wintypes as W
import sys
import threading
from PyQt5.QtCore import Qt,QObject,QTimer,pyqtSignal
from PyQt5.QtGui import QCursor,QImage
from PyQt5.QtWidgets import QApplication
from background_worker import BackgroundWorker


def native_rect(hwnd):
    user=C.windll.user32;rect=W.RECT();point=W.POINT()
    user.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
    user.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)]
    if not user.GetClientRect(hwnd,C.byref(rect)) or not user.ClientToScreen(hwnd,C.byref(point)):return None
    return point.x,point.y,rect.right,rect.bottom


def behind(hwnd,rect,size):
    # Restoring the previous affinity is essential: this is not a persistent
    # screenshot exclusion or a change to any other application's window.
    if sys.getwindowsversion().build<19041:return None
    from resource_glass_capture import grab_tiny,_blur
    user=C.windll.user32;previous=W.DWORD()
    user.GetWindowDisplayAffinity.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    user.SetWindowDisplayAffinity.argtypes=[W.HWND,W.DWORD]
    if not user.GetWindowDisplayAffinity(hwnd,C.byref(previous)):return None
    if not user.SetWindowDisplayAffinity(hwnd,0x11):return None
    try:img=grab_tiny(*rect,*size)
    finally:user.SetWindowDisplayAffinity(hwnd,previous.value)
    return _blur(_blur(img.convertToFormat(QImage.Format_ARGB32_Premultiplied))) if img is not None else None


class GlassJob(BackgroundWorker):
    ready=pyqtSignal(object)
    def __init__(self,hwnd):
        super().__init__();self.hwnd=hwnd;self.want=None;self.lock=threading.Lock();self.signature=None
    def request(self,rect,size,logical):
        with self.lock:self.want=(rect,size,logical) if rect else None
    def run(self):
        while not self.cancelled.is_set():
            with self.lock:want=self.want
            if want:
                rect,size,logical=want
                try:img=behind(self.hwnd,rect,size)
                except (OSError,ValueError,RuntimeError):img=None
                if img is not None:
                    small=img.scaled(8,4,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                    bits=small.constBits();bits.setsize(small.byteCount());signature=(bytes(bits),logical)
                    if signature!=self.signature and not self.cancelled.is_set():
                        self.signature=signature;self.ready.emit((logical,img))
            self.cancelled.wait(.25)


class LiveGlass(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.job=None;self.revision=0;self.image=None;self.closed=False
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.request)
    def sync(self,enabled):
        if self.closed:return
        if not enabled:
            self.timer.stop();self.image=None;self.revision+=1
            if self.job:self.job.requestInterruption();self.job.deleteLater();self.job=None
            return
        if self.window.service.runtime.dock.preview:return
        if self.job is None:
            self.job=GlassJob(int(self.window.winId()));self.job.ready.connect(self.receive,Qt.QueuedConnection)
            self.request();self.job.start();self.timer.start()
    def request(self):
        w=self.window
        if not w.isVisible():self.sync(False);return
        if not self.job:return
        if w.geometry().contains(QCursor.pos()) or QApplication.activePopupWidget():
            # Affinity is changed briefly during capture. Keep the last image
            # while the capsule or one of its menus is receiving input.
            self.job.request(None,None,None)
            return
        rect=native_rect(int(w.winId()))
        if not rect or min(rect[2:])<=0:return
        size=(max(2,min(160,w.width()//10)),max(2,min(100,w.height()//10)))
        self.job.request(rect,size,w.geometry().getRect())
    def receive(self,value):
        if self.closed or self.sender() is not self.job:return
        rect,img=value
        if rect!=self.window.geometry().getRect():return
        self.image=img;self.revision+=1;self.window.update()
    def close(self):self.sync(False);self.closed=True
