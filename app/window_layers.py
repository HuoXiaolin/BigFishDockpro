"""Win32 stacking for app windows. Never activate a window to change its layer."""
import ctypes as C
from ctypes import wintypes as W


TOPMOST = -1
BOTTOM = 1
LAYER_FLAGS = 0x0213  # NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER
_user = None


def native():
    global _user
    if _user is None:
        user = C.WinDLL('user32', use_last_error=True)
        user.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
        user.SetWindowPos.restype = W.BOOL
        user.GetWindowLongW.argtypes = [W.HWND, C.c_int]
        user.GetWindowLongW.restype = W.LONG
        user.SetWindowLongPtrW.argtypes = [W.HWND, C.c_int, C.c_ssize_t]
        user.SetWindowLongPtrW.restype = C.c_ssize_t
        user.GetWindow.argtypes = [W.HWND, W.UINT]
        user.GetWindow.restype = W.HWND
        user.GetShellWindow.restype = W.HWND
        user.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
        user.GetWindowRect.restype = W.BOOL
        user.GetForegroundWindow.restype = W.HWND
        _user = user
    return _user


def is_topmost(hwnd):
    return bool(native().GetWindowLongW(hwnd, -20) & 8)


def restack(hwnd, after):
    return bool(native().SetWindowPos(hwnd, after, 0, 0, 0, 0, LAYER_FLAGS))


def shell_owner():
    return native().GetShellWindow() or 0


def owner_of(hwnd):
    return native().GetWindow(hwnd, 4) or 0  # GW_OWNER


def desktop_layer(hwnd, top, owner=0):
    if owner_of(hwnd) != owner:
        native().SetWindowLongPtrW(hwnd, -8, owner)  # GWLP_HWNDPARENT of a top-level window
    return restack(hwnd, TOPMOST if top else BOTTOM) and owner_of(hwnd) == owner


def click_through(window, enabled):
    # These widgets are already layered (Qt translucent backgrounds). The
    # Win32 style passes input to other processes; the Qt flag covers children.
    from PyQt5.QtCore import Qt
    window.setAttribute(Qt.WA_TransparentForMouseEvents, enabled)
    hwnd = int(window.winId())
    user = native()
    old = user.GetWindowLongW(hwnd, -20)
    new = old | 0x20 if enabled else old & ~0x20
    if old != new:
        user.SetWindowLongPtrW(hwnd, -20, new)


def covers_above(cover, hwnd):
    if not cover or cover == hwnd or not is_topmost(cover):
        return False
    user = native()
    a, b = W.RECT(), W.RECT()
    if not user.GetWindowRect(cover, C.byref(a)) or not user.GetWindowRect(hwnd, C.byref(b)):
        return False
    if max(a.left, b.left) >= min(a.right, b.right) or max(a.top, b.top) >= min(a.bottom, b.bottom):
        return False
    window = user.GetWindow(hwnd, 3)  # GW_HWNDPREV, nearest first
    for _ in range(4096):
        if not window or not is_topmost(window):break
        if window == cover:
            return True
        window = user.GetWindow(window, 3)
    return False


def repair_top(hwnd, cover):
    if not is_topmost(hwnd) or covers_above(cover, hwnd):
        # Preserve other windows that Windows already places above the fullscreen window.
        after = native().GetWindow(cover, 3) if cover else None
        restack(hwnd, after if after and after != hwnd and is_topmost(after) else TOPMOST)


class ForegroundLayers:
    """Coalesce native foreground/fullscreen changes. No idle polling."""
    def __init__(self, parent, refresh):
        from PyQt5.QtCore import QTimer
        self.timer = QTimer(parent)
        self.timer.setSingleShot(True);self.timer.setInterval(35)
        self.timer.timeout.connect(refresh)
        self.user = user = native()
        proto = C.WINFUNCTYPE(None,W.HANDLE,W.DWORD,W.HWND,W.LONG,W.LONG,W.DWORD,W.DWORD)
        user.SetWinEventHook.argtypes=[W.DWORD,W.DWORD,W.HMODULE,proto,W.DWORD,W.DWORD,W.DWORD]
        user.SetWinEventHook.restype=W.HANDLE
        user.UnhookWinEvent.argtypes=[W.HANDLE]
        self.callback = proto(self.event)
        self.hooks = [hook for event in (3,0x8004,0x800b)
                      if (hook:=user.SetWinEventHook(event,event,None,self.callback,0,0,2))]

    def event(self, hook, event, hwnd, obj, child, thread, stamp):
        if event==3 or (hwnd and obj==child==0 and hwnd==self.user.GetForegroundWindow()):
            if not self.timer.isActive():self.timer.start()

    def close(self):
        self.timer.stop()
        for hook in self.hooks:self.user.UnhookWinEvent(hook)
        self.hooks.clear()
