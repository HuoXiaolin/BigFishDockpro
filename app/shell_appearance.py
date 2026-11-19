"""Own the native shell styling lifetime without replacing system flyout windows."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from PyQt5.QtCore import QObject, QProcess, QTimer, Qt, pyqtSignal
from shell_appearance_model import KINDS, appearance, panel_ink, settings, encode_ini, shows_backdrop

PAYLOAD_FILES = ('BigFishShellAppearance.exe', 'BigFishStartStyle.dll', 'BigFishNotificationStyle.dll')
BUILD_ID = re.compile(r'[0-9a-f]{16}')
HOSTS = {'startmenuexperiencehost.exe': 'start', 'searchhost.exe': 'start',
         'shellexperiencehost.exe': 'notifications', 'shellhost.exe': 'notifications'}


class ShellWindowEvents:
    """Wake discovery when a Shell window is created/shown, without fast polling."""
    def __init__(self, wake):
        self.wake, self.handle, self.callback = wake, None, None

    def start(self):
        if self.handle or sys.platform != 'win32' or os.environ.get('FISHDOCK_TEST_DESKTOP'):
            return
        from ctypes import wintypes as W
        user = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND,
                                          W.LONG, W.LONG, W.DWORD, W.DWORD)
        user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
        user.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
        user.SetWinEventHook.argtypes = [W.DWORD, W.DWORD, W.HMODULE, callback_type, W.DWORD, W.DWORD, W.DWORD]
        user.SetWinEventHook.restype = W.HANDLE

        def on_window(_hook, event, hwnd, obj, child, _thread, _time):
            if event == 0x8001 or not hwnd or obj or child:  # EVENT_OBJECT_DESTROY
                return
            try:
                name = ctypes.create_unicode_buffer(96)
                user.GetClassNameW(hwnd, name, len(name))
                if name.value not in ('Windows.UI.Core.CoreWindow', 'ControlCenterWindow'):
                    return
                pid = W.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    self.wake(pid.value, hwnd)
            except Exception:
                # WinEvent callbacks must not propagate into user32.
                return

        self.callback = callback_type(on_window)
        self.handle = user.SetWinEventHook(0x8000, 0x8002, None, self.callback, 0, 0, 2)
        if not self.handle:
            self.callback = None

    def stop(self):
        if self.handle:
            from ctypes import wintypes as W
            user = ctypes.WinDLL('user32', use_last_error=True)
            user.UnhookWinEvent.argtypes = [W.HANDLE]
            user.UnhookWinEvent(self.handle)
        self.handle, self.callback = None, None


def payload_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'shell-appearance'
    return Path(__file__).resolve().parents[1] / 'artifacts/shell-appearance'


def verify_payload(root):
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('protocol') != 1 or set(manifest.get('files', {})) != set(PAYLOAD_FILES):
        raise ValueError('系统面板组件清单不完整')
    if not isinstance(manifest.get('build'), str) or not BUILD_ID.fullmatch(manifest['build']):
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


def signal_host(pid, name=None, notify=True):
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
        return not notify or bool(kernel.SetEvent(event))
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


def shell_hosts(names=None):
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
            name = entry.szExeFile.lower()
            kind = HOSTS.get(name)
            session = wintypes.DWORD()
            if kind and kernel.ProcessIdToSessionId(entry.th32ProcessID, ctypes.byref(session)) and session.value == ours.value:
                result[entry.th32ProcessID] = kind
                if names is not None:
                    names[entry.th32ProcessID] = name
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return result


def foreground_target(hosts):
    if not hosts or os.environ.get('FISHDOCK_TEST_DESKTOP'):
        return None
    from ctypes import wintypes as W
    from window_layers import native
    user = native()
    window = user.GetForegroundWindow()
    if not window:
        return None
    user.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    user.GetWindowThreadProcessId.restype = W.DWORD
    pid = W.DWORD()
    user.GetWindowThreadProcessId(window, ctypes.byref(pid))
    if pid.value in hosts:
        return user, window, hosts[pid.value]
    return None


def foreground_surface(hosts, start_bounds, shown_windows=()):
    target = foreground_target(hosts)
    if not hosts or (target is None and not shown_windows):
        return None
    from ctypes import wintypes as W
    from taskbar_surface import composed_color
    from window_layers import native
    user=native()
    user.WindowFromPoint.argtypes=[W.POINT];user.WindowFromPoint.restype=W.HWND
    user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
    user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
    user.IsWindowVisible.argtypes=[W.HWND]
    candidates=dict.fromkeys(([target[1]] if target else [])+list(shown_windows))
    for window in candidates:
        pid=W.DWORD();rect=W.RECT()
        user.GetWindowThreadProcessId(window,ctypes.byref(pid))
        kind=hosts.get(pid.value)
        if not kind or not user.IsWindowVisible(window) or not user.GetWindowRect(window,ctypes.byref(rect)):
            continue
        if kind=='start':
            measured=start_bounds(window,user)
            if (measured and rect.left-1<=measured[0]<measured[2]<=rect.right+1
                    and rect.top-1<=measured[1]<measured[3]<=rect.bottom+1):
                rect=W.RECT(*measured)
        width,height=rect.right-rect.left,rect.bottom-rect.top
        if width<120 or height<80:continue
        # Some shell hosts span the monitor or keep focus on the taskbar.
        # Only sample points on the visible flyout, including its child windows.
        root=user.GetAncestor(window,2)
        points=[]
        for x in (.06,.27,.51,.77,.94):
            for y in (.13,.35,.57,.79,.94):
                point=(rect.left+round(width*x),rect.top+round(height*y))
                hit=user.WindowFromPoint(W.POINT(*point))
                if hit and user.GetAncestor(hit,2)==root:points.append(point)
        if len(points)>=5:
            color=composed_color(points)
            if color is not None:return kind,color
    return None


class ShellAppearance(QObject):
    changed = pyqtSignal(str)

    def __init__(self, dock, api):
        super().__init__(dock)
        self.dock, self.api = dock, api
        self.root = Path(api.CONFIG_DIR) / 'shell-appearance'
        self.payload = None
        self.build = ''
        self.disabled = bool(dock.preview or os.environ.get('FISHDOCK_TEST_DESKTOP'))
        self.supported = sys.platform == 'win32' and sys.getwindowsversion().build >= 22000
        self.status = '未开启；保留系统外观。'
        self.closed = self.suspended = False
        self.last = {}
        self.themes = {}
        self.start_profile = None
        self.start_surface = None
        self.pending_start_surface = None
        self.start_live_ink = None
        self.start_footer_color = None
        self.start_window = None
        self.shown_windows = {}
        self.ink_open_deadline = 0.
        self.notification_profile = self.notification_surface = None
        self.ink_timer = QTimer(self)
        self.ink_timer.setSingleShot(True)
        self.ink_timer.timeout.connect(self.refresh_foreground)
        self.hosts = {}
        self.host_names = {}
        self.start_attached_at = {}
        self.start_recent_exits = []
        self.start_paused = False
        self.attached = set()
        self.attempts = {}
        self.process = None
        self.active_pid = None
        self.owner_start = owner_start_time()
        self.errors = {}
        self.containers = {}
        self.start_handoffs = {}
        self.panel_mapping = None
        self.panel_handles = {}
        self.sync_failures = 0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.VeryCoarseTimer)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.sync)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.timeout)
        self.next_attach = QTimer(self)
        self.next_attach.setSingleShot(True)
        self.next_attach.timeout.connect(self.sync)
        self.window_events = ShellWindowEvents(self.window_created)

    def window_created(self, pid, window=None):
        if self.closed or self.suspended or self.disabled:
            return
        kind = self.hosts.get(pid)
        if (kind == 'start' and self.start_paused) or (kind and not self.dock.cfg.get(f'shell_{kind}_enabled')):
            return
        if window:
            self.shown_windows.pop(pid,None)
            self.shown_windows[pid]=window
        sample_on_open = kind == 'start' or (kind and self.dock.cfg.get(f'shell_{kind}_text_mode', 'auto') == 'auto')
        if sample_on_open:
            self.ink_open_deadline=time.monotonic()+2.
        if pid in self.attached:
            # An existing process may create a new XAML thread. Ask the native
            # initializer to examine it even when the preferences did not change.
            self.signal(pid)
            if sample_on_open and not self.ink_timer.isActive():
                self.ink_timer.start(100)
        else:
            handoff = self.start_handoffs.get(pid)
            now = time.monotonic()
            if handoff and handoff[0] and now >= handoff[1]:
                # A suspended date host can acknowledge only when the user opens it.
                self.start_handoffs[pid] = (handoff[0], now + 2)
            if not self.next_attach.isActive() or self.next_attach.remainingTime() > 0:
                self.next_attach.start(0)

    def message(self, text):
        if self.status != text:
            self.status = text
            self.changed.emit(text)

    def build_for(self, kind):
        return self.build if kind in KINDS else ''

    def write(self, kind, data, root=None, build=None):
        root = root or self.root
        build = self.build_for(kind) if build is None else build
        key = (str(root), kind, build)
        content = encode_ini(data)
        if self.last.get(key) == content:
            return False
        root.mkdir(parents=True, exist_ok=True)
        name = f'{kind}.{build}.ini' if build else kind + '.ini'
        temporary = root / (name + '.tmp')
        temporary.write_bytes(content)
        os.replace(temporary, root / name)
        self.last[key] = content
        return True

    def event_name(self, pid, build):
        container = self.containers.get(pid)
        name = container['event'] if container else 'Local\\BigFishDock.ShellAppearance.' + str(pid)
        return name + '.' + build if build else name

    def signal(self, pid):
        return signal_host(pid, self.event_name(pid, self.build_for(self.hosts.get(pid))))

    def status_path(self, pid, build):
        container = self.containers.get(pid)
        root = container['root'] if container else self.root
        return root / (f'{pid}.{build}.json' if build else f'{pid}.json')

    def read_status(self, path, pid):
        try:
            if path.stat().st_size <= 4096:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, dict) and data.get('pid') == pid and data.get('protocol') == 1 and data.get('owner_pid') == os.getpid():
                    return data
        except (OSError, ValueError):
            pass
        return {}

    def staged_restore_stamp(self, path, pid):
        # Older versions can finish writing their acknowledgement while a
        # concurrent reader still prevents the atomic rename on Windows.
        staged = path.with_name(path.name + '.tmp')
        try:
            stamp = staged.stat().st_mtime_ns
        except OSError:
            return None
        if self.read_status(staged, pid).get('state') == 'restored':
            return stamp
        return None

    def prepare_start_handoff(self, pid):
        """Restore resident shell components before loading this build."""
        kind = self.hosts[pid]
        if pid not in self.start_handoffs:
            container = self.containers.get(pid)
            components = container['payload'].parent if container else self.payload.parent
            versions = ['']  # Releases before the versioned IPC used a single legacy event.
            versions.extend(path.name for path in components.iterdir()
                            if BUILD_ID.fullmatch(path.name) and path.name != self.build and path.is_dir())
            pending = {}
            for build in versions:
                event = self.event_name(pid, build)
                if not signal_host(pid, event, notify=False):
                    continue
                path = self.status_path(pid, build)
                if self.read_status(path, pid).get('state') == 'restored':
                    continue
                data = {'enabled': '0', 'owner_pid': str(os.getpid()), 'owner_start': self.owner_start}
                if container:
                    from shell_container import status_handle
                    data[f'status_handle_{pid}'] = str(status_handle(pid, path))
                pending[build] = self.staged_restore_stamp(path, pid)
                self.write(kind, data, path.parent, build)
                signal_host(pid, event)
            self.start_handoffs[pid] = (pending, time.monotonic() + 8)
        pending, deadline = self.start_handoffs[pid]
        for build, prior_staged in tuple(pending.items()):
            path = self.status_path(pid, build)
            # The canonical receipt was checked before the request. Its owner
            # and state can change while a long-lived writer retains its timestamp.
            if self.read_status(path, pid).get('state') == 'restored':
                del pending[build]
                continue
            staged = self.staged_restore_stamp(path, pid)
            if staged is not None and staged != prior_staged:
                del pending[build]
        if pending and time.monotonic() >= deadline:
            self.errors[pid] = '旧组件尚未还原，可重试接入或重新登录 Windows'
        elif pending:
            # Restore acknowledgements normally arrive within a message-loop
            # turn; don't wait for the five-second host discovery interval.
            if not self.next_attach.isActive() or self.next_attach.remainingTime() > 100:
                self.next_attach.start(100)
        elif not pending:
            self.errors.pop(pid, None)
        return not pending

    def prepare_container(self, pid):
        if pid in self.containers:return self.containers[pid]
        from shell_container import context, owner_handle, status_handle
        container = context(pid)
        if container:
            container['payload'] = stage_payload(payload_root(), container['root'] / 'components')
            container['owner_handle'] = owner_handle(pid)
            build = self.build_for(self.hosts[pid])
            name = f'{pid}.{build}.json' if build else f'{pid}.json'
            container['status_handle'] = status_handle(pid, container['root'] / name)
        self.containers[pid] = container
        return container

    def start_panel_bounds(self, window, user):
        from ctypes import wintypes as W
        pid = W.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if self.host_names.get(pid.value) == 'startmenuexperiencehost.exe':
            name = ctypes.create_unicode_buffer(96)
            user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
            user.GetClassNameW(window, name, len(name))
            if name.value == 'Windows.UI.Core.CoreWindow':
                self.start_window = (window, pid.value)
            data = self.read_status(self.status_path(pid.value, self.build), pid.value)
            bounds = data.get('start_bounds_px')
            if isinstance(bounds, list) and len(bounds) == 4 and all(type(v) is int for v in bounds):
                return bounds
        return None

    def start_window_visible(self):
        if not self.start_window:
            return False
        from ctypes import wintypes as W
        from window_layers import native
        window, expected_pid = self.start_window
        user = native()
        pid = W.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if pid.value != expected_pid or self.hosts.get(expected_pid) != 'start':
            self.start_window = None
            return False
        user.IsWindowVisible.argtypes = [W.HWND]
        user.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
        user.MonitorFromWindow.restype = W.HANDLE
        if not user.IsWindowVisible(window) or not user.MonitorFromWindow(window, 0):
            return False
        cloaked = W.DWORD()
        get_attribute = ctypes.windll.dwmapi.DwmGetWindowAttribute
        get_attribute.argtypes = [W.HWND, W.DWORD, ctypes.c_void_p, W.DWORD]
        get_attribute(window, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        return not cloaked.value

    def sampled_surface(self, light, transparent):
        # Read only an active flyout already owned by a connected shell host.
        hosts = {pid: kind for pid, kind in self.hosts.items() if pid in self.attached and
                 self.dock.cfg.get(f'shell_{kind}_enabled') and
                 (kind == 'start' or self.dock.cfg.get(f'shell_{kind}_text_mode', 'auto') == 'auto') and
                 shows_backdrop(appearance(self.dock.cfg, kind, light, transparent))}
        windows=tuple(self.shown_windows[pid] for pid in reversed(self.shown_windows) if pid in hosts)
        sample=foreground_surface(hosts,self.start_panel_bounds,windows)
        if not self.ink_timer.isActive():
            if sample:
                self.ink_timer.start(500)
            elif hosts and time.monotonic()<self.ink_open_deadline:
                self.ink_timer.start(150)
        return sample

    def remember_start_surface(self, sample, light, transparent):
        profile = appearance(self.dock.cfg, 'start', light, transparent)
        if profile != self.start_profile or not self.dock.cfg.get('shell_start_enabled'):
            self.start_profile = profile
            self.start_surface = self.pending_start_surface = None
            self.start_footer_color = None
        if sample and sample[0] == 'start':
            self.pending_start_surface = sample[1]
        if not self.dock.cfg.get('shell_start_enabled') or not shows_backdrop(profile):
            return False
        current = foreground_target(self.hosts)
        if (sample and sample[0]=='start') or (current and current[2]=='start'):
            # The opening animation can briefly report a zero-sized panel.
            if not self.ink_timer.isActive():
                self.ink_timer.start(500)
            if sample and sample[0] == 'start':
                ink_changed = profile['text_mode'] == 'auto' and self.start_live_ink != panel_ink(profile, sample[1])
                color_changed = self.start_footer_color is None or any(abs(now-old) >= 12 for now,old in zip(sample[1],self.start_footer_color))
                return ink_changed or color_changed
            return False
        # A windowed account/power flyout can change foreground ownership
        # during a press. Only rebuild the full theme once Start is offscreen.
        if self.pending_start_surface is None or self.start_window_visible():
            return False
        # Refresh the full theme offscreen. While Start is open only its shared
        # foreground brush changes, preserving focus and native flyout commands.
        self.start_surface = self.pending_start_surface
        self.pending_start_surface = None
        if profile['text_mode'] != 'auto':
            return False
        ink = panel_ink(profile, self.start_surface)
        return self.themes.get('start') != ('Light' if ink == '#000000' else 'Dark')

    def refresh_foreground(self):
        if self.disabled or self.closed or self.suspended or not self.attached:
            return
        light, transparent = system_appearance(self.api)
        sample = self.sampled_surface(light, transparent)
        if self.remember_start_surface(sample, light, transparent):
            self.sync(sample)
        elif sample and sample[0] != 'start':
            kind, color = sample
            profile = appearance(self.dock.cfg, kind, light, transparent)
            self.notification_profile,self.notification_surface=profile,color
            ink = panel_ink(profile, color)
            theme = 'Light' if ink == '#000000' else 'Dark'
            if self.themes.get(kind) != theme:
                self.sync(sample)

    def sync(self, sample=None):
        if self.closed or self.suspended:
            return
        enabled = {kind for kind in KINDS if self.dock.cfg.get(f'shell_{kind}_enabled', False)}
        if 'start' not in enabled:
            self.clear_start_exit_history()
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
        self.window_events.start()
        try:
            if self.payload is None:
                self.payload = stage_payload(payload_root(), Path(os.environ.get('LOCALAPPDATA', self.api.CONFIG_DIR)) / 'BigFishDock/ShellAppearance')
                self.build = json.loads((self.payload / 'manifest.json').read_text(encoding='utf-8'))['build']
            light, transparent = system_appearance(self.api)
            names = {}
            current = shell_hosts(names)
            self.shown_windows={pid:window for pid,window in self.shown_windows.items() if pid in current}
            self.host_names = names
            self.check_start_exits(current, time.monotonic())
            requested = enabled
            if self.start_paused:
                enabled = enabled - {'start'}
            self.attached.intersection_update(current)
            self.hosts = current
            for pid in list(self.containers):
                if pid not in current:self.containers.pop(pid, None)
            for pid in list(self.start_handoffs):
                if pid not in current:self.start_handoffs.pop(pid, None)
            for pid in list(self.panel_handles):
                if pid not in current:self.panel_handles.pop(pid)
            for pid in list(self.errors):
                if pid not in current:
                    self.errors.pop(pid, None)
            for pid in list(self.attempts):
                if pid not in current:
                    self.attempts.pop(pid, None)
            sample = sample if sample is not None else self.sampled_surface(light, transparent)
            self.remember_start_surface(sample, light, transparent)
            profile=appearance(self.dock.cfg,'notifications',light,transparent)
            if profile!=self.notification_profile or 'notifications' not in enabled:
                self.notification_profile=profile
                self.notification_surface=None
            if sample and sample[0]=='notifications':self.notification_surface=sample[1]
            surface_colors={'start':self.start_surface,'notifications':self.notification_surface}
            system_text_light = None
            if any(self.dock.cfg.get(f'shell_{kind}_text_mode') == 'system' for kind in enabled):
                from taskbar_text import system_mode
                mode = system_mode()
                system_text_light = None if mode is None else bool(mode)
            for kind in KINDS:
                data = settings(self.dock.cfg, kind, os.getpid(), light, transparent,
                                surface_colors.get(kind), system_text_light)
                if kind == 'start':
                    if (self.root / 'trace-start-menu-input').is_file():
                        data['trace_menu_input'] = '1'
                    if self.pending_start_surface is not None:
                        if 'bigfish_live_ink' in data:
                            data['bigfish_live_ink'] = panel_ink(self.start_profile, self.pending_start_surface)
                        self.start_footer_color = tuple(round(channel) for channel in self.pending_start_surface)
                        data['bigfish_footer_surface'] = '#%02x%02x%02x' % self.start_footer_color
                    self.start_live_ink = data.get('bigfish_live_ink')
                if kind == 'start' and self.start_paused:
                    data['enabled'] = '0'
                data['owner_start'] = self.owner_start
                if kind == 'start' and kind in enabled:
                    from shell_container import panel_geometry_mapping, share_panel_geometry
                    if self.panel_mapping is None:
                        self.panel_mapping = panel_geometry_mapping()
                    for pid, host_kind in current.items():
                        if host_kind != kind:
                            continue
                        if pid not in self.panel_handles:
                            try:
                                self.panel_handles[pid] = share_panel_geometry(pid, self.panel_mapping)
                            except OSError:
                                continue
                        data[f'panel_geometry_{pid}'] = str(self.panel_handles[pid])
                changed = self.write(kind, data)
                self.themes[kind] = data['bigfish_theme']
                for pid, host_kind in current.items():
                    if host_kind != kind:continue
                    if pid not in self.containers and time.monotonic() < self.attempts.get(pid, (0, 0))[1]:continue
                    try:
                        can_signal = pid in self.attached
                        container = self.prepare_container(pid) if kind in enabled else self.containers.get(pid)
                        if container:
                            local = dict(data, **{'owner_handle_' + str(other): str(item['owner_handle'])
                                for other, item in self.containers.items() if item and item['root'] == container['root']})
                            local.update({'status_handle_' + str(other): str(item['status_handle'])
                                for other, item in self.containers.items() if item and item['root'] == container['root']})
                            if self.write(kind, local, container['root']) and can_signal:self.signal(pid)
                        elif changed and can_signal:self.signal(pid)
                    except OSError as error:
                        self.errors[pid] = '组件目录或通信未就绪：' + str(error)
                        count = min(3, self.attempts.get(pid, (0, 0))[0]+1)
                        self.attempts[pid] = (count, time.monotonic()+(5, 15, 60)[count-1])
            self.sync_failures = 0
            self.timer.start(5000)
            if self.process is None:
                now = time.monotonic()
                # A host that is still starting must not keep other panels at
                # the back of the queue. Connect new hosts before retrying one.
                # Make the taskbar date host ready first on a cold Dock launch.
                for pid in sorted(current, key=lambda p: (self.attempts.get(p, (0, 0)),
                                  names.get(p) != 'shellexperiencehost.exe', current[p] != 'notifications')):
                    kind = current[pid]
                    count, after = self.attempts.get(pid, (0, 0))
                    if kind in enabled and pid in self.containers and pid not in self.attached and now >= after:
                        if not self.prepare_start_handoff(pid):
                            continue
                        self.attach(pid, kind)
                        break
            self.update_status(requested)
        except (OSError, ValueError, KeyError) as error:
            # Logon can precede package LocalState, payload staging or the Shell
            # being ready. A transient failure must not permanently stop recovery.
            self.sync_failures = min(3, self.sync_failures + 1)
            self.timer.start((5, 15, 60)[self.sync_failures - 1] * 1000)
            self.message('美化未应用，系统外观保留：' + str(error))
            self.api.log('shell appearance: ' + str(error))

    def attach(self, pid, kind):
        count = min(3, self.attempts.get(pid, (0, 0))[0] + 1)
        self.attempts[pid] = (count, time.monotonic() + (5, 15, 60)[count-1])
        self.active_pid = pid
        if self.host_names.get(pid) == 'startmenuexperiencehost.exe':
            self.start_attached_at.setdefault(pid, time.monotonic())
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
            # Drain ready hosts immediately; the five-second discovery timer is
            # for hosts that appear later, not a delay between each attachment.
            self.next_attach.start(0)

    def update_status(self, enabled):
        states = []
        for kind, title in (('start', '开始菜单'), ('notifications', '通知与快捷面板')):
            if kind not in enabled:
                continue
            if kind == 'start' and self.start_paused:
                states.append('开始菜单：系统进程连续退出，已恢复系统样式。可点击「重试接入」。')
                continue
            hosts = [pid for pid, value in self.hosts.items() if value == kind]
            matched = failed = 0
            pending = 0
            upgrading = False
            missing_search = False
            waiting_for_search_styles = False
            waiting_for_search_position = False
            calendar_seen = False
            tracking_calendar = False
            for pid in hosts:
                upgrading |= bool(self.start_handoffs.get(pid, ({}, 0))[0])
                data = self.read_status(self.status_path(pid, self.build_for(kind)), pid)
                if 'calendar_matched' in data:
                    tracking_calendar |= self.host_names.get(pid) == 'shellexperiencehost.exe'
                    calendar_seen |= bool(data['calendar_matched'])
                if data.get('state') == 'applied' and data.get('matches', 0) > 0:
                    matched += 1
                    missing_search |= data.get('search_button') is False
                    waiting_for_search_styles |= data.get('search_styles') is False
                    waiting_for_search_position |= data.get('search_position') is False
                else:
                    pending += 1
                failed += int(data.get('state') == 'failed' or data.get('errors', 0) > 0)
            error = next((self.errors[pid] for pid in hosts if pid in self.errors), '')
            state = ('部分已应用；' + error if matched and error else error) if error else (
                '部分控件未适配，可关闭并恢复' if failed else
                '正在切换已加载的组件' if upgrading else
                '外观已应用，等待搜索入口显示' if missing_search else
                '外观已应用，等待搜索内容样式' if waiting_for_search_styles else
                '外观已应用，等待开始菜单与搜索对齐' if waiting_for_search_position else
                '部分已应用，其余等待系统面板打开' if matched and pending else
                '已连接，等待日历首次显示' if tracking_calendar and not calendar_seen and self.dock.cfg.get('shell_notifications_calendar', True) else
                '已应用' if matched else '等待系统面板打开')
            states.append(title + '：' + state)
        self.message('；'.join(states))

    def clear_start_exit_history(self):
        self.start_attached_at.clear()
        self.start_recent_exits.clear()
        self.start_paused = False

    def check_start_exits(self, current, now):
        # Stop sending the same appearance to immediately replaced Start hosts.
        # A suspended process keeps its PID. Search and notification PIDs are
        # never tracked. A manual retry or a disable/enable starts a fresh run.
        for pid, attached_at in tuple(self.start_attached_at.items()):
            if now - attached_at > 15:
                del self.start_attached_at[pid]
            elif pid not in current:
                del self.start_attached_at[pid]
                self.start_recent_exits.append(now)
        self.start_recent_exits = [t for t in self.start_recent_exits if now - t <= 60]
        if len(self.start_recent_exits) >= 3:
            self.start_paused = True

    def retry(self):
        self.clear_start_exit_history()
        self.attempts.clear()
        self.errors.clear()
        self.attached.clear()
        self.start_handoffs.clear()
        self.last.clear()
        self.sync()

    def restore(self):
        self.timer.stop()
        self.next_attach.stop()
        self.ink_timer.stop()
        self.start_window = None
        self.shown_windows.clear()
        self.ink_open_deadline = 0.
        self.notification_profile=self.notification_surface=None
        self.window_events.stop()
        if self.disabled:
            return
        for root, kind, build in tuple(self.last):
            if build != self.build_for(kind):
                continue
            try:
                data={'enabled':'0','owner_pid':str(os.getpid()),'owner_start':self.owner_start}
                for pid, item in self.containers.items():
                    if item and str(item['root']) == root:
                        data['owner_handle_'+str(pid)]=str(item['owner_handle'])
                        data['status_handle_'+str(pid)]=str(item['status_handle'])
                self.write(kind, data, Path(root), build)
            except OSError as error:
                self.api.log('shell appearance restore: ' + str(error))
        for pid in self.hosts:
            self.signal(pid)

    def suspend(self):
        self.suspended = True
        self.start_attached_at.clear()
        self.start_recent_exits.clear()
        self.restore()

    def resume(self):
        self.suspended = False
        self.sync()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.restore()
        if self.panel_mapping is not None:
            from shell_container import close_panel_geometry
            close_panel_geometry(self.panel_mapping)
            self.panel_mapping = None
        self.deadline.stop()
        if self.process is not None:
            process = self.process
            process.kill()
            process.waitForFinished(250)
