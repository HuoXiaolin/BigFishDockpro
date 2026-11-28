"""Sparse colors of the windows directly beneath a translucent desktop component."""
import ctypes as C
from ctypes import wintypes as W
from functools import lru_cache

from taskbar_surface import _bindings, _sample_screen_dc
from window_layers import (WALLPAPER_HOSTS, _dwm_window_attribute, client_frame, native,
                           points_in_surface, surface_role, visible_frame, window_class)


COLUMNS, ROWS = 16, 8


@lru_cache(maxsize=1)
def _user():
    user = native()
    user.GetWindowDC.argtypes = [W.HWND]
    user.GetWindowDC.restype = W.HDC
    user.ReleaseDC.argtypes = [W.HWND, W.HDC]
    user.WindowFromPoint.argtypes = [W.POINT]
    user.WindowFromPoint.restype = W.HWND
    user.MonitorFromWindow.argtypes = [W.HWND,W.DWORD]
    user.MonitorFromWindow.restype = W.HANDLE
    user.MonitorFromPoint.argtypes = [W.POINT,W.DWORD]
    user.MonitorFromPoint.restype = W.HANDLE
    user.GetWindowDisplayAffinity.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    return user


def _colors(hwnd, points):
    user, gdi = _bindings()
    dc = _user().GetWindowDC(hwnd) if hwnd else user.GetDC(None)
    if not dc:
        return [None] * len(points)
    try:
        values = _sample_screen_dc(gdi, dc, points)
        return [None if v == 0xffffffff else (v & 255, v >> 8 & 255, v >> 16 & 255) for v in values]
    finally:
        user.ReleaseDC(hwnd, dc)


def _exposed_colors(hwnd, frame, points):
    """GPU windows can have no GDI backing. Use visible pixels of that same HWND."""
    user = _user()
    left, top, right, bottom = frame
    neighbours = set()
    for x, y in points:
        neighbours.update(((x, top-2), (x, bottom+1), (left-2, y), (right+1, y)))
    exposed = []
    for x, y in sorted(neighbours):
        hit = user.WindowFromPoint(W.POINT(x, y))
        if hit and user.GetAncestor(hit, 2) == hwnd:  # GA_ROOT
            exposed.append((x, y))
    if not exposed:
        return []
    return [(p, color) for p, color in zip(exposed, _colors(None, exposed)) if color is not None]


def _window_colors(hwnd, frame, rect, points, flags):
    local = [(x-rect.left, y-rect.top) for x, y in points]
    from window_readback import rendered_colors
    compositor = flags & 0x00200000  # WS_EX_NOREDIRECTIONBITMAP
    if compositor:
        rendered = rendered_colors(hwnd,rect,local)
        if rendered:
            return rendered,'应用渲染读回'
    colors = _colors(hwnd, local)
    if not compositor and not any(colors):
        rendered = rendered_colors(hwnd,rect,local)
        if rendered:
            return rendered,'应用渲染读回'
    # Some DirectComposition clients expose an empty GDI surface. Validate a
    # uniform surface against *the same* visible points before substituting any
    # edge colors. A real black page, or a white page with a dark toolbar, is valid.
    if compositor or len(set(colors)) == 1:
        exposed = _exposed_colors(hwnd, frame, points)
        if exposed:
            reference = _colors(hwnd, [(x-rect.left, y-rect.top) for (x,y), _ in exposed])
            different = [(p, actual) for (p, actual), expected in zip(exposed, reference)
                         if expected is None or max(abs(a-b) for a,b in zip(actual,expected)) > 28]
            if len(different) * 2 > len(exposed) or compositor:
                if not compositor:
                    rendered = rendered_colors(hwnd,rect,local)
                    if rendered:
                        return rendered,'应用渲染读回'
                def nearest(point):
                    x, y = point
                    return min(exposed, key=lambda item:(x-item[0][0])**2+(y-item[0][1])**2)[1]
                return [nearest(p) for p in points],'同一应用邻近的可见像素'
    return colors,'窗口设备上下文'


