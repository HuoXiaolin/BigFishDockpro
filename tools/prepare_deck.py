"""Build the opt-in AI/media helper from the pinned, licensed reference source."""
import os,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'artifacts/deck-bridge/BigFishDeckBridge.exe'


def prepare():
    project=ROOT/'tools/DeckBridge/DeckBridge.csproj'
    sources=[Path(__file__),ROOT/'assets/dock.ico']+[p for p in project.parent.rglob('*') if p.suffix in ('.cs','.csproj') and not {'obj','bin'}.intersection(p.parts)]
    for part in ('BrimDeck','BrimDeck.Core'):
        sources.extend(p for p in (ROOT/'references/BrimDeck/src'/part).rglob('*') if p.suffix in ('.cs','.csproj','.json') and not {'obj','bin'}.intersection(p.parts))
    if not (ROOT/'references/BrimDeck/LICENSE').is_file():raise RuntimeError('Missing pinned BrimDeck sources and license.')
    if TARGET.is_file() and TARGET.stat().st_mtime_ns>=max(p.stat().st_mtime_ns for p in sources):return TARGET
    sdk=os.environ.get('BIGFISH_DOTNET') or (r'D:\Agant\toolchain\dotnet\dotnet.exe' if Path(r'D:\Agant\toolchain\dotnet\dotnet.exe').is_file() else shutil.which('dotnet'))
    if not sdk:raise RuntimeError('Building AI/media requires .NET 10 SDK. Running the helper requires the shared .NET 10 Desktop Runtime (x64).')
    env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_CLI_HOME=str(ROOT/'artifacts/dotnet-home'),NUGET_PACKAGES=str(ROOT/'artifacts/nuget'))
    args=[sdk,'publish',str(project),'-c','Release','-r','win-x64','--self-contained','false','-o',str(TARGET.parent),'--nologo','-v','minimal']
    feed=ROOT/'artifacts/nuget-feed'
    if feed.exists():args+=['--source',str(feed)]
    for command in (args,[str(TARGET),'--self-test']):
        result=subprocess.run(command,env=env,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
        print(result.stdout);print(result.stderr);result.check_returncode()
    return TARGET


if __name__=='__main__':print(prepare())
