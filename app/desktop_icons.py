"""Temporarily hide Explorer's icon view; restore its original visibility."""
import ctypes
import json
import logging
import os
from pathlib import Path
from ctypes import wintypes
from PyQt5.QtCore import QObject, QTimer


class DesktopIcons(QObject):
    def __init__(self, preview=False, finder=None, journal_path=None):
        super().__init__()
        self.preview, self.finder = preview, finder
        self.enabled = False
        self.hidden = {}
        self.journal = Path(journal_path) if journal_path and not preview else None
        self.hook = None
        self.user = ctypes.windll.user32
        self.user.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
        self.user.FindWindowExW.restype = wintypes.HWND
        self.user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetParent.argtypes = [wintypes.HWND]
        self.user.GetParent.restype = wintypes.HWND
        self.user.IsWindow.argtypes = [wintypes.HWND]
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.enum_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.enum_type, wintypes.LPARAM]
        self.event_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                            wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
        self.callback = self.event_type(self.event)
        self.user.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
                                            self.event_type, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        self.user.SetWinEventHook.restype = wintypes.HANDLE
        self.user.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.hide_icons)
        self.destroyed.connect(lambda: self.restore_native())
        if self.journal and self.journal.exists():
            try:
                records = json.loads(self.journal.read_text(encoding='utf-8'))
                self.hidden = {int(hwnd): (int(pid), bool(visible)) for hwnd, pid, visible in records}
                self.restore_native()
            except (OSError, ValueError, TypeError):
                logging.warning('Unable to recover desktop-icon visibility journal')

    def views(self):
        if self.finder: return self.finder()
        if self.preview: return []
        views = []
        def visit(hwnd, data):
            # Only Explorer desktop hosts; folder windows may also contain DefView.
            name=ctypes.create_unicode_buffer(128)
            self.user.GetClassNameW(hwnd,name,len(name))
            if name.value not in ('Progman','WorkerW'):return True
            view = self.user.FindWindowExW(hwnd, None, 'SHELLDLL_DefView', None)
            if view:
                icons = self.user.FindWindowExW(view, None, 'SysListView32', None)
                if icons: views.append(icons)
            return True
        self.user.EnumWindows(self.enum_type(visit), 0)
        return views

    def pid(self, hwnd):
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def event(self, hook, event, hwnd, object_id, child, thread, timestamp):
        if not self.enabled or not hwnd or object_id != 0: return
        name = ctypes.create_unicode_buffer(128)
        self.user.GetClassNameW(hwnd, name, len(name))
        if name.value in ('SysListView32', 'SHELLDLL_DefView') and not self.timer.isActive():
            self.timer.start()

    def set_enabled(self, enabled):
        enabled = bool(enabled) and (not self.preview or self.finder is not None)
        if enabled == self.enabled: return
        if not enabled:
            self.timer.stop()
            self.restore_native()
            return
        self.enabled = True
        self.hook = self.user.SetWinEventHook(0x8002, 0x8002, None, self.callback, 0, 0, 0)
        self.hide_icons()

    def hide_icons(self):
        if not self.enabled: return
        views = self.views()
        records = dict(self.hidden)
        for hwnd in views:
            if hwnd not in records or records[hwnd][0] != self.pid(hwnd):
                records[hwnd] = (self.pid(hwnd), bool(self.user.GetWindowLongW(hwnd, -16) & 0x10000000))
        if self.journal and (records != self.hidden or not self.journal.exists()):
            try:
                self.journal.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.journal.with_suffix('.tmp')
                temporary.write_text(json.dumps([[hwnd, pid, visible] for hwnd, (pid, visible) in records.items()]), encoding='utf-8')
                os.replace(temporary, self.journal)
            except OSError:
                logging.warning('Desktop icons kept visible because visibility journal could not be saved')
                return
        self.hidden = records
        for hwnd in views:
            self.user.ShowWindow(hwnd, 0)

    def legacy_view(self, hwnd):
        # An old journal may include a folder view. Restore only the exact
        # surviving Explorer list view recorded by that version.
        if self.finder is not None or not self.user.IsWindow(hwnd):return False
        name=ctypes.create_unicode_buffer(128);self.user.GetClassNameW(hwnd,name,len(name))
        if name.value!='SysListView32':return False
        parent=self.user.GetParent(hwnd)
        if not parent:return False
        self.user.GetClassNameW(parent,name,len(name))
        return name.value=='SHELLDLL_DefView'

    def restore_native(self):
        self.enabled = False
        if self.hook:
            self.user.UnhookWinEvent(self.hook)
            self.hook = None
        if not self.hidden: return
        current = set(self.views());remaining={}
        for hwnd, (pid, was_visible) in self.hidden.items():
            if (hwnd in current or self.legacy_view(hwnd)) and self.pid(hwnd) == pid and was_visible:
                self.user.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                if not self.user.GetWindowLongW(hwnd,-16)&0x10000000:remaining[hwnd]=(pid,was_visible)
        self.hidden=remaining
        if self.journal:
            try:
                if remaining:
                    temporary=self.journal.with_suffix('.tmp')
                    temporary.write_text(json.dumps([[hwnd,pid,visible] for hwnd,(pid,visible) in remaining.items()]),encoding='utf-8')
                    os.replace(temporary,self.journal)
                else:self.journal.unlink(missing_ok=True)
            except OSError: logging.warning('Unable to update desktop-icon visibility journal')

    def close(self):
        self.timer.stop()
        self.restore_native()
