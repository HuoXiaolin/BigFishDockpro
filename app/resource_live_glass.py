"""Sample a narrow strip beside the capsule for the live glass tint."""
import ctypes as C
from ctypes import wintypes as W
import threading
from PyQt5.QtCore import Qt,QObject,QRect,QTimer,pyqtSignal
from PyQt5.QtGui import QCursor,QImage
from PyQt5.QtWidgets import QApplication
from background_worker import BackgroundWorker


def adjacent_strip(rect, display):
    if rect.intersected(display).isEmpty():
        return None
    thickness, gap = 16, 2
    horizontal = (
        QRect(rect.x(), rect.y() - thickness - gap, rect.width(), thickness),
        QRect(rect.x(), rect.bottom() + 1 + gap, rect.width(), thickness),
    )
    vertical = (
        QRect(rect.x() - thickness - gap, rect.y(), thickness, rect.height()),
        QRect(rect.right() + 1 + gap, rect.y(), thickness, rect.height()),
    )
    candidates = (*horizontal, *vertical) if rect.width() >= rect.height() else (*vertical, *horizontal)
    for candidate in candidates:
        region = candidate.intersected(display)
        if min(region.width(), region.height()) >= 4:
            return region
    return None


def native_strip(hwnd):
    from resource_taskbar import MonitorInfo
    from window_layers import native
    user = native()
    user.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
    user.MonitorFromWindow.restype = W.HANDLE
    user.GetMonitorInfoW.argtypes = [W.HANDLE, C.c_void_p]
    rect = W.RECT()
    info = MonitorInfo()
    info.size = C.sizeof(info)
    if not user.GetWindowRect(hwnd, C.byref(rect)) or not user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), C.byref(info)):
        return None
    display = info.monitor
    return adjacent_strip(QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top),
                          QRect(display.left, display.top, display.right - display.left, display.bottom - display.top))


def capture_strip(rect, size):
    from resource_glass_capture import grab_tiny,_blur
    img=grab_tiny(*rect,*size)
    return _blur(_blur(img.convertToFormat(QImage.Format_ARGB32_Premultiplied))) if img is not None else None


class GlassJob(BackgroundWorker):
    ready=pyqtSignal(object)
    def __init__(self):
        super().__init__();self.want=None;self.lock=threading.Lock();self.signature=None
    def request(self,rect,size,logical):
        with self.lock:self.want=(rect,size,logical) if rect else None
    def run(self):
        while not self.cancelled.is_set():
            with self.lock:want=self.want
            if want:
                rect,size,logical=want
                try:img=capture_strip(rect,size)
                except (OSError,ValueError,RuntimeError):img=None
                pixels=None
                if img is not None:
                    small=img.scaled(8,4,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
                    bits=small.constBits();bits.setsize(small.byteCount());pixels=bytes(bits)
                signature=(pixels,logical)
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
            self.timer.stop()
            if self.image is not None:
                self.image=None;self.revision+=1
            if self.job:self.job.requestInterruption();self.job.deleteLater();self.job=None
            return
        if self.window.service.runtime.dock.preview:return
        if self.job is None:
            self.job=GlassJob();self.job.ready.connect(self.receive,Qt.QueuedConnection)
            self.request();self.job.start();self.timer.start()
    def request(self):
        w=self.window
        if not w.isVisible():self.sync(False);return
        if not self.job:return
        if w.press is not None or w.liquid.landing or w.geometry().contains(QCursor.pos()) or QApplication.activePopupWidget():
            self.job.request(None,None,None)
            return
        region=native_strip(int(w.winId()))
        if region is None:
            self.job.request(None,None,None)
            if self.image is not None:
                self.image=None;self.revision+=1;w.update()
            return
        width, height = max(2,min(160,w.width()//10)), max(2,min(100,w.height()//10))
        size = (width,min(6,height)) if region.width()>=region.height() else (min(6,width),height)
        self.job.request(region.getRect(),size,w.geometry().getRect())
    def receive(self,value):
        if self.closed or self.sender() is not self.job:return
        rect,img=value
        if rect!=self.window.geometry().getRect() or img is None and self.image is None:return
        self.image=img;self.revision+=1;self.window.update()
    def close(self):self.sync(False);self.closed=True
