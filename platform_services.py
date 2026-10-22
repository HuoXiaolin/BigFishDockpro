"""Small Windows services without a second runtime or a permanent worker thread."""
import ctypes
from ctypes import wintypes
import os


def foreground_fullscreen(exclude_pid=None):
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user.MonitorFromWindow.restype = wintypes.HANDLE
    user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    hwnd = user.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == (exclude_pid or os.getpid()):
        return False
    user.IsZoomed.argtypes = [wintypes.HWND]
    user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    if user.IsZoomed(hwnd) and user.GetWindowLongW(hwnd, -16) & 0x00c00000:
        return False
    name = ctypes.create_unicode_buffer(256)
    user.GetClassNameW(hwnd, name, len(name))
    if name.value in ('Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'):
        return False
    rect = wintypes.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    class MONITORINFO(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                    ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
    info = MONITORINFO()
    info.size = ctypes.sizeof(info)
    if not user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
        return False
    return covers_monitor((rect.left, rect.top, rect.right, rect.bottom),
                          (info.monitor.left, info.monitor.top, info.monitor.right, info.monitor.bottom))


def covers_monitor(rect, monitor):
    # Maximized work-area windows leave the taskbar gap and must not count.
    return all(abs(a-b) <= 2 for a, b in zip(rect, monitor))


def set_priority(level):
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    # Above-normal, never HIGH/REALTIME, to preserve normal Windows responsiveness.
    classes = {'low': 0x4000, 'normal': 0x20, 'high': 0x8000}
    return bool(kernel.SetPriorityClass(kernel.GetCurrentProcess(), classes.get(level, 0x20)))
