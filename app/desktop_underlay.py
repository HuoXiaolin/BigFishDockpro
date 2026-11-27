"""Sparse colors of the windows directly beneath a translucent desktop component."""
import ctypes as C
from ctypes import wintypes as W
from functools import lru_cache

from taskbar_surface import _bindings, _sample_screen_dc
from window_layers import DESKTOP_WINDOW_CLASSES, _dwm_window_attribute, native


COLUMNS, ROWS = 16, 8


@lru_cache(maxsize=1)
def _user():
    user = native()
    user.GetWindowDC.argtypes = [W.HWND]
    user.GetWindowDC.restype = W.HDC
    user.ReleaseDC.argtypes = [W.HWND, W.HDC]
    user.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
    user.WindowFromPoint.argtypes = [W.POINT]
    user.WindowFromPoint.restype = W.HWND
    user.GetAncestor.argtypes = [W.HWND, W.UINT]
    user.GetAncestor.restype = W.HWND
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
            return rendered
    colors = _colors(hwnd, local)
    if not compositor and not any(colors):
        rendered = rendered_colors(hwnd,rect,local)
        if rendered:
            return rendered
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
                        return rendered
                def nearest(point):
                    x, y = point
                    return min(exposed, key=lambda item:(x-item[0][0])**2+(y-item[0][1])**2)[1]
                return [nearest(p) for p in points]
    return colors


def window_samples(window, local_rect):
    """Return a 16 by 8 grid. Empty cells belong to the wallpaper or are unavailable."""
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QWidget
    if not window.isVisible() or not window.testAttribute(Qt.WA_WState_Created) or local_rect.isEmpty():
        return None
    user = _user()
    hwnd = int(window.winId())
    client, origin = W.RECT(), W.POINT()
    if not user.GetClientRect(hwnd, C.byref(client)) or not user.ClientToScreen(hwnd, C.byref(origin)):
        return None
    # Both the window DC and the z-order rectangles are in native pixels.
    # Qt global positions need not share the same origin at mixed display scales.
    sx, sy = client.right/max(1,window.width()), client.bottom/max(1,window.height())
    frame = origin.x, origin.y, origin.x+client.right, origin.y+client.bottom
    points = [(origin.x+int(sx*(local_rect.x()+local_rect.width()*(x+.5)/COLUMNS)),
               origin.y+int(sy*(local_rect.y()+local_rect.height()*(y+.5)/ROWS)))
              for y in range(ROWS) for x in range(COLUMNS)]
    pending = list(range(len(points)))
    result = [None] * len(points)
    current = hwnd
    seen = {hwnd}
    attribute = _dwm_window_attribute()
    name = C.create_unicode_buffer(128)
    rect, bounds, cloaked, affinity = W.RECT(), W.RECT(), W.DWORD(), W.DWORD()
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
        if ((flags & 0x80020) == 0x80020 or
                overlay is not None and (overlay.property('clickThroughKey') or overlay.property('desktopLayerKey'))):
            continue
        box = bounds if attribute(current,9,C.byref(bounds),C.sizeof(bounds)) == 0 else rect
        inside = [i for i in pending if box.left<=points[i][0]<box.right and box.top<=points[i][1]<box.bottom]
        if not inside:
            continue
        user.GetClassNameW(current,name,len(name))
        if name.value not in DESKTOP_WINDOW_CLASSES and not (user.GetWindowDisplayAffinity(current,C.byref(affinity)) and affinity.value):
            colors = _window_colors(current,frame,rect,[points[i] for i in inside],flags)
            for i,color in zip(inside,colors):
                result[i] = color
        covered = set(inside)
        pending = [i for i in pending if i not in covered]
    return tuple(result) if any(color is not None for color in result) else None
