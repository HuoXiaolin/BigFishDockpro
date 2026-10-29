"""Wallpaper-only backdrop shared by Dock, collection cards and sticky notes."""
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


def capture_behind(window,windows=()):
    if sys.platform!='win32':return None
    screen=QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
    if screen is None:return None
    try:
        from wallpaper_source import capture
        return capture(window,screen)
    except (OSError,ValueError,AttributeError,RuntimeError):return None


def surface_windows(dock):
    runtime=getattr(getattr(dock,'tray',None),'runtime',None)
    clock=getattr(runtime,'clock',None);calendar=getattr(runtime,'calendar',None)
    windows=[dock]+([clock] if clock else [])+([calendar] if calendar else [])+[window for manager in (getattr(runtime,'panels',None),getattr(runtime,'notes',None))
                   for window in getattr(manager,'windows',{}).values()]

    return windows
