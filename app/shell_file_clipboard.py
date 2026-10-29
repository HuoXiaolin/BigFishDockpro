"""Windows Shell file clipboard support; folders decide copy/move and conflicts."""
import ctypes
import os
import struct
from ctypes import wintypes

PREFERRED='application/x-qt-windows-mime;value="Preferred DropEffect"'
COPY=1
MOVE=2


def set_file_clipboard(paths,cut=False,owner=0):
    """Publish CF_HDROP and Shell Preferred DropEffect as native clipboard data."""
    paths=list(dict.fromkeys(os.path.abspath(path) for path in paths))
    if not paths or any(not os.path.exists(path) for path in paths):raise ValueError('所选文件不存在或无法访问，请刷新后重试。')
    payload=struct.pack('<IiiII',20,0,0,0,1)+('\0'.join(paths)+'\0\0').encode('utf-16-le')
    effect=struct.pack('<I',MOVE if cut else COPY)
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.RegisterClipboardFormatW.argtypes=[wintypes.LPCWSTR];user.RegisterClipboardFormatW.restype=wintypes.UINT
    user.OpenClipboard.argtypes=[wintypes.HWND];user.OpenClipboard.restype=wintypes.BOOL
    user.EmptyClipboard.restype=wintypes.BOOL;user.SetClipboardData.argtypes=[wintypes.UINT,wintypes.HANDLE];user.SetClipboardData.restype=wintypes.HANDLE
    user.CloseClipboard.restype=wintypes.BOOL
    kernel.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t];kernel.GlobalAlloc.restype=wintypes.HANDLE
    kernel.GlobalLock.argtypes=[wintypes.HANDLE];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[wintypes.HANDLE];kernel.GlobalFree.argtypes=[wintypes.HANDLE]
    def allocate(data):
        handle=kernel.GlobalAlloc(2,len(data))
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        pointer=kernel.GlobalLock(handle)
        if not pointer:kernel.GlobalFree(handle);raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(pointer,data,len(data));kernel.GlobalUnlock(handle);return handle
    file_handle=effect_handle=None;opened=False
    try:
        fmt=user.RegisterClipboardFormatW('Preferred DropEffect')
        if not fmt:raise ctypes.WinError(ctypes.get_last_error())
        file_handle=allocate(payload);effect_handle=allocate(effect)
        if not user.OpenClipboard(wintypes.HWND(owner)):raise OSError('剪贴板正被其他程序使用，请稍后重试。')
        opened=True
        if not user.EmptyClipboard():raise ctypes.WinError(ctypes.get_last_error())
        if not user.SetClipboardData(15,file_handle):raise ctypes.WinError(ctypes.get_last_error())
        file_handle=None  # Ownership transferred to the clipboard.
        if not user.SetClipboardData(fmt,effect_handle):
            user.EmptyClipboard()  # Never publish a cut as an unmarked copy.
            raise ctypes.WinError(ctypes.get_last_error())
        effect_handle=None
    finally:
        if opened:user.CloseClipboard()
        if file_handle:kernel.GlobalFree(file_handle)
        if effect_handle:kernel.GlobalFree(effect_handle)


def preferred_effect(mime):
    # Qt 5 may advertise a Windows custom MIME format but return empty data;
    # inspect the native Shell format so a cut is never mistaken for a copy.
    if mime and mime.hasFormat(PREFERRED):
        data=bytes(mime.data(PREFERRED))
        if len(data)>=4:return MOVE if struct.unpack('<I',data[:4])[0]&MOVE else COPY
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.RegisterClipboardFormatW.argtypes=[wintypes.LPCWSTR];user.RegisterClipboardFormatW.restype=wintypes.UINT
    user.OpenClipboard.argtypes=[wintypes.HWND];user.OpenClipboard.restype=wintypes.BOOL
    user.GetClipboardData.argtypes=[wintypes.UINT];user.GetClipboardData.restype=wintypes.HANDLE
    kernel.GlobalLock.argtypes=[wintypes.HANDLE];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[wintypes.HANDLE];kernel.GlobalSize.argtypes=[wintypes.HANDLE];kernel.GlobalSize.restype=ctypes.c_size_t
    fmt=user.RegisterClipboardFormatW('Preferred DropEffect')
    if not fmt:raise OSError('无法读取 Windows 剪贴板格式。')
    if not user.OpenClipboard(None):raise OSError('剪贴板正被其他程序使用，请稍后重试。')
    try:
        if not user.IsClipboardFormatAvailable(fmt):return COPY
        handle=user.GetClipboardData(fmt)
        if not handle or kernel.GlobalSize(handle)<4:raise OSError('无法读取文件复制或剪切状态。')
        pointer=kernel.GlobalLock(handle)
        if not pointer:raise OSError('无法读取文件复制或剪切状态。')
        try:return MOVE if ctypes.c_uint32.from_address(pointer).value&MOVE else COPY
        finally:kernel.GlobalUnlock(handle)
    finally:user.CloseClipboard()


