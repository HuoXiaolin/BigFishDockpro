"""Narrow IPC with the built-in notification AppContainer, without ACL changes."""
import ctypes
from ctypes import wintypes as W
import os
from pathlib import Path
import re


def _api():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    security = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.GetPackageFamilyName.argtypes = [W.HANDLE, ctypes.POINTER(W.UINT), W.LPWSTR]
    kernel.GetAppContainerNamedObjectPath.argtypes = [W.HANDLE, ctypes.c_void_p, W.ULONG, W.LPWSTR, ctypes.POINTER(W.ULONG)]
    security.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)]
    security.GetTokenInformation.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD)]
    return kernel, security


def context(pid):
    kernel, security = _api()
    process = kernel.OpenProcess(0x1000, False, pid)
    if not process:raise ctypes.WinError(ctypes.get_last_error())
    token = W.HANDLE()
    try:
        if not security.OpenProcessToken(process, 8, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        value, size = W.DWORD(), W.DWORD()
        if not security.GetTokenInformation(token, 29, ctypes.byref(value), 4, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not value.value:return None
        family = ctypes.create_unicode_buffer(256);length = W.UINT(len(family))
        error = kernel.GetPackageFamilyName(process, ctypes.byref(length), family)
        if error:raise ctypes.WinError(error)
        if not re.fullmatch(r'Microsoft\.Windows\.ShellExperienceHost_[a-z0-9]+', family.value):
            raise OSError('不支持的系统面板沙箱')
        namespace = ctypes.create_unicode_buffer(1024);length = W.ULONG()
        if not kernel.GetAppContainerNamedObjectPath(token, None, len(namespace), namespace, ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'root': Path(os.environ['LOCALAPPDATA']) / 'Packages' / family.value / 'LocalState/BigFishDock/shell-appearance',
                'event': 'Local\\' + namespace.value + '\\BigFishDock.ShellAppearance.' + str(pid)}
    finally:
        if token:kernel.CloseHandle(token)
        kernel.CloseHandle(process)


def _duplicate(pid, source, access):
    kernel, _ = _api()
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.DuplicateHandle.argtypes = [W.HANDLE, W.HANDLE, W.HANDLE, ctypes.POINTER(W.HANDLE), W.DWORD, W.BOOL, W.DWORD]
    target = kernel.OpenProcess(0x0040, False, pid)
    if not target:raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = W.HANDLE();ours = kernel.GetCurrentProcess()
        if not kernel.DuplicateHandle(ours, source or ours, target, ctypes.byref(result), access, False, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return result.value
    finally:
        kernel.CloseHandle(target)


def owner_handle(pid):
    """Only a wait/query handle to this Dock, never read/write process access."""
    return _duplicate(pid, None, 0x100000 | 0x1000)


def status_handle(pid, path):
    """Grant writes to this one status file; keep package directory ACLs intact."""
    kernel, _ = _api()
    kernel.CreateFileW.argtypes = [W.LPCWSTR,W.DWORD,W.DWORD,ctypes.c_void_p,W.DWORD,W.DWORD,W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    file = kernel.CreateFileW(str(path), 0x40000000, 7, None, 4, 0x80, None)
    if file == ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:return _duplicate(pid, file, 0x40000000)
    finally:kernel.CloseHandle(file)
