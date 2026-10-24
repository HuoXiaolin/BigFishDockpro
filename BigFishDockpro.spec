# Build a directory bundle, then let the installer compress it once with LZMA2.
from pathlib import Path
import os
root = Path(SPECPATH)
single_file = os.environ.get('FISHDOCK_ONEFILE') == '1'
a = Analysis([str(root / 'dock.py')], pathex=[str(root)],
    binaries=[], datas=[(str(root / 'dock.ico'), '.'), (str(root / '使用说明.md'), '.'), (str(root / 'LICENSE'), '.'),
                        (str(root / 'licenses'), 'licenses'),
                        (str(root / 'artifacts/generated/version.json'), '.')],
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
    # uses QPainter's raster engine, with no OpenGL, QML, SVG or Qt networking.
    if name.rsplit('/', 1)[-1] in {
        'opengl32sw.dll', 'd3dcompiler_47.dll', 'libegl.dll', 'libglesv2.dll',
        'qt5quick.dll', 'qt5qml.dll', 'qt5qmlmodels.dll', 'qt5websockets.dll',
        'qt5network.dll', 'qt5dbus.dll', 'qt5svg.dll'}:
        return False
    if '/translations/' in name:
        return False
    if '/plugins/' in name:
        return name.endswith(('/platforms/qwindows.dll', '/imageformats/qico.dll',
                              '/imageformats/qjpeg.dll'))
    return True
a.binaries = [e for e in a.binaries if retain(e)]
a.datas = [e for e in a.datas if retain(e)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, *( [a.binaries, a.datas] if single_file else [[]] ),
          exclude_binaries=not single_file,
          name='BigFishDockpro',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, manifest=str(root/'BigFishDockpro.manifest'), icon=str(root / 'dock.ico'), version=str(root / 'artifacts/generated/version_info.txt'))
if not single_file:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BigFishDockpro')
