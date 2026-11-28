"""Win32 stacking for app windows. Never activate a window to change its layer."""
import ctypes as C
from ctypes import wintypes as W
import os
from functools import lru_cache


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
        user.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
        user.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
        user.GetForegroundWindow.restype = W.HWND
        user.GetCursorPos.argtypes = [C.POINTER(W.POINT)]
        user.GetCursorPos.restype = W.BOOL
        user.GetAsyncKeyState.argtypes = [C.c_int]
        user.GetAsyncKeyState.restype = C.c_short
        user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        user.GetClassNameW.restype = C.c_int
        user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        user.GetWindowThreadProcessId.restype = W.DWORD
        user.GetAncestor.argtypes = [W.HWND, W.UINT]
        user.GetAncestor.restype = W.HWND
        user.GetWindowRgnBox.argtypes = [W.HWND,C.POINTER(W.RECT)]
        user.GetWindowRgn.argtypes = [W.HWND,W.HRGN]
        user.GetLayeredWindowAttributes.argtypes = [W.HWND,C.POINTER(W.DWORD),C.POINTER(W.BYTE),C.POINTER(W.DWORD)]
        for check in (user.IsWindowVisible,user.IsIconic):
            check.argtypes=[W.HWND];check.restype=W.BOOL
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


def set_owner(hwnd, owner):
    if owner_of(hwnd) != owner:
        native().SetWindowLongPtrW(hwnd, -8, owner)  # GWLP_HWNDPARENT of a top-level window
    return owner_of(hwnd) == owner


def desktop_layer(hwnd, top, owner=0):
    owned = set_owner(hwnd, owner)
    return restack(hwnd, TOPMOST if top else BOTTOM) and owned


def effective_top(cfg, custom_top):
    mode = cfg.get('desktop_layer_mode', 'custom')
    return custom_top if mode == 'custom' else mode == 'top'


def place_desktop(window, cfg, custom_top=False, *, shell_owned=False):
    top = effective_top(cfg, custom_top)
    owner = shell_owner() if shell_owned and not top and not os.environ.get('FISHDOCK_TEST_DESKTOP') else 0
    return desktop_layer(int(window.winId()), top, owner)


def click_through(window, enabled):
    # These widgets are already layered (Qt translucent backgrounds). The
    # Win32 style passes input to other processes; the Qt flag covers children.
    from PyQt5.QtCore import Qt
    if window.testAttribute(Qt.WA_TransparentForMouseEvents)!=enabled:
        window.setAttribute(Qt.WA_TransparentForMouseEvents, enabled)
    hwnd = int(window.winId())
    user = native()
    old = user.GetWindowLongW(hwnd, -20)
    new = old | 0x20 if enabled else old & ~0x20
    if old != new:
        user.SetWindowLongPtrW(hwnd, -20, new)


WALLPAPER_HOSTS = frozenset({'Progman','WorkerW','SHELLDLL_DefView'})
DESKTOP_WINDOW_CLASSES=WALLPAPER_HOSTS | {'Shell_TrayWnd','Shell_SecondaryTrayWnd'}
_HUD_CLASSES = {'CEF-OSC-WIDGET','tooltips_class32','SysShadow'}
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_LAYERED = 0x80, 0x40000, 0x80000
WS_EX_NOREDIRECTIONBITMAP, WS_EX_NOACTIVATE = 0x200000, 0x08000000


def window_class(hwnd):
    name = C.create_unicode_buffer(256)
    return name.value if hwnd and native().GetClassNameW(hwnd,name,len(name)) else ''


def client_frame(hwnd):
    """Client origin and size in the same native coordinate space as the monitor."""
    user = native()
    client, origin = W.RECT(), W.POINT()
    if user.GetClientRect(hwnd,C.byref(client)) and user.ClientToScreen(hwnd,C.byref(origin)) and client.right>0 and client.bottom>0:
        return origin.x, origin.y, client.right, client.bottom


def visible_frame(hwnd, rect):
    frame = W.RECT()
    if _dwm_window_attribute()(hwnd,9,C.byref(frame),C.sizeof(frame))==0 and frame.right>frame.left and frame.bottom>frame.top:
        return frame
    return rect


def classify_surface(hwnd, name, flags):
    """Classify a top-level surface for both pointer routing and background colors."""
    if name in DESKTOP_WINDOW_CLASSES or hwnd == native().GetShellWindow():
        return 'desktop','系统桌面或任务栏'
    if not name or name in _HUD_CLASSES:
        return 'overlay','无窗口类名或属于提示框、阴影、性能叠加层'
    if flags & WS_EX_LAYERED and flags & 0x20:
        return 'overlay','分层窗口允许鼠标穿透'
    if flags & WS_EX_LAYERED:  # A layered window can be invisible without WS_EX_TRANSPARENT.
        alpha, mode = W.BYTE(), W.DWORD()
        if native().GetLayeredWindowAttributes(hwnd,None,C.byref(alpha),C.byref(mode)) and mode.value & 2 and not alpha.value:
            return 'overlay','整个窗口的透明度为零'
    if not flags & WS_EX_APPWINDOW and not native().GetWindowLongW(hwnd,-16) & 0xc00000:  # WS_CAPTION
        owner = owner_of(hwnd)
        if owner and window_class(owner) in WALLPAPER_HOSTS:
            return 'overlay','桌面宿主拥有的无标题窗口'
        tool = flags & WS_EX_TOOLWINDOW
        passive = flags & WS_EX_NOACTIVATE
        composited = flags & (WS_EX_LAYERED | WS_EX_NOREDIRECTIONBITMAP)
        # An HWND may have a hidden proxy owner. Only a visible application owner
        # distinguishes its tool palette from a standalone HUD or pet canvas.
        transparent=flags & 0x20
        if (not owner or not native().IsWindowVisible(owner)) and (
                (tool and passive) or ((composited or transparent) and (tool or passive))):
            return 'overlay','独立的无激活或透明工具窗口'
    return 'application','应用窗口覆盖此点'


