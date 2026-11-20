"""Deliver real Windows session messages to both packaged portable launchers in isolation."""
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from uuid import uuid4

from run_isolated_test import assert_isolated, desktop_name

ROOT = Path(__file__).resolve().parents[1]
QUERY_END_SESSION = 0x0011
END_SESSION = 0x0016
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258


class StartupInfo(ctypes.Structure):
    _fields_ = [('cb', W.DWORD), ('lpReserved', W.LPWSTR), ('lpDesktop', W.LPWSTR),
                ('lpTitle', W.LPWSTR), ('dwX', W.DWORD), ('dwY', W.DWORD),
                ('dwXSize', W.DWORD), ('dwYSize', W.DWORD), ('dwXCountChars', W.DWORD),
                ('dwYCountChars', W.DWORD), ('dwFillAttribute', W.DWORD), ('dwFlags', W.DWORD),
                ('wShowWindow', W.WORD), ('cbReserved2', W.WORD), ('lpReserved2', ctypes.c_void_p),
                ('hStdInput', W.HANDLE), ('hStdOutput', W.HANDLE), ('hStdError', W.HANDLE)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [('hProcess', W.HANDLE), ('hThread', W.HANDLE), ('dwProcessId', W.DWORD), ('dwThreadId', W.DWORD)]


class Windows:
    def __init__(self, desktop):
        k = self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        u = self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.window_callback = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        k.CreateProcessW.argtypes = [W.LPCWSTR, W.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                     W.BOOL, W.DWORD, ctypes.c_void_p, W.LPCWSTR,
                                     ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
        k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        k.OpenProcess.restype = W.HANDLE
        k.CloseHandle.argtypes = [W.HANDLE]
        k.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        k.WaitForSingleObject.restype = W.DWORD
        k.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        k.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
        u.GetThreadDesktop.argtypes = [W.DWORD]
        u.GetThreadDesktop.restype = W.HANDLE
        u.GetProcessWindowStation.restype = W.HANDLE
        u.EnumDesktopWindows.argtypes = [W.HANDLE, self.window_callback, W.LPARAM]
        u.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
        u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
        u.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT,
                                          ctypes.POINTER(ctypes.c_size_t)]
        u.SendMessageTimeoutW.restype = W.LPARAM
        u.ShutdownBlockReasonQuery.argtypes = [W.HWND, W.LPWSTR, ctypes.POINTER(W.DWORD)]
        self.desktop = u.GetThreadDesktop(k.GetCurrentThreadId())
        self.desktop_path = f'{desktop_name(u.GetProcessWindowStation())}\\{desktop}'

    def launch(self, executable, output):
        startup = StartupInfo(cb=ctypes.sizeof(StartupInfo), lpDesktop=self.desktop_path,
                              dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=0)
        info = ProcessInfo()
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([
            str(executable), '--startup-test', str(output), '--session-close-probe']))
        if not self.kernel.CreateProcessW(str(executable), command, None, None, False, 0, None,
                                          str(executable.parent), ctypes.byref(startup), ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.kernel.CloseHandle(info.hThread)
        return info.hProcess, info.dwProcessId

    def windows_for(self, process_id):
        windows = {}

        @self.window_callback
        def collect(window, _):
            pid = W.DWORD()
            self.user.GetWindowThreadProcessId(window, ctypes.byref(pid))
            if pid.value == process_id:
                name = ctypes.create_unicode_buffer(256)
                self.user.GetClassNameW(window, name, len(name))
                windows[int(window)] = name.value
            return True

        if not self.user.EnumDesktopWindows(self.desktop, collect, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return windows

    def send(self, window, message, confirmed=0):
        result = ctypes.c_size_t()
        if not self.user.SendMessageTimeoutW(window, message, confirmed, 0, 3, 6000, ctypes.byref(result)):
            raise ctypes.WinError(ctypes.get_last_error())
        return result.value

    def block_reason(self, window):
        size = W.DWORD(256)
        reason = ctypes.create_unicode_buffer(size.value)
        if self.user.ShutdownBlockReasonQuery(window, reason, ctypes.byref(size)):
            return reason.value
        return None

    def open_process(self, pid):
        handle = self.kernel.OpenProcess(0x101001, False, pid)  # sync, read exit status, test cleanup
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def wait(self, handle, timeout=0):
        result = self.kernel.WaitForSingleObject(handle, timeout)
        if result == WAIT_OBJECT_0:
            return True
        if result == WAIT_TIMEOUT:
            return False
        raise ctypes.WinError(ctypes.get_last_error())

    def exit_code(self, handle):
        code = W.DWORD()
        if not self.kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value


def verify(win, executable, output, bundled):
    output.mkdir(parents=True)
    temp = output / 'temp'
    temp.mkdir()
    old_temp = {key: os.environ.get(key) for key in ('TMP', 'TEMP')}
    launcher = dock = helper = None
    try:
        for key in old_temp:
            os.environ[key] = str(temp)
        launcher, launcher_pid = win.launch(executable, output)
        ready = output / 'session-ready.json'
        deadline = time.monotonic() + 35
        while not ready.is_file():
            if (output / 'result.json').is_file():
                raise AssertionError((output / 'result.json').read_text(encoding='utf-8'))
            if win.wait(launcher, 40) or time.monotonic() >= deadline:
                raise AssertionError(f'{executable.name}: no Dock session test window')
        data = json.loads(ready.read_text(encoding='utf-8'))
        hwnd = data['hwnd']
        assert hwnd in win.windows_for(data['pid']), data
        launcher_window, = (h for h, cls in win.windows_for(launcher_pid).items()
                            if cls == 'PyInstallerOnefileHiddenWindow')
        bundle = Path(data['runtime_dir']).resolve()
        assert bundle.parent == temp.resolve() and bundle.name.startswith('_MEI') and bundle.is_dir(), bundle
        dock = win.open_process(data['pid'])
        assert bool(data['helper_pid']) is bundled, data
        if bundled:
            helper = win.open_process(data['helper_pid'])
            assert not win.wait(helper)
        for hwnd_to_check in (hwnd, launcher_window):
            assert win.send(hwnd_to_check, QUERY_END_SESSION) == 1, hwnd_to_check
        assert win.block_reason(launcher_window) is None, 'The launcher registered a session blocker'
        for hwnd_to_check in (hwnd, launcher_window):
            win.send(hwnd_to_check, END_SESSION, 0)
        assert not win.wait(dock, 100) and not win.wait(launcher) and bundle.is_dir()
        with (output / 'test-config' / 'config.json').open(encoding='utf-8-sig') as cfg:
            assert json.load(cfg)['dock_visible']
        for hwnd_to_check in (hwnd, launcher_window):
            assert win.send(hwnd_to_check, QUERY_END_SESSION) == 1, hwnd_to_check
        assert win.block_reason(launcher_window) is None
        win.send(hwnd, END_SESSION, 1)
        win.send(launcher_window, END_SESSION, 1)
        assert win.wait(dock, 3200) and win.exit_code(dock) == 0, 'Dock failed to close cleanly'
        assert win.wait(launcher, 3200) and win.exit_code(launcher) == 0, 'The launcher failed to close cleanly'
        assert not bundle.exists(), f'The launcher did not clean {bundle}'
        if helper:
            assert win.wait(helper, 500), 'The bundled .NET helper was still running after Dock exited'
        return {'package': executable.name, 'cancel_keeps_dock_running': True, 'launcher_blocker': False,
                'dock_exit_code': 0, 'launcher_exit_code': 0, 'temporary_directory_removed': True,
                'bundled_helper_exited': bool(helper)}
    finally:
        for key, value in old_temp.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for process in (helper, dock, launcher):
            if process:
                if not win.wait(process):
                    win.kernel.TerminateProcess(process, 1)
                    win.wait(process, 1000)
                win.kernel.CloseHandle(process)


def main(output):
    output = Path(output)
    checks = []
    try:
        desktop = assert_isolated()
        win = Windows(desktop)
        run = output / uuid4().hex
        for name, bundled in [('BigFishDockpro.exe', False), ('BigFishDockpro-Portable-dotNET-x64.exe', True)]:
            checks.append(verify(win, ROOT / 'release' / name, run / Path(name).stem, bundled))
        result = {'passed': True, 'scope': 'packaged-window-session-messages', 'checks': checks}
    except Exception:
        result = {'passed': False, 'checks': checks, 'error': traceback.format_exc()}
        print(result['error'], file=sys.stderr)
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[-1]))
