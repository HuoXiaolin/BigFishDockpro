"""Run Qt GUI verification on a separate Windows desktop, never the input desktop."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


def desktop_name(handle):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                               ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    buffer = ctypes.create_unicode_buffer(256)
    needed = wintypes.DWORD()
    if not user32.GetUserObjectInformationW(handle, 2, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value


def assert_isolated():
    expected = os.environ.get('FISHDOCK_TEST_DESKTOP')
    station_name=os.environ.get('FISHDOCK_TEST_STATION')
    if not expected:
        raise RuntimeError('GUI tests require run_isolated_test.py; foreground fallback is prohibited.')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    if station_name:
        user32.OpenWindowStationW.argtypes=[wintypes.LPCWSTR,wintypes.BOOL,wintypes.DWORD];user32.OpenWindowStationW.restype=wintypes.HANDLE
        user32.SetProcessWindowStation.argtypes=[wintypes.HANDLE]
        station=user32.OpenWindowStationW(station_name,False,0x37f)
        if not station or not user32.SetProcessWindowStation(station):raise RuntimeError('Cannot attach isolated clipboard station: '+str(ctypes.WinError(ctypes.get_last_error())))
        # Keep the station handle open until process exit.
        user32.GetProcessWindowStation.restype=wintypes.HANDLE
        if desktop_name(user32.GetProcessWindowStation())!=station_name:raise RuntimeError('Clipboard station isolation failed.')
    user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
    user32.GetThreadDesktop.restype = wintypes.HANDLE
    actual = desktop_name(user32.GetThreadDesktop(kernel32.GetCurrentThreadId()))
    # CPython's STARTUPINFO adapter does not forward lpDesktop on all builds.
    # Bind this GUI thread before QApplication creates any native windows.
    if actual != expected:
        user32.OpenDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        user32.OpenDesktopW.restype = wintypes.HANDLE
        user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
        desktop = user32.OpenDesktopW(expected, 0, False, 0x01ff)
        if not desktop or not user32.SetThreadDesktop(desktop):
            raise RuntimeError('Cannot attach the GUI thread to its isolated desktop: ' + str(ctypes.WinError(ctypes.get_last_error())))
        # Keep this handle for the lifetime of the GUI thread; Windows closes it on exit.
        actual = desktop_name(user32.GetThreadDesktop(kernel32.GetCurrentThreadId()))
    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    current = user32.OpenInputDesktop(0, False, 1)
    try:
        input_name = desktop_name(current) if current else '<unavailable:%s>' % ctypes.get_last_error()
        # UOI_IO directly proves that our desktop does not receive user input,
        # including when the active secure desktop cannot be opened by this user.
        receiving = wintypes.BOOL()
        needed = wintypes.DWORD()
        own = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        verified = user32.GetUserObjectInformationW(own, 6, ctypes.byref(receiving), ctypes.sizeof(receiving), ctypes.byref(needed))
        if actual != expected or not verified or receiving.value or input_name == actual:
            raise RuntimeError('The test desktop is not verified as separate from the input desktop: thread=%s expected=%s input=%s' % (actual, expected, input_name))
    finally:
        if current:
            user32.CloseDesktop(current)
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--target', default='dock.py')
    parser.add_argument('--output', required=True)
    parser.add_argument('--runtime-check',action='store_true')
    parser.add_argument('--clipboard-test',action='store_true')
    parser.add_argument('--startup', action='store_true')
    parser.add_argument('--autostart', action='store_true')
    parser.add_argument('--fresh-profile', action='store_true')
    parser.add_argument('--visibility-profile',action='store_true')
    parser.add_argument('--resume-profile',action='store_true')
    parser.add_argument('--timeout', type=int, default=55)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    name = 'Fishdock_Test_' + uuid.uuid4().hex
    station=None;station_name=''
    if args.clipboard_test:
        station_name='Fishdock_Clipboard_'+uuid.uuid4().hex
        user32.CreateWindowStationW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p];user32.CreateWindowStationW.restype=wintypes.HANDLE
        user32.GetProcessWindowStation.restype=wintypes.HANDLE;user32.SetProcessWindowStation.argtypes=[wintypes.HANDLE]
        user32.CloseWindowStation.argtypes=[wintypes.HANDLE]
        original=user32.GetProcessWindowStation();station=user32.CreateWindowStationW(station_name,0,0x37f,None)
        if not station or not user32.SetProcessWindowStation(station):raise RuntimeError('Cannot create isolated clipboard station: '+str(ctypes.WinError(ctypes.get_last_error())))
        try:handle=user32.CreateDesktopW(name,None,None,0,0x01ff,None)
        finally:
            if not user32.SetProcessWindowStation(original):raise RuntimeError('Cannot restore test launcher window station.')
    else:handle=user32.CreateDesktopW(name,None,None,0,0x01ff,None)
    if not handle:
        if station:user32.CloseWindowStation(station)
        raise RuntimeError('Cannot create isolated desktop; no foreground fallback: ' + str(ctypes.WinError(ctypes.get_last_error())))
    try:
        target = Path(args.target).resolve()
        command = ([str(Path(args.python).resolve()), str(target)] if target.suffix.lower() == '.py' else [str(target)])
        command += ['--clipboard-test' if args.clipboard_test else '--startup-test' if args.startup else '--runtime-check' if args.runtime_check else '--self-test', str(output)]
        if args.autostart:
            command.append('--autostart')
        if args.fresh_profile:
            command.append('--fresh-profile')
        if args.visibility_profile:command.append('--visibility-profile')
        if args.resume_profile:command.append('--resume-profile')
        startup = subprocess.STARTUPINFO()
        startup.lpDesktop = name
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        env = dict(os.environ, FISHDOCK_TEST_DESKTOP=name, PYTHONIOENCODING='utf-8')
        if station_name:env['FISHDOCK_TEST_STATION']=station_name
        result_path = output/'result.json'
        if result_path.exists():
            result_path.unlink()
        with (output/'process.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen(command, cwd=target.parent, env=env, startupinfo=startup,
                creationflags=subprocess.CREATE_NO_WINDOW, stdout=log, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=max(5,min(180,args.timeout)))
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise RuntimeError('Isolated verification timed out; only the test process was stopped.')
        if code or not result_path.exists():
            raise RuntimeError('Isolated test failed: exit %s, see %s' % (code, output/'process.log'))
        result = json.loads(result_path.read_text(encoding='utf-8'))
        if not result.get('passed'):
            raise RuntimeError('Verification failed: ' + str(result.get('error')))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        user32.CloseDesktop(handle)
        if station:user32.CloseWindowStation(station)


if __name__ == '__main__':
    main()
