"""Read Windows power and the default render endpoint on the resource sampler."""
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID


class PowerStatus(C.Structure):
    _fields_ = [
        ('ac', W.BYTE), ('flags', W.BYTE), ('percent', W.BYTE), ('saver', W.BYTE),
        ('remaining', W.DWORD), ('lifetime', W.DWORD),
    ]


def battery_status(ac, flags, percent):
    level = percent if 0 <= percent <= 100 else None
    if flags != 255 and flags & 128:
        return None, 'ac' if ac == 1 else 'no_battery'
    if flags != 255 and flags & 8:
        return level, 'charging'
    if ac == 1:
        return level, 'full' if level == 100 else 'plugged'
    return level, 'battery' if ac == 0 or level is not None else 'unknown'


GUID = C.c_ubyte * 16
ENUMERATOR_CLASS = GUID.from_buffer_copy(UUID('BCDE0395-E52F-467C-8E3D-C4579291692E').bytes_le)
ENUMERATOR = GUID.from_buffer_copy(UUID('A95664D2-9614-4F35-A746-DE8DB63617E6').bytes_le)
ENDPOINT_VOLUME = GUID.from_buffer_copy(UUID('5CDF2C82-841E-4546-9722-0CF74078229A').bytes_le)
NETWORK_MANAGER_CLASS = GUID.from_buffer_copy(UUID('DCB00C01-570F-4A9B-8D69-199FDBA5723B').bytes_le)
NETWORK_MANAGER = GUID.from_buffer_copy(UUID('DCB00000-570F-4A9B-8D69-199FDBA5723B').bytes_le)
OUT_INTERFACE = C.POINTER(C.c_void_p)


class WlanConnectionHeader(C.Structure):
    # WLAN_CONNECTION_ATTRIBUTES through wlanAssociationAttributes.dot11Ssid.
    _fields_ = [('state', W.DWORD), ('mode', W.DWORD), ('profile', W.WCHAR * 256),
                ('ssid_length', W.DWORD), ('ssid', C.c_ubyte * 32)]


@lru_cache(maxsize=1)
def wlan_api():
    try:
        wlan=C.WinDLL('wlanapi')
    except OSError:
        return None
    wlan.WlanOpenHandle.argtypes=[W.DWORD,C.c_void_p,C.POINTER(W.DWORD),C.POINTER(W.HANDLE)]
    wlan.WlanQueryInterface.argtypes=[W.HANDLE,C.POINTER(GUID),C.c_int,C.c_void_p,C.POINTER(W.DWORD),OUT_INTERFACE,C.c_void_p]
    wlan.WlanFreeMemory.argtypes=[C.c_void_p]
    wlan.WlanFreeMemory.restype=None
    wlan.WlanCloseHandle.argtypes=[W.HANDLE,C.c_void_p]
    return wlan


