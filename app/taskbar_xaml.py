"""Portable TranslucentTB adapter with owned process lifecycle."""
import json
import os
from pathlib import Path
from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtGui import QColor


def shell_handle():
    import ctypes
    from ctypes import wintypes
    user=ctypes.windll.user32
    user.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR]
    user.FindWindowW.restype=wintypes.HWND
    return user.FindWindowW('Shell_TrayWnd',None)


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
              'show_line': mode == 'system'}, 'hide_tray': True, 'disable_saving': True}
    for state in ('visible_window', 'maximized_window', 'start_opened', 'search_opened',
                  'task_view_opened', 'battery_saver'):
        result[state + '_appearance'] = {'enabled': False}
    return result


EFFECT_KEYS = ('taskbar_mode', 'taskbar_color', 'taskbar_opacity', 'taskbar_blur')


def effect_key(cfg):
    return tuple(cfg.get(key) for key in EFFECT_KEYS)


def resident_program():
    """Identify the TranslucentTB control window on this desktop, including portable copies."""
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    window = user.FindWindowW('TrayWindow', 'TranslucentTB')
    if not window:
        return None
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId(window, ctypes.byref(pid))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
    process = kernel.OpenProcess(0x1000, False, pid.value)
    if process:
        try:
            path = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(path))
            if kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                return Path(path.value)
        finally:
            kernel.CloseHandle(process)
    return None


class XamlTaskbar:
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
        self.desired = None
        self.retries = 0
        self.shell_timer = QTimer(dock);self.shell_timer.setInterval(2500)
        self.shell_timer.timeout.connect(self.shell_changed)
        self.apply_timer = QTimer(dock);self.apply_timer.setSingleShot(True)
        self.apply_timer.timeout.connect(self.apply_desired)

    def shell_changed(self):
        if self.closed or self.desired is None:return
        current=shell_handle()
        if current!=self.shell:
            self.shell=current;self.retries=0
            self.apply_timer.stop()
            if current:self.apply_timer.start(750)

    def apply_desired(self):
        if self.closed or self.pending is not None or self.desired is None:return
        current=shell_handle()
        if current and current==self.shell:self.apply(self.desired)
        elif current!=self.shell:self.shell_changed()

    def schedule_recovery(self):
        delays=(1000,2000,4000,8000)
        if self.monitor_shell and self.desired is not None and self.shell and self.retries<len(delays):
            self.apply_timer.start(delays[self.retries]);self.retries+=1

    def write(self, cfg):
        path = self.directory / 'settings.json'
        temporary = path.with_suffix('.pending')
        temporary.write_text(json.dumps(configuration(cfg), ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)

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
        return isinstance(actual, dict) and all(actual.get(key) == value for key, value in expected.items())

    def confirmed(self, cfg):
        return (cfg['taskbar_mode'] != 'system' and self.pending is None
                and resident_program() == self.program and self.configuration_matches(cfg))

    def sync(self):
        cfg = {key:self.dock.cfg[key] for key in EFFECT_KEYS}
        self.apply_timer.stop()
        self.retries=0
        self.desired=None if cfg['taskbar_mode']=='system' else cfg
        if self.monitor_shell:
            if self.desired is None:
                self.shell_timer.stop();self.shell=None
            else:
                self.shell=shell_handle()
                if not self.shell_timer.isActive():self.shell_timer.start()
        if self.pending is not None:
            # The owned process is stopping. Only the most recent request should run next.
            self.pending = cfg
            return
        if cfg['taskbar_mode'] == 'system' and self.process.state() != QProcess.NotRunning:
            self.pending = cfg
            self.stop_timer.start(2000)
            self.process.terminate()
            return
        self.apply_when_ready(cfg)

    def apply_when_ready(self,cfg):
        if self.monitor_shell and cfg['taskbar_mode']!='system' and self.process.state()==QProcess.NotRunning:
            if self.shell:self.apply_timer.start(750)
        else:self.apply(cfg)

    def apply(self, cfg):
        try:
            self.write(cfg)
        except OSError as error:
            self.report(cfg, False, '任务栏效果未应用：无法保存组件配置，'+str(error)+'；可点击重新应用。')
            return
        state = self.process.state()
        if cfg['taskbar_mode'] == 'system':
            self.active = self.starting = None
            self.shared = False
            self.report(cfg, True, '任务栏外观已恢复跟随系统。')
        elif state == QProcess.Starting:
            self.starting = cfg
        elif state == QProcess.Running:
            # The portable backend watches settings.json, including atomic replacement.
            self.starting = None
            self.active = cfg
            self.report(cfg, True, '已更新运行中的任务栏组件配置。')
        else:
            resident = resident_program()
            if resident == self.program:
                self.shared = True
                self.active = cfg
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
        self.active, self.starting = self.starting, None
        self.report(self.active, True, '任务栏组件已启动。')

    def failed(self, error):
        # Read/write channel errors are unrelated to the watched settings file.
        # A crash is reported once with its exit code by finished().
        if self.closed or error != QProcess.FailedToStart:
            return
        if self.pending is not None:
            self.finished()
        elif self.starting is not None:
            cfg, self.starting = self.starting, None
            self.report(cfg, False, '任务栏组件未能启动：'+self.process.errorString()+'；可点击重新应用。')
            self.schedule_recovery()

    def finished(self, code=0, status=QProcess.NormalExit):
        self.stop_timer.stop()
        if self.closed:
            return
        previous = self.active or self.starting
        self.active = self.starting = None
        if self.pending is not None:
            cfg, self.pending = self.pending, None
            self.apply_when_ready(cfg)
        elif previous is not None:
            # A second TranslucentTB launcher exits normally after handing off to its resident.
            if status == QProcess.NormalExit and code == 0 and self.confirmed(previous):
                self.active = previous
                self.shared = True
                self.report(previous, True, '任务栏效果由现有组件提供。')
            else:
                self.report(previous, False, f'任务栏组件已退出（退出码 {code}），可点击重新应用。')
                self.schedule_recovery()

    def close(self,shutdown=False):
        self.closed = True
        for name in ('shell_timer','apply_timer'):
            timer=getattr(self,name,None)
            if timer is not None:timer.stop()
        if getattr(self, 'shared', False) and self.active and self.confirmed(self.active):
            # Restore only our last configuration. The other process owns its lifecycle.
            try:
                self.write(dict(self.active, taskbar_mode='system'))
            except OSError as error:
                self.log('未能恢复共享任务栏组件配置：'+str(error))
        self.pending = None
        self.stop_timer.stop()
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(100 if shutdown else 1500):
                self.process.kill()
                self.process.waitForFinished(100 if shutdown else 1000)
