"""Opt-in composition effects for classic Windows taskbars."""
import ctypes
import os
import sys
from pathlib import Path
from ctypes import wintypes
from PyQt5.QtCore import QObject, pyqtSignal
from taskbar_xaml import effect_key

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


class _TaskbarEvents(QObject):
    changed = pyqtSignal(str)


class TaskbarAppearance:
    def __init__(self, dock, log):
        from PyQt5.QtCore import QTimer

        self.dock = dock
        self.log = log
        self.events = _TaskbarEvents(dock)
        self.changed = self.events.changed
        self.error = ''
        self._effect = None
        self._pending_effect = None
        self.active = set()
        self.timer = QTimer(dock)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self.refresh)
        self.backend = None
        self.xaml = None
        self.payload = None
        self.install_process = None
        from taskbar_text import TaskbarText
        import dock as api
        self.text = TaskbarText(Path(api.CONFIG_DIR)/'taskbar-text-restore.json',log,
            enabled=sys.platform=='win32' and not dock.preview and not os.environ.get('FISHDOCK_TEST_DESKTOP'))
        if dock.preview or os.environ.get('FISHDOCK_TEST_DESKTOP'):
            self.status = '隔离预览中不修改系统任务栏。'
        elif sys.platform == 'win32' and sys.getwindowsversion().build >= 22000:
            self.directory = Path(os.environ['LOCALAPPDATA']) / 'BigFishDock/TaskbarBackend/2026.2'
            payload = Path(getattr(sys, '_MEIPASS', '')) / 'taskbar-payload'
            native_arch = os.environ.get('PROCESSOR_ARCHITEW6432') or os.environ.get('PROCESSOR_ARCHITECTURE')
            if native_arch == 'AMD64' and getattr(sys, 'frozen', False) and (payload / 'backend/TranslucentTB.exe').is_file():
                self.payload = payload
            if not self.load_xaml():
                self.status = ('尚未安装任务栏组件，可从本程序离线安装。' if self.payload else
                               '尚未安装任务栏组件。请使用完整安装包，勾选任务栏效果组件。')
        elif sys.platform != 'win32':
            self.status = '当前 Windows 任务栏需要 XAML 后端，保留系统外观。'
        else:
            self.status = '传统任务栏后端可用，保存后应用。'
            try:
                self.backend = self.bind()
            except (OSError, AttributeError):
                self.status = '当前系统缺少任务栏合成接口。'

    def load_xaml(self):
        if self.xaml is not None:
            return True
        if not (self.directory / 'TranslucentTB.exe').is_file():
            return False
        from taskbar_xaml import XamlTaskbar
        self.xaml = XamlTaskbar(self.dock, self.directory, self.log, self.xaml_completed)
        self.backend = self.xaml
        self.status = 'Windows 11 XAML 后端已就绪。'
        return True

    def install_offline(self, complete):
        if self.payload is None or self.install_process is not None:
            return False
        from PyQt5.QtCore import QProcess
        process = QProcess(self.dock)
        self.install_process = process

        def finish(ok):
            if self.install_process is not process:
                return
            self.install_process = None
            process.deleteLater()
            if ok and self.load_xaml():
                self.sync()
                complete(True, self.status)
            else:
                complete(False, '组件安装失败，可重试或使用完整安装包。日志位于 %TEMP%/BigFishDockpro-taskbar-install.log。')

        process.finished.connect(lambda code, status: finish(code == 0 and status == QProcess.NormalExit))
        process.errorOccurred.connect(lambda error: finish(False) if error == QProcess.FailedToStart else None)
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        process.start(str(powershell), ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                      '-ExecutionPolicy', 'Bypass', '-File', str(self.payload / 'install_taskbar_frameworks.ps1'),
                      '-BackendDirectory', str(self.directory)])
        return True

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

    def set_status(self, message, error=''):
        self.status, self.error = message, error
        signal = getattr(self, 'changed', None)
        if signal is not None:
            signal.emit(message)

    def xaml_completed(self, effect, success, message):
        if effect != effect_key(self.dock.cfg):
            return
        self._pending_effect = None
        self._effect = effect if success else None
        self.set_status(message, '' if success else message)

    def retry(self):
        self._effect = None
        self._pending_effect = None
        return self.sync(force=True)

    def sync(self, force=False):
        self.text.sync(self.dock.cfg.get('taskbar_text_mode','system'))
        effect = effect_key(self.dock.cfg)
        if not force and (getattr(self, '_effect', None) == effect or
                          getattr(self, '_pending_effect', None) == effect):
            return not bool(getattr(self, 'error', ''))
        if self.xaml is not None:
            self._pending_effect = effect
            self.set_status('正在应用任务栏效果…')
            self.xaml.sync()
            return not bool(getattr(self, 'error', ''))
        if self.backend is None:
            return False
        if self.dock.cfg['taskbar_mode'] == 'system':
            self.restore_native()
            self._effect = effect
            self.set_status('任务栏外观已恢复跟随系统。')
            return True
        accepted = self.refresh(force=True)
        self._effect = effect if accepted else None
        self.timer.start()
        return accepted

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
        if rejected:
            self._effect = None
            self.set_status('系统未接受部分任务栏效果，可点击重新应用。', '系统未接受部分任务栏效果。')
            if force:
                self.log(self.error)
        elif force or self.error:
            self._effect = effect_key(cfg)
            self.set_status('任务栏效果已应用。')
        return not rejected

    def restore_native(self):
        self.timer.stop()
        if self.backend:
            windows, _, restore = self.backend
            for hwnd, _ in self.active & windows():
                restore(hwnd)
        self.active.clear()

    def close(self):
        self.text.close()
        if self.xaml is not None:self.xaml.close()
        else:self.restore_native()