def clipboard_paths(mime):
    if not mime or not mime.hasUrls():raise ValueError('剪贴板中没有可用的文件路径；请先在资源管理器复制文件。')
    urls=mime.urls()
    if not urls or any(not url.isLocalFile() for url in urls):raise ValueError('仅支持文件和文件夹；虚拟附件请先保存到文件夹。')
    paths=list(dict.fromkeys(os.path.abspath(url.toLocalFile()) for url in urls))
    if any(not os.path.exists(path) for path in paths):raise ValueError('剪贴板中的文件不存在或无法访问。')
    return paths


class SHFILEOPSTRUCT(ctypes.Structure):
    _fields_=[('hwnd',wintypes.HWND),('wFunc',wintypes.UINT),('pFrom',wintypes.LPCWSTR),
              ('pTo',wintypes.LPCWSTR),('fFlags',wintypes.WORD),('fAnyOperationsAborted',wintypes.BOOL),
              ('hNameMappings',ctypes.c_void_p),('lpszProgressTitle',wintypes.LPCWSTR)]


def paste_into_folder(folder,owner=0,preferred=COPY,paths=None):
    """Use Windows file operations for actual file paths; preserve conflict safety."""
    if not os.path.isdir(folder):raise ValueError('粘贴目标文件夹不存在或无法访问。')
    if not paths:raise ValueError('剪贴板中没有可粘贴的文件。')
    paths=list(dict.fromkeys(os.path.abspath(path) for path in paths))
    if any(not os.path.exists(path) for path in paths):raise ValueError('剪贴板中的文件不存在或无法访问。')
    if preferred==MOVE:
        def already_in_target(path):
            try:return os.path.samefile(os.path.dirname(path),folder)
            except OSError:return os.path.normcase(os.path.abspath(os.path.dirname(path)))==os.path.normcase(os.path.abspath(folder))
        paths=[path for path in paths if not already_in_target(path)]
        if not paths:return 'same-folder'
    # PCZZSTR: every absolute source name and the target end with a double NUL.
    sources=ctypes.create_unicode_buffer('\0'.join(paths)+'\0\0')
    target=ctypes.create_unicode_buffer(os.path.abspath(folder)+'\0\0')
    operation=SHFILEOPSTRUCT();operation.hwnd=wintypes.HWND(owner);operation.wFunc=1 if preferred==MOVE else 2
    operation.pFrom=ctypes.cast(sources,wintypes.LPCWSTR);operation.pTo=ctypes.cast(target,wintypes.LPCWSTR)
    operation.fFlags=0x0040|0x0008  # Allow undo; rename on collision, never silently overwrite.
    shell=ctypes.WinDLL('shell32',use_last_error=True);shell.SHFileOperationW.argtypes=[ctypes.POINTER(SHFILEOPSTRUCT)];shell.SHFileOperationW.restype=ctypes.c_int
    result=shell.SHFileOperationW(ctypes.byref(operation))
    if operation.fAnyOperationsAborted:return 'cancelled'
    if result:raise OSError('Windows 文件操作未完成（错误 0x%08X）。'%(result&0xffffffff))
    return 'completed'


