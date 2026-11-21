"""Windows hardware names and persistent keys for the resource counters."""
from collections import Counter
import ctypes as C
from ctypes import wintypes as W
from hashlib import sha256
from typing import NamedTuple
from uuid import UUID


class Device(NamedTuple):
    name: str
    number: int | str  # Runtime LUID, disk number, or Windows display name.
    instance: str = ''  # Monitor PnP instance for the brightness provider.
    aliases: tuple[int, ...] = ()  # Alternate LUIDs exposed for the same physical GPU.


def device_key(kind, identifier):
    return kind + ':' + sha256(identifier.casefold().encode('utf-8')).hexdigest()[:32]


class Luid(C.Structure):
    _fields_ = [('low', W.DWORD), ('high', W.LONG)]


class AdapterDesc(C.Structure):
    _fields_ = [('description', W.WCHAR * 128), ('vendor', W.UINT), ('device', W.UINT),
                ('subsystem', W.UINT), ('revision', W.UINT), ('dedicated', C.c_size_t),
                ('system', C.c_size_t), ('shared', C.c_size_t), ('luid', Luid), ('flags', W.UINT)]


class OpenAdapter(C.Structure):
    _fields_ = [('luid', Luid), ('handle', W.UINT)]


class QueryAdapter(C.Structure):
    _fields_ = [('handle', W.UINT), ('kind', C.c_int), ('data', C.c_void_p), ('size', W.UINT)]


class AdapterPnpKey(C.Structure):
    _fields_ = [('physical', W.UINT), ('kind', C.c_int), ('path', C.c_void_p), ('length', C.POINTER(W.UINT))]


