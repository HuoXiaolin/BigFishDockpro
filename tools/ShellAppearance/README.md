# Native shell appearance backend

The application owns the settings, payload staging, lifetime and status. The
bundled DLLs adapt the GPL v3 XAML visual-tree/style engine from
[ramensoftware/windhawk-mods](https://github.com/ramensoftware/windhawk-mods).
No Windhawk service, installation, registry configuration, user JavaScript,
telemetry or remote style downloads are used. See the original source headers
and `references/ShellStyler/PIN.json` for authors, source URLs and content hashes.
MinHook 1.3.4 is retained with its BSD-2-Clause notices in `references/MinHook`.

## Shared toolchain

Use `D:\Agant\toolchain\shell_styler` (or the build `-Toolchain` root):

- `compiler/`: [windhawk-compiler-1.6.7z](https://github.com/ramensoftware/windhawk-dependencies/releases/download/v1.6/windhawk-compiler-1.6.7z), SHA-256 `16352e7dfa65d092af7b7113ddf6cae695e3678da500e611828c1bf2a7d9a2d0`.
- `include/winrt/`: [merged C++/WinRT headers](https://github.com/ramensoftware/windhawk-dependencies/releases/download/v1.6/winrt_winui2_2.8.7_winui3_1.7.250401001.7z), SHA-256 `43870ab78640c7c62d1825a3d39532f3bf78a4fe3895173a1615f521c82f55b3`.
- The existing shared `mingw/mingw64/bin/windres.exe` embeds the isolated native probe manifest. The compiler and header archives are shared development dependencies, not application downloads.

Run `.venv\Scripts\python.exe tools\prepare_shell_appearance.py`. Pinned vendor
sources remain unchanged; adaptations are explicit in that build script. It
builds the GUI launcher and two self-contained x64 DLLs under
`artifacts/shell-appearance`, with a SHA-256 payload manifest. The normal build
includes these files in both installer and single-file editions.

## Lifetime and scope

The launcher checks session, executable path and a fixed shell-process allowlist
before loading a DLL. It does not stop/restart Explorer or shell hosts. Native
property changes are reversible. The glass grid arranges the native app list and
pinned apps side by side where supported by the Start visual tree. Original app lists, pinned
apps, search, quick actions, media, notifications, calendar and power actions
remain Windows-owned.

An exact main-process creation timestamp guards against stale PID reuse. The
worker waits on configuration/status events and the owner process, without an
idle polling loop. The UI process checks for restarted hosts every five seconds
only while enabled; unchanged settings do not cause style reapplication. A
small dormant DLL remains loaded after restore so pending COM callbacks cannot
call unloaded code. It is released by the system host's normal exit.

`ShellExperienceHost` is an AppContainer on current Windows builds. Its DLL and
generated settings are staged inside its own package LocalState, using the
existing inherited package permissions. The controller qualifies the refresh
event with `GetAppContainerNamedObjectPath` and duplicates only a synchronize /
limited-query handle to itself and a write handle to one host status file.
No application-directory ACLs are broadened. See Microsoft's
[named object sharing documentation](https://learn.microsoft.com/en-us/windows/apps/develop/communication/sharing-named-objects).
Status aggregation retains per-host failures, including when ShellHost already
styled quick settings successfully.

The app offers only generated bounded settings, not arbitrary XAML/JavaScript
imports. Layout adaptations never set a native window's screen position. The
adapter disables upstream process restarts, feature-layout forcing and network
telemetry. Windows updates can still change undocumented visual-tree names.

## Verification

`tools/shell_native_test.py`, via `tools/run_isolated_test.py`, creates synthetic
native XAML controls on a verified non-input desktop and tests actual material
application, two-column Start layout and original-property restoration. The
standalone probe refuses the input desktop and never injects another process.
`tests/shell_appearance_tests.py` checks configuration/lifecycle and the Qt pages;
OS operations in lifecycle scenarios are mocked. These checks run before the
standard Quick delivery and in the final single-file UI suite respectively.

`tools/shell_container_test.py` runs an owned, windowless AppContainer child on
the isolated desktop. It validates package-local DLL loading/config reads,
qualified events, the narrow owner handle, and the shipped native status writer.
Only that disposable non-input test desktop receives the test package SID and
low integrity label; the user's desktop and application-directory ACLs are never
changed. The exact generated test files are removed after the child exits.

This is not acceptance of every live shell layout or enterprise security policy.
Failure must retain the system UI and expose retry/disable controls, not claim
that a rule was applied merely because the launcher exited successfully.
