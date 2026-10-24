"""Read launchable desktop applications from this Windows desktop; no process command lines."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from app_catalog import path_key,is_uninstall_entry

HOSTS={'applicationframehost.exe','runtimebroker.exe','shellexperiencehost.exe','startmenuexperiencehost.exe',
       'searchhost.exe','searchapp.exe','textinputhost.exe','lockapp.exe','conhost.exe','openconsole.exe','msiexec.exe'}
SHELL_CLASSES={'Progman','WorkerW','Shell_TrayWnd','Shell_SecondaryTrayWnd'}


def collect_apps(windows,lookup,cancelled=lambda:False,exclude_pid=None):
    excluded=os.getpid() if exclude_pid is None else exclude_pid
    cache={};rows={}
    for window in windows:
        if cancelled():return []
        pid=window['pid']
        if pid==excluded or not window.get('visible') or window.get('cloaked') or window.get('tool') or window.get('class') in SHELL_CLASSES:continue
        if pid not in cache:cache[pid]=lookup(pid)
        app=cache[pid]
        if not app or not app.get('path') or is_uninstall_entry(app):continue
        if not app['path'].lower().startswith('shell:') and Path(app['path']).name.casefold() in HOSTS:continue
        rows.setdefault(path_key(app['path']),dict(app,source='正在运行',column='running'))
        if len(rows)>=256:break
    return sorted(rows.values(),key=lambda app:(app['name'].casefold(),app['path'].casefold()))


def _description(path):
    fallback=Path(path).stem
    if path.startswith('\\\\'):return fallback
    version=ctypes.windll.version
    version.GetFileVersionInfoSizeW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(wintypes.DWORD)]
    version.GetFileVersionInfoW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
    version.VerQueryValueW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.UINT)]
    size=version.GetFileVersionInfoSizeW(path,None)
    if not size or size>4*1024*1024:return fallback
    data=ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path,0,size,data):return fallback
    pointer=ctypes.c_void_p();length=wintypes.UINT()
    translations=[]
    if version.VerQueryValueW(data,r'\VarFileInfo\Translation',ctypes.byref(pointer),ctypes.byref(length)) and length.value>=4:
        values=ctypes.cast(pointer,ctypes.POINTER(wintypes.WORD));translations.append((values[0],values[1]))
    translations.extend([(0x409,0x4b0),(0x804,0x4b0)])
    for language,codepage in translations:
        field='\\StringFileInfo\\%04x%04x\\FileDescription'%(language,codepage)
        if version.VerQueryValueW(data,field,ctypes.byref(pointer),ctypes.byref(length)) and length.value>1:
            return ctypes.wstring_at(pointer,length.value-1).strip()[:120] or fallback
    return fallback


def discover_running_apps(cancelled=lambda:False,exclude_pid=None):
    if os.environ.get('FISHDOCK_TEST_DESKTOP'):
        from run_isolated_test import assert_isolated
        assert_isolated()  # A QThread must enumerate the private test desktop too.
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.IsWindowVisible.argtypes=[wintypes.HWND];user.GetWindowTextLengthW.argtypes=[wintypes.HWND]
    user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int];user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.EnumWindows.argtypes=[callback,wintypes.LPARAM];user.EnumWindows.restype=wintypes.BOOL
    user.EnumChildWindows.argtypes=[wintypes.HWND,callback,wintypes.LPARAM]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetApplicationUserModelId.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.UINT),wintypes.LPWSTR]
    dwm=ctypes.windll.dwmapi;dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    process_cache={}
    def process(pid):
        if pid in process_cache:return process_cache[pid]
        result=None;handle=kernel.OpenProcess(0x1000,False,pid)
        if handle:
            try:
                path=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(path))
                if kernel.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)):
                    executable=path.value;target=executable
                    length=wintypes.UINT()
                    if kernel.GetApplicationUserModelId(handle,ctypes.byref(length),None)==122 and 0<length.value<4096:
                        identity=ctypes.create_unicode_buffer(length.value)
                        if kernel.GetApplicationUserModelId(handle,ctypes.byref(length),identity)==0:target='shell:AppsFolder\\'+identity.value
                    result={'path':target,'name':_description(executable)}
            finally:kernel.CloseHandle(handle)
        process_cache[pid]=result
        return result
    windows=[];errors=[]
    @callback
    def window(hwnd,param):
        if cancelled() or len(windows)>=4096:return False
        try:
            if not user.IsWindowVisible(hwnd) or user.GetWindowTextLengthW(hwnd)<=0:return True
            name=ctypes.create_unicode_buffer(256);user.GetClassNameW(hwnd,name,len(name))
            if name.value in SHELL_CLASSES:return True
            cloaked=wintypes.DWORD()
            dwm.DwmGetWindowAttribute(hwnd,14,ctypes.byref(cloaked),ctypes.sizeof(cloaked))
            if cloaked.value or user.GetWindowLongPtrW(hwnd,-20)&0x80:return True
            pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            if name.value=='ApplicationFrameWindow':
                @callback
                def child(child_hwnd,unused):
                    child_pid=wintypes.DWORD();user.GetWindowThreadProcessId(child_hwnd,ctypes.byref(child_pid))
                    if child_pid.value and child_pid.value!=pid.value:
                        pid.value=child_pid.value;return False
                    return True
                user.EnumChildWindows(hwnd,child,0)
            windows.append({'pid':pid.value,'visible':True,'class':name.value})
            return True
        except Exception as error:errors.append(error);return False
    success=user.EnumWindows(window,0)
    if errors:raise errors[0]
    if not success and not cancelled() and len(windows)<4096:raise ctypes.WinError(ctypes.get_last_error())
    return collect_apps(windows,process,cancelled,exclude_pid)
