# Third-party notices

BigFishDockpro is distributed under the GNU General Public License version 3
only (`GPL-3.0-only`). See the project root `LICENSE` for the license text.
The corresponding application source and build scripts are included in the
source distribution for [BigFishDockpro](https://github.com/HuoXiaolin/BigFishDockpro).

The original iOS-style-Dock code retains its MIT copyright and permission
notice in [iOS-style-Dock-MIT.txt](iOS-style-Dock-MIT.txt). The notices below
apply to their respective third-party components.

See [第三方授权与来源](第三方授权与来源.md) for design references, incorporated
source code, runtime integrations, and the scope of asset permissions.

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
  The portable launcher is built from `references/pyinstaller-6.16.0.tar.gz`
  with the Windows session cleanup changes in `tools/prepare_portable_bootloader.py`.
- lunardate 0.3.0: LI Daobing and contributors, GPL-3.0-or-later; license included in lunardate-LICENSE.txt.
  Source: https://pypi.org/project/lunardate/0.3.0/
- Microsoft Visual C++ redistributable DLLs: Microsoft Corporation, distributed
  as runtime dependencies of the Python / Qt binary wheels.

No GlassDesk or GlassBoard source or proprietary assets are included.

## Native Windows shell appearance

- Windows 11 Start Menu Styler and Notification Center Styler by m417z and
  contributors, https://github.com/ramensoftware/windhawk-mods, GPL v3.
  Unmodified upstream sources, authors and SHA-256 pins are retained in
  `references/ShellStyler`. BigFishDock's adapter, lifecycle, folder rail,
  launcher and build-time transformations are in `tools/ShellAppearance` and
  `tools/prepare_shell_appearance.py`. GPL text: ShellStyler-GPL-3.0.txt.
- MinHook 1.3.4 by Tsuda Kageyu, including HDE by Vyacheslav Patkov,
  https://github.com/TsudaKageyu/minhook/tree/v1.3.4, BSD-2-Clause.
  Copyright and redistribution notices: MinHook-BSD.txt.
- C++/WinRT headers by Microsoft Corporation,
  https://github.com/microsoft/cppwinrt, MIT; notice: CppWinRT-MIT.txt.
- LLVM-MinGW runtime components linked into the native shell backend, from
  https://github.com/ramensoftware/windhawk-dependencies/releases/tag/v1.6.
  License text and LLVM exceptions: LLVM-MinGW-LICENSE.txt.
  Compiler packages and header versions/hashes are documented in
  `tools/ShellAppearance/README.md` in the source distribution.

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
  and vector face code are adapted from its Python source to the existing
  PyQt5 app. Source is retained under `references/Wisland` and
  the original copyright/license is in Wisland-MIT.txt. Its PySide6 runtime,
  ASR models, stock service and application UI are not bundled.
- Weather data: Open-Meteo (https://open-meteo.com/), credited in the optional
  weather component's remarks. The app requests only configured city names
  or coordinates and a three-day forecast; no location permission is used.

## Mouse pointers

- The Bibata Modern Amber Regular and Ice Regular cursor files are from
  [Bibata Cursor v2.0.6](https://github.com/ful1e5/Bibata_Cursor/releases/tag/v2.0.6)
  by Abdulkaiz Khatri. The original CUR and ANI files are stored losslessly.
  The [v2.0.6 source](https://github.com/ful1e5/Bibata_Cursor/tree/v2.0.6) is
  available under GPL-3.0-or-later. See the included GPL v3 license text.
- Spirit and Tinted Glass by silica-dev build on Bibata and use GPL v3.
  [Bibata Cursor Translucent source and license](https://github.com/silica-dev/Bibata_Cursor_Translucent)
- Future by yeyushengfan258 is based on Capitaine and uses GPL v3.
  [Future source and license](https://github.com/yeyushengfan258/Future-cursors)
- Layan White by vinceliuice is based on Capitaine and uses GPL v3.
  [Layan source and license](https://github.com/vinceliuice/Layan-cursors)
- Phinger Light by Philipp Schaffrath (phisch) remains under CC BY-SA 4.0.
  [Phinger source artwork and license](https://github.com/phisch/phinger-cursors)

The five Windows cursor archives above retain the supplied CUR and ANI files,
role mappings, attribution, and license texts. Their Windows role mappings use
the link pointer for the location and person roles.

The local delivery built with `-LocalCursorStyles` includes the user-supplied
W11 Cursor Light Free by Jepri Creations, Cool Dog Jake, Luffy, and
GrokBot-Soft-Pointer. Each scheme preserves its original pointer files and role
assignments. The GrokBot scheme uses the 17 supplied ANI files assigned to its
Windows roles. The upstream study reserves rights in the character and extracted
materials to xAI or the respective rights holders and restricts commercial use
and redistribution.
[Original study statement](https://github.com/blessonism/grok-icon-study/blob/b7e6cd48db4eeba13271c653c38e1ad0f48037b4/README.md#免责声明)

## Hardware monitoring reference

LiteMonitor by Diorser is a reference for desktop and taskbar monitoring and
fan sensor classification. Dock's implementation is in `tools/HardwareFans.cs`.
LiteMonitor describes its project license as MIT in its
[upstream README](https://github.com/Diorser/LiteMonitor#readme).

## Natural reminder sounds

The recordings used in the bundled reminder sounds are licensed under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The app uses
short excerpts with soft fades and adjusted volume.

| Cue | Recording and creator |
| --- | --- |
| Agenda | [Rain on Window by RadioWaffle](https://freesound.org/people/RadioWaffle/sounds/877437/) |
| Focus complete | [fire-crackling.wav by jmehlferber](https://freesound.org/people/jmehlferber/sounds/370938/) |
| Break complete | [Gentle Waves - Quiet Beach 2 by amholma](https://freesound.org/people/amholma/sounds/376796/) |
| Water | [Water drop (splash) by bolkmar](https://freesound.org/people/bolkmar/sounds/451126/) |
| Low battery | [Water Drop by willstepp](https://freesound.org/people/willstepp/sounds/188293/) |
| AI quota | [WindyLeaves by TimOut789](https://freesound.org/people/TimOut789/sounds/751869/) |
