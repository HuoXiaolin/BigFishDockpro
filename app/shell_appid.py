"""Read Shell app identities without changing shortcuts, windows or profiles."""
import ctypes
from ctypes import wintypes
from native_file_menu import GUID,method,release

class Key(ctypes.Structure):
    _fields_=[('fmtid',GUID),('pid',wintypes.DWORD)]
class Payload(ctypes.Union):
    _fields_=[('pointer',ctypes.c_void_p),('record',ctypes.c_void_p*2)]
class Value(ctypes.Structure):
    _anonymous_=('data',)
    _fields_=[('vt',ctypes.c_ushort),('reserved',ctypes.c_ushort*3),('data',Payload)]

def read_store(store):
    key=Key();key.fmtid=GUID('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3');key.pid=5
    value=Value();ole=ctypes.WinDLL('ole32');ole.PropVariantClear.argtypes=[ctypes.POINTER(Value)]
    try:
        if method(store,5,ctypes.c_long,ctypes.POINTER(Key),ctypes.POINTER(Value))(store,ctypes.byref(key),ctypes.byref(value))>=0:
            if value.vt in (8,31) and value.pointer:return ctypes.wstring_at(value.pointer)[:1024]
        return ''
    finally:ole.PropVariantClear(ctypes.byref(value))

def shortcut_id(link):
    store=ctypes.c_void_p();iid=GUID('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
    try:
        if method(link,0,ctypes.c_long,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p))(link,ctypes.byref(iid),ctypes.byref(store))>=0 and store:return read_store(store)
        return ''
    finally:release(store)

def window_id(hwnd):
    ole=ctypes.WinDLL('ole32');ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD];ole.CoInitializeEx.restype=ctypes.c_long
    initialized=ole.CoInitializeEx(None,2)>=0
    store=ctypes.c_void_p();iid=GUID('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
    shell=ctypes.WinDLL('shell32');shell.SHGetPropertyStoreForWindow.argtypes=[wintypes.HWND,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)];shell.SHGetPropertyStoreForWindow.restype=ctypes.c_long
    try:
        if shell.SHGetPropertyStoreForWindow(hwnd,ctypes.byref(iid),ctypes.byref(store))>=0 and store:return read_store(store)
        return ''
    finally:
        release(store)
        if initialized:ole.CoUninitialize()

def arguments_list(arguments):
    shell=ctypes.WinDLL('shell32');kernel=ctypes.WinDLL('kernel32')
    shell.CommandLineToArgvW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_int)];shell.CommandLineToArgvW.restype=ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    size=ctypes.c_int();pointer=shell.CommandLineToArgvW('app '+arguments,ctypes.byref(size))
    try:return [pointer[i] for i in range(1,size.value)] if pointer else []
    finally:
        if pointer:kernel.LocalFree(pointer)
