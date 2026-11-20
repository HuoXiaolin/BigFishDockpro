"""Stop optional child creation at the start of Windows logoff/shutdown."""
import subprocess
import sys
import threading
import time
import weakref

from PyQt5.QtCore import QProcess

_ending = False
_processes = weakref.WeakSet()
_graceful = weakref.WeakSet()
_native = set()
_native_lock = threading.Lock()


def system_ending():
    if sys.platform != 'win32':
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetSystemMetrics(0x2000))  # SM_SHUTTINGDOWN


def allowed():
    return not _ending and not system_ending()


def set_ending(value):
    global _ending
    with _native_lock:
        _ending = bool(value)
        if not _ending:
            return
        for process in _native:
            try:
                if process.poll() is None:
                    process.kill()
            except OSError:
                pass
    # Stop only our read-only probes; the Deck bridge gets its quit command
    # from DeckBridge.close. Do not wait during WM_QUERYENDSESSION.
    for process in tuple(_processes):
        try:
            if process.state() != QProcess.NotRunning:
                process.kill()
        except RuntimeError:  # Qt may have deleted the wrapper during teardown.
            _processes.discard(process)


def start(process, program, arguments, *, graceful=False):
    if not allowed():
        return False
    (_graceful if graceful else _processes).add(process)
    process.start(str(program), arguments)
    return True


def start_native(arguments, **options):
    """Register the bundled PresentMon process before shutdown can proceed."""
    with _native_lock:
        if not allowed():
            return None
        _native.difference_update([p for p in _native if p.poll() is not None])
        process = subprocess.Popen(arguments, **options)
        _native.add(process)
        return process


def release_native(process):
    with _native_lock:
        if process.poll() is not None:
            _native.discard(process)


def drain():
    """Reap our bundled helpers before the onefile parent deletes the runtime."""
    qt_processes = tuple(_processes) + tuple(_graceful)
    with _native_lock:
        native = tuple(_native)

    def wait_until(deadline):
        for process in qt_processes:
            try:
                if process.state() != QProcess.NotRunning:
                    process.waitForFinished(max(0, int((deadline - time.monotonic()) * 1000)))
            except RuntimeError:
                pass  # A finished Qt process may already have been deleted.
        for process in native:
            try:
                process.wait(timeout=max(0., deadline - time.monotonic()))
            except (OSError, subprocess.TimeoutExpired):
                pass

    wait_until(time.monotonic() + .25)
    for process in qt_processes:
        try:
            if process.state() != QProcess.NotRunning:
                process.kill()
        except RuntimeError:
            pass
    wait_until(time.monotonic() + .20)
    for process in native:
        release_native(process)
