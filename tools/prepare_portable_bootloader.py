"""Build the pinned PyInstaller GUI bootloader with BigFishDock's session cleanup."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '6.16.0'
SOURCE_SHA256 = '53559fe1e041a234f2b4dcc3288ea8bdd57f7cad8a6644e422c27bb407f3edef'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Unexpected pinned source around {old[:100]!r}')
    return text.replace(old, new, 1)


def patch(source):
    win32 = source / 'pyi_utils_win32.c'
    main = source / 'pyi_main.c'
    text = win32.read_text(encoding='utf-8')
    begin = text.index('        case WM_QUERYENDSESSION: {')
    end = text.index('        default: {', begin)
    text = text[:begin] + r'''        case WM_QUERYENDSESSION: {
            pyi_ctx = (struct PYI_CONTEXT *)GetWindowLongPtr(hwnd, GWLP_USERDATA);
            /* The child handles its own session messages. Allow the query
             * immediately, without registering a shutdown blocker. */
            if (!pyi_ctx->session_shutdown) {
                pyi_ctx->session_shutdown = 1;
            }
            return TRUE;
        }
        case WM_ENDSESSION: {
            pyi_ctx = (struct PYI_CONTEXT *)GetWindowLongPtr(hwnd, GWLP_USERDATA);
            if (!wParam) {
                if (pyi_ctx->session_shutdown == 1) {
                    pyi_ctx->session_shutdown = 0;
                }
                return 0;
            }
            if (pyi_ctx->session_shutdown > 1) {
                return 0;
            }
            pyi_ctx->session_shutdown = 2; /* Confirmed; bounded cleanup, no UI. */
            if (WaitForSingleObject(pyi_ctx->child_process.hProcess, 1800) == WAIT_OBJECT_0) {
                int status = pyi_main_onefile_parent_cleanup(pyi_ctx);
                pyi_ctx->session_shutdown = status < 0 ? 4 : 3; /* Cleaned once. */
            }
            /* If the child is still saving, let Windows handle the session.
             * The ordinary child-exit path can still clean up if it finishes. */
            return 0;
        }
''' + text[end:]
    text = replace_once(text, '    ZeroMemory(&hidden_window_class, sizeof(hidden_window_class));', '''    /* This parent must receive WM_ENDSESSION after the normal-priority child. */
    SetProcessShutdownParameters(0x270, SHUTDOWN_NORETRY);
    ZeroMemory(&hidden_window_class, sizeof(hidden_window_class));''')
    text = replace_once(text, 'TEXT("PyInstaller Onefile Hidden Window")', 'TEXT("BigFishDock Portable")')
    begin = text.index('        /* If we received WM_QUERYENDSESSION, keep looping until we')
    end = text.index('\n    }', begin)
    text = text[:begin] + '''        /* The child is already gone. Give Windows a short chance to send the
         * decision, then proceed with cleanup even if no decision arrives. */
        ULONGLONG deadline = GetTickCount64() + 750;
        while (pyi_ctx->session_shutdown == 1 && GetTickCount64() < deadline) {
            MsgWaitForMultipleObjects(0, NULL, FALSE, 50, QS_ALLINPUT);
            while (PeekMessageW(&msg, pyi_ctx->hidden_window, 0, 0, PM_REMOVE) > 0) {
                TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
        }''' + text[end:]
    text = replace_once(text,
        '    const int max_attempts = 15; /* Maximum number of attempts in retry loop */\n'
        '    const int delay = 1000; /* Delay for retry loop (milliseconds) */',
        '    const int max_attempts = pyi_ctx->session_shutdown ? 3 : 15;\n'
        '    const int delay = pyi_ctx->session_shutdown ? 100 : 1000;')
    win32.write_text(text, encoding='utf-8')

    text = main.read_text(encoding='utf-8')
    begin = text.index('int pyi_main_onefile_parent_cleanup(struct PYI_CONTEXT *pyi_ctx)\n{')
    old = '    int ret = 0;'
    i = text.index(old, begin)
    text = text[:i] + '''    int ret = 0;
#ifdef _WIN32
    /* The hidden-window handler may already have freed the archive. */
    if (pyi_ctx->session_shutdown >= 3) {
        return pyi_ctx->session_shutdown == 4 ? -1 : 0;
    }
#endif''' + text[i+len(old):]
    text = replace_once(text, '''        if (pyi_ctx->strict_unpack_mode) {
            PYI_ERROR("Failed to remove temporary directory: %s\\n", pyi_ctx->application_home_dir);
            ret = -1;
        } else {
            PYI_WARNING("Failed to remove temporary directory: %s\\n", pyi_ctx->application_home_dir);
        }''', '''#ifdef _WIN32
        /* A locked file must never put up a modal dialog while logging off.
         * For best-effort cleanup, use the system debug stream at normal exit, too. */
        if (pyi_ctx->session_shutdown || !pyi_ctx->strict_unpack_mode) {
            OutputDebugStringW(L"BigFishDock Portable: could not remove the temporary directory.\\n");
            OutputDebugStringA(pyi_ctx->application_home_dir);
            ret = pyi_ctx->strict_unpack_mode ? -1 : 0;
        } else
#endif
        if (pyi_ctx->strict_unpack_mode) {
            PYI_ERROR("Failed to remove temporary directory: %s\\n", pyi_ctx->application_home_dir);
            ret = -1;
        } else {
            PYI_WARNING("Failed to remove temporary directory: %s\\n", pyi_ctx->application_home_dir);
        }''')
    main.write_text(text, encoding='utf-8')


def build(toolchain):
    from PyInstaller import __version__
    if __version__ != VERSION:
        raise ValueError(f'PyInstaller {VERSION} required for the portable bootloader')
    source = ROOT / 'references' / f'pyinstaller-{VERSION}.tar.gz'
    with source.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != SOURCE_SHA256:
            raise ValueError('Portable bootloader source archive checksum mismatch')
    compiler = toolchain.resolve() / 'mingw/mingw64/bin/gcc.exe'
    env = os.environ.copy()
    env['PATH'] = str(compiler.parent) + os.pathsep + env['PATH']
    compiler_id = subprocess.check_output([compiler, '-dumpfullversion', '-dumpversion'], env=env)
    key = hashlib.sha256(Path(__file__).read_bytes() + compiler_id + os.fsencode(compiler)).hexdigest()[:16]
    cache = ROOT / 'artifacts/portable-bootloader'
    project = cache / key / f'pyinstaller-{VERSION}'
    compiled = project / 'PyInstaller/bootloader/Windows-64bit-intel/runw.exe'
    if not compiled.is_file():
        with tarfile.open(source, 'r:gz') as archive:
            files = [m for m in archive if m.name.startswith(f'{project.name}/bootloader/')
                     or m.name == f'{project.name}/PyInstaller/_shared_with_waf.py']
            archive.extractall(cache / key, members=files, filter='data')
        patch(project / 'bootloader/src')
        subprocess.run([sys.executable, 'waf', 'configure', 'build_releasew', 'install_releasew', '--gcc'],
                       cwd=project / 'bootloader', env=env, check=True)
    target = cache / 'runw.exe'
    if not target.is_file() or target.read_bytes() != compiled.read_bytes():
        staged = target.with_suffix('.tmp')
        shutil.copyfile(compiled, staged)
        staged.replace(target)
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--toolchain', type=Path, required=True)
    build(parser.parse_args().toolchain)
