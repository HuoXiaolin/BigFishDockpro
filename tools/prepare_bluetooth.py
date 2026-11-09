"""Compile the on-demand Bluetooth probe with the Windows inbox .NET Framework."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tools'/'BluetoothBattery.cs'
SENSORS=ROOT/'tools'/'HardwareSensors.cs'
CPU=ROOT/'tools'/'CpuSensors.cs'
EXTENDED=ROOT/'tools'/'HardwareExtended.cs'
FANS=ROOT/'tools'/'HardwareFans.cs'
MODULES=[ROOT/'assets'/'pawnio'/(name+'.bin') for name in ('AMDFamily17','IntelMSR')]
TASKBAR=ROOT/'tools'/'TaskbarSpace.cs'
TARGET=ROOT/'artifacts'/'generated'/'DesktopResourceProbe.exe'


def prepare():
    sources=(SOURCE,SENSORS,CPU,EXTENDED,FANS,TASKBAR)
    if TARGET.is_file() and TARGET.stat().st_mtime_ns>=max(p.stat().st_mtime_ns for p in (*sources,*MODULES,Path(__file__))):return TARGET
    win=Path(os.environ['SystemRoot'])
    fx=win/'Microsoft.NET'/'Framework64'/'v4.0.30319'
    metadata=win/'System32'/'WinMetadata'
    refs=[fx/(n+'.dll') for n in ('System.Runtime','System.Runtime.InteropServices.WindowsRuntime',
          'System.Runtime.WindowsRuntime','System.Threading.Tasks','System.Collections','System.ObjectModel','System.Web.Extensions','System.Management')]
    refs += [fx/'WPF'/(n+'.dll') for n in ('WindowsBase','UIAutomationClient','UIAutomationTypes')]
    refs += [metadata/(n+'.winmd') for n in ('Windows.Devices','Windows.Foundation','Windows.Storage','Windows.System')]
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TARGET.parent) as folder:
        output=Path(folder)/TARGET.name
        args=[str(fx/'csc.exe'),'/nologo','/optimize+','/target:exe','/platform:x64','/out:'+str(output)]
        args+=['/resource:'+str(module)+','+module.name for module in MODULES]
        result=subprocess.run(args+['/reference:'+str(p) for p in refs]+[str(p) for p in sources],
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(result.stdout.decode('mbcs',errors='replace'))
        os.replace(output,TARGET)
    return TARGET


if __name__=='__main__':print(prepare())
