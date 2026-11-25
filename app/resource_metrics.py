"""Windows resource counters. Imported by the sampler only while metrics are requested."""
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import math
import os
import re
import time

U64=C.c_ulonglong
NET_KEYS=frozenset(('network','traffic','system_status','connection','network_links','network_utilization','network_devices'))
DEVICE_KEYS=frozenset(('system_status','battery','connection','volume','microphone','network_links'))


class MemoryStatus(C.Structure):
    _fields_=[('length',W.DWORD),('load',W.DWORD)]+[(name,U64) for name in (
        'total','available','page_total','page_available','virtual_total','virtual_available','extended')]


class IfRow(C.Structure):
    # MIB_IF_ROW2 from netioapi.h, including both octet counters and their native alignment.
    _fields_=[('luid',U64),('index',W.DWORD),('guid',C.c_byte*16),
        ('alias',W.WCHAR*257),('description',W.WCHAR*257),('address_length',W.DWORD),
        ('address',C.c_byte*32),('permanent_address',C.c_byte*32)]+[
        (name,W.DWORD) for name in ('mtu','type','tunnel','media','physical','access','direction')]+[
        ('flags',C.c_ubyte),('oper',W.DWORD),('admin',W.DWORD),('media_state',W.DWORD),
        ('net_guid',C.c_byte*16),('connection',W.DWORD)]+[(name,U64) for name in (
        'tx_speed','rx_speed','received','in_ucast','in_nucast','in_drop','in_errors','unknown',
        'in_uni_bytes','in_multi_bytes','in_broad_bytes','sent','out_ucast','out_nucast','out_drop',
        'out_errors','out_uni_bytes','out_multi_bytes','out_broad_bytes','out_queue')]


class IfTable(C.Structure):
    _fields_=[('count',W.DWORD),('rows',IfRow*1)]


class CounterValue(C.Structure):
    _fields_=[('status',W.DWORD),('number',C.c_double)]


class CounterItem(C.Structure):
    _fields_=[('name',W.LPWSTR),('value',CounterValue)]


COUNTERS={'cpu_cores':{'cores':r'\Processor Information(*)\% Processor Time'},
          'gpu':{'engines':r'\GPU Engine(*)\Utilization Percentage'},
          'disk_activity':{'disk_idle':r'\PhysicalDisk(*)\% Idle Time'}}
ENGINE_NAME=re.compile(r'(luid_(?:0x)?[0-9a-f]+_(?:0x)?[0-9a-f]+_phys_\d+_eng_\d+)(?:_|$)',re.I)


def ip_helper():
    lib = C.WinDLL('iphlpapi')
    lib.GetIfTable2.argtypes = [C.POINTER(C.POINTER(IfTable))]
    lib.FreeMibTable.argtypes = [C.c_void_p]
    lib.FreeMibTable.restype = None
    return lib


@contextmanager
def interface_rows(ip):
    table = C.POINTER(IfTable)()
    if ip.GetIfTable2(C.byref(table)) or not table:
        yield None
        return
    try:
        count = table.contents.count
        yield ((IfRow * count).from_address(C.addressof(table.contents) + IfTable.rows.offset)
               if count <= 65536 else None)
    finally:
        ip.FreeMibTable(table)


def network_key(row):
    guid = bytes(row.guid)
    return 'net:' + guid.hex() if any(guid) else ''


def selectable_interface(row):
    return row.type not in (24, 131) and not row.flags & 2  # Skip loopback, tunnel and NDIS filter layers.


def interfaces_as_devices(rows):
    from resource_devices import Device
    adapters = sorted((r for r in rows if selectable_interface(r) and (r.alias or r.description)),
                      key=lambda r: (not r.flags & 1, r.oper != 1, r.alias.casefold(), r.index))
    return {key: Device(r.alias or r.description, r.luid) for r in adapters if (key := network_key(r))}


def network_devices():
    with interface_rows(ip_helper()) as rows:
        return interfaces_as_devices(rows or ())


def scan_devices(metric):
    from resource_devices import disk_devices, display_devices, gpu_devices
    discover = {'gpu': gpu_devices, 'disk_activity': disk_devices,
                'network_utilization': network_devices, 'display': display_devices}
    try:
        return discover[metric]()
    except (OSError, AttributeError):
        return {}


