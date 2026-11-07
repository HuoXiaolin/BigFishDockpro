"""Stack the readout without activating it or moving Explorer or pinned tools."""
import ctypes as C
import os
from ctypes import wintypes as W
from platform_services import same_monitor
from window_layers import LAYER_FLAGS, covers_above, is_topmost


def place_layer(hwnd, taskbar, layer, user=None, *, cover=None):
    user = user or C.windll.user32
    user.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
    if layer == 'top':
        if not same_monitor(cover,hwnd):cover=None
        after = overlapping_topmost(hwnd, taskbar, user, cover) or -1
    else:
        user.GetWindow.argtypes = [W.HWND, W.UINT]
        user.GetWindow.restype = W.HWND
        user.GetWindowLongPtrW.argtypes = [W.HWND, C.c_int]
        user.GetWindowLongPtrW.restype = C.c_ssize_t
        shell_topmost = bool(user.GetWindowLongPtrW(taskbar, -20) & 0x8)
        if not shell_topmost and user.GetWindowLongPtrW(hwnd, -20) & 0x8:
            user.SetWindowPos(hwnd, -2, 0, 0, 0, 0, LAYER_FLAGS)
        # A bottom readout belongs just above its taskbar, otherwise the taskbar itself covers it.
        after = user.GetWindow(taskbar, 3)
        if after == hwnd:
            return True
        if not shell_topmost and after and user.GetWindowLongPtrW(after, -20) & 0x8:
            after = 0
        if not after:
            after = -1 if shell_topmost else 0
    return bool(user.SetWindowPos(hwnd, after, 0, 0, 0, 0, LAYER_FLAGS))


def restore_input_layer(hwnd,taskbar,user=None,*,cover=None,transparent=False):
    user=user or C.windll.user32
    if covers_above(cover,hwnd) or (transparent and (not is_topmost(hwnd) or covers_above(taskbar,hwnd))):
        return place_layer(hwnd,taskbar,'top',user,cover=cover)
    if transparent:return False
    user.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
    user.WindowFromPoint.argtypes=[W.POINT];user.WindowFromPoint.restype=W.HWND
    user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
    rect=W.RECT()
    if not user.GetWindowRect(hwnd,C.byref(rect)):return False
    hidden=False
    for fraction in (.15,.5,.85):
        hit=user.WindowFromPoint(W.POINT(round(rect.left+(rect.right-rect.left)*fraction),(rect.top+rect.bottom)//2))
        root=user.GetAncestor(hit,2) if hit else 0
        if root==taskbar:hidden=True
        elif root!=hwnd:return False  # Respect menus, dialogs and other apps.
    if not hidden and is_topmost(hwnd):return False
    # No activation, geometry or owner changes. Reassert only our own window.
    return place_layer(hwnd, taskbar, 'top', user, cover=cover)


def overlapping_topmost(hwnd, taskbar, user, cover=None):
    """Find the lowest overlapping topmost window so pinned tools stay interactive."""
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
        return None
    shell_pid = W.DWORD()
    user.GetWindowThreadProcessId(taskbar, C.byref(shell_pid))
    ignored = {os.getpid(), shell_pid.value}
    found = None
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    @callback_type
    def visit(window, _):
        nonlocal found
        # The fullscreen window may itself be topmost. Leave small pinned tools
        # already above it in place, and don't insert under the fullscreen window.
        if window == cover:
            return False
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
        found = window
        return True

    user.EnumWindows.argtypes = [callback_type, W.LPARAM]
    user.EnumWindows(visit, 0)
    return found
