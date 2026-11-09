"""Reclaim unused caches when idle; never page live objects out of the process."""
import ctypes as C
import time
from ctypes import wintypes as W
from PyQt5.QtCore import QTimer,Qt
from PyQt5.QtGui import QCursor,QPixmapCache
from PyQt5.QtWidgets import QApplication


class MemoryCounters(C.Structure):
    _fields_=[('cb',W.DWORD),('faults',W.DWORD)]+[(name,C.c_size_t) for name in
        ('peak_ws','working_set','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private','private_ws','shared_commit')]


def private_resident():
    kernel=C.windll.kernel32;kernel.GetCurrentProcess.restype=W.HANDLE
    get=C.windll.psapi.GetProcessMemoryInfo;get.argtypes=[W.HANDLE,C.c_void_p,W.DWORD];get.restype=W.BOOL
    value=MemoryCounters();value.cb=C.sizeof(value)
    return value.private_ws if get(kernel.GetCurrentProcess(),C.byref(value),value.cb) else 0


def release_unused_heap():
    # Windows 8.1+: HeapOptimizeResources decommits UNUSED LFH blocks. This is
    # not EmptyWorkingSet/SetProcessWorkingSetSize and does not discard live pages.
    # https://learn.microsoft.com/windows/win32/api/heapapi/nf-heapapi-heapsetinformation
    class Info(C.Structure):_fields_=[('version',W.DWORD),('flags',W.DWORD)]
    info=Info(1,0);function=C.windll.kernel32.HeapSetInformation
    function.argtypes=[W.HANDLE,C.c_int,C.c_void_p,C.c_size_t];function.restype=W.BOOL
    return bool(function(None,3,C.byref(info),C.sizeof(info)))


class MemoryBudget:
    def __init__(self,runtime):
        self.runtime=runtime;self.cursor=QCursor.pos();self.last_release=0.
        self.timer=QTimer(runtime.dock);self.timer.setInterval(5000);self.timer.timeout.connect(self.check);self.timer.start()

    def check(self):
        runtime=self.runtime;cursor=QCursor.pos();moved=cursor!=self.cursor;self.cursor=cursor
        if runtime.closed or moved or runtime.ui_busy() or QApplication.mouseButtons()!=Qt.NoButton:return
        if time.monotonic()-self.last_release<60:return
        self.reclaim(trim_caches=private_resident()>=44*2**20)

    def prepare_settings(self):
        """Drop hidden renderers before allocating a settings window."""
        if self.runtime.closed:
            return
        if not self.reclaim():self.release_hidden()

    def release_hidden(self):
        runtime = self.runtime
        runtime.panels.release_hidden_windows()
        popup = runtime.dock.extras.popup
        if popup is not None:
            popup.release_idle_resources()
        window = runtime.resources.window
        if window is not None:
            window.release_inactive_views()

    def reclaim(self, *, trim_caches=True):
        runtime=self.runtime
        if runtime.closed or runtime.ui_busy() or QApplication.mouseButtons()!=Qt.NoButton:return False
        self.last_release=time.monotonic()
        self.release_hidden()
        dialog=getattr(runtime.tray,'settings_dialog',None)
        if dialog is not None and not dialog.isVisible() and not getattr(dialog, '_suspended', False):
            dialog.deleteLater();del runtime.tray.settings_dialog
        importer=getattr(runtime.tray,'importer',None)
        if importer and (not importer.dialog or not importer.dialog.isVisible()):importer.release_memory()
        if not trim_caches:return True
        from app_catalog import clear_discovery_cache
        from wallpaper_source import image_file
        clear_discovery_cache();image_file.cache_clear();QPixmapCache.clear();runtime.dock.icons.clear()
        for item in runtime.dock.items:
            scaled=item.get('_scaled')
            if scaled:
                for key in list(scaled)[:-1]:scaled.pop(key,None)
        # Let deferred widget destruction finish before releasing allocator caches.
        QTimer.singleShot(0,self.finish)
        return True

    def finish(self):
        # A settings window can open while the deferred deletions finish.
        # Returning unused allocator pages is safe with the new window visible.
        if (not self.runtime.closed and QApplication.mouseButtons() == Qt.NoButton
                and QApplication.activePopupWidget() is None):
            release_unused_heap()

    def close(self):
        self.timer.stop()
