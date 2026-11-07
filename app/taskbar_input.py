"""Repair only a taskbar overlay hidden beneath its own Explorer surface."""
import ctypes as C
import os
from ctypes import wintypes as W


def restore_input_layer(hwnd,taskbar,user=None):
    user=user or C.windll.user32
    user.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
    user.WindowFromPoint.argtypes=[W.POINT];user.WindowFromPoint.restype=W.HWND
    user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
    user.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
    rect=W.RECT()
    if not user.GetWindowRect(hwnd,C.byref(rect)):return False
    hidden=False
    for fraction in (.15,.5,.85):
        hit=user.WindowFromPoint(W.POINT(round(rect.left+(rect.right-rect.left)*fraction),(rect.top+rect.bottom)//2))
        root=user.GetAncestor(hit,2) if hit else 0
        if root==taskbar:hidden=True
        elif root!=hwnd:return False  # Respect menus, dialogs and other apps.
    if not hidden:return False
    # No activation, geometry or owner changes. Reassert only our own window.
    return bool(user.SetWindowPos(hwnd,-1,0,0,0,0,0x213))


def has_foreign_overlay(hwnd, taskbar):
    """Detect a pinned tool window even when the strip sits above it."""
    user = C.windll.user32
    dwm = C.windll.dwmapi
    user.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user.GetWindowLongPtrW.argtypes = [W.HWND, C.c_int]
    user.GetWindowLongPtrW.restype = C.c_ssize_t
    user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    user.IsWindowVisible.argtypes = [W.HWND]
    user.IsIconic.argtypes = [W.HWND]
    user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
    dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]
    bounds = W.RECT()
    if not user.GetWindowRect(hwnd, C.byref(bounds)):
        return False
    shell_pid = W.DWORD()
    user.GetWindowThreadProcessId(taskbar, C.byref(shell_pid))
    ignored = {os.getpid(), shell_pid.value}
    found = False
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    @callback_type
    def visit(window, _):
        nonlocal found
        if window in (hwnd, taskbar) or not user.IsWindowVisible(window) or user.IsIconic(window):
            return True
        style = user.GetWindowLongPtrW(window, -20)
        if not style & 0x8 or style & 0x20:
            return True
        pid = W.DWORD()
        user.GetWindowThreadProcessId(window, C.byref(pid))
        if pid.value in ignored:
            return True
        other = W.RECT()
        if not user.GetWindowRect(window, C.byref(other)):
            return True
        if (max(bounds.left, other.left) >= min(bounds.right, other.right)
                or max(bounds.top, other.top) >= min(bounds.bottom, other.bottom)):
            return True
        cloaked = W.DWORD()
        dwm.DwmGetWindowAttribute(window, 14, C.byref(cloaked), C.sizeof(cloaked))
        if cloaked.value:
            return True
        name = C.create_unicode_buffer(96)
        user.GetClassNameW(window, name, len(name))
        # This system canvas can remain visible while no pen input is active.
        if name.value.startswith('ShellHandwritingCanvas'):
            return True
        found = True
        return False

    user.EnumWindows.argtypes = [callback_type, W.LPARAM]
    user.EnumWindows(visit, 0)
    return found
