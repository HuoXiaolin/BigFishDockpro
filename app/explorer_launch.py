"""Delegate to the existing desktop Explorer, not a child of the Dock process.
Reference: https://devblogs.microsoft.com/oldnewthing/20131118-00/?p=2643
"""
import ctypes
from ctypes import wintypes
from native_file_menu import GUID,method,release


class Payload(ctypes.Union):
    _fields_=[('number',ctypes.c_long),('pointer',ctypes.c_void_p),('record',ctypes.c_void_p*2)]


class Variant(ctypes.Structure):
    _anonymous_=('value',)
    _fields_=[('vt',ctypes.c_ushort),('reserved',ctypes.c_ushort*3),('value',Payload)]


def launch(path,directory,arguments='',verb='open',show_command=1):
    ole=ctypes.WinDLL('ole32');auto=ctypes.WinDLL('oleaut32')
    ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD];ole.CoInitializeEx.restype=ctypes.c_long
    ole.CoCreateInstance.argtypes=[ctypes.POINTER(GUID),ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)]
    ole.CoCreateInstance.restype=ctypes.c_long
    auto.SysAllocString.argtypes=[wintypes.LPCWSTR];auto.SysAllocString.restype=ctypes.c_void_p
    auto.VariantClear.argtypes=[ctypes.POINTER(Variant)]
    pointers=[];variants=[];initialized=ole.CoInitializeEx(None,2)
    def check(result):
        if result<0:raise OSError('Windows desktop launch failed: 0x%08x'%(result&0xffffffff))
    def output(call,*args):
        pointer=ctypes.c_void_p();pointers.append(pointer);check(call(*args,ctypes.byref(pointer)))
        if not pointer:raise OSError('Windows desktop returned an empty interface')
        return pointer
    def query(pointer,iid):
        return output(method(pointer,0,ctypes.c_long,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)),pointer,ctypes.byref(GUID(iid)))
    def string(value):
        variant=Variant();variant.vt=8;variant.pointer=auto.SysAllocString(value);variants.append(variant)
        if not variant.pointer:raise MemoryError('Cannot allocate Shell argument')
        return variant
    try:
        if initialized<0 and initialized!=-2147417850:check(initialized)
        windows=output(ole.CoCreateInstance,ctypes.byref(GUID('9ba05972-f6a8-11cf-a442-00a0c90a8f39')),None,4,ctypes.byref(GUID('85cb6900-4d95-11cf-960c-0080c7f4ee85')))
        empty=Variant();hwnd=ctypes.c_long()
        desktop=output(method(windows,15,ctypes.c_long,ctypes.POINTER(Variant),ctypes.POINTER(Variant),ctypes.c_int,ctypes.POINTER(ctypes.c_long),ctypes.c_int,ctypes.POINTER(ctypes.c_void_p)),windows,ctypes.byref(empty),ctypes.byref(empty),8,ctypes.byref(hwnd),1)
        provider=query(desktop,'6d5140c1-7436-11ce-8034-00aa006009fa')
        browser=output(method(provider,3,ctypes.c_long,ctypes.POINTER(GUID),ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)),provider,ctypes.byref(GUID('4c96be40-915c-11cf-99d3-00aa004ae837')),ctypes.byref(GUID('000214e2-0000-0000-c000-000000000046')))
        view=output(method(browser,15,ctypes.c_long,ctypes.POINTER(ctypes.c_void_p)),browser)
        view_dispatch=output(method(view,15,ctypes.c_long,ctypes.c_uint,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)),view,0,ctypes.byref(GUID('00020400-0000-0000-c000-000000000046')))
        folder=query(view_dispatch,'e7a1af80-4d96-11cf-960c-0080c7f4ee85')
        application=output(method(folder,7,ctypes.c_long,ctypes.POINTER(ctypes.c_void_p)),folder)
        dispatch=query(application,'a4c6892c-3ba9-11d2-9dea-00c04fb16162')
        target=string(path);parameters=string(arguments);cwd=string(directory);verb=string(verb or 'open');show=Variant();show.vt=3;show.number=show_command
        # IShellDispatch2::ShellExecute; VARIANT arguments are passed by value.
        check(method(dispatch,31,ctypes.c_long,ctypes.c_void_p,Variant,Variant,Variant,Variant)(dispatch,target.pointer,parameters,cwd,verb,show))
    finally:
        for variant in variants:auto.VariantClear(ctypes.byref(variant))
        for pointer in reversed(pointers):release(pointer)
        if initialized>=0:ole.CoUninitialize()
