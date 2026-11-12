"""Compile the resource probe with the shared SDK for the Windows inbox .NET Framework."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tools'/'BluetoothBattery.cs'
PERIPHERALS=ROOT/'tools'/'PeripheralBattery.cs'
CUSTOM_PERIPHERALS=ROOT/'tools'/'PeripheralBattery.Custom.cs'
SENSORS=ROOT/'tools'/'HardwareSensors.cs'
CPU=ROOT/'tools'/'CpuSensors.cs'
EXTENDED=ROOT/'tools'/'HardwareExtended.cs'
FANS=ROOT/'tools'/'HardwareFans.cs'
MODULES=[ROOT/'assets'/'pawnio'/(name+'.bin') for name in ('AMDFamily17','IntelMSR')]
TASKBAR=ROOT/'tools'/'TaskbarSpace.cs'
APP_TRAFFIC=ROOT/'tools'/'AppTraffic.cs'
TARGET=ROOT/'artifacts'/'generated'/'DesktopResourceProbe.exe'
SHARED_DOTNET=Path(r'D:\Agant\toolchain\dotnet\dotnet.exe')


def prepare(dotnet: Path = SHARED_DOTNET):
    sources=(SOURCE,PERIPHERALS,CUSTOM_PERIPHERALS,SENSORS,CPU,EXTENDED,FANS,TASKBAR,APP_TRAFFIC)
    if TARGET.is_file() and TARGET.stat().st_mtime_ns>=max(p.stat().st_mtime_ns for p in (*sources,*MODULES,Path(__file__))):return TARGET
    dotnet=dotnet.resolve()
    env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',
             DOTNET_CLI_HOME=str(ROOT/'artifacts/dotnet-home'))
    sdk_version=subprocess.check_output([str(dotnet),'--version'],cwd=ROOT,env=env,
                                        text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=30).strip()
    compiler=dotnet.parent/'sdk'/sdk_version/'Roslyn'/'bincore'/'csc.dll'
    if not compiler.is_file():raise RuntimeError(f'Missing shared C# compiler: {compiler}')
    print(f'C# compiler: {compiler}',flush=True)
    win=Path(os.environ['SystemRoot'])
    fx=win/'Microsoft.NET'/'Framework64'/'v4.0.30319'
    metadata=win/'System32'/'WinMetadata'
    refs=[fx/(n+'.dll') for n in ('mscorlib','System','System.Core','System.Runtime','System.Runtime.InteropServices.WindowsRuntime',
          'System.Runtime.WindowsRuntime','System.Threading.Tasks','System.Collections','System.ObjectModel','System.Web.Extensions','System.Management')]
    refs += [fx/'WPF'/(n+'.dll') for n in ('WindowsBase','UIAutomationClient','UIAutomationTypes')]
    refs += [metadata/(n+'.winmd') for n in ('Windows.Devices','Windows.Foundation','Windows.Storage','Windows.System')]
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TARGET.parent) as folder:
        output=Path(folder)/TARGET.name
        args=[str(dotnet),str(compiler),'/nologo','/noconfig','/nostdlib+','/optimize+',
              '/target:exe','/platform:x64','/out:'+str(output)]
        args+=['/resource:'+str(module)+','+module.name for module in MODULES]
        result=subprocess.run(args+['/reference:'+str(p) for p in refs]+[str(p) for p in sources],
                              env=env,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW,timeout=60)
        if result.returncode:
            raise RuntimeError(result.stdout.decode('mbcs',errors='replace'))
        os.replace(output,TARGET)
    return TARGET


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet',type=Path,default=SHARED_DOTNET)
    print(prepare(parser.parse_args().dotnet))
