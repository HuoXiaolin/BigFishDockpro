"""Build the 2026.2 ExplorerTAP with XAML-root matching and flyout styling."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile


SOURCE_COMMIT = 'd4636e439865df0a1a1419db408e055740ce5c74'
SOURCE_SHA256 = 'c66c067e591589ad2eeb1dbffb8845c4da5ef060debb3ff9fbe5efd3f8298fd1'
FIX_COMMIT = 'b8716c1207037013515a289c365918cb4aea109e'


def replace_once(code, old, new):
    if code.count(old) != 1:
        raise ValueError('Unexpected upstream ExplorerTAP source: ' + old)
    return code.replace(old, new, 1)


def add_taskbar_flyouts(tap):
    for name in ('taskbar_overflow.hpp', 'taskbar_context_menu.hpp'):
        shutil.copy2(Path(__file__).with_name(name), tap / name)
    shutil.copy2(Path(__file__).with_name('ShellAppearance') / 'start_footer_paint.h', tap)
    header = tap / 'taskbarappearanceservice.hpp'
    code = replace_once(header.read_text(encoding='utf-8-sig'), '#include "wilx.hpp"',
                        '#include "wilx.hpp"\n#include "taskbar_context_menu.hpp"')
    code = replace_once(code, '\tvoid RegisterTaskbar(InstanceHandle frameHandle, HWND window);',
                        '\tbigfish::TrayOverflow TrayOverflow;\n\tbigfish::TaskbarContextMenus ContextMenus;\n'
                        '\tvoid RegisterTaskbar(InstanceHandle frameHandle, HWND window);')
    header.write_text(code, encoding='utf-8')

    watcher = tap / 'visualtreewatcher.cpp'
    code = watcher.read_text(encoding='utf-8-sig')
    code = replace_once(code, '\t\telse if (type_view == L"Taskbar.TaskbarFrame")',
                        '\t\telse if (m_AppearanceService->TrayOverflow.Observe(element.Handle, relation.Parent, type_view, '
                        'std::wstring_view{name ? name.get() : L"", SysStringLen(name.get())}))\n'
                        '\t\t{\n\t\t\tm_AppearanceService->TrayOverflow.Add(element.Handle, FromHandle<wuxc::Border>(element.Handle));\n\t\t}\n'
                        '\t\telse if (type_view.ends_with(L"MenuFlyoutPresenter"))\n'
                        '\t\t{\n\t\t\tm_AppearanceService->ContextMenus.Add(element.Handle, FromHandle<wuxc::MenuFlyoutPresenter>(element.Handle));\n\t\t}\n'
                        '\t\telse if (type_view == L"Taskbar.TaskbarFrame")')
    code = replace_once(code, 'case Remove: // only element.Handle is valid\n',
                        'case Remove: // only element.Handle is valid\n\t\tm_AppearanceService->TrayOverflow.Remove(element.Handle);\n'
                        '\t\tm_AppearanceService->ContextMenus.Remove(element.Handle);\n')
    watcher.write_text(code, encoding='utf-8')

    service = tap / 'taskbarappearanceservice.cpp'
    code = service.read_text(encoding='utf-8-sig')
    for signature, call in (('SetTaskbarBorderVisibility(HWND taskbar, BOOL visible)', 'Refresh'),
                            ('RestoreAllTaskbarsToDefault()', 'Restore')):
        start = f'HRESULT TaskbarAppearanceService::{signature} try\n{{\n'
        code = replace_once(code, start, start + f'\tTrayOverflow.{call}();\n\tContextMenus.{call}();\n')
    service.write_text(code, encoding='utf-8')


def build(archive_path, compiler, output, probe=False):
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Expected official TranslucentTB 2026.2 source archive')
    output.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive_path) as archive:
        archive.extractall(output)
    source = output / ('TranslucentTB-' + SOURCE_COMMIT)
    tap = source / 'ExplorerTAP'
    watcher = tap / 'visualtreewatcher.cpp'
    code = watcher.read_text(encoding='utf-8-sig')
    old = 'const auto rootGrid = FromHandle<wux::UIElement>(relation.Parent);'
    if code.count(old) != 1 or code.count('content == rootGrid') != 1:
        raise ValueError('Upstream taskbar watcher changed')
    # The old direct parent is still useful during initialization before a XamlRoot exists.
    code = code.replace(old,
        'const auto frame = FromHandle<wux::UIElement>(element.Handle);\n'
        '\t\t\t\tconst auto xamlRoot = frame ? frame.XamlRoot() : nullptr;\n'
        '\t\t\t\tconst auto rootContent = xamlRoot ? xamlRoot.Content() : FromHandle<wux::UIElement>(relation.Parent);')
    watcher.write_text(code.replace('content == rootGrid', 'content == rootContent'), encoding='utf-8')
    add_taskbar_flyouts(tap)

    vc, = (compiler / 'VC/Tools/MSVC').glob('14.44.*')
    binaries = vc / 'bin/Hostx64/x64'
    sdk = compiler / 'microsoft.windows.sdk.cpp/c/Include/10.0.26100.0'
    tools = compiler / 'microsoft.windows.sdk.buildtools/bin/10.0.26100.0/x64'
    libraries = compiler / 'microsoft.windows.sdk.cpp.x64/c'
    detours = compiler / 'Detours/Detours-4b8c659f549b0ab21cf649377c7a84eb708f5e68/src'
    wil = compiler / 'wil/wil-1.0.250325.1/include'
    generated = output / 'generated'
    generated.mkdir(exist_ok=True)
    (generated / 'detours').mkdir(exist_ok=True)
    shutil.copy2(detours / 'detours.h', generated / 'detours/detours.h')
    environment = dict(os.environ,
        PATH=os.pathsep.join(map(str, (binaries, tools, os.environ['PATH']))),
        INCLUDE=os.pathsep.join(map(str, (vc / 'include', *(sdk / name for name in ('ucrt','shared','um','winrt','cppwinrt'))))),
        LIB=os.pathsep.join(map(str, (vc / 'lib/x64', libraries / 'ucrt/x64', libraries / 'um/x64'))))

    for name in ('TaskbarBrush', 'ITaskbarAppearanceService', 'IVersionedApi', 'ExplorerTAP'):
        subprocess.run([str(tools / 'midl.exe'), '/nologo', '/env', 'x64', '/Oicf', '/robust',
                        '/out', str(generated), '/I', str(tap), '/h', name+'.h', str(tap / (name+'.idl'))],
                       cwd=tap, env=environment, check=True)

    header = generated / 'proxy_config.h'
    header.write_text('#define RPCPROXY_ENABLE_CPP_NO_CINTERFACE\n#define ENTRY_PREFIX PSFactory_\n'
        '#define PROXY_CLSID_IS {0xe8721a60,0x3798,0x448f,{0xa0,0x1b,0xdc,0x4a,0xf6,0x5a,0x78,0xb}}\n', encoding='ascii')
    sources = [*sorted(tap.glob('*.cpp')), *sorted((tap/'effects').glob('*.cpp')), *sorted(generated.glob('*.c'))]
    sources += [detours / (name+'.cpp') for name in ('detours','modules','disasm','image','creatwth','disolx86','disolx64','disolia64','disolarm','disolarm64')]
    include = [source / 'Common', generated, wil]
    macros = ('EXPLORERTAP_EXPORTS','WINRT_NO_MODULE_LOCK','WINRT_WINDOWS_ABI','_HIDE_GLOBAL_ASYNC_STATUS',
              'WIN32_LEAN_AND_MEAN','UNICODE','_UNICODE','NOMINMAX','_WINDOWS','_WIN32_WINNT=0x0A00','BUILD_TYPE=1',
              'WIL_LOCK_EXCEPTION_MODE','RESULT_SUPPRESS_STATIC_INITIALIZERS','WIL_USE_STL=1')
    cl = [str(binaries / 'cl.exe'), '/nologo', '/std:c++latest', '/Zc:preprocessor', '/MT', '/EHsc', '/MP4',
          '/O2', '/utf-8', '/guard:cf', *(f'/D{macro}' for macro in macros), *(f'/I{path}' for path in include)]
    arguments = [*cl, '/LD', f'/FI{header}', *(str(path) for path in sources), '/link', '/Brepro', '/guard:cf', '/NODEFAULTLIB:OLDNAMES',
                 f'/DEF:{tap / "ExplorerTAP.def"}',
                 f'/OUT:{output / "ExplorerTAP.dll"}', 'dxguid.lib', 'ole32.lib', 'oleaut32.lib', 'rpcrt4.lib',
                 'runtimeobject.lib', 'user32.lib', 'gdi32.lib', 'shell32.lib', 'shlwapi.lib', 'uuid.lib',
                 'comctl32.lib', 'dwmapi.lib']
    subprocess.run(arguments, cwd=output, env=environment, check=True)
    print('ExplorerTAP patch', FIX_COMMIT, hashlib.sha256((output/'ExplorerTAP.dll').read_bytes()).hexdigest())
    if probe:
        fixture = Path(__file__).resolve().parents[1] / 'tests/fixtures/tray_overflow_probe.cpp'
        manifest = Path(__file__).with_name('ShellAppearance') / 'probe.manifest'
        subprocess.run([*cl, f'/I{tap}', str(fixture), str(tap / 'XamlBlurBrush.cpp'),
                        *(str(path) for path in sorted((tap/'effects').glob('*.cpp'))), '/link', '/NODEFAULTLIB:OLDNAMES',
                        '/MANIFEST:EMBED', f'/MANIFESTINPUT:{manifest}',
                        f'/OUT:{output / "TrayOverflowProbe.exe"}', 'ole32.lib', 'oleaut32.lib', 'user32.lib', 'runtimeobject.lib',
                        'gdi32.lib', 'shlwapi.lib', 'dxguid.lib', 'uuid.lib', 'comctl32.lib', 'dwmapi.lib'],
                       cwd=output, env=environment, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    build(args.source.resolve(), args.compiler.resolve(), args.output.resolve(), args.probe)
