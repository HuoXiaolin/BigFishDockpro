"""Fetch immutable release license texts and keep provenance for redistributing Qt."""
import json
from pathlib import Path
import tarfile
import urllib.request

root = Path(__file__).resolve().parent.parent
dest = root / 'licenses'
dest.mkdir(exist_ok=True)
with urllib.request.urlopen('https://pypi.org/pypi/PyQt5/5.15.11/json') as response:
    meta = json.load(response)
source = next(u for u in meta['urls'] if u['packagetype'] == 'sdist')
archive = root / 'references/PyQt5-5.15.11.tar.gz'
urllib.request.urlretrieve(source['url'], archive)
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        if Path(member.name).name.startswith('LICENSE'):
            (dest / ('PyQt5-' + Path(member.name).name)).write_bytes(tar.extractfile(member).read())
(dest / 'Qt-5.15.2-LICENSE.txt').write_bytes((root / '.venv/Lib/site-packages/PyQt5_Qt5-5.15.2.dist-info/LICENSE').read_bytes())
urllib.request.urlretrieve('https://raw.githubusercontent.com/python/cpython/v3.12.14/LICENSE', dest / 'Python-3.12.14-LICENSE.txt')
(dest / 'THIRD-PARTY-NOTICES.md').write_text('''# Third-party notices

The base BigFishDock source is MIT licensed (root LICENSE). Added code is MIT
licensed. The combined binary distributed with GPL PyQt5 is provided under
GPL v3; complete application source and build scripts accompany this release
in the accompanying Fishdock source directory. Original MIT notices remain applicable.

- PyQt5 5.15.11: Riverbank Computing Ltd, GPL v3; license texts included here.
  Source: https://pypi.org/project/PyQt5/5.15.11/#files
- PyQt5-sip 12.20.0: Riverbank Computing Ltd, BSD-2-Clause.
  Source: https://pypi.org/project/PyQt5-sip/12.20.0/#files
- Qt 5.15.2: The Qt Company Ltd and contributors, LGPL v3 / GPL; license text included.
  Source: https://download.qt.io/archive/qt/5.15/5.15.2/single/
  This directory distribution keeps Qt DLLs dynamically linked and replaceable.
- Python 3.12.14: Python Software Foundation; license included.
  Source: https://www.python.org/downloads/release/python-31214/
- PyInstaller 6.16.0 bootloader: GPL v2 with bootloader distribution exception.
  Source and license: https://github.com/pyinstaller/pyinstaller/tree/v6.16.0
- lunardate 0.3.0: LI Daobing and contributors, GPL-3.0-or-later; license included in lunardate-LICENSE.txt.
  Source: https://pypi.org/project/lunardate/0.3.0/
- Microsoft Visual C++ redistributable DLLs: Microsoft Corporation, distributed
  as runtime dependencies of the Python / Qt binary wheels.

No GlassDesk or GlassBoard source or proprietary assets are included.
''', encoding='utf-8')
for package, version in [('PyQt5-sip', '12.20.0'), ('pyinstaller', '6.16.0')]:
    with urllib.request.urlopen(f'https://pypi.org/pypi/{package}/{version}/json') as response:
        urls = json.load(response)['urls']
    source = next(u for u in urls if u['packagetype'] == 'sdist')
    path = root / f'references/{package}-{version}.tar.gz'
    urllib.request.urlretrieve(source['url'], path)
    with tarfile.open(path) as tar:
        for member in tar.getmembers():
            if Path(member.name).name in ('LICENSE', 'LICENSE.txt', 'COPYING.txt') and member.isfile() and len(Path(member.name).parts) == 2:
                (dest / f'{package}-LICENSE.txt').write_bytes(tar.extractfile(member).read())
                break

import importlib.metadata as metadata
package=metadata.distribution('lunardate')
license_file=next(package.locate_file(item) for item in metadata.files('lunardate') if str(item).endswith('licenses/LICENSE.txt'))
(dest/'lunardate-LICENSE.txt').write_bytes(license_file.read_bytes())
