"""Build the bundled, offline shell styling backend from pinned GPL/BSD sources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tools/ShellAppearance'
BUILD=ROOT/'artifacts/shell-build'
PAYLOAD=ROOT/'artifacts/shell-appearance'
NAMES=('BigFishShellAppearance.exe','BigFishStartStyle.dll','BigFishNotificationStyle.dll')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    cxx=[*common,'-std=c++23','-fms-extensions','-I'+str(headers),'-I'+str(ROOT/'references/MinHook/include'),'-I'+str(SOURCE)]
    objects=[]
    def run(args):
        result=subprocess.run([str(a) for a in args],cwd=BUILD,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=300)
        with (BUILD/'compile.log').open('a',encoding='utf-8') as stream:stream.write(result.stdout)
        if result.returncode:
            print(result.stdout[-14000:]);raise RuntimeError('Native shell compilation failed: '+str(args[-1]))
    (BUILD/'compile.log').write_text('',encoding='utf-8')
    for filename in ('buffer.c','hook.c','trampoline.c','hde/hde64.c'):
        path=ROOT/'references/MinHook/src'/filename;obj=BUILD/(path.stem+'.o');objects.append(obj)
        run([cc,*common,'-c',path,'-o',obj])
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
        if kind=='start':
            # Separate existing new-layout columns in-process; never force OS
            # feature flags or restart the shell to select a legacy layout.
            code=code.replace('    return disableNewStartMenuLayout;\n}',
                '    if (disableNewStartMenuLayout == DisableNewStartMenuLayout::windowsDefault && useNewLayoutVariant)\n'
                '        disableNewStartMenuLayout = DisableNewStartMenuLayout::newLayoutSideBySide;\n'
                '    return disableNewStartMenuLayout;\n}')
        generated=BUILD/(kind+'.cpp')
        generated.write_text(('#define BIGFISH_START_ENGINE 1\n' if kind=='start' else '')+'#include "engine_adapter.h"\n'+code+'\n#include "engine_probe.h"\n#include "engine_lifecycle.cpp"\n',encoding='utf-8')
        run([compiler,*cxx,'-shared','-static',generated,*objects,'-lcomctl32','-lole32','-loleaut32','-lruntimeobject','-lshlwapi','-lshell32','-ladvapi32','-luuid','-lversion','-Wl,--no-insert-timestamp','-o',PAYLOAD/output])
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
