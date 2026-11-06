"""Open only the bundled, hash-pinned official installer after a user click."""
import hashlib
import os
from pathlib import Path
from resource_probes import binary

DIGEST='1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032'


def installed():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
            version=str(winreg.QueryValueEx(key,'DisplayVersion')[0])
        return version if (Path(os.environ['ProgramFiles'])/'PawnIO'/'PawnIOLib.dll').is_file() else ''
    except OSError:return ''


def launch():
    path=binary('PawnIO_setup.exe')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=DIGEST:raise ValueError('内置 PawnIO 安装包校验失败。')
    # ShellExecute handles the official installer's elevation manifest and normal Windows UI.
    os.startfile(str(path))
