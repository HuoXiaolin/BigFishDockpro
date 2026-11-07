"""Populate a verified HTTPS NuGet feed when Windows TLS is unavailable."""
from pathlib import Path
import re,shutil,sys,zipfile
from urllib.request import urlopen
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
FEED=ROOT/'artifacts/nuget-feed'
SEEN=set()


def fetch(name,version):
    name=name.lower();version=version.strip('[]()').split(',')[0].strip()
    if not version or (name,version) in SEEN:return
    SEEN.add((name,version));target=FEED/f'{name}.{version}.nupkg'
    if not target.exists():
        cached=Path('D:/Agant/toolchain/nuget/packages')/name/version/target.name
        if cached.exists():shutil.copy2(cached,target)
        else:
            with urlopen(f'https://api.nuget.org/v3-flatcontainer/{name}/{version}/{target.name}',timeout=60) as response:
                with target.with_suffix('.tmp').open('wb') as out:shutil.copyfileobj(response,out)
            target.with_suffix('.tmp').replace(target)
    print(name,version,flush=True)
    with zipfile.ZipFile(target) as package:
        spec=ET.fromstring(package.read(next(n for n in package.namelist() if n.endswith('.nuspec'))))
    for node in spec.iter():node.tag=node.tag.rsplit('}',1)[-1]
    deps=spec.find('metadata/dependencies')
    if deps is None:return
    groups=deps.findall('group')
    if groups:
        def score(group):
            tf=group.get('targetFramework','').lower()
            match=re.search(r'(?:net|netcoreapp|\.netcoreapp)(\d+(?:\.\d+)?)',tf)
            if match and 5<=float(match[1])<=10:return 100+float(match[1])+('windows' in tf)*.1
            match=re.search(r'(?:netstandard|\.netstandard)(\d+(?:\.\d+)?)',tf)
            if match:return 50+float(match[1])
            return 0 if not tf else -1
        eligible=[g for g in groups if score(g)>=0]
        deps=max(eligible,key=score) if eligible else deps
    for dep in deps.findall('dependency'):fetch(dep.get('id'),dep.get('version'))


if __name__=='__main__':
    FEED.mkdir(parents=True,exist_ok=True)
    pairs=list(zip(sys.argv[1::2],sys.argv[2::2])) or [('Jint','4.16.3'),('ZstdSharp.Port','0.8.8'),('NAudio.Wasapi','2.2.1'),
        ('System.Management','10.0.0'),('Microsoft.Windows.SDK.NET.Ref','10.0.19041.57'),
        ('Microsoft.NETCore.App.Runtime.win-x64','10.0.12'),('Microsoft.WindowsDesktop.App.Runtime.win-x64','10.0.12')]
    for name,version in pairs:fetch(name,version)
