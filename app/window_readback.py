"""Bounded off-thread color sampling for windows rendered by DirectComposition."""
import ctypes as C
from ctypes import wintypes as W
import struct
import threading
import time

from PyQt5.QtCore import QObject, Qt, pyqtSignal, pyqtSlot

from taskbar_surface import _bindings
from window_layers import native


class _Updates(QObject):
    ready = pyqtSignal()

    @pyqtSlot()
    def refresh(self):
        from component_contrast import refresh_visible
        refresh_visible(live_only=True)


class _Window:
    def __init__(self):
        self.requests = {}
        self.colors = {}
        self.finished = 0
        self.busy = False


_lock = threading.Lock()
_slots = threading.BoundedSemaphore(2)
_windows = {}
_updates = None


def _render(hwnd, tid, pid, dimensions, points):
    user = native()
    owner, rect, affinity = W.DWORD(), W.RECT(), W.DWORD()
    if (user.GetWindowThreadProcessId(hwnd,C.byref(owner))!=tid or owner.value!=pid or
            not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd) or not user.GetWindowRect(hwnd,C.byref(rect)) or
            (rect.right-rect.left,rect.bottom-rect.top)!=dimensions or
            user.GetWindowDisplayAffinity(hwnd,C.byref(affinity)) and affinity.value):
        return {}
    points = {(x,y) for x,y in points if 0<=x<dimensions[0] and 0<=y<dimensions[1]}
    if not points:
        return {}
    width = max(x for x,y in points)+1
    height = max(y for x,y in points)+1
    if width*height > 12_000_000:
        return {}
    _,gdi = _bindings()
    dc = gdi.CreateCompatibleDC(None)
    if not dc:
        return {}
    bitmap = previous = None
    try:
        info = struct.pack('<IiiHHIIiiII',40,width,-height,1,32,0,0,0,0,0,0)
        bits = C.c_void_p()
        bitmap = gdi.CreateDIBSection(dc,info,0,C.byref(bits),None,0)
        if not bitmap or not bits.value:
            return {}
        previous = gdi.SelectObject(dc,bitmap)
        if not previous:
            return {}
        buffer = C.cast(bits,C.POINTER(W.DWORD))
        sentinel = 0xf52a6b97
        for x,y in points:
            buffer[y*width+x] = sentinel
        user.PrintWindow.argtypes = [W.HWND,W.HDC,W.UINT]
        if not user.PrintWindow(hwnd,dc,2):  # PW_RENDERFULLCONTENT
            return {}
        gdi.GdiFlush()
        result = {}
        for x,y in points:
            v = buffer[y*width+x]
            if v != sentinel:
                result[x,y] = (v>>16 & 255, v>>8 & 255, v & 255)
        return result
    finally:
        if previous:gdi.SelectObject(dc,previous)
        if bitmap:gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)


def _read(key, entry, desktop):
    changed = False
    try:
        user = native()
        user.SetThreadDesktop.argtypes = [W.HANDLE]
        if not user.SetThreadDesktop(desktop):
            return
        # Batch the cards covering this window in one native render.
        time.sleep(.02)
        with _lock:
            regions = tuple(entry.requests)
        points = set().union(*regions)
        colors = _render(*key,points)
        answers = {region:tuple(colors.get(p) for p in region) for region in regions}
        with _lock:
            changed = any(value!=entry.colors.get(region) and any(value) for region,value in answers.items())
            entry.colors = answers
    finally:
        with _lock:
            entry.finished = time.monotonic()
            entry.busy = False
        _slots.release()
        if changed:
            try:_updates.ready.emit()
            except RuntimeError:pass  # Qt may already have shut down.


def rendered_colors(hwnd, rect, points):
    """Return only the requested grid, never wait for a foreign window to paint."""
    global _updates
    if _updates is None:
        _updates = _Updates()
        _updates.ready.connect(_updates.refresh,Qt.QueuedConnection)
    user = native()
    pid = W.DWORD()
    tid = user.GetWindowThreadProcessId(hwnd,C.byref(pid))
    key = hwnd,tid,pid.value,(rect.right-rect.left,rect.bottom-rect.top)
    region = tuple(points)
    now = time.monotonic()
    with _lock:
        for old,item in list(_windows.items()):
            if not item.busy and now-item.finished>2.5:
                del _windows[old]
        if key not in _windows and len(_windows)>=16:
            return None
        entry = _windows.setdefault(key,_Window())
        entry.requests = {r:t for r,t in entry.requests.items() if now-t<2}
        if region not in entry.requests and len(entry.requests)>=32:
            return None
        entry.requests[region] = now
        stored = entry.colors.get(region) if now-entry.finished<2 else None
        if not entry.busy and (region not in entry.colors or now-entry.finished>.7) and _slots.acquire(False):
            user.GetThreadDesktop.argtypes=[W.DWORD]
            user.GetThreadDesktop.restype=W.HANDLE
            desktop=user.GetThreadDesktop(C.windll.kernel32.GetCurrentThreadId())
            entry.busy=True
            threading.Thread(target=_read,args=(key,entry,desktop),name='DesktopWindowColors',daemon=True).start()
    return stored if stored and any(stored) else None
