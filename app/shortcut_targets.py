"""Read Windows shortcut targets without launching or resolving remote targets."""
import ctypes
import os
import uuid
from pathlib import Path


def lnk_metadata(path):
    if os.name != 'nt': return None
    ole = ctypes.WinDLL('ole32')
    pointer = ctypes.c_void_p
    guid_type = ctypes.c_ubyte * 16
    def guid(value): return guid_type.from_buffer_copy(uuid.UUID(value).bytes_le)
    def method(obj, index, *args):
        table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(pointer))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, pointer, *args)(table[index])
    ole.CoInitializeEx.argtypes = [pointer, ctypes.c_ulong]
    ole.CoCreateInstance.argtypes = [pointer, pointer, ctypes.c_ulong, pointer, ctypes.POINTER(pointer)]
    ole.CoUninitialize.argtypes = []
    initialized = ole.CoInitializeEx(None, 2)
    link, persist = pointer(), pointer()
    try:
        if ole.CoCreateInstance(guid('00021401-0000-0000-c000-000000000046'), None, 1,
                                guid('000214f9-0000-0000-c000-000000000046'), ctypes.byref(link)) < 0:
            return None
        if method(link, 0, pointer, ctypes.POINTER(pointer))(link,
                guid('0000010b-0000-0000-c000-000000000046'), ctypes.byref(persist)) < 0: return None
        if method(persist, 5, ctypes.c_wchar_p, ctypes.c_ulong)(persist, os.path.abspath(path), 0) < 0: return None
        value = ctypes.create_unicode_buffer(32768)
        method(link, 3, ctypes.c_wchar_p, ctypes.c_int, pointer, ctypes.c_ulong)(link, value, len(value), None, 4)
        target = os.path.expandvars(value.value)
        args = ctypes.create_unicode_buffer(32768)
        method(link, 10, ctypes.c_wchar_p, ctypes.c_int)(link, args, len(args))
        if not target:
            pidl, name = pointer(), pointer()
            shell = ctypes.WinDLL('shell32')
            shell.SHGetNameFromIDList.argtypes = [pointer, ctypes.c_ulong, ctypes.POINTER(pointer)]
            ole.CoTaskMemFree.argtypes = [pointer]
            try:
                if method(link, 4, ctypes.POINTER(pointer))(link, ctypes.byref(pidl)) == 0 and pidl:
                    if shell.SHGetNameFromIDList(pidl, 0x80028000, ctypes.byref(name)) == 0 and name:
                        target = ctypes.wstring_at(name)
                        if target.startswith('::'): target = 'shell:'+target
            finally:
                if name: ole.CoTaskMemFree(name)
                if pidl: ole.CoTaskMemFree(pidl)
        if not target:return None
        cwd=ctypes.create_unicode_buffer(32768);icon=ctypes.create_unicode_buffer(32768)
        index=ctypes.c_int();show=ctypes.c_int(1)
        method(link,8,ctypes.c_wchar_p,ctypes.c_int)(link,cwd,len(cwd))
        method(link,16,ctypes.c_wchar_p,ctypes.c_int,ctypes.POINTER(ctypes.c_int))(link,icon,len(icon),ctypes.byref(index))
        method(link,14,ctypes.POINTER(ctypes.c_int))(link,ctypes.byref(show))
        flags=ctypes.c_uint();data=pointer()
        try:
            if method(link,0,pointer,ctypes.POINTER(pointer))(link,guid('45e2b4ae-b1c3-11d0-b92f-00a0c90312e1'),ctypes.byref(data))>=0 and data:
                method(data,6,ctypes.POINTER(ctypes.c_uint))(data,ctypes.byref(flags))
        finally:
            if data:method(data,2)(data)
        from shell_appid import shortcut_id
        app_id=shortcut_id(link)
        return dict(path=target,arguments=args.value.strip(),working_directory=os.path.expandvars(cwd.value),app_user_model_id=app_id,
                    icon=os.path.expandvars(icon.value),icon_index=index.value,
                    show_command=show.value if show.value in (1,3,7) else 1,verb='runas' if flags.value&0x2000 else '')
    except (OSError, ValueError):
        return None
    finally:
        for obj in (persist, link):
            if obj: method(obj, 2)(obj)
        if initialized >= 0: ole.CoUninitialize()
    return None


def lnk_details(path):
    info=lnk_metadata(path)
    return (info['path'],info['arguments']) if info else None


def lnk_target(path):
    details = lnk_details(path)
    return details[0] if details else None


def shortcut_target(path):
    suffix = Path(path).suffix.casefold()
    if suffix == '.lnk': return lnk_target(path)
    if suffix == '.url':
        from configparser import ConfigParser, Error
        from urllib.parse import urlsplit
        from urllib.request import url2pathname
        try:
            data = Path(path).read_bytes()[:65536]
            try: text = data.decode('utf-8-sig')
            except UnicodeDecodeError: text = data.decode('mbcs')
            parser = ConfigParser(interpolation=None)
            parser.read_string(text)
            url = urlsplit(parser.get('InternetShortcut', 'URL', fallback=''))
            if url.scheme.casefold() == 'file':
                return url2pathname(('//'+url.netloc if url.netloc and url.netloc != 'localhost' else '')+url.path)
        except (OSError, ValueError, Error): pass
    return None