def invoke(instance, slot, result, types, *args):
    table = C.cast(instance, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(result, C.c_void_p, *types)(table[slot])(instance, *args)


def release(*interfaces):
    for interface in interfaces:
        if interface:
            invoke(interface, 2, W.ULONG, ())  # IUnknown::Release


class DeviceStatus:
    def __init__(self, kernel):
        self.power = kernel.GetSystemPowerStatus
        self.power.argtypes = [C.POINTER(PowerStatus)]
        self.power.restype = W.BOOL
        self.com=None;self.free_string=None
        self.connection_cache=None

    def prepare_com(self):
        self.com = C.WinDLL('ole32')
        self.com.CoInitializeEx.argtypes = [C.c_void_p, W.DWORD]
        self.com.CoInitializeEx.restype = C.c_long
        self.com.CoUninitialize.argtypes = []
        self.com.CoUninitialize.restype = None
        self.com.CoCreateInstance.argtypes = [
            C.POINTER(GUID), C.c_void_p, W.DWORD, C.POINTER(GUID), C.POINTER(C.c_void_p),
        ]
        self.com.CoCreateInstance.restype = C.c_long

    def battery(self):
        status = PowerStatus()
        if not self.power(C.byref(status)):
            return None, 'unknown'
        return battery_status(status.ac, status.flags, status.percent)

    @contextmanager
    def apartment(self):
        if self.com is None:self.prepare_com()
        hr = self.com.CoInitializeEx(None, 0)
        try:
            yield hr >= 0 or hr & 0xffffffff == 0x80010106
        finally:
            if hr >= 0:
                self.com.CoUninitialize()

    def volume(self):
        with self.apartment() as ready:
            if not ready:return None
            enum,device,endpoint=C.c_void_p(),C.c_void_p(),C.c_void_p()
            try:
                if self.com.CoCreateInstance(C.byref(ENUMERATOR_CLASS),None,1,C.byref(ENUMERATOR),C.byref(enum))<0:
                    return None
                # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia).
                if invoke(enum,4,C.c_long,(C.c_int,C.c_int,OUT_INTERFACE),0,1,C.byref(device))<0:
                    return None
                if invoke(device,3,C.c_long,(C.POINTER(GUID),W.DWORD,C.c_void_p,OUT_INTERFACE),
                          C.byref(ENDPOINT_VOLUME),23,None,C.byref(endpoint))<0:
                    return None
                level,muted=C.c_float(),W.BOOL()
                if invoke(endpoint,9,C.c_long,(C.POINTER(C.c_float),),C.byref(level))<0:
                    return None
                if invoke(endpoint,15,C.c_long,(C.POINTER(W.BOOL),),C.byref(muted))<0:
                    return None
                if 0<=level.value<=1:
                    return round(100*level.value),bool(muted.value)
            finally:
                release(endpoint,device,enum)

    def connection_name(self,adapter,alias,now,wireless=False):
        if adapter is None:
            self.connection_cache=None
            return ''
        cache=self.connection_cache
        if cache is None or cache[0]!=adapter or now>=cache[1]:
            ssid=self.connected_ssid(adapter) if wireless else ''
            cache=self.connection_cache=(adapter,now+5,ssid or self.network_profile(adapter))
        return alias,cache[2]

    def connected_ssid(self,adapter):
        """Read the association on this interface, including when its network profile was renamed."""
        wlan=wlan_api()
        if wlan is None:
            return ''
        version,size,handle,buffer=W.DWORD(),W.DWORD(),W.HANDLE(),C.c_void_p()
        if wlan.WlanOpenHandle(2,None,C.byref(version),C.byref(handle)):
            return ''
        try:
            guid=GUID.from_buffer_copy(adapter)
            if wlan.WlanQueryInterface(handle,C.byref(guid),7,None,C.byref(size),C.byref(buffer),None):
                return ''
            if not buffer or size.value<C.sizeof(WlanConnectionHeader):
                return ''
            row=C.cast(buffer,C.POINTER(WlanConnectionHeader)).contents
            if row.state!=1 or not 0<row.ssid_length<=32:
                return ''
            raw=bytes(row.ssid[:row.ssid_length])
            for encoding in ('utf-8','mbcs'):
                try:
                    name=raw.decode(encoding)
                except UnicodeDecodeError:
                    continue
                if name.isprintable():
                    return name
            return ''
        finally:
            if buffer:wlan.WlanFreeMemory(buffer)
            wlan.WlanCloseHandle(handle,None)

    def network_profile(self,adapter):
        with self.apartment() as ready:
            if not ready:return ''
            manager,enum=C.c_void_p(),C.c_void_p()
            try:
                if self.com.CoCreateInstance(C.byref(NETWORK_MANAGER_CLASS),None,1,
                                             C.byref(NETWORK_MANAGER),C.byref(manager))<0:
                    return ''
                # INetworkListManager and IEnumNetworkConnections derive from IDispatch.
                if invoke(manager,9,C.c_long,(OUT_INTERFACE,),C.byref(enum))<0:
                    return ''
                for _ in range(128):
                    connection=C.c_void_p();fetched=W.ULONG()
                    if invoke(enum,8,C.c_long,(W.ULONG,OUT_INTERFACE,C.POINTER(W.ULONG)),
                              1,C.byref(connection),C.byref(fetched))!=0 or not fetched.value:
                        release(connection)
                        break
                    try:
                        guid=GUID()
                        if invoke(connection,12,C.c_long,(C.POINTER(GUID),),C.byref(guid))==0 and bytes(guid)==adapter:
                            name=self.profile_name(connection)
                            if name:return name
                    finally:
                        release(connection)
            finally:
                release(enum,manager)
        return ''

    def profile_name(self,connection):
        network,name=C.c_void_p(),C.c_void_p()
        try:
            connected=C.c_short()
            if invoke(connection,9,C.c_long,(C.POINTER(C.c_short),),C.byref(connected))<0 or not connected.value:
                return ''
            if invoke(connection,7,C.c_long,(OUT_INTERFACE,),C.byref(network))<0:
                return ''
            if invoke(network,7,C.c_long,(OUT_INTERFACE,),C.byref(name))==0 and name:
                return ' '.join(C.wstring_at(name).split())
            return ''
        finally:
            if name:
                if self.free_string is None:
                    self.free_string=C.WinDLL('oleaut32').SysFreeString
                    self.free_string.argtypes=[C.c_void_p];self.free_string.restype=None
                self.free_string(name)
            release(network)
