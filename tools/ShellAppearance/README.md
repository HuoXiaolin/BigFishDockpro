# Native shell appearance backend

The application owns the settings, payload staging, lifetime and status. The
bundled DLLs adapt the GPL v3 XAML visual-tree/style engine from
[ramensoftware/windhawk-mods](https://github.com/ramensoftware/windhawk-mods).
No Windhawk service, installation, registry configuration, user JavaScript,
telemetry or remote style downloads are used. See the original source headers
and `references/ShellStyler/PIN.json` for authors, source URLs and content hashes.
MinHook 1.3.4 is retained with its BSD-2-Clause notices in `references/MinHook`.

The system tray overflow uses the same notification background parameters. It
is hosted by Explorer and uses the existing taskbar component's XAML observer.
The observer applies the brush to `OverflowFlyoutBackgroundBorder` and restores
the saved native property when the style is disabled or its owner exits.
[Native taskbar background targets](https://github.com/ramensoftware/windows-11-taskbar-styling-guide#tray-overflow-background)

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

Start, Search and notification hosts use configuration, status files and refresh events scoped to
the staged native build. On upgrade the controller asks resident builds to
restore their properties, waits for their acknowledgement, then activates the
new build. Start reports whether the footer search button has been laid out.
Ready hosts connect consecutively; a failed Start attachment does not hold up
the notification queue. Restore acknowledgements are checked every 100 ms
during the bounded handoff instead of waiting for another discovery interval.

An out-of-context WinEvent hook wakes discovery on native Shell window creation
and display; the five-second timer remains a fallback. An attached notification
observer prepares an uninitialized UI thread on its first visual-tree callback,
so the first elements are not skipped until a settings refresh.

Window-dispatch messages include the build ID. Callback exceptions are contained
on the target UI thread. Teardown revokes column layout handlers, removes the
style watchers, then restores column values. A rejected property is recorded and
the remaining properties are still restored. This addresses the local crash dump
with `BF_LocalLayout::restore -> BF_ClearStartColumns -> UninitializeSettingsAndTap`
unwinding through the user32 callback. Regression coverage includes the complete
layout under the real TAP observer, settings refresh and production teardown.

CoreWindow creation can occur before XAML diagnostics are ready. Initialization
is deferred to the UI message loop and retries readiness failures at bounded
intervals. A failed attempt clears its initialized flag and partial state, so
it cannot permanently latch the component into an unstyled state. Disabling
the component cancels pending initialization. Native status includes the
initialization phase, attempt count and last HRESULT.

`ShellExperienceHost` and `SearchHost` can run in AppContainers. Their DLLs and
generated settings are staged inside their respective package LocalState, using the
existing inherited package permissions. The controller qualifies the refresh
event with `GetAppContainerNamedObjectPath` and duplicates only a synchronize /
limited-query handle to itself and a write handle to one host status file.
An anonymous eight-byte section carries the Start surface rectangle in physical
pixels. Start publishes its background bounds, and Search receives read-only
access. No application-directory ACLs are broadened. See Microsoft's
[named object sharing documentation](https://learn.microsoft.com/en-us/windows/apps/develop/communication/sharing-named-objects).
Status aggregation retains per-host failures, including when ShellHost already
styled quick settings successfully.

The app offers generated bounded settings. The Start layout keeps its system
anchor. Search measures from its XAML layout window, checks the face against
the visible viewport, and adjusts the host position and size to fit. Before
Start publishes visible bounds on that monitor, Search uses the taskbar work
area. Disabling the style restores the native host bounds.
Search sizes its viewport independently of the page offset, then aligns the
content root. Deriving host height from a centered page offset caused repeated
layouts to grow the window above the monitor. Hidden/offscreen Start rectangles
do not replace the last visible anchor.

The classic tree positions its two content roots inside their original layout
slots. It never reparents them or assigns DataContext: native template ownership,
routed commands and subsequent view-model changes remain intact. Layout starts
after Loaded and restores local properties on teardown. Upstream rules for the
same root Margin/Width/RenderTransform are removed rather than competing with
the layout adapter and causing a XAML layout loop. The native footer gets
dedicated grid slots for its existing controls and Search; a PowerOptionsView
wrapper is not mistaken for the nested PowerButton. Pinned item containers and
wrap cells use up to four 88 × 84 DIP slots. The preferred frame measures
608 × 552 DIPs with 16-DIP outer margins and column spacing. A smaller work
area reduces the cell width or column count. The account avatar aligns with
the list icons, and the name aligns with the app labels. A folder uses its own
three-column grid of 76 × 84 DIP cells. It expands toward the left if the
pinned column is narrower than its 264-DIP surface. Positive offsets have
compensating trailing margins so the
original parent's available size does not implicitly clip their right edge.
Column alignment also includes the native template's inner containers, not just
the two outer roots. The loaded Windows resources contain a 63-DIP pinned-header
margin, 32-DIP pinned-root padding and 52-DIP app-list panel margin. The adapter
normalizes the paths to the named headers/lists while preserving item templates,
and leaves a 10-DIP paging column beside the four pinned cells. A nested FrameRoot
no longer receives the whole menu's width. The grouped GridView app-list variant
gets one column sized to the available app-list width. All original inner values
are restored when disabled.

The redesigned tree is recognized through the loaded `MainMenu`, `AllAppsGrid`
and `TopLevelHeader` controls. The pinned heading and its expand button are
resolved by their descendants, including templates with unnamed containers.
The two columns are applied together after their native parts load. Each owns a
scroll viewport. The frame and background share the same dimensions, and the
original search entry stays available until the footer shortcut fits. Teardown
restores each moved control to its original slot. An incomplete template retains
its native layout.
The adapter disables upstream process restarts, feature-layout forcing and
network telemetry. Windows updates can still change undocumented visual-tree names.

## Verification

`tools/shell_lifecycle_test.py` is part of the standard build. It runs the real
MinHook and XAML diagnostics/TAP path in owned, isolated XAML hosts. Both engines
are checked with an existing window, before XAML construction, and after a
deliberate early-readiness failure, followed by refresh and restore. This covers
the connection sequence that direct style/geometry fixtures do not exercise.

`tools/shell_native_test.py`, via `tools/run_isolated_test.py`, creates synthetic
native XAML controls on a verified non-input desktop and tests actual material
application, both Start sizing frames, Search alignment with offsets and
clipping in separate XAML hosts, the direct Search entry, footer actions and
their popups, and original-property restoration. The
standalone probe refuses the input desktop and never injects another process.
The complete layout fixture additionally reproduces column overflow and 96-DIP
containers in 76-DIP cells, checks all 15 tile rectangles and the nested footer,
and saves native rendered bitmaps for the base and expanded-folder views. It
includes the inner margins/padding and paging column from local Windows templates:
the pre-fix engine fails these checks. Both ListView and grouped GridView app-list
structures are covered, including restoration of the inner template values. It
also hit-tests the rightmost tiles and folder surface, since measured element
bounds alone do not reveal ancestor layout clipping. Search is repositioned eight times including
a simulated OS host resize; both its viewport and face must remain coincident.
Cold-tree registration, unchanged parents/Loaded lifecycle, inherited view-model
updates and dummy native power/flyout Click handlers are also checked. These
dummy actions never call shutdown, restart or logoff.
The redesigned Start probe uses both named and unnamed header containers. It
checks late loading, app rows, pinned cells, the original expand button and
native layout restoration through the same observer used at runtime.
`tests/shell_appearance_tests.py` checks configuration/lifecycle and the Qt pages;
OS operations in lifecycle scenarios are mocked. These checks run before the
standard Quick delivery and in the final single-file UI suite respectively.
The controller retries temporary staging/connection failures with a bounded
delay, including after three failed attempts; a delayed or restarted Shell host
does not require toggling the saved appearance preference off and on.

`tools/shell_container_test.py` runs an owned, windowless AppContainer child on
the isolated desktop. It validates package-local DLL loading/config reads,
qualified events, the narrow owner handle, and the shipped native status writer.
Only that disposable non-input test desktop receives the test package SID and
low integrity label; the user's desktop and application-directory ACLs are never
changed. The exact generated test files are removed after the child exits.

This is not acceptance of every live shell layout or enterprise security policy.
Failure must retain the system UI and expose retry/disable controls, not claim
that a rule was applied merely because the launcher exited successfully.
