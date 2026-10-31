"""On-click window reuse, independent of startup/running-dot/lite-mode polling."""
import ctypes,os
from ctypes import wintypes
from app_catalog import path_key

def activation_target(entry):
    from shortcut_mapping import map_entry
    item=map_entry(entry,validate=False)
    if not item or item.get('verb')=='runas':return None
    path=item['path']
    arguments=item.get('arguments','');app_id=item.get('app_user_model_id','')
    if arguments:
        from shell_appid import arguments_list
        tokens=arguments_list(arguments)
        browser=os.path.basename(path).casefold() in ('chrome.exe','msedge.exe','brave.exe','chromium.exe')
        selectors=('--profile-directory=','--user-data-dir=','--app-id=','--source-shortcut-location=')
        if not (browser and app_id and tokens and all(token.startswith(selectors) for token in tokens)):return None
    if app_id and path.casefold().endswith('.exe'):return ('window_aumid',app_id.casefold(),path_key(path),bool(arguments))
    if path.casefold().startswith('shell:appsfolder\\'):return ('aumid',path.split('\\',1)[1].casefold())
    if path.casefold().endswith('.exe'):return ('exe',path_key(path))
    return None

def matching_window(target,windows):
    if target is None:return None
    if target[0]=='window_aumid':
        candidates=[w for w in windows if w.get('path') and path_key(w['path'])==target[2]]
        for window in candidates:
            if str(window.get('window_aumid','')).casefold()==target[1]:return window
        if candidates and not target[3] and not any(w.get('window_aumid') for w in candidates):return candidates[0]
        return None
    for window in windows:
        if target[0]=='aumid' and str(window.get('aumid','')).casefold()==target[1]:return window
        if target[0]=='exe' and window.get('path') and path_key(window['path'])==target[1]:return window
    return None

def native_windows(exclude_pid=None):
    if os.environ.get('FISHDOCK_TEST_DESKTOP'):
        from run_isolated_test import assert_isolated
        assert_isolated()
    exclude=os.getpid() if exclude_pid is None else exclude_pid
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.IsWindowVisible.argtypes=[wintypes.HWND];user.GetWindowTextLengthW.argtypes=[wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int];user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
    user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetApplicationUserModelId.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.UINT),wintypes.LPWSTR]
    dwm=ctypes.WinDLL('dwmapi');dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    cache={};windows=[]
    def process(pid):
        if pid in cache:return cache[pid]
        result={};handle=kernel.OpenProcess(0x1000,False,pid)
        if handle:
            try:
                path=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(path))
                if kernel.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)):result['path']=path.value
                length=wintypes.UINT()
                if kernel.GetApplicationUserModelId(handle,ctypes.byref(length),None)==122 and 0<length.value<4096:
                    value=ctypes.create_unicode_buffer(length.value)
                    if kernel.GetApplicationUserModelId(handle,ctypes.byref(length),value)==0:result['aumid']=value.value
            finally:kernel.CloseHandle(handle)
        cache[pid]=result;return result
    callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.EnumWindows.argtypes=[callback,wintypes.LPARAM]
    user.EnumChildWindows.argtypes=[wintypes.HWND,callback,wintypes.LPARAM]
    @callback
    def collect(hwnd,unused):
        if len(windows)>=4096:return False
        if not user.IsWindowVisible(hwnd) or user.GetWindowTextLengthW(hwnd)<=0:return True
        if user.GetWindowLongPtrW(hwnd,-20)&0x80:return True
        name=ctypes.create_unicode_buffer(256);user.GetClassNameW(hwnd,name,len(name))
        if name.value in ('Progman','WorkerW','Shell_TrayWnd','Shell_SecondaryTrayWnd'):return True
        cloaked=wintypes.DWORD();dwm.DwmGetWindowAttribute(hwnd,14,ctypes.byref(cloaked),ctypes.sizeof(cloaked))
        if cloaked.value:return True
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if name.value=='ApplicationFrameWindow':
            @callback
            def child(child_hwnd,unused):
                value=wintypes.DWORD();user.GetWindowThreadProcessId(child_hwnd,ctypes.byref(value))
                if value.value and value.value!=pid.value:pid.value=value.value;return False
                return True
            user.EnumChildWindows(hwnd,child,0)
        if pid.value and pid.value!=exclude:
            info=process(pid.value)
            if info:windows.append(dict(info,hwnd=int(hwnd),pid=pid.value))
        return True
    user.EnumWindows(collect,0)
    return windows

def activate_window(hwnd):
    user=ctypes.WinDLL('user32',use_last_error=True)
    for name in ('IsWindow','IsWindowVisible','IsIconic','BringWindowToTop','SetForegroundWindow'):
        getattr(user,name).argtypes=[wintypes.HWND]
    user.GetLastActivePopup.argtypes=[wintypes.HWND];user.GetLastActivePopup.restype=wintypes.HWND
    user.ShowWindowAsync.argtypes=[wintypes.HWND,ctypes.c_int]
    if not user.IsWindow(hwnd):return False
    if user.IsIconic(hwnd):user.ShowWindowAsync(hwnd,9)
    popup=user.GetLastActivePopup(hwnd)
    if popup and user.IsWindowVisible(popup):hwnd=popup
    user.BringWindowToTop(hwnd)
    if not user.SetForegroundWindow(hwnd):
        class Flash(ctypes.Structure):
            _fields_=[('size',wintypes.UINT),('hwnd',wintypes.HWND),('flags',wintypes.DWORD),('count',wintypes.UINT),('timeout',wintypes.DWORD)]
        info=Flash(ctypes.sizeof(Flash),hwnd,3,3,0)
        user.FlashWindowEx.argtypes=[ctypes.POINTER(Flash)];user.FlashWindowEx(ctypes.byref(info))
    # A focus restriction must not result in launching a duplicate instance.
    return True

def activate_existing(entry):
    target=activation_target(entry)
    if target is None:return False
    windows=native_windows()
    if target[0]=='window_aumid':
        from shell_appid import window_id
        for window in windows:
            if window.get('path') and path_key(window['path'])==target[2]:window['window_aumid']=window_id(window['hwnd'])
    match=matching_window(target,windows)
    return bool(match and activate_window(match['hwnd']))
