"""Build the opt-in AI/media helper from the pinned, licensed reference source."""
import argparse
import os,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'artifacts/deck-bridge/BigFishDeckBridge.exe'
SHARED_PACKAGES=Path(r'D:\Agant\toolchain\nuget\packages')


def prepare(dotnet=None, shared_packages=SHARED_PACKAGES):
    project=ROOT/'tools/DeckBridge/DeckBridge.csproj'
    sources=[Path(__file__),ROOT/'assets/dock.ico']+[p for p in project.parent.rglob('*') if p.suffix in ('.cs','.csproj') and not {'obj','bin'}.intersection(p.parts)]
    for part in ('BrimDeck','BrimDeck.Core'):
        sources.extend(p for p in (ROOT/'references/BrimDeck/src'/part).rglob('*') if p.suffix in ('.cs','.csproj','.json') and not {'obj','bin'}.intersection(p.parts))
    if not (ROOT/'references/BrimDeck/LICENSE').is_file():raise RuntimeError('Missing pinned BrimDeck sources and license.')
    if TARGET.is_file() and TARGET.stat().st_mtime_ns>=max(p.stat().st_mtime_ns for p in sources):return TARGET
    if dotnet is not None:
        sdk=str(dotnet.resolve())
    else:
        shared=Path(r'D:\Agant\toolchain\dotnet\dotnet.exe')
        sdk=os.environ.get('BIGFISH_DOTNET') or (str(shared) if shared.is_file() else shutil.which('dotnet'))
    if not sdk:raise RuntimeError('Building AI/media requires .NET 10 SDK. Running the helper requires the shared .NET 10 Desktop Runtime (x64).')
    print(f'.NET SDK host: {sdk}',flush=True)
    env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_HOME=str(ROOT/'artifacts/dotnet-home'),NUGET_PACKAGES=str(ROOT/'artifacts/nuget'))
    args=[sdk,'publish',str(project),'-c','Release','-r','win-x64','--self-contained','false','-o',str(TARGET.parent),'--nologo','-v','minimal']
    if shared_packages.is_dir():
        print(f'NuGet fallback packages: {shared_packages}',flush=True)
        args.append(f'-p:RestoreAdditionalProjectFallbackFolders={shared_packages.resolve()}')
    feed=ROOT/'artifacts/nuget-feed'
    if feed.exists():args+=['--source',str(feed)]
    for command in (args,[str(TARGET),'--self-test']):
        result=subprocess.run(command,env=env,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
        print(result.stdout);print(result.stderr);result.check_returncode()
    return TARGET


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dotnet',type=Path)
    parser.add_argument('--shared-packages',type=Path,default=SHARED_PACKAGES)
    options=parser.parse_args()
    print(prepare(options.dotnet, options.shared_packages))
