"""Opt-in composition effects for classic Windows taskbars."""
import ctypes
import os
import sys
from ctypes import wintypes

MODES = [('跟随系统', 'system'), ('全透明', 'clear'), ('自定义颜色', 'color'),
         ('亚克力模糊', 'acrylic'), ('玻璃模糊', 'glass')]


class AccentPolicy(ctypes.Structure):
    _fields_ = [('state', ctypes.c_int), ('flags', ctypes.c_int),
                ('color', wintypes.DWORD), ('animation', ctypes.c_int)]


class CompositionData(ctypes.Structure):
    _fields_ = [('attribute', ctypes.c_int), ('data', ctypes.c_void_p),
                ('size', ctypes.c_size_t)]


def accent_policy(mode, color, opacity):
    from PyQt5.QtGui import QColor

    shade = QColor(color)
    if not shade.isValid():
        shade = QColor('#85c6ed')
    alpha = round(255 * max(0, min(100, opacity)) / 100)
    abgr = (alpha << 24) | (shade.blue() << 16) | (shade.green() << 8) | shade.red()
    if mode == 'clear':
        return AccentPolicy(2, 0, 0, 0)
    if mode == 'color':
        return AccentPolicy(2, 0, abgr, 0)
    if mode == 'acrylic':
        return AccentPolicy(4, 0, abgr | 0x01000000 if not alpha else abgr, 0)
    if mode == 'glass':
        return AccentPolicy(3, 0, abgr, 0)
    return AccentPolicy(0, 0, 0, 0)


class TaskbarAppearance:
    def __init__(self, dock, log):
        from PyQt5.QtCore import QTimer

        self.dock = dock
        self.log = log
        self.active = set()
        self.timer = QTimer(dock)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self.refresh)
        self.backend = None
        self.xaml = None
        if dock.preview or os.environ.get('FISHDOCK_TEST_DESKTOP'):
            self.status = '隔离预览中不修改系统任务栏。'
        elif sys.platform == 'win32' and sys.getwindowsversion().build >= 22000:
            from pathlib import Path
            directory = Path(os.environ['LOCALAPPDATA']) / 'BigFishDock/TaskbarBackend/2026.2'
            if (directory / 'TranslucentTB.exe').is_file():
                from taskbar_xaml import XamlTaskbar
                self.xaml = XamlTaskbar(dock, directory, log)
                self.backend = self.xaml
                self.status = 'Windows 11 XAML 后端已就绪。'
            else:
                self.status = '尚未安装 Windows 11 任务栏组件。'
        elif sys.platform != 'win32':
            self.status = '当前 Windows 任务栏需要 XAML 后端，保留系统外观。'
        else:
            self.status = '传统任务栏后端可用，保存后应用。'
            try:
                self.backend = self.bind()
            except (OSError, AttributeError):
                self.status = '当前系统缺少任务栏合成接口。'

    @staticmethod
    def bind():
        user = ctypes.WinDLL('user32', use_last_error=True)
        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
        user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.SetWindowCompositionAttribute.argtypes = [wintypes.HWND, ctypes.POINTER(CompositionData)]
        user.SetWindowCompositionAttribute.restype = wintypes.BOOL
        user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

        def windows():
            result = set()

            @callback
            def collect(hwnd, _):
                name = ctypes.create_unicode_buffer(64)
                user.GetClassNameW(hwnd, name, len(name))
                if name.value in ('Shell_TrayWnd', 'Shell_SecondaryTrayWnd'):
                    pid = wintypes.DWORD()
                    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    result.add((hwnd, pid.value))
                return True

            user.EnumWindows(collect, 0)
            return result

        def apply(hwnd, policy):
            data = CompositionData(19, ctypes.addressof(policy), ctypes.sizeof(policy))
            return bool(user.SetWindowCompositionAttribute(hwnd, ctypes.byref(data)))

        def restore(hwnd):
            apply(hwnd, accent_policy('system', '', 0))
            user.PostMessageW(hwnd, 0x031A, 0, 0)

        return windows, apply, restore

    def sync(self):
        if self.xaml is not None:
            self.xaml.sync()
            return
        if self.backend is None:
            return
        if self.dock.cfg['taskbar_mode'] == 'system':
            self.close()
            return
        self.refresh(force=True)
        self.timer.start()

    def refresh(self, force=False):
        windows, apply, _ = self.backend
        current = windows()
        self.active.intersection_update(current)
        cfg = self.dock.cfg
        policy = accent_policy(cfg['taskbar_mode'], cfg['taskbar_color'], cfg['taskbar_opacity'])
        rejected = False
        for handle in current if force else current - self.active:
            if apply(handle[0], policy):
                self.active.add(handle)
            else:
                rejected = True
        if rejected and force:
            self.log('系统拒绝应用部分任务栏效果。')

    def close(self):
        if self.xaml is not None:
            self.xaml.close()
            return
        self.timer.stop()
        if self.backend:
            windows, _, restore = self.backend
            for hwnd, _ in self.active & windows():
                restore(hwnd)
        self.active.clear()
