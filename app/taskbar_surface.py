"""Read a few composed shell colors, without keeping a desktop image."""
import ctypes
import struct
from ctypes import wintypes
from functools import lru_cache
from statistics import median


@lru_cache(maxsize=1)
def _bindings():
    user = ctypes.WinDLL('user32')
    gdi = ctypes.WinDLL('gdi32')
    user.GetDC.argtypes = [wintypes.HWND]
    user.GetDC.restype = wintypes.HDC
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user.MonitorFromPoint.restype = wintypes.HANDLE
    gdi.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi.GetPixel.restype = wintypes.DWORD
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                     wintypes.HANDLE, wintypes.DWORD]
    gdi.CreateDIBSection.restype = wintypes.HBITMAP
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.ExtCreateRegion.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    gdi.ExtCreateRegion.restype = wintypes.HRGN
    gdi.SelectClipRgn.argtypes = [wintypes.HDC, wintypes.HRGN]
    gdi.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                           wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    return user, gdi


def _sample_screen_dc(gdi, dc, points):
    left, top = map(min, zip(*points))
    right, bottom = map(max, zip(*points))
    width, height = right - left + 1, bottom - top + 1
    if width * height > 4_194_304:
        return [gdi.GetPixel(dc, x, y) for x, y in points]

    # A screen GetPixel waits for composition. Copy only the sampling dots in
    # one BitBlt, then read the same COLORREF values from a temporary memory DC.
    dots = [(x - left, y - top) for x, y in points]
    distinct = sorted(set(dots), key=lambda point: (point[1], point[0]))
    rects = b''.join(struct.pack('<4i', x, y, x + 1, y + 1) for x, y in distinct)
    region_data = struct.pack('<8I', 32, 1, len(distinct), len(rects), 0, 0, width, height) + rects
    bitmap_info = struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    memory = gdi.CreateCompatibleDC(dc)
    bitmap = region = previous = None
    try:
        if memory:
            bitmap = gdi.CreateDIBSection(dc, bitmap_info, 0, ctypes.byref(bits), None, 0)
            region = gdi.ExtCreateRegion(None, len(region_data), region_data)
        if bitmap and region:
            previous = gdi.SelectObject(memory, bitmap)
            if (previous and gdi.SelectClipRgn(memory, region) > 0 and
                    gdi.BitBlt(memory, 0, 0, width, height, dc, left, top, 0x00CC0020)):
                return [gdi.GetPixel(memory, x, y) for x, y in dots]
    finally:
        if previous:
            gdi.SelectObject(memory, previous)
        if region:
            gdi.DeleteObject(region)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if memory:
            gdi.DeleteDC(memory)
    return [gdi.GetPixel(dc, x, y) for x, y in points]


def composed_color(points):
    user, gdi = _bindings()
    points = [(x, y) for x, y in points if user.MonitorFromPoint(wintypes.POINT(x, y), 0)]
    if len(points) < 5:
        return None
    dc = user.GetDC(None)
    if not dc:
        return None
    try:
        colors = _sample_screen_dc(gdi, dc, points)
    finally:
        user.ReleaseDC(None, dc)
    colors = [value for value in colors if value != 0xffffffff]
    if len(colors) < 5:
        return None
    return tuple(median((value >> shift) & 255 for value in colors) for shift in (0, 8, 16))
