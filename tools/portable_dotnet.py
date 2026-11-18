"""Supply verified Microsoft runtime files to the self-contained Windows executable."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
VERSION = '10.0.15'
BASENAME = 'BigFishDockpro-Portable-dotNET-x64.exe'
CACHE = ROOT / 'artifacts' / 'dotnet-redist'
# SHA-512 from https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json
ARCHIVES = (
    ('Runtime', 'dotnet-runtime', '06f0bedd59ae4ac722ada805a6d6bbf605bcdc790c71f59b7003878072902b5cde5dec8c40c0baa81192660d4748e9d79afdbdcb0c0ea9d6b821d0a044c4c6dd'),
    ('WindowsDesktop', 'windowsdesktop-runtime', 'd82ee2e70f0c1ee7af3a908a944541993782aa80a3fd2b2e02a3fdf27edc81c0ad946f14a3fe34bae295f1b7a23f5d35a466239726e4457bb200de0344e077c4'),
)


def digest(path, algorithm='sha256'):
    with path.open('rb') as file:
        return hashlib.file_digest(file, algorithm).hexdigest()


def prepare():
    CACHE.mkdir(parents=True, exist_ok=True)
    paths = []
    for channel, name, expected in ARCHIVES:
        filename = f'{name}-{VERSION}-win-x64.zip'
        path = CACHE / filename
        if not path.is_file() or digest(path, 'sha512') != expected:
            url = f'https://builds.dotnet.microsoft.com/dotnet/{channel}/{VERSION}/{filename}'
            request = Request(url, headers={'User-Agent': 'BigFishDockpro-build'})
            with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as draft:
                pending = Path(draft.name)
            try:
                with urlopen(request, timeout=120) as source, pending.open('wb') as output:
                    shutil.copyfileobj(source, output)
                if digest(pending, 'sha512') != expected:
                    raise ValueError(f'Microsoft SHA-512 mismatch for {filename}')
                pending.replace(path)
            finally:
                pending.unlink(missing_ok=True)
        paths.append(path)
    return paths


def runtime_entries():
    """Return PyInstaller DATA entries, preserving the framework tree and original signed bytes."""
    stage = CACHE / VERSION
    entries = {}
    for package in prepare():
        with ZipFile(package) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                relative = PurePosixPath(member.filename.replace('\\', '/'))
                if relative.is_absolute() or '..' in relative.parts or ':' in str(relative):
                    raise ValueError(f'Invalid runtime path {relative}')
                key = 'dotnet/' + relative.as_posix()
                payload = archive.read(member)
                path = stage / relative
                if key in entries:
                    if path.read_bytes() != payload:
                        raise ValueError(f'Conflicting Microsoft runtime file {relative}')
                    continue
                if not path.is_file() or path.read_bytes() != payload:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as draft:
                        pending = Path(draft.name)
                    try:
                        pending.write_bytes(payload)
                        pending.replace(path)
                    finally:
                        pending.unlink(missing_ok=True)
                entries[key] = (key, str(path), 'DATA')
    required = ('dotnet.exe','LICENSE.txt','ThirdPartyNotices.txt',f'host/fxr/{VERSION}/hostfxr.dll',
                f'shared/Microsoft.NETCore.App/{VERSION}/coreclr.dll',
                f'shared/Microsoft.WindowsDesktop.App/{VERSION}/PresentationFramework.dll')
    if any('dotnet/' + name not in entries for name in required):
        raise ValueError('Private desktop runtime is incomplete.')
    return list(entries.values())


def verify():
    from PyInstaller.archive.readers import CArchiveReader
    artifact = ROOT / 'release' / BASENAME
    embedded = CArchiveReader(str(artifact))
    names = {key.replace('\\','/'):key for key in embedded.toc if key.replace('\\','/').startswith('dotnet/')}
    expected = {name:Path(path) for name,path,_ in runtime_entries()}
    if names.keys() != expected.keys():
        raise ValueError('Embedded runtime files differ from the official x64 distribution.')
    for name, path in expected.items():
        if embedded.extract(names[name]) != path.read_bytes():
            raise ValueError(f'Embedded runtime payload differs: {name}')
    output = ROOT / 'artifacts' / 'dotnet-portable-test'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='单文件 便携-', dir=output) as temp:
        executable = Path(temp) / BASENAME
        shutil.copy2(artifact, executable)
        if list(Path(temp).iterdir()) != [executable]:
            raise ValueError('Validation must start with only the executable in its folder.')
        missing = str(Path(temp) / 'no-system-runtime')
        env = dict(os.environ, DOTNET_ROOT=missing, DOTNET_ROOT_X64=missing, DOTNET_MULTILEVEL_LOOKUP='0',
                   FISHDOCK_VERIFY_PRIVATE_DOTNET='1')
        subprocess.run([sys.executable, str(ROOT / 'tools/run_isolated_test.py'), '--target', str(executable),
                        '--startup', '--fresh-profile', '--timeout', '100', '--output', str(output)],
                       env=env, check=True)
        if list(Path(temp).iterdir()) != [executable]:
            raise ValueError('The portable executable left sidecar files in its launch folder.')
    result_path = output / 'result.json'
    result = json.loads(result_path.read_text(encoding='utf-8'))
    if not result.get('passed') or result.get('private_runtime', {}).get('version') != VERSION:
        raise ValueError('The standalone executable did not verify its private runtime.')
    result['executable_sha256'] = digest(artifact)
    result['embedded_runtime_files'] = len(expected)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = {'prepare': prepare, 'verify': verify}
    parser.add_argument('action', choices=actions)
    action = parser.parse_args().action
    print(actions[action]())
