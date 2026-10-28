"""Keep external programs independent from the frozen application's DLL search path."""
import contextlib
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import threading

_lock = threading.RLock()
_ENV_KEYS = ('PATH','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QML2_IMPORT_PATH','QML_IMPORT_PATH')


def _inside(value, root):
    try:return Path(value).resolve().is_relative_to(root)
    except (OSError,ValueError):return False


@contextlib.contextmanager
def clean_environment():
    """ShellExecute inherits process state too; restore it even when launch fails."""
    frozen = getattr(sys,'_MEIPASS',None)
    if not frozen:
        yield dict(os.environ)
        return
    root=Path(frozen).resolve()
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetDllDirectoryW.argtypes=[ctypes.c_uint,ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
    with _lock:
        length=kernel.GetDllDirectoryW(0,None)
        previous=ctypes.create_unicode_buffer(length+1)
        kernel.GetDllDirectoryW(len(previous),previous)
        saved={key:os.environ.get(key) for key in _ENV_KEYS+('PYINSTALLER_RESET_ENVIRONMENT',)}
        if not kernel.SetDllDirectoryW(None):raise ctypes.WinError(ctypes.get_last_error())
        try:
            for key in _ENV_KEYS:
                if key in os.environ:
                    parts=[part for part in os.environ[key].split(os.pathsep) if part and not _inside(part,root)]
                    if parts:os.environ[key]=os.pathsep.join(parts)
                    else:os.environ.pop(key,None)
            os.environ['PYINSTALLER_RESET_ENVIRONMENT']='1'
            yield dict(os.environ)
        finally:
            for key,value in saved.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
            kernel.SetDllDirectoryW(previous.value or None)


def startfile(path):
    target=Path(path)
    directory=str(target.parent) if target.is_absolute() and target.exists() else str(Path(sys.executable).parent)
    with clean_environment():os.startfile(str(path),cwd=directory)


def launch_direct(path):
    low=path.lower()
    if low.startswith('shell:appsfolder\\'):
        with clean_environment() as env:
            return subprocess.Popen(['explorer.exe',path],cwd=str(Path(sys.executable).parent),env=env,close_fds=True)
    if low.endswith('.exe') and os.path.isfile(path):
        with clean_environment() as env:
            return subprocess.Popen([path],cwd=str(Path(path).resolve().parent),env=env,close_fds=True)
    startfile(path)


def launch(path):
    target=Path(path)
    directory=str(target.resolve().parent) if target.is_absolute() and target.exists() else str(Path(sys.executable).parent)
    try:
        from explorer_launch import launch as explorer_launch
        # Explorer owns the child and its environment; no app-group/DLL inheritance.
        return explorer_launch(str(path),directory)
    except OSError:
        # Shell unavailable (e.g. alternate desktop): retain the cleaned direct route.
        return launch_direct(path)