def paste_popup_point(owner):
    """Return native screen coordinates, without mixing Qt logical pixels."""
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.GetWindowRect.restype=wintypes.BOOL
    user.GetCursorPos.argtypes=[ctypes.POINTER(wintypes.POINT)]
    user.GetCursorPos.restype=wintypes.BOOL
    rect=wintypes.RECT()
    if owner and user.GetWindowRect(owner,ctypes.byref(rect)) and rect.right>rect.left and rect.bottom>rect.top:
        return wintypes.POINT((rect.left+rect.right)//2,(rect.top+rect.bottom)//2)
    point=wintypes.POINT()
    if not user.GetCursorPos(ctypes.byref(point)):
        raise OSError('无法确定文件操作菜单的弹出位置，请重试。')
    return point


def paste_shell_clipboard(folder, owner=0, preferred=COPY, sequence=None):
    """Pass the original OLE data object to the folder's native drop target.

    Remote Desktop may expose FileGroupDescriptor/FileContents instead of paths.
    Windows owns delayed rendering, streams, conflict UI and transfer feedback.
    Do not enumerate/extract the payload or clear the clipboard ourselves.
    """
    if not os.path.isdir(folder):raise ValueError('粘贴目标文件夹不存在或无法访问。')
    from native_file_menu import GUID,method,release,NativeFileMenu
    shell=ctypes.WinDLL('shell32',use_last_error=True)
    ole=ctypes.WinDLL('ole32',use_last_error=True)
    ole.OleInitialize.argtypes=[ctypes.c_void_p];ole.OleInitialize.restype=ctypes.c_long
    ole.OleGetClipboard.argtypes=[ctypes.POINTER(ctypes.c_void_p)];ole.OleGetClipboard.restype=ctypes.c_long
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
    shell.SHParseDisplayName.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p),wintypes.DWORD,ctypes.c_void_p]
    shell.SHParseDisplayName.restype=ctypes.c_long
    shell.SHGetDesktopFolder.argtypes=[ctypes.POINTER(ctypes.c_void_p)];shell.SHGetDesktopFolder.restype=ctypes.c_long
    data=ctypes.c_void_p();desktop=ctypes.c_void_p();target=ctypes.c_void_p();drop=ctypes.c_void_p();pidl=ctypes.c_void_p()
    initialized=False;entered=False;check=NativeFileMenu.check
    class POINTL(ctypes.Structure):
        _fields_=[('x',wintypes.LONG),('y',wintypes.LONG)]
    try:
        check(ole.OleInitialize(None),'无法初始化 Windows 文件传输');initialized=True
        check(ole.OleGetClipboard(ctypes.byref(data)),'无法读取 Windows 文件剪贴板')
        if not data.value:raise ValueError('剪贴板中没有可粘贴的文件。')
        check(shell.SHParseDisplayName(os.path.abspath(folder),None,ctypes.byref(pidl),0,None),'无法定位粘贴目标')
        check(shell.SHGetDesktopFolder(ctypes.byref(desktop)),'无法访问 Windows 文件系统')
        iid=GUID('000214e6-0000-0000-c000-000000000046')
        bind=method(desktop,5,ctypes.c_long,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p))
        check(bind(desktop,pidl,None,ctypes.byref(iid),ctypes.byref(target)),'无法打开粘贴目标')
        iid=GUID('00000122-0000-0000-c000-000000000046')
        create=method(target,8,ctypes.c_long,wintypes.HWND,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p))
        check(create(target,owner,ctypes.byref(iid),ctypes.byref(drop)),'目标不支持 Windows 文件接收')
        anchor=paste_popup_point(owner)
        point=POINTL(anchor.x,anchor.y);effect=wintypes.DWORD(preferred);keys=4 if preferred==MOVE else 8
        enter=method(drop,3,ctypes.c_long,ctypes.c_void_p,wintypes.DWORD,POINTL,ctypes.POINTER(wintypes.DWORD))
        entered=True
        check(enter(drop,data,keys,point,ctypes.byref(effect)),'Windows 无法接收剪贴板文件')
        if not effect.value:raise ValueError('Windows 未提供可粘贴的文件；请确认远程文件剪贴板已就绪。')
        if sequence is not None and sequence!=ctypes.windll.user32.GetClipboardSequenceNumber():
            raise ValueError('剪贴板内容已变化，请重新粘贴。')
        effect.value=preferred
        transfer=method(drop,6,ctypes.c_long,ctypes.c_void_p,wintypes.DWORD,POINTL,ctypes.POINTER(wintypes.DWORD))
        from external_launch import clean_environment
        # Once Drop is called, Windows owns completion/cancellation and cut feedback.
        entered=False
        with clean_environment():check(transfer(drop,data,keys,point,ctypes.byref(effect)),'Windows 文件传输未完成')
        return 'shell-submitted'
    finally:
        if entered and drop.value:method(drop,5,ctypes.c_long)(drop)
        for pointer in (drop,target,desktop,data):release(pointer)
        if pidl.value:ole.CoTaskMemFree(pidl)
        if initialized:ole.OleUninitialize()
