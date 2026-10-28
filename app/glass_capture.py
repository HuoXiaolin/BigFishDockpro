"""Bounded screen capture shared by Dock, collection cards and sticky notes."""
import ctypes
import sys
from ctypes import wintypes
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication


def valid_backdrop(pixmap):
    # Older Windows/drivers can report success yet supply an opaque black mask.
    # Reject only effectively empty frames, never brighten genuine dark images.
    if pixmap is None or pixmap.isNull():return False
    image=pixmap.toImage().scaled(12,12,Qt.IgnoreAspectRatio,Qt.FastTransformation)
    return any(image.pixelColor(x,y).alpha()>8 and max(image.pixelColor(x,y).getRgb()[:3])>3
               for x in range(image.width()) for y in range(image.height()))


def capture_behind(window,windows):
    if sys.platform!='win32' or sys.getwindowsversion().build<19041:return None
    screen=QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
    if screen is None:return None
    rect=window.frameGeometry();origin=screen.geometry()
    # QScreen accepts logical, screen-local coordinates and returns DPR pixels.
    # A partially off-screen card safely falls back to its existing theme tint.
    if not origin.contains(rect):return None
    user=ctypes.windll.user32
    user.SetWindowDisplayAffinity.argtypes=[wintypes.HWND,wintypes.DWORD]
    user.SetWindowDisplayAffinity.restype=wintypes.BOOL
    user.GetWindowDisplayAffinity.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowDisplayAffinity.restype=wintypes.BOOL
    restored=[];seen=set()
    try:
        for item in [window]+list(windows):
            if not item.isVisible():continue
            hwnd=int(item.winId())
            if hwnd in seen:continue
            seen.add(hwnd);original=wintypes.DWORD()
            if not user.GetWindowDisplayAffinity(hwnd,ctypes.byref(original)):return None
            # Preserve pre-existing affinity; never undo another component's state.
            if original.value!=0x11:
                if not user.SetWindowDisplayAffinity(hwnd,0x11):return None
                restored.append((hwnd,original.value))
        if int(window.winId()) not in seen:return None
        ctypes.windll.dwmapi.DwmFlush()
        pixmap=screen.grabWindow(0,rect.x()-origin.x(),rect.y()-origin.y(),rect.width(),rect.height())
        return pixmap if valid_backdrop(pixmap) else None
    except (OSError,AttributeError,RuntimeError):
        return None
    finally:
        for hwnd,original in reversed(restored):user.SetWindowDisplayAffinity(hwnd,original)


def surface_windows(dock):
    runtime=getattr(getattr(dock,'tray',None),'runtime',None)
    clock=getattr(runtime,'clock',None);calendar=getattr(runtime,'calendar',None)
    windows=[dock]+([clock] if clock else [])+([calendar] if calendar else [])+[window for manager in (getattr(runtime,'panels',None),getattr(runtime,'notes',None))
                   for window in getattr(manager,'windows',{}).values()]

    return windows