def surface_role(hwnd,name,flags):
    return classify_surface(hwnd,name,flags)[0]


@lru_cache(maxsize=1)
def _regions():
    gdi = C.WinDLL('gdi32',use_last_error=True)
    gdi.CreateRectRgn.argtypes = [C.c_int]*4
    gdi.CreateRectRgn.restype = W.HRGN
    gdi.PtInRegion.argtypes = [W.HRGN,C.c_int,C.c_int]
    gdi.DeleteObject.argtypes = [W.HANDLE]
    return gdi


def points_in_surface(hwnd, rect, flags, points, indices):
    """Clip candidate native screen points to the window's actual shape."""
    box = W.RECT()
    kind = native().GetWindowRgnBox(hwnd,C.byref(box))
    if not kind:  # ordinary unshaped window
        return indices
    if kind == 1:  # NULLREGION
        return []
    coords = [(i, rect.right-1-points[i][0] if flags & 0x400000 else points[i][0]-rect.left,
               points[i][1]-rect.top) for i in indices]
    if kind == 2:
        return [i for i,x,y in coords if box.left<=x<box.right and box.top<=y<box.bottom]
    gdi = _regions()
    region = gdi.CreateRectRgn(0,0,0,0)
    if not region:
        return []
    try:
        if not native().GetWindowRgn(hwnd,region):
            return []
        return [i for i,x,y in coords if gdi.PtInRegion(region,x,y)]
    finally:
        gdi.DeleteObject(region)


def cursor_position():
    point=W.POINT()
    return point if native().GetCursorPos(C.byref(point)) else None


def alt_pressed():
    pressed = native().GetAsyncKeyState
    return bool((pressed(0xA4) | pressed(0xA5)) & 0x8000)  # VK_LMENU / VK_RMENU


def application_under(hwnd,point,trace=None):
    """Check the native stacking order at the pointer instead of the foreground focus."""
    if trace is not None:
        trace.update(point=(point.x,point.y) if point is not None else None,
                     inside=False,windows=[],reason='无法读取鼠标坐标')
    if point is None:
        return False
    user=native()
    rect=W.RECT()
    def contains(target):
        return (user.GetWindowRect(target,C.byref(rect)) and
                rect.left<=point.x<rect.right and rect.top<=point.y<rect.bottom)

    if not contains(hwnd):
        if trace is not None:trace['reason']='采样点在胶囊窗口外'
        return False
    if trace is not None:
        trace.update(inside=True,reason='下方没有命中可交互的应用')
    def observe(handle,name,flags,reason,decisive=False,process=None):
        if trace is None:return
        if decisive:trace['reason']=reason
        if len(trace['windows'])>=12 and not decisive:return
        if process is None:
            ident=W.DWORD()
            user.GetWindowThreadProcessId(handle,C.byref(ident))
            process=ident.value
        trace['windows'].append((handle,process,name,flags,(rect.left,rect.top,rect.right,rect.bottom),reason))
    pid=W.DWORD()
    cloaked=W.DWORD()
    window_attribute=_dwm_window_attribute()
    current=hwnd
    own_pid=os.getpid()
    seen={hwnd}
    while True:
        current=user.GetWindow(current,2)  # GW_HWNDNEXT
        if not current or current in seen:break
        seen.add(current)
        if not user.IsWindowVisible(current) or user.IsIconic(current) or not contains(current):
            continue
        flags=user.GetWindowLongW(current,-20)
        if window_attribute(current,14,C.byref(cloaked),C.sizeof(cloaked))==0 and cloaked.value:
            if trace is not None:observe(current,window_class(current),flags,'跳过 DWM 隐藏的窗口')
            continue
        name=window_class(current)
        role,reason=classify_surface(current,name,flags)
        if role=='overlay':
            if trace is not None:observe(current,name,flags,'跳过：'+reason)
            continue
        if not points_in_surface(current,rect,flags,[(point.x,point.y)],[0]):
            if trace is not None:observe(current,name,flags,'跳过窗口区域的空洞')
            continue
        if role=='desktop':
            if trace is not None:observe(current,name,flags,reason,True)
            return False
        if not user.GetWindowThreadProcessId(current,C.byref(pid)) or pid.value==own_pid:
            if trace is not None:observe(current,name,flags,'跳过本进程或无法归属的窗口',process=pid.value)
            continue
        frame=visible_frame(current,rect)
        if not (frame.left<=point.x<frame.right and frame.top<=point.y<frame.bottom):
            if trace is not None:observe(current,name,flags,'跳过应用阴影与外边距',process=pid.value)
            continue
        if trace is not None:observe(current,name,flags,reason,True,pid.value)
        return True
    return False


_window_attribute=None


def _dwm_window_attribute():
    global _window_attribute
    if _window_attribute is None:
        function=C.WinDLL('dwmapi').DwmGetWindowAttribute
        function.argtypes=[W.HWND,W.DWORD,C.c_void_p,W.DWORD]
        function.restype=C.c_long
        _window_attribute=function
    return _window_attribute


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
