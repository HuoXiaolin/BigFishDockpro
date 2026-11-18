"""Build the bundled, offline shell styling backend from pinned GPL/BSD sources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tools/ShellAppearance'
BUILD=ROOT/'artifacts/shell-build'
PAYLOAD=ROOT/'artifacts/shell-appearance'
NAMES=('BigFishShellAppearance.exe','BigFishStartStyle.dll','BigFishNotificationStyle.dll')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_classic_start(code):
    # The in-place adapter owns these layout properties. Do not leave upstream
    # property watchers enforcing a second Margin/Width/RenderTransform: that
    # produces a layout feedback loop as each side restores its own value.
    start = code.index('const Theme g_themeSideBySideMinimal_variant_ClassicStartMenu')
    end = code.index('\n}};', start)
    theme = code[start:end]
    for name in ('UndockedRoot', 'AllAppsRoot'):
        pattern = r'ThemeTargetStyles\{L"Windows.UI.Xaml.Controls.Grid#' + name + r'", \{.*?\}\}'
        theme, count = re.subn(pattern, 'ThemeTargetStyles{L"Windows.UI.Xaml.Controls.Grid#' + name + '", {L"Visibility=Visible"}}', theme, flags=re.S)
        assert count == 1
    # These old three-column folder offsets exceed the compact pinned column.
    theme, count = re.subn(r'    ThemeTargetStyles\{L"StartMenu\.ExpandedFolderList[^\n]+\{.*?\}\},\n', '', theme, flags=re.S)
    assert count == 3
    for original, compact in (
            ('L"Margin=-575,0,0,0"', 'L"Padding=0"'),
            ('L"Margin=38,0,-38,0"', 'L"Margin=0"'),
            ('L"Height=504"', 'L"Height=460"')):
        assert theme.count(original) == 1
        theme = theme.replace(original, compact)
    return code[:start] + theme + code[end:]


def adapt_search_content(code, build_id):
    marker='std::wstring CreateWebViewJsCodeForApply() {'
    assert code.count(marker)==1
    code=code.replace(marker, '#include "search_web_content.h"\n'+marker)
    code,count=re.subn(
        r'    auto canonicalUri = source\.AbsoluteCanonicalUri\(\);\n'
        r'.*?\n    std::wstring jsCode = CreateWebViewJsCodeForApply\(\);',
        '    if (!BF_IsSearchDocument(source)) return false;\n\n'
        '    std::wstring jsCode = CreateWebViewJsCodeForApply();', code, flags=re.S)
    assert count==2
    fragments=(
        ('''        if (!document.getElementById(styleElementId)) {
            const style = document.createElement("style");
            style.id = styleElementId;
            style.textContent = styleContent;
            document.head.appendChild(style);
        }''', '''        let style = document.getElementById(styleElementId);
        if (!style) {
            const target = document.head || document.documentElement;
            if (!target) return "bigfish-search-waiting";
            style = document.createElement("style");
            style.id = styleElementId;
            target.appendChild(style);
        }
        if (style.textContent !== styleContent) style.textContent = styleContent;
        return style.sheet && style.sheet.cssRules.length ? "bigfish-search-styled" : "bigfish-search-waiting";'''),
        ('''    webViewElement.InvokeScriptAsync(
        L"eval", winrt::single_threaded_vector<winrt::hstring>(
                     {winrt::hstring(jsCode.c_str(), jsCode.size())}));''',
         '''    BF_WatchSearchStyles(webViewElement.InvokeScriptAsync(
        L"eval", winrt::single_threaded_vector<winrt::hstring>(
                     {winrt::hstring(jsCode.c_str(), jsCode.size())})));'''),
        ('''            operationPtr, winrt::take_ownership_from_abi};

    return true;
}

void ApplyCustomizationsIfWebView''', '''            operationPtr, winrt::take_ownership_from_abi};
    BF_WatchSearchStyles(operation);

    return true;
}

void ApplyCustomizationsIfWebView'''),
        ('''    if (g_target == Target::SearchHost) {
        ProcessWebStylesFromSettings(styleConstants,
                                     theme ? theme->webViewTargetStyles
                                           : std::vector<ThemeTargetStyles>{});
    }''', '''    ProcessWebStylesFromSettings(styleConstants,
                                 theme ? theme->webViewTargetStyles
                                       : std::vector<ThemeTargetStyles>{});'''),
        ('''    if (!g_webContentCss.empty() || !g_webContentJs.empty()) {
        try {
            ApplyCustomizationsIfWebView(elementId, element);''', '''    if (!g_webContentCss.empty()) {
        try {
            if (BF_IsSearchView(element)) ApplyCustomizationsIfWebView(elementId, element);'''),
    )
    for original, replacement in fragments:
        assert code.count(original)==1
        code=code.replace(original, replacement)
    return code.replace('windhawk-windows-11-start-menu-styler-style', 'bigfish-windows-search-style-'+build_id)


def defer_xaml_initialization(code, kind):
    # An early diagnostics failure used to keep the initialized flag set for
    # the rest of the process lifetime. CoreWindow creation is not XAML-ready.
    start = code.index('void InitializeSettingsAndTap() {')
    end = code.index('\n}\n', start) + 2
    initialize = code[start:end]
    failed = '    if (FAILED(hr)) {\n        Wh_Log(L"Error %08X", hr);\n    }'
    assert initialize.count(failed) == 1
    reset = ('UninitializeSettingsAndTap();' if kind == 'start' else 'g_initialized = false;')
    initialize = initialize.replace(failed, '    if (FAILED(hr)) {\n        '+reset+'\n'
        '        bf_last_error = static_cast<unsigned long>(hr);\n'
        '    } else { bf_init_state=2;bf_last_error=0; }')
    work = '    ProcessAllStylesFromSettings();' if kind == 'start' else '    HRESULT hr = InjectWindhawkTAP();'
    assert initialize.count(work) == 1
    initialize = initialize.replace(work, '    try {\n'+work)
    flag = 'g_targetThreadId = 0;' if kind == 'start' else 'g_initialized = false;'
    initialize = initialize[:-1] + '    } catch (...) {\n        const auto failure=winrt::to_hresult();\n'
    if kind == 'start':
        initialize += '        try {UninitializeSettingsAndTap();} catch (...) {}\n'
    initialize += '        '+flag+'\n        bf_last_error=static_cast<unsigned long>(failure.value);\n    }\n}'
    code = code[:start] + initialize + code[end:]
    start = code.index('void OnWindowCreated(HWND hWnd, LPCWSTR lpClassName, PCSTR funcName) {')
    end = code.index('\nusing CreateWindowInBand_t', start)
    classes = ('L"Windows.UI.Core.CoreWindow"' if kind == 'start' else
               'L"Windows.UI.Core.CoreWindow",L"ControlCenterWindow"')
    code = code[:start] + '#include "initialization.h"\n' + '''void OnWindowCreated(HWND hWnd,LPCWSTR lpClassName,PCSTR) {
    if (!hWnd || !((ULONG_PTR)lpClassName & ~(ULONG_PTR)0xffff)) return;
    for (auto name : {''' + classes + '''}) {
        if (_wcsicmp(lpClassName,name)==0) {BF_RequestShellInitialization(hWnd);break;}
    }
}
''' + code[end:]
    start = code.index('void Wh_ModAfterInit() {')
    end = code.index('\nvoid Wh_ModUninit()', start)
    request = ('BF_RequestShellInitialization(GetCoreWnd());' if kind == 'start' else
               'for (auto window : GetCoreWnds()) BF_RequestShellInitialization(window);')
    code = code[:start] + 'void Wh_ModAfterInit() {\n    '+request+'\n}\n' + code[end:]
    code = code.replace('BOOL Wh_ModInit() {', 'BOOL Wh_ModInit() {\n'
        '    bf_init_enabled=true;++bf_init_generation;bf_init_state=0;bf_init_attempts=0;')
    code = code.replace('void Wh_ModUninit() {', 'void Wh_ModUninit() {\n'
        '    bf_init_enabled=false;++bf_init_generation;bf_init_state=0;')
    cleanup = 'void UninitializeSettingsAndTap() {' if kind == 'start' else 'void UninitializeForCurrentThread() {'
    assert code.count(cleanup) == 1
    code = code.replace(cleanup, cleanup+'\n    BF_CancelThreadInitialization();')
    # These callbacks run inside user32. C++ exceptions cannot escape into a
    # caller compiled with another exception ABI. Always finish hook cleanup.
    code = code.replace('        proc(procParam);\n        return true;',
        '        try {proc(procParam);return true;}\n'
        '        catch (...) {Wh_Log(L"Error %08X: UI dispatch",winrt::to_hresult());return false;}')
    for invoke in ('param->proc(param->procParam);',):
        code = code.replace(invoke, 'try {'+invoke+'} catch (...) {Wh_Log(L"Error %08X: UI dispatch",winrt::to_hresult());}')
    if kind == 'notification':
        # An existing global TAP already observes newly created UI threads.
        # Don't discard their first Add callbacks while a timer is pending.
        marker='HRESULT VisualTreeWatcher::OnVisualTreeChange(ParentChildRelation relation, VisualElement element, VisualMutationType mutationType) try'
        assert code.count(marker)==1
        code=code.replace(marker,'void InitializeForCurrentThread();\n\n'+marker)
        guard='    if (!g_initializedForThread)\n    {\n        Wh_Log(L"Not initialized for thread %u", GetCurrentThreadId());'
        assert code.count(guard)==1
        code=code.replace(guard,'    if (!g_initializedForThread && bf_init_enabled) InitializeForCurrentThread();\n'+guard)
        apply = ('void ApplyCustomizations(ElementId elementId,\n'
                 '                         FrameworkElement element,\n'
                 '                         PCWSTR fallbackClassName) {')
        assert code.count(apply)==1
        code=code.replace(apply, '#include "notification_loaded.h"\n'+apply+
                          '\n    BF_QueueNotificationLoaded(element,fallbackClassName);')
        end=code.index('\n}\n',code.index(apply))
        code=code[:end]+'''
    if (element.Name()==L"CalendarCenterGrid" && !resolved.overridesPerVSG.empty() &&
        !bf_calendar_matched.exchange(true) && bf_status_event) SetEvent(bf_status_event);'''+code[end:]
        for entry in ('BOOL Wh_ModInit() {','void Wh_ModSettingsChanged() {','void Wh_ModUninit() {'):
            assert code.count(entry)==1
            code=code.replace(entry,entry+'\n    bf_calendar_matched=false;')
        # A pending weak subscription doesn't retain a diagnostics handle.
        remove='            CleanupCustomizations(FindElementId(element.Handle));'
        assert code.count(remove)==1
        code=code.replace(marker,'static void BF_RemoveNotificationLoad(InstanceHandle handle);\n'+marker)
        code=code.replace(remove,'            BF_RemoveNotificationLoad(element.Handle);\n'+remove)
        cleanup='void UninitializeForCurrentThread() {'
        code=code.replace(cleanup,cleanup+'\n    BF_ClearNotificationLoads();')
    return code


def build(toolchain):
    compiler=toolchain/'shell_styler/compiler/bin/clang++.exe'
    cc=compiler.with_name('clang-20.exe')
    headers=toolchain/'shell_styler/include'
    if not compiler.is_file() or not (headers/'winrt/Windows.UI.Xaml.h').is_file():
        raise RuntimeError('Shell appearance requires the shared LLVM-MinGW and WinRT headers; see tools/ShellAppearance/README.md.')
    pin=json.loads((ROOT/'references/ShellStyler/PIN.json').read_text(encoding='utf-8'))
    for item in pin['files']:
        if sha(ROOT/'references/ShellStyler'/item['name'])!=item['sha256']:
            raise ValueError('Pinned shell source changed: '+item['name'])
    sources=[*(p for p in SOURCE.iterdir() if p.suffix in ('.cpp','.h','.manifest')),ROOT/'tools/prepare_shell_appearance.py',* (ROOT/'references/ShellStyler').glob('*'),*(ROOT/'references/MinHook').rglob('*.c'),*(ROOT/'references/MinHook').rglob('*.h')]
    fingerprint=hashlib.sha256(''.join(str(p.relative_to(ROOT))+sha(p) for p in sorted(sources) if p.is_file()).encode()).hexdigest()
    stamp=BUILD/'stamp.json'
    if stamp.is_file() and all((PAYLOAD/name).is_file() for name in (*NAMES,'manifest.json')):
        cached=json.loads(stamp.read_text())
        if cached.get('fingerprint')==fingerprint and all(sha(PAYLOAD/name)==digest for name,digest in cached['hashes'].items()):
            print('Shell appearance backend: verified build cache',flush=True);return
    BUILD.mkdir(parents=True,exist_ok=True);PAYLOAD.mkdir(parents=True,exist_ok=True)
    common=['--target=x86_64-w64-windows-gnu','-DUNICODE','-D_UNICODE','-D_WIN32_WINNT=0x0A00','-DWINVER=0x0A00','-O2']
    cxx=[*common,'-std=c++23','-fms-extensions',f'-DBIGFISH_BUILD_ID=L"{fingerprint[:16]}"',
         '-I'+str(headers),'-I'+str(ROOT/'references/MinHook/include'),'-I'+str(SOURCE)]
    objects=[]
    log_lock=Lock()
    def run(args):
        result=subprocess.run([str(a) for a in args],cwd=BUILD,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=300)
        with log_lock:
            with (BUILD/'compile.log').open('a',encoding='utf-8') as stream:stream.write(result.stdout)
        if result.returncode:
            print(result.stdout[-14000:]);raise RuntimeError('Native shell compilation failed: '+str(args[-1]))
    (BUILD/'compile.log').write_text('',encoding='utf-8')
    for filename in ('buffer.c','hook.c','trampoline.c','hde/hde64.c'):
        path=ROOT/'references/MinHook/src'/filename;obj=BUILD/(path.stem+'.o');objects.append(obj)
        run([cc,*common,'-c',path,'-o',obj])
    engine_commands=[]
    for kind,output in (('start',NAMES[1]),('notification',NAMES[2])):
        print('Building '+output,flush=True)
        code=(ROOT/'references/ShellStyler'/f'{kind}.wh.cpp').read_text(encoding='utf-8')
        # Keep the pinned tree observer and original-value restoration. Disable
        # upstream telemetry/network and process restarts in this embedding.
        code=code.replace('StartStatsTimer();','/* BigFishDock: no usage telemetry. */')
        code=code.replace('ExitProcess(0);','BF_LayoutPending();')
        # mingw-w64's generated WinRT ABI header specializes both BYTE and
        # boolean, although RPC aliases both to unsigned char. C++/WinRT uses
        # bool for WinRT Boolean; scope this workaround to that ABI header.
        code=code.replace('#include <windows.graphics.effects.h>',
            '#include <rpcndr.h>\n#define boolean bool\n#include <windows.graphics.effects.h>\n#undef boolean')
        code=defer_xaml_initialization(code, kind)
        if kind=='start':
            code=compact_classic_start(code)
            apply = 'void ApplyCustomizations(ElementId elementId,\n                         FrameworkElement element,\n                         PCWSTR fallbackClassName) {'
            observe = '    HandleSeparatePinnedScroll(element);'
            cleanup = 'void UninitializeSettingsAndTap() {'
            assert all(code.count(marker) == 1 for marker in (apply, observe, cleanup))
            code=code.replace(apply, '#include "start_layout.h"\n#include "start_frame.h"\n#include "start_search_button.h"\n'+apply)
            code=code.replace(observe, '    BF_WatchShellPanel(element);\n'+observe+
                              '\n    BF_QueueStartColumns(element);\n    BF_QueueStartFolder(element);\n    BF_QueueStartSearchButton(element);\n    BF_QueueStartPopup(element);')
            code=code.replace(cleanup, cleanup+'\n    BF_SuspendStartColumns();\n    BF_ClearSearchStylesStatus();\n    BF_ClearStartFrames();\n    BF_ClearSearchFrames();\n    BF_ClearStartSearchButtons();')
            # Upstream property watchers must be removed before original column
            # values are restored; otherwise they enforce the styled values
            # while the adapter tries to put the native layout back.
            end=code.index('\n}\n',code.index(cleanup))
            code=code[:end]+'\n    BF_ClearStartColumns();'+code[end:]
            code=adapt_search_content(code, fingerprint[:16])
            # Separate existing new-layout columns in-process; never force OS
            # feature flags or restart the shell to select a legacy layout.
            code=code.replace('    return disableNewStartMenuLayout;\n}',
                '    if (disableNewStartMenuLayout == DisableNewStartMenuLayout::windowsDefault && useNewLayoutVariant)\n'
                '        disableNewStartMenuLayout = DisableNewStartMenuLayout::newLayoutSideBySide;\n'
                '    return disableNewStartMenuLayout;\n}')
        generated=BUILD/(kind+'.cpp')
        generated.write_text(('#define BIGFISH_START_ENGINE 1\n' if kind=='start' else '')+'#include "engine_adapter.h"\n'+code+'\n#include "engine_probe.h"\n#include "engine_lifecycle.cpp"\n',encoding='utf-8')
        engine_commands.append([compiler,*cxx,'-shared','-static',generated,*objects,'-lcomctl32','-lole32','-loleaut32','-lruntimeobject','-lshlwapi','-lshell32','-ladvapi32','-luuid','-lversion','-Wl,--no-insert-timestamp','-o',PAYLOAD/output])
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run,engine_commands))
    print('Building '+NAMES[0],flush=True)
    run([compiler,*cxx,'-static','-municode','-mwindows',SOURCE/'launcher.cpp','-lshell32','-ladvapi32','-Wl,--no-insert-timestamp','-o',PAYLOAD/NAMES[0]])
    windres=toolchain/'mingw/mingw64/bin/windres.exe'
    (BUILD/'probe.rc').write_text('1 24 "'+(SOURCE/'probe.manifest').as_posix()+'"\n')
    run([windres,'-i',BUILD/'probe.rc','-o',BUILD/'probe-res.o'])
    run([compiler,*cxx,'-static','-municode','-mwindows',SOURCE/'probe.cpp',BUILD/'probe-res.o','-lshell32','-o',BUILD/'BigFishShellProbe.exe'])
    run([compiler,*cxx,'-static','-municode',SOURCE/'container_probe.cpp','-ladvapi32','-luser32','-o',BUILD/'BigFishContainerProbe.exe'])
    hashes={name:sha(PAYLOAD/name) for name in NAMES}
    manifest={'protocol':1,'build':fingerprint[:16],'files':hashes}
    (PAYLOAD/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    stamp.write_text(json.dumps({'fingerprint':fingerprint,'hashes':hashes},indent=2),encoding='utf-8')
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--toolchain',type=Path,default=Path(r'D:\Agant\toolchain'))
    build(parser.parse_args().toolchain)
