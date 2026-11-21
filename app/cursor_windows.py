"""Read and apply the current user's Windows pointer scheme."""
import ctypes
import sys
from ctypes import wintypes


ROLES = ('Arrow', 'Help', 'AppStarting', 'Wait', 'Crosshair', 'IBeam', 'NWPen', 'No',
         'SizeNS', 'SizeWE', 'SizeNWSE', 'SizeNESW', 'SizeAll', 'UpArrow', 'Hand', 'Pin', 'Person')
KEY = r'Control Panel\Cursors'
NAMES = ('', 'Scheme Source', *ROLES)
AERO_NAME = '@main.cpl,-1020'


class CursorSystem:
    def __init__(self, enabled=True):
        self.enabled = enabled and sys.platform == 'win32'

    def read(self):
        if not self.enabled:
            return {}
        import winreg
        values = {}
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY)
        except FileNotFoundError:
            return values
        with key:
            for name in NAMES:
                try:
                    values[name] = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    pass
        return values

    @staticmethod
    def defaults():
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r'SOFTWARE\Microsoft\Windows\CurrentVersion\Control Panel\Cursors\Schemes') as key:
                paths, _ = winreg.QueryValueEx(key, 'Windows Aero')
            parts = paths.split(',')[:len(ROLES)]
            if len(parts) == len(ROLES):
                return dict(zip(ROLES, parts)), AERO_NAME, 2
        except FileNotFoundError:
            pass
        return dict.fromkeys(ROLES, ''), '', 0

    def apply(self, name, files):
        if not self.enabled:
            raise OSError('当前会话无法切换 Windows 鼠标样式。')
        import winreg
        paths, label, source = self.defaults()
        if name is not None:
            self.check_files(files.values())
            paths.update({role: str(path) for role, path in files.items()})
            label, source = name, 0
        previous = self.read()
        values = {role: (paths[role], winreg.REG_EXPAND_SZ) for role in ROLES}
        values[''] = (label, winreg.REG_SZ)
        values['Scheme Source'] = (source, winreg.REG_DWORD)
        if values == previous:
            return
        try:
            self.write(values)
            self.reload()
        except OSError as error:
            try:
                self.write(previous)
                self.reload()
            except OSError as restore_error:
                raise OSError(f'切换失败，恢复原方案时也遇到错误：{restore_error}') from error
            raise

    @staticmethod
    def check_files(paths):
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        load = user32.LoadImageW
        load.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                         ctypes.c_int, ctypes.c_int, wintypes.UINT]
        load.restype = wintypes.HANDLE
        destroy = user32.DestroyCursor
        destroy.argtypes = [wintypes.HANDLE]
        destroy.restype = wintypes.BOOL
        for path in dict.fromkeys(paths):
            cursor = load(None, str(path), 2, 0, 0, 0x10 | 0x40)
            if not cursor:
                raise OSError(f'Windows 无法加载指针 {path.name}。')
            destroy(cursor)

    @staticmethod
    def write(values):
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in NAMES:
                if name in values:
                    value, kind = values[name]
                    winreg.SetValueEx(key, name, 0, kind, value)
                else:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass

    @staticmethod
    def reload():
        call = ctypes.WinDLL('user32', use_last_error=True).SystemParametersInfoW
        call.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT]
        call.restype = wintypes.BOOL
        if not call(0x0057, 0, None, 0):  # SPI_SETCURSORS
            raise ctypes.WinError(ctypes.get_last_error())


def native_default(values):
    name = values.get('', ('',))[0]
    arrow = values.get('Arrow', ('',))[0]
    return name == AERO_NAME or not (name or arrow)
