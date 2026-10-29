"""Static, click-through corner masks: four tiny surfaces per monitor."""
import ctypes
from ctypes import wintypes
import logging
from PyQt5.QtCore import Qt, QRectF, QObject, QTimer
from PyQt5.QtGui import QPainter, QPainterPath, QColor
from PyQt5.QtWidgets import QWidget, QApplication


class Corner(QWidget):
    def __init__(self, radius, right, bottom):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle('大肥鱼Dock 屏幕圆角')
        self.radius, self.right, self.bottom = radius, right, bottom
        self.resize(radius, radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        square = QPainterPath()
        square.addRect(QRectF(self.rect()))
        circle = QPainterPath()
        r = self.radius
        circle.addEllipse(QRectF(-r if self.right else 0, -r if self.bottom else 0, 2*r, 2*r))
        painter.fillPath(square.subtracted(circle), QColor(0, 0, 0))


class CornerManager(QObject):
    def __init__(self):
        super().__init__()
        self.widgets = []
        self.layout = None
        self.handles = set()
        self.hooks = []
        self.watching = False
        self.raise_timer = QTimer(self)
        self.raise_timer.setSingleShot(True)
        self.raise_timer.setInterval(0)
        self.raise_timer.timeout.connect(self.ensure_topmost)
        self.restacking = False
        self.user = ctypes.windll.user32
        self.user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.user.GetTopWindow.argtypes = [wintypes.HWND]
        self.user.GetTopWindow.restype = wintypes.HWND
        self.user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetWindow.restype = wintypes.HWND
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.BeginDeferWindowPos.argtypes = [ctypes.c_int]
        self.user.BeginDeferWindowPos.restype = wintypes.HANDLE
        self.user.DeferWindowPos.argtypes = [wintypes.HANDLE, wintypes.HWND, wintypes.HWND,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.user.DeferWindowPos.restype = wintypes.HANDLE
        self.user.EndDeferWindowPos.argtypes = [wintypes.HANDLE]
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.event_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD,
                                            wintypes.HWND, wintypes.LONG, wintypes.LONG,
                                            wintypes.DWORD, wintypes.DWORD)
        # Keep the callback alive until every native hook has been unregistered.
        self.event_callback = self.event_type(self.window_event)
        self.user.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
                                            self.event_type, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        self.user.SetWinEventHook.restype = wintypes.HANDLE
        self.user.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        # Also cover QApplication destruction after initialization/test failure,
        # when aboutToQuit may never have been emitted. No Qt calls in this slot.
        self.destroyed.connect(lambda: self.stop_watching())

    def window_event(self, hook, event, hwnd, object_id, child_id, thread, timestamp):
        if not self.watching or not self.widgets or not hwnd or hwnd in self.handles:
            return
        relevant = event == 3  # EVENT_SYSTEM_FOREGROUND, including taskbar activation.
        if not relevant and object_id == 0:
            name = ctypes.create_unicode_buffer(256)
            self.user.GetClassNameW(hwnd, name, len(name))
            relevant = name.value in ('Shell_TrayWnd', 'Shell_SecondaryTrayWnd')
            if event in (0x8002, 0x8004):  # Another topmost surface was shown/reordered.
                relevant = relevant or bool(self.user.GetWindowLongW(hwnd, -20) & 8)
        if relevant and not self.restacking:
            # Repair in the event callback, not 50 ms (several frames) later.
            # One zero-delay pass also covers the rest of an activation burst.
            self.ensure_topmost()
            if not self.raise_timer.isActive():
                self.raise_timer.start()

    def watch_stacking(self):
        # OUTOFCONTEXT callbacks run on this Qt message-loop thread. No injected
        # DLL, focus changes, or idle polling; bursts share one short single shot.
        self.watching = True
        for event in (3, 0x8002, 0x8004, 0x800B):
            handle = self.user.SetWinEventHook(event, event, None, self.event_callback, 0, 0, 0)
            if handle:
                self.hooks.append(handle)
            else:
                logging.warning('Screen-corner window event hook unavailable: %s', event)

    def stop_watching(self):
        self.watching = False
        for hook in self.hooks:
            if not self.user.UnhookWinEvent(hook):
                logging.warning('Unable to release screen-corner window event hook')
        self.hooks.clear()

    def stacking_current(self, handles):
        remaining = set(handles)
        current = self.user.GetTopWindow(None)
        for _ in range(4096):
            if not current:
                return not remaining
            if current in remaining:
                remaining.remove(current)
                if not remaining:
                    return True
            elif self.user.IsWindowVisible(current):
                return False
            current = self.user.GetWindow(current, 2)  # GW_HWNDNEXT
        return False

    def ensure_topmost(self):
        if self.restacking:
            return
        handles = [int(w.winId()) for w in self.widgets if w.isVisible()]
        if not handles or self.stacking_current(handles):
            return
        self.restacking = True
        try:
            # Commit the four corners together; never hide, repaint or activate
            # their windows just because another application gained focus.
            batch = self.user.BeginDeferWindowPos(len(handles))
            if batch:
                for handle in handles:
                    batch = self.user.DeferWindowPos(batch, handle, -1, 0, 0, 0, 0, 0x213)
                    if not batch:
                        break
                if batch and self.user.EndDeferWindowPos(batch):
                    return
            for handle in handles:
                if not self.user.SetWindowPos(handle, -1, 0, 0, 0, 0, 0x213):
                    logging.warning('Unable to restore screen-corner stacking')
        finally:
            self.restacking = False

    def apply(self, enabled, radius):
        layout = (radius, tuple((s.geometry().x(), s.geometry().y(), s.geometry().width(),
                                s.geometry().height()) for s in QApplication.screens())) if enabled and radius > 0 else None
        # Mode/settings refresh must not destroy/recreate unchanged masks.
        if layout == self.layout:
            return
        self.close()
        if not enabled or radius <= 0:
            return
        self.layout = layout
        for screen in QApplication.screens():
            geo = screen.geometry()
            r = min(radius, geo.width()//4, geo.height()//4)
            for right, bottom in [(False, False), (True, False), (False, True), (True, True)]:
                corner = Corner(r, right, bottom)
                corner.move(geo.right()+1-r if right else geo.left(), geo.bottom()+1-r if bottom else geo.top())
                corner.show()
                # Reapply after show: never accept work-area/taskbar avoidance.
                corner.move(geo.right()+1-r if right else geo.left(), geo.bottom()+1-r if bottom else geo.top())
                self.widgets.append(corner)
        self.handles = {int(widget.winId()) for widget in self.widgets}
        self.ensure_topmost()
        self.watch_stacking()

    def close(self):
        self.stop_watching()
        self.raise_timer.stop()
        self.handles.clear()
        self.layout = None
        for widget in self.widgets:
            widget.hide()
            widget.deleteLater()
        self.widgets.clear()