def com_method(interface, slot, result, *args):
    vtable = C.cast(interface, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(result, C.c_void_p, *args)(vtable[slot])


def bind(library, name, result, *args):
    call = getattr(library, name)
    call.argtypes = args
    call.restype = result
    return call


def gpu_devices():
    """Bridge DXGI's adapter LUID to its name and durable adapter identity."""
    dxgi = C.WinDLL('dxgi')
    gdi = C.WinDLL('gdi32')
    open_adapter = bind(gdi, 'D3DKMTOpenAdapterFromLuid', W.LONG, C.POINTER(OpenAdapter))
    close_adapter = bind(gdi, 'D3DKMTCloseAdapter', W.LONG, C.POINTER(W.UINT))
    query = bind(gdi, 'D3DKMTQueryAdapterInfo', W.LONG, C.POINTER(QueryAdapter))
    create = bind(dxgi, 'CreateDXGIFactory1', W.LONG, C.c_void_p, C.POINTER(C.c_void_p))
    iid = C.create_string_buffer(UUID('770aae78-f26f-4dba-a829-253c83d1b387').bytes_le)
    factory = C.c_void_p()
    if create(iid, C.byref(factory)):
        return {}
    adapters = {}
    try:
        # The IDXGIFactory1 and IDXGIAdapter1 additions follow the inherited interfaces.
        enumerate_adapter = com_method(factory, 12, W.LONG, W.UINT, C.POINTER(C.c_void_p))
        for index in range(64):
            adapter = C.c_void_p()
            if enumerate_adapter(factory, index, C.byref(adapter)):
                break
            try:
                desc = AdapterDesc()
                if com_method(adapter, 10, W.LONG, C.POINTER(AdapterDesc))(adapter, C.byref(desc)) or desc.flags & 2:
                    continue  # Software renderers are not physical GPUs.
                number = ((desc.luid.high & 0xffffffff) << 32) | desc.luid.low
                identity = f'{desc.vendor:x}:{desc.device:x}:{desc.subsystem:x}'
                address = (W.UINT * 3)(0xffffffff)
                guid = (C.c_ubyte * 16)()
                has_address = False
                opened = OpenAdapter(desc.luid)
                if not open_adapter(C.byref(opened)):
                    try:
                        path = C.create_unicode_buffer(512)
                        length = W.UINT(len(path))
                        pnp = AdapterPnpKey(0, 1, C.addressof(path), C.pointer(length))
                        has_address = (not query(C.byref(QueryAdapter(opened.handle, 6, C.addressof(address), C.sizeof(address))))
                                       and address[0] != 0xffffffff)
                        if not query(C.byref(QueryAdapter(opened.handle, 41, C.addressof(pnp), C.sizeof(pnp)))) and path.value:
                            # The registry path may use a different ControlSet number after reboot.
                            identity = path.value.casefold().partition('\\enum\\')[2] or path.value
                        elif has_address:
                            identity += ':' + ':'.join(map(str, address))
                        elif not query(C.byref(QueryAdapter(opened.handle, 4, C.addressof(guid), C.sizeof(guid)))) and any(guid):
                            identity += ':' + bytes(guid).hex()
                        else:
                            identity += f':luid:{number:x}'
                    finally:
                        close_adapter(C.byref(W.UINT(opened.handle)))
                else:
                    identity += f':luid:{number:x}'
                adapters.setdefault(identity, []).append((has_address, number, desc.description.strip() or 'GPU'))
            finally:
                com_method(adapter, 2, W.ULONG)(adapter)
    finally:
        com_method(factory, 2, W.ULONG)(factory)
    names = Counter(rows[0][2] for rows in adapters.values())
    devices = {}
    for index, (identity, rows) in enumerate(adapters.items(), 1):
        _, number, name = max(rows, key=lambda row: row[0])
        if names[rows[0][2]] > 1:
            name += f' · {index}'
        aliases = tuple(sorted({luid for _, luid, _ in rows if luid != number}))
        devices[device_key('gpu', identity)] = Device(name, number, aliases=aliases)
    return devices


class DeviceInfo(C.Structure):
    _fields_ = [('size', W.DWORD), ('guid', C.c_byte * 16), ('devinst', W.DWORD), ('reserved', C.c_size_t)]


def disk_devices():
    """Pair each present disk's PnP instance with its current physical disk number."""
    setup = C.WinDLL('setupapi')
    kernel = C.WinDLL('kernel32')
    guid = C.create_string_buffer(UUID('53f56307-b6bf-11d0-94f2-00a0c91efb8b').bytes_le)
    get_set = bind(setup, 'SetupDiGetClassDevsW', W.HANDLE, C.c_void_p, W.LPCWSTR, W.HWND, W.DWORD)
    invalid = C.c_void_p(-1).value
    devices = get_set(guid, None, None, 0x12)  # DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    if devices in (None, invalid):
        return {}
    destroy = bind(setup, 'SetupDiDestroyDeviceInfoList', W.BOOL, W.HANDLE)
    try:
        enumerate_disk = bind(setup, 'SetupDiEnumDeviceInterfaces', W.BOOL,
                              W.HANDLE, C.c_void_p, C.c_void_p, W.DWORD, C.POINTER(DeviceInfo))
        detail = bind(setup, 'SetupDiGetDeviceInterfaceDetailW', W.BOOL,
                      W.HANDLE, C.POINTER(DeviceInfo), C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.POINTER(DeviceInfo))
        instance_id = bind(setup, 'SetupDiGetDeviceInstanceIdW', W.BOOL,
                           W.HANDLE, C.POINTER(DeviceInfo), W.LPWSTR, W.DWORD, C.POINTER(W.DWORD))
        property_value = bind(setup, 'SetupDiGetDeviceRegistryPropertyW', W.BOOL,
                              W.HANDLE, C.POINTER(DeviceInfo), W.DWORD, C.c_void_p, C.c_void_p, W.DWORD, C.c_void_p)
        open_disk = bind(kernel, 'CreateFileW', W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p,
                         W.DWORD, W.DWORD, W.HANDLE)
        ioctl = bind(kernel, 'DeviceIoControl', W.BOOL, W.HANDLE, W.DWORD, C.c_void_p, W.DWORD,
                     C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p)
        close = bind(kernel, 'CloseHandle', W.BOOL, W.HANDLE)
        result = {}
        for index in range(256):
            interface = DeviceInfo(C.sizeof(DeviceInfo))
            if not enumerate_disk(devices, None, guid, index, C.byref(interface)):
                break
            size = W.DWORD()
            detail(devices, C.byref(interface), None, 0, C.byref(size), None)
            if not 8 <= size.value <= 32768:
                continue
            path = C.create_string_buffer(size.value)
            C.cast(path, C.POINTER(W.DWORD)).contents.value = 8 if C.sizeof(C.c_void_p) == 8 else 6
            info = DeviceInfo(C.sizeof(DeviceInfo))
            if not detail(devices, C.byref(interface), path, size, None, C.byref(info)):
                continue
            pnp_id = C.create_unicode_buffer(512)
            if not instance_id(devices, C.byref(info), pnp_id, len(pnp_id), None):
                continue
            handle = open_disk(C.wstring_at(C.addressof(path) + 4), 0, 3, None, 3, 0, None)
            if handle in (None, invalid):
                continue
            try:
                record, returned = (W.DWORD * 3)(), W.DWORD()
                if not ioctl(handle, 0x2d1080, None, 0, record, C.sizeof(record), C.byref(returned), None):
                    continue  # IOCTL_STORAGE_GET_DEVICE_NUMBER, no read/write access needed.
                if returned.value != C.sizeof(record) or record[1] == 0xffffffff:
                    continue
            finally:
                close(handle)
            name = C.create_unicode_buffer(512)
            for prop in (12, 0):  # SPDRP_FRIENDLYNAME, SPDRP_DEVICEDESC
                if property_value(devices, C.byref(info), prop, None, name, C.sizeof(name), None) and name.value:
                    break
            title = f'磁盘 {record[1]}'
            if name.value:
                title += f' · {name.value}'
            result[device_key('disk', pnp_id.value)] = Device(title, record[1])
        return dict(sorted(result.items(), key=lambda row: row[1].number))
    finally:
        destroy(devices)


class DisplayDevice(C.Structure):
    _fields_ = [('size', W.DWORD), ('name', W.WCHAR * 32), ('description', W.WCHAR * 128),
                ('flags', W.DWORD), ('identifier', W.WCHAR * 128), ('key', W.WCHAR * 128)]


def display_devices():
    user = C.WinDLL('user32')
    enumerate_display = bind(user, 'EnumDisplayDevicesW', W.BOOL, W.LPCWSTR, W.DWORD,
                             C.POINTER(DisplayDevice), W.DWORD)
    result = {}
    for index in range(64):
        source = DisplayDevice(C.sizeof(DisplayDevice))
        if not enumerate_display(None, index, C.byref(source), 0):
            break
        if not source.flags & 1 or source.flags & 8:  # Only active desktop sources, excluding mirroring drivers.
            continue
        display = DisplayDevice(C.sizeof(DisplayDevice))
        enumerate_display(source.name, 0, C.byref(display), 1)  # EDD_GET_DEVICE_INTERFACE_NAME
        parts = display.identifier.removeprefix('\\\\?\\').split('#')
        instance = '\\'.join(parts[:3]) if len(parts) >= 4 else ''
        device_id = device_key('display', instance or source.name)
        source_name = source.name.rsplit('\\', 1)[-1]
        name = f'{source_name} · {display.description or source.description}'
        result[device_id] = Device(name, source.name, instance)
    return result
