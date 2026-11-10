"""Populate a verified HTTPS NuGet feed when Windows TLS is unavailable."""
import argparse
from pathlib import Path
import re,shutil,zipfile
from urllib.request import urlopen
from xml.etree import ElementTree as ET
from prepare_deck import SHARED_PACKAGES

ROOT=Path(__file__).resolve().parents[1]
FEED=ROOT/'artifacts/nuget-feed'
SEEN=set()


def fetch(name,version,shared_packages=SHARED_PACKAGES):
    name=name.lower();version=version.strip('[]()').split(',')[0].strip()
    if not version or (name,version) in SEEN:return
    SEEN.add((name,version));target=FEED/f'{name}.{version}.nupkg'
    cached=shared_packages/name/version/target.name
    if cached.is_file() and cached.with_name('.nupkg.metadata').is_file():
        target=cached
    elif not target.exists():
        if cached.is_file():shutil.copy2(cached,target)
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
    for dep in deps.findall('dependency'):fetch(dep.get('id'),dep.get('version'),shared_packages)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared-packages',type=Path,default=SHARED_PACKAGES)
    parser.add_argument('packages',nargs='*',metavar='PACKAGE_OR_VERSION')
    options=parser.parse_args()
    FEED.mkdir(parents=True,exist_ok=True)
    pairs=list(zip(options.packages[::2],options.packages[1::2],strict=True)) or [('Jint','4.16.3'),('ZstdSharp.Port','0.8.8'),('NAudio.Wasapi','2.2.1'),
        ('System.Management','10.0.0'),('Microsoft.Windows.SDK.NET.Ref','10.0.19041.57'),
        ('Microsoft.NETCore.App.Runtime.win-x64','10.0.12'),('Microsoft.WindowsDesktop.App.Runtime.win-x64','10.0.12')]
    for name,version in pairs:fetch(name,version,options.shared_packages)
