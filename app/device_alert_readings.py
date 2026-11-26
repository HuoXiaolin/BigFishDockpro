"""Read audio switches off the UI thread and receive Windows brightness changes."""
import ctypes as C
from ctypes import wintypes as W
from functools import lru_cache
import subprocess
from uuid import UUID

from PyQt5.QtCore import QObject, pyqtSignal
from background_worker import BackgroundWorker
from device_status import DeviceStatus, GUID


@lru_cache(maxsize=1)
def has_oem_touchpad():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\BIOS') as key:
            vendor = winreg.QueryValueEx(key, 'SystemManufacturer')[0].strip().upper()
        return vendor in ('HUAWEI', 'HONOR')
    except OSError:
        return False


class TouchpadSwitchRead(BackgroundWorker):
    reported = pyqtSignal(str)

    def run(self):
        from probe_lifecycle import start_native, release_native
        from resource_probes import binary
        while not self.cancelled.is_set():
            ready = False
            try:
                process = start_native([str(binary('DesktopResourceProbe.exe')), '--touchpad-events'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                if process is None:
                    return
                self.own_process(process)
                try:
                    with process:
                        for line in process.stdout:
                            event = line.strip()
                            if event == b'ready':
                                ready = True
                            elif event in (b'on', b'off'):
                                self.reported.emit(event.decode('ascii'))
                finally:
                    self.release_process(process)
                    release_native(process)
            except OSError:
                pass
            if self.cancelled.is_set():
                return
            self.reported.emit('pending' if ready else 'windows')
            if not ready or self.cancelled.wait(2):
                return


class AudioSwitchRead(BackgroundWorker):
    changed = pyqtSignal(str, object)

    def __init__(self, keys):
        super().__init__()
        self.keys = keys

    def run(self):
        audio = DeviceStatus(C.WinDLL('kernel32'))
        reads = {'microphone': audio.microphone_enabled, 'volume': audio.volume}
        previous = {}
        while not self.cancelled.is_set():
            for key in self.keys:
                try:
                    value = reads[key]()
                except OSError:
                    value = None
                if key not in previous or value != previous[key]:
                    previous[key] = value
                    self.changed.emit(key, value)
            self.cancelled.wait(.20)


BRIGHTNESS = UUID('8ffee2c6-2d01-46be-adb9-398addc5b4ff').bytes_le
PowerCallback = C.WINFUNCTYPE(W.ULONG, C.c_void_p, W.ULONG, C.c_void_p)


class PowerSubscription(C.Structure):
    _fields_ = [('callback', PowerCallback), ('context', C.c_void_p)]


class PowerSetting(C.Structure):
    _fields_ = [('guid', GUID), ('length', W.DWORD), ('percent', W.DWORD)]


class BrightnessNotifications(QObject):
    changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.handle = W.HANDLE()
        self.power = C.WinDLL('powrprof')
        self.subscription = PowerSubscription(PowerCallback(self.receive), None)
        register = self.power.PowerSettingRegisterNotification
        register.argtypes = [C.POINTER(GUID), W.DWORD, C.POINTER(PowerSubscription), C.POINTER(W.HANDLE)]
        register.restype = W.DWORD
        self.power.PowerSettingUnregisterNotification.argtypes = [W.HANDLE]

    def start(self):
        guid = GUID.from_buffer_copy(BRIGHTNESS)
        return self.power.PowerSettingRegisterNotification(C.byref(guid), 2, C.byref(self.subscription), C.byref(self.handle)) == 0

    def receive(self, context, kind, data):
        if kind == 0x8013 and data:  # PBT_POWERSETTINGCHANGE
            setting = PowerSetting.from_address(data)
            if bytes(setting.guid) == BRIGHTNESS and setting.length == 4 and setting.percent <= 100:
                self.changed.emit(setting.percent)
        return 0

    def close(self):
        if self.handle:
            self.power.PowerSettingUnregisterNotification(self.handle)
            self.handle = W.HANDLE()
        self.deleteLater()
