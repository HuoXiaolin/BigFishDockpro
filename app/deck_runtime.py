"""Locate the packaged or installed x64 .NET 10 Desktop Runtime."""
import os
import sys
from pathlib import Path

RUNTIME_URL='https://dotnet.microsoft.com/en-us/download/dotnet/10.0'


def private_runtime():
    bundle = getattr(sys, '_MEIPASS', None)
    if not bundle:
        return None
    root = Path(bundle) / 'dotnet'
    if not (root / 'dotnet.exe').is_file():
        return None
    for desktop in (root / 'shared/Microsoft.WindowsDesktop.App').glob('10.0.*'):
        version = desktop.name
        if version[5:].isdigit() and all(path.is_file() for path in (
            desktop / 'PresentationFramework.dll', root / 'shared/Microsoft.NETCore.App' / version / 'coreclr.dll',
            root / 'host/fxr' / version / 'hostfxr.dll',
        )):
            return root
    return None


def installed_runtime():
    private = private_runtime()
    if private is not None:
        return private
    paths=[]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\dotnet\Setup\InstalledVersions\x64',0,winreg.KEY_READ|winreg.KEY_WOW64_32KEY) as key:paths.append(Path(winreg.QueryValueEx(key,'InstallLocation')[0]))
    except (OSError,ImportError):pass
    folder=os.environ.get('ProgramW6432') or os.environ.get('ProgramFiles')
    if folder:paths.append(Path(folder)/'dotnet')
    for root in paths:
        try:
            desktop=root/'shared/Microsoft.WindowsDesktop.App';core=root/'shared/Microsoft.NETCore.App'
            valid=lambda p:p.name.startswith('10.0.') and p.name[5:].isdigit()
            if any(valid(p) and (p/'PresentationFramework.dll').is_file() for p in desktop.iterdir()) and any(valid(p) and (p/'coreclr.dll').is_file() for p in core.iterdir()):return root
        except OSError:continue
    return None
