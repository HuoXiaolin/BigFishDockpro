"""Host Windows Shell IContextMenu for real file items plus card commands."""
import ctypes
import os
import uuid
from ctypes import wintypes

SHELL_FIRST=1
SHELL_LAST=0x5fff
APP_FIRST=0x7000


class GUID(ctypes.Structure):
    _fields_=[('Data1',ctypes.c_uint32),('Data2',ctypes.c_uint16),('Data3',ctypes.c_uint16),('Data4',ctypes.c_ubyte*8)]
    def __init__(self,value):
        super().__init__();ctypes.memmove(ctypes.byref(self),uuid.UUID(value).bytes_le,16)


def method(pointer,index,restype,*args):
    table=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype,ctypes.c_void_p,*args)(table[index])


def release(pointer):
    if pointer and pointer.value:method(pointer,2,ctypes.c_ulong)(pointer)


class DEFCONTEXTMENU(ctypes.Structure):
    _fields_=[('hwnd',wintypes.HWND),('pcmcb',ctypes.c_void_p),('pidlFolder',ctypes.c_void_p),
              ('psf',ctypes.c_void_p),('cidl',wintypes.UINT),('apidl',ctypes.POINTER(ctypes.c_void_p)),
              ('punkAssociationInfo',ctypes.c_void_p),('cKeys',wintypes.UINT),('aKeys',ctypes.c_void_p)]


class CMINVOKECOMMANDINFOEX(ctypes.Structure):
    _fields_=[('cbSize',wintypes.DWORD),('fMask',wintypes.DWORD),('hwnd',wintypes.HWND),
              ('lpVerb',ctypes.c_void_p),('lpParameters',ctypes.c_void_p),('lpDirectory',ctypes.c_void_p),
              ('nShow',ctypes.c_int),('dwHotKey',wintypes.DWORD),('hIcon',wintypes.HANDLE),
              ('lpTitle',ctypes.c_void_p),('lpVerbW',ctypes.c_void_p),('lpParametersW',ctypes.c_void_p),
              ('lpDirectoryW',ctypes.c_void_p),('lpTitleW',ctypes.c_void_p),('ptInvoke',wintypes.POINT)]


