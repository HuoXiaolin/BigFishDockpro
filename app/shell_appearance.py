"""Own the native shell styling lifetime without replacing system flyout windows."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from PyQt5.QtCore import QObject, QProcess, QTimer, Qt, pyqtSignal
from shell_appearance_model import KINDS, appearance, panel_ink, settings, encode_ini

PAYLOAD_FILES = ('BigFishShellAppearance.exe', 'BigFishStartStyle.dll', 'BigFishNotificationStyle.dll')
HOSTS = {'startmenuexperiencehost.exe': 'start', 'shellexperiencehost.exe': 'notifications', 'shellhost.exe': 'notifications'}


def payload_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'shell-appearance'
    return Path(__file__).resolve().parents[1] / 'artifacts/shell-appearance'


def verify_payload(root):
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('protocol') != 1 or set(manifest.get('files', {})) != set(PAYLOAD_FILES):
        raise ValueError('系统面板组件清单不完整')
    if not isinstance(manifest.get('build'), str) or not __import__('re').fullmatch('[0-9a-f]{16}', manifest['build']):
        raise ValueError('系统面板组件版本无效')
    for name in PAYLOAD_FILES:
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != manifest['files'][name]:
            raise ValueError('系统面板组件校验失败：' + name)
    return manifest


def stage_payload(source, destination):
    manifest = verify_payload(source)
    target = destination / manifest['build']
    if target.exists():
        verify_payload(target)
        return target
    target.mkdir(parents=True)
    try:
        for name in (*PAYLOAD_FILES, 'manifest.json'):
            temporary = target / (name + '.tmp')
            shutil.copyfile(source / name, temporary)
            os.replace(temporary, target / name)
        verify_payload(target)
    except Exception:
        # A partially copied directory must not be accepted on the next try.
        for name in (*PAYLOAD_FILES, 'manifest.json'):
            for file in (target / name, target / (name + '.tmp')):
                file.unlink(missing_ok=True)
        target.rmdir()
        raise
    return target


def signal_host(pid, name=None):
    if sys.platform != 'win32':
        return False
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.SetEvent.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    event = kernel.OpenEventW(2, False, name or 'Local\\BigFishDock.ShellAppearance.' + str(pid))
    if not event:
        return False
    try:
        return bool(kernel.SetEvent(event))
    finally:
        kernel.CloseHandle(event)


def owner_start_time():
    """An exact native creation timestamp prevents stale PID reuse after a crash."""
    if sys.platform != 'win32':
        return '0'
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)]*4
    values = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *(ctypes.byref(value) for value in values)):
        raise ctypes.WinError(ctypes.get_last_error())
    return str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)


def system_appearance(api):
    light = api.system_is_light()
    transparent = True
    if sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                transparent = bool(winreg.QueryValueEx(key, 'EnableTransparency')[0])
        except OSError:
            pass
    return light, transparent


def shell_hosts():
    from ctypes import wintypes
    class ProcessEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', ctypes.c_long),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR*260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    ours = wintypes.DWORD()
    if not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(ours)):
        return {}
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    result = {}
    try:
        entry = ProcessEntry();entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            kind = HOSTS.get(entry.szExeFile.lower())
            session = wintypes.DWORD()
            if kind and kernel.ProcessIdToSessionId(entry.th32ProcessID, ctypes.byref(session)) and session.value == ours.value:
                result[entry.th32ProcessID] = kind
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return result


def foreground_surface(hosts):
    if not hosts or os.environ.get('FISHDOCK_TEST_DESKTOP'):
        return None
    from ctypes import wintypes as W
    from window_layers import native
    from taskbar_surface import composed_color
    user = native()
    window = user.GetForegroundWindow()
    if not window:
        return None
    user.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    user.GetWindowThreadProcessId.restype = W.DWORD
    pid = W.DWORD()
    user.GetWindowThreadProcessId(window, ctypes.byref(pid))
    kind = hosts.get(pid.value)
    if kind is None:
        return None
    rect = W.RECT()
    if not user.GetWindowRect(window, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 120 or height < 80:
        return None
    # Stay inside the glass and away from most labels and buttons.
    points = ((rect.left + round(width*x), rect.top + round(height*y))
              for x in (.1, .5, .9) for y in (.23, .41, .62, .81))
    color = composed_color(points)
    return (kind, color) if color is not None else None


class ShellAppearance(QObject):
    changed = pyqtSignal(str)

    def __init__(self, dock, api):
        super().__init__(dock)
        self.dock, self.api = dock, api
        self.root = Path(api.CONFIG_DIR) / 'shell-appearance'
        self.payload = None
        self.disabled = bool(dock.preview or os.environ.get('FISHDOCK_TEST_DESKTOP'))
        self.supported = sys.platform == 'win32' and sys.getwindowsversion().build >= 22000
        self.status = '未开启；保留系统外观。'
        self.closed = self.suspended = False
        self.last = {}
        self.themes = {}
        self.hosts = {}
        self.attached = set()
        self.attempts = {}
        self.process = None
        self.active_pid = None
        self.owner_start = owner_start_time()
        self.errors = {}
        self.containers = {}
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.VeryCoarseTimer)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.sync)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.timeout)

    def message(self, text):
        if self.status != text:
            self.status = text
            self.changed.emit(text)

    def write(self, kind, data, root=None):
        root = root or self.root
        key = (str(root), kind)
        content = encode_ini(data)
        if self.last.get(key) == content:
            return False
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / (kind + '.ini.tmp')
        temporary.write_bytes(content)
        os.replace(temporary, root / (kind + '.ini'))
        self.last[key] = content
        return True

    def signal(self, pid):
        container = self.containers.get(pid)
        return signal_host(pid, container['event']) if container else signal_host(pid)

    def prepare_container(self, pid):
        if pid in self.containers:return self.containers[pid]
        from shell_container import context, owner_handle, status_handle
        container = context(pid)
        if container:
            container['payload'] = stage_payload(payload_root(), container['root'] / 'components')
            container['owner_handle'] = owner_handle(pid)
            container['status_handle'] = status_handle(pid, container['root'] / (str(pid)+'.json'))
        self.containers[pid] = container
        return container

    def sampled_surface(self, light, transparent):
        # Read only an active flyout already owned by a connected shell host.
        hosts = {pid: kind for pid, kind in self.hosts.items() if pid in self.attached and
                 self.dock.cfg.get(f'shell_{kind}_enabled') and
                 self.dock.cfg.get(f'shell_{kind}_text_mode', 'auto') == 'auto' and
                 appearance(self.dock.cfg, kind, light, transparent)['opacity'] < 100}
        return foreground_surface(hosts)

    def refresh_foreground(self):
        if self.disabled or self.closed or self.suspended or not self.attached:
            return
        light, transparent = system_appearance(self.api)
        sample = self.sampled_surface(light, transparent)
        if sample:
            kind, color = sample
            ink = panel_ink(appearance(self.dock.cfg, kind, light, transparent), color)
            theme = 'Light' if ink == '#000000' else 'Dark'
            if self.themes.get(kind) != theme:
                self.sync(sample)

    def sync(self, sample=None):
        if self.closed or self.suspended:
            return
        enabled = {kind for kind in KINDS if self.dock.cfg.get(f'shell_{kind}_enabled', False)}
        if self.disabled:
            self.message('隔离预览：未修改系统面板。')
            return
        if not self.supported:
            self.message('系统面板美化支持 Windows 11；当前保留系统外观。')
            return
        if not enabled:
            self.restore()
            self.message('未开启；已请求恢复系统外观。' if self.hosts else '未开启；保留系统外观。')
            return
        try:
            if self.payload is None:
                self.payload = stage_payload(payload_root(), Path(os.environ.get('LOCALAPPDATA', self.api.CONFIG_DIR)) / 'BigFishDock/ShellAppearance')
            light, transparent = system_appearance(self.api)
            current = shell_hosts()
            self.attached.intersection_update(current)
            self.hosts = current
            for pid in list(self.containers):
                if pid not in current:self.containers.pop(pid, None)
            for pid in list(self.errors):
                if pid not in current:
                    self.errors.pop(pid, None)
                    self.attempts.pop(pid, None)
            sample = sample if sample is not None else self.sampled_surface(light, transparent)
            system_text_light = None
            if any(self.dock.cfg.get(f'shell_{kind}_text_mode') == 'system' for kind in enabled):
                from taskbar_text import system_mode
                mode = system_mode()
                system_text_light = None if mode is None else bool(mode)
            for kind in KINDS:
                color = sample[1] if sample and sample[0] == kind else None
                data = settings(self.dock.cfg, kind, os.getpid(), light, transparent, color, system_text_light)
                data['owner_start'] = self.owner_start
                changed = self.write(kind, data)
                self.themes[kind] = data['bigfish_theme']
                for pid, host_kind in current.items():
                    if host_kind != kind:continue
                    if pid not in self.containers and self.attempts.get(pid, (0, 0))[0] >= 3:continue
                    try:
                        container = self.prepare_container(pid) if kind in enabled else self.containers.get(pid)
                        if container:
                            local = dict(data, **{'owner_handle_' + str(other): str(item['owner_handle'])
                                for other, item in self.containers.items() if item and item['root'] == container['root']})
                            local.update({'status_handle_' + str(other): str(item['status_handle'])
                                for other, item in self.containers.items() if item and item['root'] == container['root']})
                            if self.write(kind, local, container['root']):self.signal(pid)
                        elif changed:self.signal(pid)
                    except OSError as error:
                        self.errors[pid] = '组件目录或通信未就绪：' + str(error)
                        count = min(3, self.attempts.get(pid, (0, 0))[0]+1)
                        self.attempts[pid] = (count, time.monotonic()+(5, 15, 60)[count-1])
            self.timer.start()
            if self.process is None:
                now = time.monotonic()
                for pid, kind in current.items():
                    count, after = self.attempts.get(pid, (0, 0))
                    if kind in enabled and pid in self.containers and pid not in self.attached and count < 3 and now >= after:
                        self.attach(pid, kind)
                        break
            self.update_status(enabled)
        except (OSError, ValueError, KeyError) as error:
            self.timer.stop()
            self.message('美化未应用，系统外观保留：' + str(error))
            self.api.log('shell appearance: ' + str(error))

    def attach(self, pid, kind):
        count = self.attempts.get(pid, (0, 0))[0] + 1
        self.attempts[pid] = (count, time.monotonic() + (5, 15, 60)[count-1])
        self.active_pid = pid
        process = self.process = QProcess(self)
        container = self.containers.get(pid)
        payload = container['payload'] if container else self.payload
        process.setProgram(str(payload / PAYLOAD_FILES[0]))
        process.setArguments(['--attach', str(pid), kind])
        process.finished.connect(self.finished)
        process.errorOccurred.connect(self.process_error)
        process.start()
        self.deadline.start(9000)

    def timeout(self):
        # Only the short-lived, owned launcher is stopped. Never kill a shell host.
        if self.process is not None:
            self.errors[self.active_pid] = '连接超时'
            self.process.kill()

    def process_error(self, error):
        if self.process is not None and error == QProcess.FailedToStart:
            self.errors[self.active_pid] = '组件无法启动'
            self.finished(29, QProcess.CrashExit)

    def finished(self, code, _status):
        process, pid = self.process, self.active_pid
        if process is None:
            return
        self.deadline.stop()
        if code == 0:
            self.attached.add(pid)
            self.errors.pop(pid, None)
        else:
            self.errors[pid] = self.errors.get(pid) or ('系统拒绝接入' if code in (20, 21, 22) else '组件连接失败（%s）' % code)
        self.process = self.active_pid = None
        process.deleteLater()
        if not self.closed and not self.suspended:
            self.update_status({kind for kind in KINDS if self.dock.cfg.get(f'shell_{kind}_enabled')})

    def update_status(self, enabled):
        states = []
        for kind, title in (('start', '开始菜单'), ('notifications', '通知与快捷面板')):
            if kind not in enabled:
                continue
            hosts = [pid for pid, value in self.hosts.items() if value == kind]
            matched = failed = 0
            pending = 0
            for pid in hosts:
                try:
                    container = self.containers.get(pid)
                    path = (container['root'] if container else self.root) / (str(pid) + '.json')
                    if path.stat().st_size > 4096:
                        pending += 1
                        continue
                    data = json.loads(path.read_text(encoding='utf-8'))
                    if data.get('pid') != pid or data.get('protocol') != 1 or data.get('owner_pid') != os.getpid():
                        pending += 1
                        continue
                    if data.get('state') == 'applied' and data.get('matches', 0) > 0:
                        matched += 1
                    else:pending += 1
                    failed += int(data.get('state') == 'failed' or data.get('errors', 0) > 0)
                except (OSError, ValueError):
                    pending += 1
            error = next((self.errors[pid] for pid in hosts if pid in self.errors), '')
            state = ('部分已应用；' + error if matched and error else error) if error else (
                '部分控件未适配，可关闭并恢复' if failed else
                '部分已应用，其余等待系统面板打开' if matched and pending else
                '已应用' if matched else '等待系统面板打开')
            states.append(title + '：' + state)
        self.message('；'.join(states))

    def retry(self):
        self.attempts.clear()
        self.errors.clear()
        self.attached.clear()
        self.last.clear()
        self.sync()

    def restore(self):
        self.timer.stop()
        if self.disabled:
            return
        for root, kind in tuple(self.last):
            try:
                data={'enabled':'0','owner_pid':str(os.getpid()),'owner_start':self.owner_start}
                for pid, item in self.containers.items():
                    if item and str(item['root']) == root:
                        data['owner_handle_'+str(pid)]=str(item['owner_handle'])
                        data['status_handle_'+str(pid)]=str(item['status_handle'])
                self.write(kind, data, Path(root))
            except OSError as error:
                self.api.log('shell appearance restore: ' + str(error))
        for pid in self.hosts:
            self.signal(pid)

    def suspend(self):
        self.suspended = True
        self.restore()

    def resume(self):
        self.suspended = False
        self.sync()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.restore()
        self.deadline.stop()
        if self.process is not None:
            process = self.process
            process.kill()
            process.waitForFinished(250)
