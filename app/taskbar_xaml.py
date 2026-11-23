"""Portable TranslucentTB adapter with owned process lifecycle."""
import ctypes
import json
import os
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from time import monotonic
from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtGui import QColor
from probe_lifecycle import allowed


_ENUM_CHILD = getattr(ctypes, 'WINFUNCTYPE', ctypes.CFUNCTYPE)(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


@lru_cache(maxsize=1)
def user32():
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    user.EnumChildWindows.argtypes = [wintypes.HWND, _ENUM_CHILD, wintypes.LPARAM]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    user.RegisterWindowMessageW.restype = wintypes.UINT
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.PostMessageW.restype = wintypes.BOOL
    return user


def window_pid(user, window):
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(window, ctypes.byref(pid))
    return pid.value


def shell_snapshot():
    user = user32()
    hwnd = user.FindWindowW('Shell_TrayWnd', None)
    pid = window_pid(user, hwnd) if hwnd else 0
    if not pid:
        return None
    islands = []
    label = ctypes.create_unicode_buffer(96)

    # The pinned TranslucentTB backend detects these children too:
    # https://github.com/TranslucentTB/TranslucentTB/blob/2026.2/TranslucentTB/taskbar/taskbarattributeworker.cpp#L1068-L1143
    # The frame HWND can precede them.
    @_ENUM_CHILD
    def collect(child, _):
        if (user.GetClassNameW(child, label, len(label))
                and label.value == 'Windows.UI.Composition.DesktopWindowContentBridge'
                and user.GetWindowTextW(child, label, len(label))
                and label.value == 'DesktopWindowXamlSource'):
            islands.append(child)
        return True

    user.EnumChildWindows(hwnd, collect, 0)
    if user.FindWindowW('Shell_TrayWnd', None) == hwnd and window_pid(user, hwnd) == pid:
        return hwnd, pid, tuple(sorted(islands))
    return None


def configuration(cfg):
    modes = {'system': 'normal', 'clear': 'clear', 'color': 'opaque',
             'acrylic': 'acrylic', 'glass': 'blur'}
    mode = cfg.get('taskbar_mode', 'system')
    color = QColor(cfg.get('taskbar_color', '#85c6ed'))
    if not color.isValid():
        color = QColor('#85c6ed')
    alpha = round(max(0, min(100, int(cfg.get('taskbar_opacity', 32)))) * 2.55)
    tint = '#00000000' if mode in ('system', 'clear') else color.name() + f'{alpha:02x}'
    result = {'desktop_appearance': {'accent': modes.get(mode, 'normal'), 'color': tint,
              'blur_radius': max(0, min(50, int(cfg.get('taskbar_blur', 12)))),
              'show_line': mode == 'system'}, 'hide_tray': True, 'disable_saving': True,
              # The DLL and overflow preferences share the versioned LocalAppData directory.
              'copy_dlls': False}
    for state in ('visible_window', 'maximized_window', 'start_opened', 'search_opened',
                  'task_view_opened', 'battery_saver'):
        result[state + '_appearance'] = {'enabled': False}
    return result


EFFECT_KEYS = ('taskbar_mode', 'taskbar_color', 'taskbar_opacity', 'taskbar_blur')
OVERFLOW_STYLE = 'tray_overflow_style'


def effect_key(cfg):
    return tuple(cfg.get(key) for key in (*EFFECT_KEYS, OVERFLOW_STYLE))


def overflow_requested(cfg):
    return cfg.get('shell_notifications_enabled', False) and cfg.get('shell_notifications_tray_overflow', True)


def effect_settings(cfg):
    settings = {key: cfg[key] for key in EFFECT_KEYS}
    if overflow_requested(cfg):
        import dock as api
        from shell_appearance import system_appearance
        from shell_appearance_model import appearance, brush_spec
        settings[OVERFLOW_STYLE] = brush_spec(appearance(cfg, 'notifications', *system_appearance(api)))
    return settings


def worker_needed(cfg):
    return cfg['taskbar_mode'] != 'system' or bool(cfg.get(OVERFLOW_STYLE))


def overflow_configuration(style):
    if style is None:
        return '[Appearance]\nBrush=0\n'
    from shell_appearance import owner_start_time
    mode, tint, amount = style
    index = {'solid': 1, 'acrylic': 2, 'blur': 3}[mode]
    return (f'[Appearance]\nBrush={index}\nTint={tint[1:]}\nAmount={round(amount * 100)}\n'
            f'OwnerPid={os.getpid()}\nOwnerStarted={owner_start_time()}\n')


def program_path(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    process = kernel.OpenProcess(0x1000, False, pid)
    if process:
        try:
            path = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(path))
            if kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                return Path(path.value)
        finally:
            kernel.CloseHandle(process)
    return None


def resident_program():
    """Identify the TranslucentTB control window on this desktop, including portable copies."""
    user = user32()
    window = user.FindWindowW('TrayWindow', 'TranslucentTB')
    return program_path(window_pid(user, window)) if window else None


def request_refresh(program, owned_pid):
    """Ask our resident worker to rediscover taskbars using its existing handler."""
    user = user32()
    tray = user.FindWindowW('TrayWindow', 'TranslucentTB')
    worker = user.FindWindowW('TTB_WorkerWindow', 'TTB_WorkerWindow')
    if not (tray and worker):
        return False
    pid = window_pid(user, tray)
    if not pid or window_pid(user, worker) != pid:
        return False
    if owned_pid is not None:
        if owned_pid != pid:
            return False
    elif program_path(pid) != program:
        return False
    message = user.RegisterWindowMessageW('TaskbarCreated')
    return bool(message and user.PostMessageW(worker, message, 0, 0))


class XamlTaskbar:
    SETTLE_MS = 1200
    CLASSIC_GRACE_SECONDS = 12
    RECOVERY_DELAYS = (2000, 5000, 10000, 20000)
    REFRESH_DELAYS = (2500, 2000, 4000, 8000)

    def __init__(self, dock, directory, log, complete=None):
        self.dock, self.directory, self.log = dock, Path(directory), log
        self.process = QProcess(dock)
        self.program = self.directory / 'TranslucentTB.exe'
        self.process.setProgram(str(self.program))
        self.process.setWorkingDirectory(str(self.directory))
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed)
        self.process.started.connect(self.started)
        self.complete = complete
        self.pending = None
        self.starting = None
        self.active = None
        self.closed = False
        self.shared = False
        self.stop_timer = QTimer(dock)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self.process.kill)
        self.monitor_shell = not (getattr(dock,'preview',False) or os.environ.get('FISHDOCK_TEST_DESKTOP'))
        self.shell = None
        self.shell_since = 0
        self.waiting_for_shell = False
        self.rebind = False
        self.desired = None
        self.retries = 0
        self.shell_timer = QTimer(dock);self.shell_timer.setInterval(2500)
        self.shell_timer.timeout.connect(self.shell_changed)
        self.apply_timer = QTimer(dock);self.apply_timer.setSingleShot(True)
        self.apply_timer.timeout.connect(self.apply_desired)
        self.refresh_timer = QTimer(dock);self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh_backend)
        self.refresh_attempt = 0

    def shell_ready(self):
        return self.shell is not None and (
            len(self.shell[2]) in (1, 2) or monotonic() - self.shell_since >= self.CLASSIC_GRACE_SECONDS)

    def observe_shell(self, current):
        if current == self.shell:
            return
        self.shell = current
        self.shell_since = monotonic()
        self.retries = 0
        self.waiting_for_shell = self.rebind = True
        self.apply_timer.stop()
        self.refresh_timer.stop()

    def shell_changed(self):
        if self.closed or self.desired is None or not allowed():
            return
        if self.desired.get(OVERFLOW_STYLE):
            # Reuse shell recovery to follow Windows theme/transparency changes.
            settings = effect_settings(self.dock.cfg)
            if settings != self.desired:
                self.sync(settings=settings)
                return
        self.observe_shell(shell_snapshot())
        self.queue_apply()

    def queue_apply(self):
        if (self.waiting_for_shell and self.pending is None and self.shell_ready()
                and not self.apply_timer.isActive()):
            self.apply_timer.start(self.SETTLE_MS)

    def apply_desired(self):
        if self.closed or self.pending is not None or self.desired is None or not allowed():
            return
        current = shell_snapshot()
        if current != self.shell:
            self.observe_shell(current)
            self.queue_apply()
        elif self.shell_ready():
            self.waiting_for_shell = False
            self.apply(self.desired)

    def schedule_recovery(self):
        if (self.monitor_shell and self.desired is not None and self.shell_ready()
                and self.retries < len(self.RECOVERY_DELAYS) and allowed()):
            self.apply_timer.start(self.RECOVERY_DELAYS[self.retries])
            self.retries += 1

    def queue_refresh(self):
        self.rebind = True
        if not self.refresh_timer.isActive() and allowed():
            self.refresh_attempt = 0
            self.refresh_timer.start(self.REFRESH_DELAYS[0])

    def refresh_backend(self):
        cfg = self.starting or self.active
        if (self.closed or self.pending is not None or self.desired is None or not self.rebind
                or cfg != self.desired or not allowed()):
            return
        current = shell_snapshot()
        if current != self.shell or not self.shell_ready():
            self.observe_shell(current)
            self.queue_apply()
            return
        state = self.process.state()
        if state == QProcess.Running or self.shared:
            pid = self.process.processId() if state == QProcess.Running else None
            if request_refresh(self.program, pid):
                self.active, self.starting = cfg, None
                self.rebind = False
                message = '任务栏组件已连接，已请求应用当前效果。'
                self.log(message)
                self.report(cfg, True, message)
                return
        if state == QProcess.NotRunning and self.shared and resident_program() is None:
            self.shared = False
            self.active = None
            self.waiting_for_shell = True
            self.queue_apply()
            return
        self.refresh_attempt += 1
        if self.refresh_attempt < len(self.REFRESH_DELAYS):
            self.refresh_timer.start(self.REFRESH_DELAYS[self.refresh_attempt])
        else:
            self.report(cfg, False, '任务栏组件未能连接到任务栏，可点击重新应用。')

    def write(self, cfg):
        path = self.directory / 'settings.json'
        temporary = path.with_suffix('.pending')
        overflow = self.directory / 'tray-overflow.ini'
        staged_overflow = overflow.with_suffix('.pending')
        try:
            temporary.write_text(json.dumps(configuration(cfg), ensure_ascii=False, indent=2), encoding='utf-8')
            if cfg.get(OVERFLOW_STYLE) or overflow.exists():
                staged_overflow.write_text(overflow_configuration(cfg.get(OVERFLOW_STYLE)), encoding='ascii')
                os.replace(staged_overflow, overflow)
            # The existing taskbar worker sees this replacement and refreshes both surfaces.
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
            staged_overflow.unlink(missing_ok=True)

    def configuration_matches(self, cfg):
        try:
            with (self.directory / 'settings.json').open('rb') as stream:
                content = stream.read(65537)
            if len(content) > 65536:
                return False
            actual = json.loads(content.decode('utf-8-sig'))
        except (OSError, ValueError, RecursionError):
            return False
        expected = configuration(cfg)
        if not isinstance(actual, dict) or any(actual.get(key) != value for key, value in expected.items()):
            return False
        style = cfg.get(OVERFLOW_STYLE)
        overflow = self.directory / 'tray-overflow.ini'
        try:
            return overflow.read_text(encoding='ascii') == overflow_configuration(style)
        except FileNotFoundError:
            return style is None
        except (OSError, ValueError):
            return False

    def owns_configuration(self, cfg):
        return (worker_needed(cfg)
                and resident_program() == self.program and self.configuration_matches(cfg))

    def confirmed(self, cfg):
        return self.pending is None and not self.rebind and self.owns_configuration(cfg)

    def sync(self, force=False, settings=None):
        if self.closed or not allowed():
            return
        cfg = effect_settings(self.dock.cfg) if settings is None else settings
        self.apply_timer.stop()
        self.retries=0
        self.desired=cfg if worker_needed(cfg) else None
        if self.monitor_shell:
            if self.desired is None:
                self.suspend_session()
                self.shell = None
                self.waiting_for_shell = self.rebind = False
            else:
                self.observe_shell(shell_snapshot())
                if force:
                    self.rebind = True
                if not self.shell_timer.isActive():self.shell_timer.start()
        if self.pending is not None:
            # The owned process is stopping. Only the most recent request should run next.
            self.pending = cfg
            return
        if not worker_needed(cfg) and self.process.state() != QProcess.NotRunning:
            self.pending = cfg
            self.stop_timer.start(2000)
            self.process.terminate()
            return
        self.apply_when_ready(cfg)

    def apply_when_ready(self, cfg):
        if self.monitor_shell and worker_needed(cfg):
            if self.waiting_for_shell or self.process.state() == QProcess.NotRunning:
                self.waiting_for_shell = True
                self.shell_changed()
                return
        self.apply(cfg)

    def apply(self, cfg):
        if self.closed or not allowed():
            return
        try:
            self.write(cfg)
        except OSError as error:
            self.report(cfg, False, '任务栏效果未应用：无法保存组件配置，'+str(error)+'；可点击重新应用。')
            if getattr(error, 'winerror', None) in (32, 33):  # transient file sharing/lock
                self.schedule_recovery()
            return
        state = self.process.state()
        if not worker_needed(cfg):
            self.active = self.starting = None
            self.shared = False
            self.report(cfg, True, '任务栏外观已恢复跟随系统。')
        elif state == QProcess.Starting:
            self.starting = cfg
        elif state == QProcess.Running:
            # The portable backend watches settings.json, including atomic replacement.
            self.active = cfg
            if self.starting is not None:
                self.starting = cfg
            if self.monitor_shell and self.rebind:
                self.queue_refresh()
            else:
                self.report(cfg, True, '已更新运行中的任务栏组件配置。')
        else:
            resident = resident_program()
            if resident == self.program:
                self.shared = True
                self.active = cfg
                if self.monitor_shell and self.rebind:
                    self.queue_refresh()
                else:
                    self.report(cfg, True, '已更新运行中的任务栏组件配置。')
            elif resident is not None:
                self.report(cfg, False, '另一份 TranslucentTB 正在管理任务栏。退出该实例后可重新应用。')
            else:
                self.shared = False
                self.starting = cfg
                self.process.start()

    def report(self, cfg, success, message):
        if not success:
            self.log(message)
        if self.complete is not None:
            self.complete(effect_key(cfg), success, message)

    def started(self):
        if self.closed or self.starting is None or self.pending is not None:
            return
        if self.monitor_shell:
            # QProcess.started only confirms Windows loaded the process. Give the
            # worker and the taskbar visual tree time to initialise, then rebind.
            self.queue_refresh()
            return
        self.active, self.starting = self.starting, None
        self.report(self.active, True, '任务栏组件已启动。')

    def failed(self, error):
        # Read/write channel errors are unrelated to the watched settings file.
        # A crash is reported once with its exit code by finished().
        if self.closed or error != QProcess.FailedToStart:
            return
        if self.pending is not None:
            self.finished()
        elif not allowed():
            self.starting = None
        elif self.starting is not None:
            cfg, self.starting = self.starting, None
            self.report(cfg, False, '任务栏组件未能启动：'+self.process.errorString()+'；可点击重新应用。')
            self.schedule_recovery()

    def finished(self, code=0, status=QProcess.NormalExit):
        self.stop_timer.stop()
        self.refresh_timer.stop()
        if self.closed:
            return
        previous = self.starting or self.active
        self.active = self.starting = None
        if not allowed():
            self.pending = None
            return
        if self.pending is not None:
            cfg, self.pending = self.pending, None
            self.apply_when_ready(cfg)
        elif previous is not None:
            # A second TranslucentTB launcher exits normally after handing off to its resident.
            if status == QProcess.NormalExit and code == 0 and self.owns_configuration(previous):
                self.active = previous
                self.shared = True
                if self.monitor_shell and self.rebind:
                    self.queue_refresh()
                else:
                    self.report(previous, True, '任务栏效果由现有组件提供。')
            else:
                self.report(previous, False, f'任务栏组件已退出（退出码 {code}），可点击重新应用。')
                self.schedule_recovery()

    def suspend_session(self):
        for name in ('shell_timer', 'apply_timer', 'refresh_timer'):
            timer=getattr(self,name,None)
            if timer is not None:timer.stop()

    def close(self,shutdown=False):
        self.closed = True
        self.suspend_session()
        if getattr(self, 'shared', False) and self.active and self.owns_configuration(self.active):
            # Restore only our last configuration. The other process owns its lifecycle.
            try:
                self.write(dict(self.active, taskbar_mode='system', tray_overflow_style=None))
            except OSError as error:
                self.log('未能恢复共享任务栏组件配置：'+str(error))
        self.pending = None
        self.stop_timer.stop()
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(100 if shutdown else 1500):
                self.process.kill()
                self.process.waitForFinished(100 if shutdown else 1000)
