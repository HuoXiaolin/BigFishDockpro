"""Find the registered x64 .NET 10 desktop runtime without launching a process."""
import os
from pathlib import Path

RUNTIME_URL='https://dotnet.microsoft.com/en-us/download/dotnet/10.0'


def installed_runtime():
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