class PerformanceCounters:
    def __init__(self,metrics):
        self.lib=C.WinDLL('pdh');self.query=W.HANDLE();self.handles={};self.warm=False;self.buffers={}
        lib=self.lib
        lib.PdhOpenQueryW.argtypes=[W.LPCWSTR,C.c_size_t,C.POINTER(W.HANDLE)]
        lib.PdhAddEnglishCounterW.argtypes=[W.HANDLE,W.LPCWSTR,C.c_size_t,C.POINTER(W.HANDLE)]
        lib.PdhCollectQueryData.argtypes=[W.HANDLE]
        lib.PdhGetFormattedCounterArrayW.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.DWORD),C.POINTER(W.DWORD),C.c_void_p]
        lib.PdhCloseQuery.argtypes=[W.HANDLE]
        if lib.PdhOpenQueryW(None,0,C.byref(self.query)):return
        for metric in metrics & COUNTERS.keys():
            for key,path in COUNTERS[metric].items():
                handle=W.HANDLE()
                if not lib.PdhAddEnglishCounterW(self.query,path,0,C.byref(handle)):
                    self.handles[key]=handle

    def read(self,key,group_engines=False):
        handle=self.handles.get(key)
        if not handle:return {}
        size=W.DWORD();count=W.DWORD()
        get=self.lib.PdhGetFormattedCounterArrayW
        for _ in range(2):
            result=get(handle,0x8200,C.byref(size),C.byref(count),None)&0xffffffff
            if result!=0x800007d2 or not 0<size.value<=16*1024*1024:return {}
            if not hasattr(self,'buffers'):self.buffers={}
            buf=self.buffers.get(key)
            if buf is None or len(buf)<size.value:
                buf = C.create_string_buffer((size.value+16383)//16384*16384)
                if len(buf) <= 256 * 1024:
                    self.buffers[key] = buf
                else:
                    self.buffers.pop(key, None)
            size.value=len(buf)
            result=get(handle,0x8200,C.byref(size),C.byref(count),buf)&0xffffffff
            if result==0:
                if count.value*C.sizeof(CounterItem)>len(buf):return {}
                items=C.cast(buf,C.POINTER(CounterItem))
                values={}
                # Walk the native array directly. GPU counters can contain many
                # per-process instances; retain only totals for physical engines.
                for index in range(count.value):
                    row=items[index]
                    if row.value.status not in (0,1):continue
                    name=row.name
                    if not name:continue
                    if group_engines:
                        match=ENGINE_NAME.search(name)
                        if match:
                            name=match.group(1).lower();values[name]=values.get(name,0)+max(0.,row.value.number)
                    else:values[name]=row.value.number
                return values
            if result!=0x800007d2:break
        return {}

    def collect(self):
        if not self.query or self.lib.PdhCollectQueryData(self.query):return False
        previous=self.warm;self.warm=True
        return previous

    def close(self):
        if self.query:self.lib.PdhCloseQuery(self.query);self.query=W.HANDLE()
        self.handles.clear()
        self.buffers.clear()


def busiest_engine(values):
    engines={}
    for name,usage in values.items():
        match=ENGINE_NAME.search(name)
        if match:
            key=match.group(1).lower();engines[key]=engines.get(key,0)+max(0.,usage)
    return min(100.,max(engines.values())) if engines else None


def gpu_loads(engines):
    """Find each adapter's busiest engine after summing per-process engine activity."""
    loads = {}
    for name, usage in engines.items():
        _, high, low, *_ = name.split('_')
        luid = (int(high, 16) << 32) | int(low, 16)
        if math.isfinite(usage):
            loads[luid] = min(100., max(loads.get(luid, 0.), usage))
    return loads


def network_rates(previous,current,elapsed):
    if previous is None or elapsed<=0:return None
    pairs=[(previous[k],v) for k,v in current.items() if k in previous
           and v[0]>=previous[k][0] and v[1]>=previous[k][1]]
    if not pairs:return None
    return tuple(sum(end[i]-start[i] for start,end in pairs)/elapsed for i in (0,1))


def link_speed(row):
    return max((v for v in (row.rx_speed,row.tx_speed) if 0<v<2**63),default=0)


def disk_loads(idle):
    loads = {}
    for name, value in idle.items():
        number = name.split(' ', 1)[0]
        if number.isascii() and number.isdecimal() and math.isfinite(value):
            index = int(number)
            loads[index] = max(loads.get(index, 0.), min(100., 100. - value))
    return loads


def busiest_disk(idle):
    return max(disk_loads(idle).values(), default=None)


def network_utilization(previous, current, elapsed):
    """Compare each direction with its own negotiated link rate. Links are full duplex."""
    if elapsed <= 0 or not previous:
        return None
    return max((value for key, ends in current.items() if key in previous
                and (value := link_utilization(previous[key], ends, elapsed)) is not None), default=None)


def link_utilization(starts, ends, elapsed):
    loads = ((after - before) * 800 / (elapsed * rate)
             for (before, old_rate), (after, rate) in zip(starts, ends)
             if rate == old_rate and 0 < rate < 2**63 and after >= before)
    peak = max(loads, default=None)
    return min(100., peak) if peak is not None else None


def network_device_readings(previous, current, elapsed):
    if not previous or elapsed <= 0:
        return {}
    readings = {}
    for key, ends in current.items():
        starts = previous.get(key)
        if starts is not None and all(end[0] >= start[0] for start, end in zip(starts, ends)):
            rates = tuple((end[0] - start[0]) / elapsed for start, end in zip(starts, ends))
            readings[key] = (rates, link_utilization(starts, ends, elapsed))
    return readings


class Sampler:
    def __init__(self,metrics,traffic_path=None):
        self.metrics=frozenset();self.last_cpu=None;self.last_net=None;self.net_time=0
        self.traffic_path=traffic_path;self.traffic=None
        self.kernel=C.WinDLL('kernel32');self.ip=None;self.ranking=None;self.pdh=None
        self.device_status=None;self.adapter=None
        self.network_device=''
        self.link_sample=None;self.network_load=None
        self.device_links=None;self.network_per_device={}
        self.inventory={};self.inventory_due={}
        self.configure(metrics)

    def configure(self,metrics):
        metrics=frozenset(metrics)
        if metrics==self.metrics:return
        added=metrics-self.metrics
        if 'rank' in added:
            from resource_processes import ProcessRanking
            self.ranking=ProcessRanking()
        elif 'rank' not in metrics:self.ranking=None
        if 'cpu' in added:self.kernel.GetSystemTimes.argtypes=[C.POINTER(W.FILETIME)]*3
        if 'cpu' not in metrics:self.last_cpu=None
        if 'memory' in added:self.kernel.GlobalMemoryStatusEx.argtypes=[C.POINTER(MemoryStatus)]
        if metrics & NET_KEYS and not self.ip:self.ip=ip_helper()
        if not metrics & NET_KEYS:self.ip=self.last_net=None;self.net_time=0
        if 'network_utilization' not in metrics:self.link_sample=self.network_load=None
        if 'network_devices' not in metrics:
            self.device_links=None;self.network_per_device={}
            self.inventory_due.pop('network_devices', None)
        for key in self.inventory.keys() - metrics:
            self.inventory.pop(key)
            self.inventory_due.pop(key)
        if metrics & DEVICE_KEYS and self.device_status is None:
            from device_status import DeviceStatus
            self.device_status=DeviceStatus(self.kernel)
        elif not metrics & DEVICE_KEYS:self.device_status=None
        if 'traffic' in added:
            from resource_traffic import TrafficLedger
            if self.traffic is None:self.traffic=TrafficLedger(self.traffic_path)
        elif 'traffic' not in metrics and self.traffic:self.traffic.pause()
        sources=metrics & COUNTERS.keys()
        if sources!=self.metrics & COUNTERS.keys():
            if self.pdh:self.pdh.close();self.pdh=None
            if sources:
                try:self.pdh=PerformanceCounters(sources)
                except (OSError,AttributeError):pass
        self.metrics=metrics

    def cpu(self):
        times=[W.FILETIME() for _ in range(3)]
        if not self.kernel.GetSystemTimes(*(C.byref(t) for t in times)):return None
        idle,kernel,user=[(x.dwHighDateTime<<32)|x.dwLowDateTime for x in times]
        total=kernel+user;old=self.last_cpu;self.last_cpu=(idle,total)
        if not old or total<=old[1]:return None
        return max(0.,min(100.,100.*(1-(idle-old[0])/(total-old[1]))))

    def memory(self):
        record=MemoryStatus();record.length=C.sizeof(record)
        if not self.kernel.GlobalMemoryStatusEx(C.byref(record)) or not record.total:return None
        return ((record.total-record.available)*100./record.total,record.total-record.available,record.total)

    def network(self,now,data):
        self.adapter=None
        self.network_load=None
        self.network_per_device={}
        with interface_rows(self.ip) as rows:
            if rows is None:
                self.last_net=self.link_sample=self.device_links=None
                if self.traffic:self.traffic.update_readings(None)
                return None
            eligible=[r for r in rows if r.oper==1 and selectable_interface(r)]
            rows_to_count=[r for r in eligible if r.flags&1] or eligible
            if 'network_links' in self.metrics:
                data['network_links']=self.device_status.active_links(eligible,now)
            readings={r.luid:(r.received,r.sent) for r in rows_to_count}
            if 'network_utilization' in self.metrics:
                links={r.luid:((r.received,r.rx_speed),(r.sent,r.tx_speed)) for r in rows_to_count}
                self.network_load=network_utilization(self.link_sample,links,now-self.net_time)
                self.link_sample=links
            if 'network_devices' in self.metrics:
                devices = {key: ((r.received,r.rx_speed),(r.sent,r.tx_speed)) for r in eligible if (key := network_key(r))}
                self.network_per_device = network_device_readings(self.device_links, devices, now-self.net_time)
                self.device_links = devices
                if now >= self.inventory_due.get('network_devices', 0):
                    data.setdefault('hardware_inventory', {})['network_utilization'] = interfaces_as_devices(rows)
                    self.inventory_due['network_devices'] = now + 15
            if 'system_status' in self.metrics or 'connection' in self.metrics:
                def adapter_priority(row):
                    previous=(self.last_net or {}).get(row.luid)
                    activity=max(0,row.received-previous[0])+max(0,row.sent-previous[1]) if previous else 0
                    return (-activity,-link_speed(row),row.index)
                if self.network_device:
                    primary=next((row for row in rows if network_key(row)==self.network_device),None)
                else:
                    primary=min(rows_to_count,key=adapter_priority,default=None)
                self.adapter=((bytes(primary.guid) if primary.oper==1 else None),primary.alias or primary.description,primary.type==71) if primary else (None,'',False)
        result=network_rates(self.last_net,readings,now-self.net_time)
        self.last_net,self.net_time=readings,now
        if 'traffic' in self.metrics:self.traffic.update_readings(readings)
        return result

    def map_devices(self, key, metric, readings, now, sample):
        if now >= self.inventory_due.get(key, 0):
            devices = scan_devices(metric)
            sample.setdefault('hardware_inventory', {})[metric] = devices
            self.inventory[key] = devices
            self.inventory_due[key] = now + 15
        values = {}
        for identifier, device in self.inventory[key].items():
            value = max((readings[n] for n in (device.number, *device.aliases) if n in readings), default=None)
            if value is not None:values[identifier] = value
        return values

    def sample(self,sample_rank=True):
        now=time.monotonic();data={'time':now}
        if 'cpu' in self.metrics:data['cpu']=self.cpu()
        if 'memory' in self.metrics:data['memory']=self.memory()
        if self.metrics & NET_KEYS:
            rates=self.network(now,data)
            if 'network' in self.metrics:data['network']=rates
            if 'network_utilization' in self.metrics:data['network_utilization']=self.network_load
            if 'network_devices' in self.metrics:data['network_devices']=self.network_per_device
            if 'traffic' in self.metrics:data['traffic']=self.traffic.snapshot()
        if self.device_status:
            full='system_status' in self.metrics
            status={}
            if full or 'battery' in self.metrics:
                status['battery']=self.device_status.battery()
            if full or 'volume' in self.metrics:
                status['volume']=self.device_status.volume()
            if 'microphone' in self.metrics:
                capture=self.device_status.volume(capture=True)
                status['microphone']=None if capture is None else not capture[1]
            if full or 'connection' in self.metrics:
                data['connection_device'] = self.network_device
                if self.adapter is None:
                    status['connection']=None
                else:
                    adapter,alias,wireless=self.adapter
                    name=self.device_status.connection_name(adapter,alias,now,wireless)
                    status['connection']=(alias,'未连接') if alias and adapter is None else name
            if full:data['system_status']=status
            data.update((key,value) for key,value in status.items() if key in self.metrics)
        ready=self.pdh and self.pdh.collect()
        if 'disk_activity' in self.metrics:
            loads=disk_loads(self.pdh.read('disk_idle')) if ready else {}
            data['disk_activity']=max(loads.values(),default=None)
            if 'disk_devices' in self.metrics:
                data['disk_devices']=self.map_devices('disk_devices','disk_activity',loads,now,data)
        if 'cpu_cores' in self.metrics:
            instances=self.pdh.read('cores') if ready else {}
            cores={tuple(map(int,name.split(','))):min(100.,max(0.,value))
                   for name,value in instances.items() if re.fullmatch(r'[0-9]+,[0-9]+',name)}
            data['cpu_cores']=[cores[index] for index in sorted(cores)]
        if 'gpu' in self.metrics:
            engines=self.pdh.read('engines',group_engines=True) if ready else {}
            data['gpu']=min(100.,max(engines.values())) if engines else None
            if 'gpu_devices' in self.metrics:
                data['gpu_devices']=self.map_devices('gpu_devices','gpu',gpu_loads(engines),now,data)
        if self.ranking and sample_rank:data['rank']=self.ranking.sample(now)
        return data

    def close(self):
        if self.pdh:self.pdh.close()
        if self.traffic:self.traffic.flush()
        self.ranking=None