def _sample_grid(window, local_rect):
    from PyQt5.QtCore import Qt
    if not window.isVisible() or not window.testAttribute(Qt.WA_WState_Created) or local_rect.isEmpty():
        return None
    hwnd = int(window.winId())
    client = client_frame(hwnd)
    if not client:
        return None
    # Both the window DC and the z-order rectangles are in native pixels.
    # Qt global positions need not share the same origin at mixed display scales.
    left,top,width,height = client
    sx, sy = width/max(1,window.width()), height/max(1,window.height())
    frame = left,top,left+width,top+height
    points = [(left+int(sx*(local_rect.x()+local_rect.width()*(x+.5)/COLUMNS)),
               top+int(sy*(local_rect.y()+local_rect.height()*(y+.5)/ROWS)))
              for y in range(ROWS) for x in range(COLUMNS)]
    return hwnd,frame,points


def exposed_wallpaper_samples(window,local_rect):
    """Last resort for unreadable wallpaper files. Only sample exposed shell pixels on this monitor."""
    grid = _sample_grid(window,local_rect)
    if not grid:
        return None
    hwnd, (left,top,right,bottom), points = grid
    user = _user()
    monitor = user.MonitorFromWindow(hwnd,0)
    if not monitor:
        return None
    neighbours = set()
    for x,y in points:
        neighbours.update(((x,top-3),(x,bottom+2),(left-3,y),(right+2,y)))
    exposed = []
    for x,y in sorted(neighbours):
        point = W.POINT(x,y)
        if user.MonitorFromPoint(point,0)!=monitor:
            continue
        hit = user.WindowFromPoint(point)
        if hit and window_class(user.GetAncestor(hit,2)) in WALLPAPER_HOSTS:
            exposed.append((x,y))
    if len(exposed)<3:
        return None
    samples = [(p,c) for p,c in zip(exposed,_colors(None,exposed)) if c is not None]
    if len(samples)<3:
        return None
    return tuple(min(samples,key=lambda s:(s[0][0]-x)**2+(s[0][1]-y)**2)[1] for x,y in points)


def window_samples(window, local_rect, *, sources=None):
    """Return a 16 by 8 grid. Empty cells belong to the wallpaper or are unavailable."""
    from PyQt5.QtWidgets import QWidget
    grid = _sample_grid(window,local_rect)
    if not grid:
        return None
    hwnd,frame,points = grid
    user = _user()
    pending = list(range(len(points)))
    result = [None] * len(points)
    current = hwnd
    seen = {hwnd}
    attribute = _dwm_window_attribute()
    rect, cloaked, affinity = W.RECT(), W.DWORD(), W.DWORD()
    while pending:
        current = user.GetWindow(current, 2)  # GW_HWNDNEXT
        if not current or current in seen:
            break
        seen.add(current)
        if not user.IsWindowVisible(current) or user.IsIconic(current) or not user.GetWindowRect(current,C.byref(rect)):
            continue
        if rect.right<=frame[0] or rect.bottom<=frame[1] or rect.left>=frame[2] or rect.top>=frame[3]:
            continue
        if attribute(current,14,C.byref(cloaked),C.sizeof(cloaked)) == 0 and cloaked.value:
            continue
        flags = user.GetWindowLongW(current,-20)
        overlay = QWidget.find(current)
        if overlay is not None and (overlay.property('clickThroughKey') or overlay.property('desktopLayerKey')):
            continue
        box = visible_frame(current,rect)
        inside = [i for i in pending if box.left<=points[i][0]<box.right and box.top<=points[i][1]<box.bottom]
        if not inside:
            continue
        name=window_class(current)
        role = surface_role(current,name,flags)
        if role=='overlay':
            continue
        inside = points_in_surface(current,rect,flags,points,inside)
        if not inside:
            continue
        method='桌面区域'
        if role=='application':
            if user.GetWindowDisplayAffinity(current,C.byref(affinity)) and affinity.value:
                method='窗口启用显示保护'
            else:
                colors,method = _window_colors(current,frame,rect,[points[i] for i in inside],flags)
                for i,color in zip(inside,colors):
                    result[i] = color
        if sources is not None:
            pid=W.DWORD()
            user.GetWindowThreadProcessId(current,C.byref(pid))
            sources.append({'HWND':hex(current),'PID':pid.value,'窗口类':name,'取色方式':method,
                            '覆盖点数':len(inside),'成功读取点数':sum(result[i] is not None for i in inside)})
        covered = set(inside)
        pending = [i for i in pending if i not in covered]
    return tuple(result) if any(color is not None for color in result) else None
