"""Prepare hash-pinned Windows 11 taskbar files for the offline installer."""
import hashlib
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'artifacts/taskbar-downloads'
PAYLOAD = ROOT / 'artifacts/taskbar-payload'
UPSTREAM = 'https://github.com/TranslucentTB/TranslucentTB'
COMPAT_TAP = ROOT / 'assets/taskbar-compat/ExplorerTAP.dll'
COMPAT_TAP_SHA256 = 'f29cb345770d7815a5e17ca9a5f3afaf9eb55de32d194d509ef951ba5766d3b3'


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
    patched = COMPAT_TAP.read_bytes()
    if hashlib.sha256(patched).hexdigest() != COMPAT_TAP_SHA256:
        raise ValueError('Unexpected taskbar compatibility DLL hash')
    (backend / 'ExplorerTAP.dll').write_bytes(patched)
    with ZipFile(vc) as archive:
        package = archive.read('x64/Microsoft.VCLibs.140.00_14.0.33519.0_x64.appx')
        (PAYLOAD / 'VCLibs-x64.appx').write_bytes(package)
    with ZipFile(xaml) as archive:
        (PAYLOAD / 'WinUI-x64.appx').write_bytes(
            archive.read('tools/AppX/x64/Release/Microsoft.UI.Xaml.2.8.appx'))
        (backend / 'Microsoft-WinUI-LICENSE.txt').write_bytes(archive.read('license.txt'))
    (backend / 'THIRD-PARTY-NOTICES.txt').write_text(
        'TranslucentTB 2026.2, GPL version 3. ExplorerTAP rebuilt locally with XAML root fix b8716c1, tray overflow and taskbar context menu styling.\n'
        f'Corresponding source and build files: {UPSTREAM}/tree/2026.2\n'
        f'Compatibility patch: {UPSTREAM}/commit/b8716c1207037013515a289c365918cb4aea109e\n'
        'Local source preparation and build: tools/build_taskbar_compat.py in BigFishDockpro source delivery.\n'
        'Flyout sources: tools/taskbar_overflow.hpp and tools/taskbar_context_menu.hpp in BigFishDockpro source delivery.\n'
        f'Release and source archives: {UPSTREAM}/releases/tag/2026.2\n',
        encoding='utf-8')
    (backend / 'TranslucentTB-LICENSE.txt').write_bytes(
        (ROOT / 'licenses/TranslucentTB-LICENSE.txt').read_bytes())
    if not (backend / 'TranslucentTB.exe').is_file():
        raise ValueError('Expected portable executable missing')


if __name__ == '__main__':
    main()
