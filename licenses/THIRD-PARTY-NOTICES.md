# Third-party notices

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

## Resource capsule AI and music adapter

- BrimDeck by MoFeng2223 and contributors: Apache-2.0, pinned at
  `5cbf5596a4163803d2411b96b37f16d925a11986` from
  https://github.com/MoFeng2223/BrimDeck . Upstream Core and selected Native
  source files are linked into BigFishDeckBridge, with a locally adapted bounded
  LogReader under tools/DeckBridge/Core; BigFishDockpro adds the JSON
  adapter and its own Qt interface. Full upstream license and third-party
  notices are retained in BrimDeck-Apache-2.0.txt and BrimDeck-ThirdPartyNotices.txt.
- Jint 4.16.3, Acornima 1.7.0, ZstdSharp.Port 0.8.8, NAudio.Core/Wasapi 2.2.1,
  System.Management/System.CodeDom 10.0.0, Windows SDK .NET projection, and
  the shared .NET 10 Windows Desktop runtime are dependencies of that helper.
  The .NET runtime is installed separately and is not bundled in this release.
  Package license files are retained under `deck/`; the upstream notices list
  each project's original authors and license. Source references are retained
  in `references/BrimDeck`, while its own UI and theme are not used by this app.

- OpenQuota by deviffyy (MIT), https://github.com/deviffyy/OpenQuota, design
  reference pinned in `references/OpenQuota-PIN.json`. Usage visualization and
  the segmented quota icon are implemented in Qt; OpenQuota's runtime/backend
  is not bundled. Original copyright and license: OpenQuota-MIT.txt.

## Liquid resource capsule

- Wisland by wisland contributors (MIT), https://github.com/AsamiAkito/wisland,
  pinned at `35478b13897149b6927d932c06013bd5e21a2db3`. The spring, liquid path,
  vector face and small GDI capture helpers are adapted from its Python source
  to the existing PyQt5 app; window ownership, bounded capture scheduling and
  theme integration are local implementations. Notification metadata polling
  follows its public design. Source is retained under `references/Wisland` and
  the original copyright/license is in Wisland-MIT.txt. Its PySide6 runtime,
  ASR models, stock service and application UI are not bundled.
- Weather data: Open-Meteo (https://open-meteo.com/), credited in the optional
  weather component's remarks. The app requests only configured city names
  or coordinates and a three-day forecast; no location permission is used.
