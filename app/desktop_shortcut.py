"""A middle-button press toggles icons only on Explorer's desktop surfaces."""
import ctypes
import logging
from ctypes import wintypes
from PyQt5.QtCore import QObject,Qt,pyqtSignal


class MouseEvent(ctypes.Structure):
    _fields_=[('pt',wintypes.POINT),('mouseData',wintypes.DWORD),('flags',wintypes.DWORD),
              ('time',wintypes.DWORD),('extra',ctypes.c_size_t)]


class DesktopMiddleShortcut(QObject):
    triggered=pyqtSignal()
    pending=pyqtSignal()

    def __init__(self,parent=None,disabled=False):
        super().__init__(parent)
        self.disabled=disabled;self.hook=None;self.enabled=False
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.callback_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
        self.callback=self.callback_type(self.mouse_event)
        self.user.SetWindowsHookExW.argtypes=[ctypes.c_int,self.callback_type,wintypes.HINSTANCE,wintypes.DWORD]
        self.user.SetWindowsHookExW.restype=wintypes.HANDLE
        self.user.UnhookWindowsHookEx.argtypes=[wintypes.HANDLE]
        self.user.CallNextHookEx.argtypes=[wintypes.HANDLE,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM]
        self.user.CallNextHookEx.restype=ctypes.c_ssize_t
        self.user.WindowFromPoint.argtypes=[wintypes.POINT];self.user.WindowFromPoint.restype=wintypes.HWND
        self.user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];self.user.GetAncestor.restype=wintypes.HWND
        self.user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
        self.user.GetShellWindow.restype=wintypes.HWND
        self.user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetModuleHandleW.argtypes=[wintypes.LPCWSTR];self.kernel.GetModuleHandleW.restype=wintypes.HMODULE
        # Never perform configuration writes or Explorer changes in the hook.
        self.pending.connect(self.dispatch,Qt.QueuedConnection)
        self.destroyed.connect(lambda:self.close())

    def class_name(self,hwnd):
        text=ctypes.create_unicode_buffer(128)
        self.user.GetClassNameW(hwnd,text,len(text))
        return text.value

    def process_id(self,hwnd):
        pid=wintypes.DWORD();self.user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        return pid.value

    def on_desktop(self,point):
        hwnd=self.user.WindowFromPoint(point)
        if not hwnd or self.class_name(hwnd) not in ('Progman','WorkerW','SHELLDLL_DefView','SysListView32'):return False
        root=self.user.GetAncestor(hwnd,2)  # GA_ROOT: excludes Explorer folder windows.
        if not root or self.class_name(root) not in ('Progman','WorkerW'):return False
        shell=self.user.GetShellWindow()
        return bool(shell and self.process_id(root)==self.process_id(shell))

    def mouse_event(self,code,message,pointer):
        try:
            if self.enabled and code==0 and message==0x0207 and pointer:  # WM_MBUTTONDOWN, never wheel/up.
                event=ctypes.cast(pointer,ctypes.POINTER(MouseEvent)).contents
                if not event.flags&1 and self.on_desktop(event.pt):self.pending.emit()
        except Exception:
            logging.exception('Desktop middle-button detection failed')
        # Preserve the original mouse message and all other applications' hooks.
        return self.user.CallNextHookEx(self.hook,code,message,pointer)

    def dispatch(self):
        if self.enabled:self.triggered.emit()

    def set_enabled(self,enabled):
        enabled=bool(enabled) and not self.disabled
        if not enabled:self.close();return
        if self.hook:return
        self.hook=self.user.SetWindowsHookExW(14,self.callback,self.kernel.GetModuleHandleW(None),0)
        self.enabled=bool(self.hook)
        if not self.hook:logging.warning('Unable to register desktop middle-button shortcut: %s',ctypes.get_last_error())

    def close(self):
        self.enabled=False
        if self.hook:
            if not self.user.UnhookWindowsHookEx(self.hook):logging.warning('Unable to release desktop mouse hook')
            self.hook=None
