# Build a directory bundle, then let the installer compress it once with LZMA2.
from pathlib import Path
import os
import ssl
root = Path(SPECPATH).parent
single_file = os.environ.get('FISHDOCK_ONEFILE') == '1'
# Some Python distributions load additional trust restrictions from ssl.py's
# directory. Keep that file beside the frozen module as well.
tls_policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
tls_data = [(str(tls_policy), '.')] if tls_policy.is_file() else []
taskbar_data = []
if single_file:
    payload = root / 'artifacts/taskbar-payload'
    taskbar_data = [(str(payload / name), 'taskbar-payload') for name in ('VCLibs-x64.appx', 'WinUI-x64.appx')]
    taskbar_data += [(str(payload / 'backend'), 'taskbar-payload/backend'),
                     (str(root / 'tools/install_taskbar_frameworks.ps1'), 'taskbar-payload')]
a = Analysis([str(root / 'app/dock.py')], pathex=[str(root/name) for name in ('app','tests','tools')],
    binaries=[], datas=[(str(root / 'artifacts/pawnio/PawnIO_setup.exe'),'resource-probe'), (str(root / 'artifacts/generated/DesktopResourceProbe.exe'), 'resource-probe'), (str(root / 'artifacts/presentmon/PresentMon.exe'), 'resource-probe'), (str(root / 'licenses/PresentMon-LICENSE.txt'),'licenses'), (str(root / 'assets/dock.ico'), 'assets'), (str(root / 'assets/holidays'), 'assets/holidays'), (str(root / '使用说明.md'), '.'), (str(root / 'LICENSE'), '.'),
                        (str(root / 'licenses'), 'licenses'),
                        (str(root / 'assets/ai-providers'), 'assets/ai-providers'),
                        (str(root / 'assets/reminder-sounds'), 'assets/reminder-sounds'),
                        (str(root / 'artifacts/deck-bridge/BigFishDeckBridge.exe'), 'deck-bridge'),
                        (str(root / 'artifacts/generated/version.json'), '.'),
                        (str(root / 'assets/default_settings.json'), 'assets')] + tls_data + taskbar_data,
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PyQt5.QtNetwork', 'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtWebEngine',
              'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtSql',
              'PyQt5.QtMultimedia', 'PyQt5.QtPrintSupport', 'PyQt5.QtTest', 'tkinter'],
    # Keep assertions executable in the bundled self-test modules.
    noarchive=False, optimize=0)
# Only the native Windows platform and the icon/image formats used by this app.
def retain(entry):
    name = entry[0].replace('\\', '/').lower()
    # Qt's hook collects optional dependencies before plugin filtering. This app
    # uses QPainter's raster engine and loads Qt SVG only for imported faces.
    if name.rsplit('/', 1)[-1] in {
        'opengl32sw.dll', 'd3dcompiler_47.dll', 'libegl.dll', 'libglesv2.dll',
        'qt5quick.dll', 'qt5qml.dll', 'qt5qmlmodels.dll', 'qt5websockets.dll',
        'qt5network.dll', 'qt5dbus.dll'}:
        return False
    if '/translations/' in name:
        return False
    if '/plugins/' in name:
        return name.endswith(('/platforms/qwindows.dll', '/imageformats/qico.dll',
                              '/imageformats/qjpeg.dll','/imageformats/qgif.dll',
                              '/imageformats/qwebp.dll','/imageformats/qtiff.dll'))
    return True
a.binaries = [e for e in a.binaries if retain(e)]
a.datas = [e for e in a.datas if retain(e)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, *( [a.binaries, a.datas] if single_file else [[]] ),
          exclude_binaries=not single_file,
          name='BigFishDockpro',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, manifest=str(root/'assets/BigFishDockpro.manifest'), icon=str(root / 'assets/dock.ico'), version=str(root / 'artifacts/generated/version_info.txt'))
if not single_file:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BigFishDockpro')