class NativeFileMenu:
    def __init__(self,owner,paths):
        self.owner=int(owner);self.paths=list(dict.fromkeys(os.path.abspath(path) for path in paths))
        if not self.paths or any(not os.path.exists(path) for path in self.paths):raise ValueError('文件不存在或无法访问，请刷新后重试。')
        self.shell=ctypes.WinDLL('shell32',use_last_error=True);self.ole=ctypes.WinDLL('ole32',use_last_error=True);self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.context=ctypes.c_void_p();self.context3=ctypes.c_void_p();self.context2=ctypes.c_void_p();self.folder=ctypes.c_void_p()
        self.pidls=[];self.root_pidl=ctypes.c_void_p();self.menu=None;self.callbacks={};self.verb_handlers={};self.next_id=APP_FIRST;self.initialized=False;self.command_count=0
        self._setup_api()
        try:self._create()
        except Exception:self.close();raise

    def _setup_api(self):
        s=self.shell;u=self.user;o=self.ole
        o.OleInitialize.argtypes=[ctypes.c_void_p];o.OleInitialize.restype=ctypes.c_long;o.OleUninitialize.argtypes=[];o.CoTaskMemFree.argtypes=[ctypes.c_void_p]
        s.SHParseDisplayName.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p),wintypes.DWORD,ctypes.c_void_p];s.SHParseDisplayName.restype=ctypes.c_long
        s.SHBindToParent.argtypes=[ctypes.c_void_p,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_void_p)];s.SHBindToParent.restype=ctypes.c_long
        s.SHGetDesktopFolder.argtypes=[ctypes.POINTER(ctypes.c_void_p)];s.SHGetDesktopFolder.restype=ctypes.c_long
        s.SHGetSpecialFolderLocation.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.POINTER(ctypes.c_void_p)];s.SHGetSpecialFolderLocation.restype=ctypes.c_long
        s.SHCreateDefaultContextMenu.argtypes=[ctypes.POINTER(DEFCONTEXTMENU),ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)];s.SHCreateDefaultContextMenu.restype=ctypes.c_long
        u.CreatePopupMenu.restype=wintypes.HMENU;u.DestroyMenu.argtypes=[wintypes.HMENU]
        u.AppendMenuW.argtypes=[wintypes.HMENU,wintypes.UINT,ctypes.c_size_t,wintypes.LPCWSTR];u.AppendMenuW.restype=wintypes.BOOL
        u.GetMenuItemCount.argtypes=[wintypes.HMENU];u.GetMenuItemCount.restype=ctypes.c_int
        u.TrackPopupMenuEx.argtypes=[wintypes.HMENU,wintypes.UINT,ctypes.c_int,ctypes.c_int,wintypes.HWND,ctypes.c_void_p];u.TrackPopupMenuEx.restype=wintypes.UINT
        u.GetCursorPos.argtypes=[ctypes.POINTER(wintypes.POINT)]

    @staticmethod
    def check(hr,what):
        if hr<0:raise OSError('%s（0x%08X）'%(what,hr&0xffffffff))

    def _create(self):
        self.check(self.ole.OleInitialize(None),'无法初始化 Windows 文件菜单');self.initialized=True
        for path in self.paths:
            pidl=ctypes.c_void_p();self.check(self.shell.SHParseDisplayName(path,None,ctypes.byref(pidl),0,None),'无法找到文件');self.pidls.append(pidl)
        iid_context=GUID('000214e4-0000-0000-c000-000000000046')
        parents={os.path.normcase(os.path.abspath(os.path.dirname(path))) for path in self.paths}
        if len(parents)==1:
            children=[];folder_iid=GUID('000214e6-0000-0000-c000-000000000046')
            for index,pidl in enumerate(self.pidls):
                parent=ctypes.c_void_p();child=ctypes.c_void_p()
                self.check(self.shell.SHBindToParent(pidl,ctypes.byref(folder_iid),ctypes.byref(parent),ctypes.byref(child)),'无法打开文件所在文件夹')
                if index==0:self.folder=parent
                else:release(parent)
                children.append(child.value)
            array=(ctypes.c_void_p*len(children))(*children)
            get=method(self.folder,10,ctypes.c_long,wintypes.HWND,wintypes.UINT,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(GUID),ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p))
            self.check(get(self.folder,self.owner,len(children),array,ctypes.byref(iid_context),None,ctypes.byref(self.context)),'无法打开系统右键菜单')
        else:
            # Multiple parents: anchor absolute PIDLs at the Shell desktop root.
            self.check(self.shell.SHGetDesktopFolder(ctypes.byref(self.folder)),'无法访问桌面命名空间')
            self.check(self.shell.SHGetSpecialFolderLocation(self.owner,0,ctypes.byref(self.root_pidl)),'无法定位桌面命名空间')
            array=(ctypes.c_void_p*len(self.pidls))(*(item.value for item in self.pidls))
            dcm=DEFCONTEXTMENU();dcm.hwnd=self.owner;dcm.pidlFolder=self.root_pidl;dcm.psf=self.folder;dcm.cidl=len(array);dcm.apidl=array
            self.check(self.shell.SHCreateDefaultContextMenu(ctypes.byref(dcm),ctypes.byref(iid_context),ctypes.byref(self.context)),'无法打开多位置文件的系统菜单')
        self.menu=self.user.CreatePopupMenu()
        if not self.menu:raise OSError('无法创建 Windows 菜单。')
        query=method(self.context,3,ctypes.c_long,wintypes.HMENU,wintypes.UINT,wintypes.UINT,wintypes.UINT,wintypes.UINT)
        hr=query(self.context,self.menu,0,SHELL_FIRST,SHELL_LAST,0);self.check(hr,'无法生成系统文件菜单')
        self.command_count=hr&0xffff
        if self.user.GetMenuItemCount(self.menu)<=0:raise OSError('Windows 未提供此选择的文件菜单。')
        for name,pointer in [('bcfce0a0-ec17-11d0-8d10-00a0c90f2719',self.context3),('000214f4-0000-0000-c000-000000000046',self.context2)]:
            iid=GUID(name);method(self.context,0,ctypes.c_long,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p))(self.context,ctypes.byref(iid),ctypes.byref(pointer))

    def add_card_commands(self,commands):
        """commands is a nested list of (label, callback or list of commands)."""
        submenu=self.user.CreatePopupMenu()
        if not submenu:raise OSError('无法创建卡片菜单。')
        try:
            def append(menu,items):
                for title,action in items:
                    if isinstance(action,list):
                        child=self.user.CreatePopupMenu()
                        if not child:raise OSError('无法创建卡片子菜单。')
                        try:
                            append(child,action)
                            if not self.user.AppendMenuW(menu,0x10,child,title):raise OSError('无法添加卡片子菜单。')
                        except Exception:self.user.DestroyMenu(child);raise
                    else:
                        identity=self.next_id;self.next_id+=1
                        if identity>0xffef:raise ValueError('卡片菜单项目过多。')
                        self.callbacks[identity]=action
                        if not self.user.AppendMenuW(menu,0,identity,title):raise OSError('无法添加卡片操作。')
            append(submenu,commands)
            if not self.user.AppendMenuW(self.menu,0x800,0,None):raise OSError('无法添加菜单分隔线。')
            if not self.user.AppendMenuW(self.menu,0x10,submenu,'大肥鱼Dock'):raise OSError('无法添加卡片菜单。')
        except Exception:self.user.DestroyMenu(submenu);raise

    def handle_message(self,message,wparam,lparam):
        if message not in (0x0117,0x002b,0x002c,0x0120):return None
        if self.context3.value:
            result=ctypes.c_ssize_t();handle=method(self.context3,7,ctypes.c_long,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,ctypes.POINTER(ctypes.c_ssize_t))
            hr=handle(self.context3,message,wparam,lparam,ctypes.byref(result))
            if hr>=0:return result.value
        elif self.context2.value:
            handle=method(self.context2,6,ctypes.c_long,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
            if handle(self.context2,message,wparam,lparam)>=0:return 0
        return None

    def command_verb(self,index):
        buffer=ctypes.create_unicode_buffer(256)
        getter=method(self.context,5,ctypes.c_long,ctypes.c_size_t,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT)
        hr=getter(self.context,index,4,None,ctypes.cast(buffer,ctypes.c_void_p),len(buffer))
        return buffer.value.lower() if hr>=0 else ''

    def invoke_verb(self,verb):
        for index in range(self.command_count):
            if self.command_verb(index)==verb:return self.invoke(SHELL_FIRST+index)
        raise ValueError('Windows 未提供此文件操作：'+verb)

    def invoke(self,identity):
        if identity in self.callbacks:self.callbacks[identity]();return 'card'
        if not (SHELL_FIRST<=identity<SHELL_FIRST+self.command_count):return 'cancelled'
        handler=self.verb_handlers.get(self.command_verb(identity-SHELL_FIRST))
        if handler:handler();return 'card'
        info=CMINVOKECOMMANDINFOEX();info.cbSize=ctypes.sizeof(info);info.fMask=0x00004000;info.hwnd=self.owner
        info.lpVerb=identity-SHELL_FIRST;info.lpVerbW=identity-SHELL_FIRST;info.nShow=1
        invoke=method(self.context,4,ctypes.c_long,ctypes.POINTER(CMINVOKECOMMANDINFOEX))
        from external_launch import clean_environment
        with clean_environment():self.check(invoke(self.context,ctypes.byref(info)),'系统文件操作未完成')
        return 'shell'

    def track(self):
        point=wintypes.POINT();self.user.GetCursorPos(ctypes.byref(point))
        selected=self.user.TrackPopupMenuEx(self.menu,0x0102,point.x,point.y,self.owner,None)
        return self.invoke(selected) if selected else 'cancelled'

    def close(self):
        if self.menu:self.user.DestroyMenu(self.menu);self.menu=None
        release(self.context3);self.context3=ctypes.c_void_p();release(self.context2);self.context2=ctypes.c_void_p()
        release(self.context);self.context=ctypes.c_void_p();release(self.folder);self.folder=ctypes.c_void_p()
        for pidl in self.pidls:
            if pidl.value:self.ole.CoTaskMemFree(pidl)
        self.pidls=[]
        if self.root_pidl.value:self.ole.CoTaskMemFree(self.root_pidl);self.root_pidl=ctypes.c_void_p()
        if self.initialized:self.ole.OleUninitialize();self.initialized=False
