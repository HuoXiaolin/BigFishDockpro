"""Read a few composed shell colors, without keeping a desktop image."""
import ctypes
from ctypes import wintypes
from functools import lru_cache
from statistics import median


def sample_points(bar):
    rect = bar['rect']
    native_x, native_y, logical_x, logical_y, scale_x, scale_y = bar['map']
    across = (.12, .24, .36, .48, .59, .69, .79, .89, .96)
    horizontal = rect.width() >= rect.height()
    # Sample near the edge of the bar, away from the centered icons and clock.
    for offset in across:
        x = rect.x() + rect.width() * (offset if horizontal else .17)
        y = rect.y() + rect.height() * (.17 if horizontal else offset)
        yield (round(native_x + (x - logical_x) / scale_x),
               round(native_y + (y - logical_y) / scale_y))


@lru_cache(maxsize=1)
def _bindings():
    user = ctypes.WinDLL('user32')
    gdi = ctypes.WinDLL('gdi32')
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.GetPixel.restype = wintypes.DWORD
    return user.GetDC, user.ReleaseDC, gdi.GetPixel


def taskbar_color(window):
    from resource_taskbar import taskbars
    screen = window.screen()
    if screen is None:
        return None
    bar = next((item for item in taskbars() if item['screen'] == screen.name()), None)
    if bar is None:
        return None
    return composed_color(sample_points(bar))


def composed_color(points):
    get_dc, release_dc, get_pixel = _bindings()
    dc = get_dc(None)
    if not dc:
        return None
    try:
        colors = [get_pixel(dc, x, y) for x, y in points]
    finally:
        release_dc(None, dc)
    colors = [value for value in colors if value != 0xffffffff]
    if len(colors) < 5:
        return None
    return tuple(median((value >> shift) & 255 for value in colors) for shift in (0, 8, 16))
