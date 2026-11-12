"""Stop optional child creation at the start of Windows logoff/shutdown."""
import sys
import weakref

from PyQt5.QtCore import QProcess

_ending = False
_processes = weakref.WeakSet()


def system_ending():
    if sys.platform != 'win32':
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetSystemMetrics(0x2000))  # SM_SHUTTINGDOWN


def allowed():
    return not _ending and not system_ending()


def set_ending(value):
    global _ending
    _ending = bool(value)
    if not _ending:
        return
    # Only these owned, read-only probes are stopped. Never wait in the native
    # session callback, and never touch other programs on the desktop.
    for process in tuple(_processes):
        try:
            if process.state() != QProcess.NotRunning:
                process.kill()
        except RuntimeError:  # Qt may have deleted the wrapper during teardown.
            _processes.discard(process)


def start(process, program, arguments):
    if not allowed():
        return False
    _processes.add(process)
    process.start(str(program), arguments)
    return True
