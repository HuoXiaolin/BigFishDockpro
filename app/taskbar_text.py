"""Opt-in taskbar foreground via Windows shell mode, with conditional restore."""
import ctypes,json,os,threading
from pathlib import Path
from ctypes import wintypes

MODES=[('跟随系统','system'),('浅色文字（白字）','light'),('深色文字（黑字）','dark')]
KEY=r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
VALUE='SystemUsesLightTheme'
_lock=threading.Lock();_thread=None;_pending=False

def read_mode():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as key:value,kind=winreg.QueryValueEx(key,VALUE)
    except FileNotFoundError:return None
    if kind!=winreg.REG_DWORD or value not in (0,1):raise OSError('Windows 明暗模式值不受支持。')
    return value

def system_mode():
    try:
        return read_mode()
    except OSError:
        return None


def foreground_ink(mode):
    return '#ffffff' if mode == 0 else '#000000'


def write_mode(value):
    if os.environ.get('FISHDOCK_TEST_DESKTOP'):raise OSError('隔离测试不修改 Windows 配色。')
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,KEY,0,winreg.KEY_SET_VALUE) as key:
        if value is None:
            try:winreg.DeleteValue(key,VALUE)
            except FileNotFoundError:pass
        else:winreg.SetValueEx(key,VALUE,0,winreg.REG_DWORD,value)

def _broadcast():
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.SendMessageTimeoutW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype=wintypes.LPARAM
    name=ctypes.create_unicode_buffer('ImmersiveColorSet');result=ctypes.c_size_t()
    user.SendMessageTimeoutW(0xffff,0x001a,0,ctypes.addressof(name),0x0002,100,ctypes.byref(result))

def notify_shell():
    """Coalesce broadcasts on one short-lived worker; never block Settings Save."""
    global _thread,_pending
    if os.environ.get('FISHDOCK_TEST_DESKTOP'):return
    with _lock:
        _pending=True
        if _thread is not None and _thread.is_alive():return
        def run():
            global _pending,_thread
            while True:
                with _lock:
                    if not _pending:_thread=None;return
                    _pending=False
                try:_broadcast()
                except (OSError,AttributeError):pass
        _thread=threading.Thread(target=run,name='TaskbarThemeNotification',daemon=True);_thread.start()

class TaskbarText:
    def __init__(self,path,log,enabled=True,read=read_mode,write=write_mode,notify=notify_shell):
        self.path=Path(path);self.log=log;self.enabled=enabled;self.read=read;self.write=write;self.notify=notify
        self.selection=None;self.error='';self.record=None
        if not enabled:return
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            valid=lambda v:v is None or (type(v) is int and v in (0,1))
            if isinstance(data,dict) and data.get('version')==1 and 'original' in data and valid(data['original']) and type(data.get('applied')) is int and data['applied'] in (0,1):self.record=data
        except (OSError,ValueError):pass

    def persist(self,record):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.pending')
        temporary.write_text(json.dumps(record),encoding='utf-8');os.replace(temporary,self.path)
        self.record=record

    def discard(self):
        self.path.unlink(missing_ok=True);self.record=None

    def restore(self):
        if self.record is None:return
        # The user may have changed Windows mode after us; their newer choice wins.
        if self.read()==self.record['applied']:
            self.write(self.record['original']);self.notify()
        self.discard()

    def sync(self,mode):
        if not self.enabled:return True
        if mode not in {'system','light','dark'}:mode='system'
        if self.selection==mode and not self.error:return True
        try:
            if mode=='system':self.restore()
            else:
                current=self.read();wanted=0 if mode=='light' else 1
                if current!=wanted:
                    original=self.record['original'] if self.record and current==self.record['applied'] else current
                    previous=self.record
                    self.persist({'version':1,'original':original,'applied':wanted})
                    try:self.write(wanted)
                    except OSError:
                        if previous:self.persist(previous)
                        else:self.discard()
                        raise
                    self.notify()
            self.selection=mode;self.error='';return True
        except OSError as error:
            self.error='任务栏文字配色未应用：'+str(error)
            self.log(self.error);return False

    def close(self,wait_ms=300):
        if not self.enabled:return
        try:self.restore()
        except OSError as error:self.log('恢复 Windows 原配色失败，已保留恢复记录：'+str(error))
        # Give the restore notification a bounded chance to reach Explorer.
        worker=_thread
        if wait_ms and worker is not None:worker.join(wait_ms/1000)
