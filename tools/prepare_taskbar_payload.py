"""Prepare hash-pinned Windows 11 taskbar files for the offline installer."""
import hashlib
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'artifacts/taskbar-downloads'
PAYLOAD = ROOT / 'artifacts/taskbar-payload'
UPSTREAM = 'https://github.com/TranslucentTB/TranslucentTB'


def fetch(name, url, sha256):
    target = CACHE / name
    if not target.exists():
        with urlopen(url, timeout=45) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError(f'Unexpected download hash: {name}')
        target.write_bytes(data)
    if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
        raise ValueError(f'Unexpected cached archive hash: {name}')
    return target


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    backend = PAYLOAD / 'backend'
    backend.mkdir(parents=True, exist_ok=True)
    portable = fetch('portable.zip', UPSTREAM + '/releases/download/2026.2/TranslucentTB-portable-x64.zip',
                     '0dbe8e0255c20e131cde536dcd0ae490d45989a7d360e26d0150dff1922ac420')
    vc = fetch('Microsoft-dependencies.zip',
               'https://github.com/microsoft/winget-cli/releases/download/v1.12.350/DesktopAppInstaller_Dependencies.zip',
               '906cad3b2be067d816b20ea4eb1df541f8a23ac4a4aa9fed70ce675cd918e6a6')
    xaml = fetch('winui.zip',
                 'https://api.nuget.org/v3-flatcontainer/microsoft.ui.xaml/2.8.7/microsoft.ui.xaml.2.8.7.nupkg',
                 '79207b10fe243eb1a8dcdc29beceba2f472f145ed31f147f7ae3f43b0659c9f7')
    with ZipFile(portable) as archive:
        archive.extractall(backend)
    with ZipFile(vc) as archive:
        package = archive.read('x64/Microsoft.VCLibs.140.00_14.0.33519.0_x64.appx')
        (PAYLOAD / 'VCLibs-x64.appx').write_bytes(package)
    with ZipFile(xaml) as archive:
        (PAYLOAD / 'WinUI-x64.appx').write_bytes(
            archive.read('tools/AppX/x64/Release/Microsoft.UI.Xaml.2.8.appx'))
        (backend / 'Microsoft-WinUI-LICENSE.txt').write_bytes(archive.read('license.txt'))
    (backend / 'THIRD-PARTY-NOTICES.txt').write_text(
        'TranslucentTB 2026.2 (unmodified), GPL version 3.\n'
        f'Corresponding source and build files: {UPSTREAM}/tree/2026.2\n'
        f'Release and source archives: {UPSTREAM}/releases/tag/2026.2\n',
        encoding='utf-8')
    (backend / 'TranslucentTB-LICENSE.txt').write_bytes(
        (ROOT / 'licenses/TranslucentTB-LICENSE.txt').read_bytes())
    if not (backend / 'TranslucentTB.exe').is_file():
        raise ValueError('Expected portable executable missing')


if __name__ == '__main__':
    main()
