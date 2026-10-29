"""Corner activation regression on the private Windows test desktop."""
import ctypes
from ctypes import wintypes
from unittest.mock import patch
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from screen_corners import CornerManager


def run(app, output, checks):
    manager = CornerManager()
    cover = QWidget(None, Qt.Tool | Qt.FramelessWindowHint |
                    Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
    cover.setAttribute(Qt.WA_ShowWithoutActivating)
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = wintypes.HWND
    focus = user.GetForegroundWindow()
    try:
        manager.apply(True, 28)
        app.processEvents()
        masks = tuple(manager.widgets)
        handles = [int(w.winId()) for w in masks]
        assert len(handles) == 4*len(app.screens())
        assert manager.raise_timer.interval() == 0
        geo = app.primaryScreen().geometry()
        cover.setGeometry(geo.left(), geo.top(), geo.width(), geo.height())
        cover.show()
        # Make the ordering fault deterministic, then exercise the callback
        # directly: restoration must be done before it returns, without a wait.
        manager.stop_watching()
        for _ in range(12):
            manager.watching = False
            user.SetWindowPos(int(cover.winId()), -1, 0, 0, 0, 0, 0x213)
            assert not manager.stacking_current(handles)
            manager.watching = True
            manager.window_event(None, 3, int(cover.winId()), 0, 0, 0, 0)
            assert manager.stacking_current(handles), 'Repair waited for a later frame'
            assert tuple(manager.widgets) == masks and all(w.isVisible() for w in masks)
        manager.raise_timer.stop()
        with patch.object(manager.user, 'BeginDeferWindowPos', wraps=user.BeginDeferWindowPos) as begin:
            for _ in range(12):
                manager.ensure_topmost()
            assert not begin.called, 'Stable layers must not be restacked'
        assert user.GetForegroundWindow() == focus, 'Corners changed foreground focus'
        manager.watching = False
        manager.watch_stacking()
        user.SetWindowPos(int(cover.winId()), -1, 0, 0, 0, 0, 0x213)
        user.NotifyWinEvent(3, int(cover.winId()), 0, 0)
        app.processEvents()
        app.processEvents()
        assert manager.stacking_current(handles), 'Native activation hook did not restore corners'
        manager.widgets[0].grab().save(str(output/'corner-switch-mask.png'))
        manager.apply(True,28)
        assert tuple(manager.widgets) == masks
        manager.apply(False,28)
        assert not manager.widgets and not manager.hooks and not manager.raise_timer.isActive()
        checks.append('corners: 12 immediate foreground repairs without a timer wait, stable HWNDs/visibility, native hook repair, redundant restack skipped, no focus change, disable cleanup')
    finally:
        manager.close()
        cover.close()
        cover.deleteLater()
