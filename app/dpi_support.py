"""One DPI owner: Windows per-monitor awareness and Qt logical-pixel rendering."""
import ctypes
import re


def prepare():
    # Source runs need the same awareness as the frozen executable manifest.
    user=ctypes.windll.user32
    try:
        user.GetThreadDpiAwarenessContext.restype=ctypes.c_void_p
        user.AreDpiAwarenessContextsEqual.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        context=user.GetThreadDpiAwarenessContext()
        if not user.AreDpiAwarenessContextsEqual(context,ctypes.c_void_p(-4)):
            user.SetProcessDpiAwarenessContext.argtypes=[ctypes.c_void_p]
            if not user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
                user.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
                user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        try:ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError,OSError):pass
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QGuiApplication
    from PyQt5.QtWidgets import QApplication
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling,True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps,True)
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)


def awareness(hwnd=None):
    user=ctypes.windll.user32
    user.GetThreadDpiAwarenessContext.restype=ctypes.c_void_p
    user.GetAwarenessFromDpiAwarenessContext.argtypes=[ctypes.c_void_p]
    if hwnd is None:context=user.GetThreadDpiAwarenessContext()
    else:
        user.GetWindowDpiAwarenessContext.argtypes=[ctypes.c_void_p]
        user.GetWindowDpiAwarenessContext.restype=ctypes.c_void_p
        context=user.GetWindowDpiAwarenessContext(ctypes.c_void_p(hwnd))
    return user.GetAwarenessFromDpiAwarenessContext(context)


def metric(value,factor,floor=1):return max(floor,round(value*factor))


def minimum(factor):return (metric(260,min(1,factor),160),metric(156,min(1,factor),96))


def panel_css(css,factor):
    def replace(match):
        return str(max(0,round(float(match.group(1))*factor)))+'px'
    return re.sub(r'([0-9]+(?:\.[0-9]+)?)px',replace,css)
