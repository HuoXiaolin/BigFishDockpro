"""Windows resource counters. Imported by the sampler only while metrics are requested."""
import ctypes as C
from ctypes import wintypes as W
import os
import re
import time

U64=C.c_ulonglong
NET_KEYS=frozenset(('network','traffic','system_status','connection'))
DEVICE_KEYS=frozenset(('system_status','battery','connection','volume'))


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
          'gpu':{'engines':r'\GPU Engine(*)\Utilization Percentage'}}
ENGINE_NAME=re.compile(r'(luid_[0-9a-fx]+_[0-9a-fx]+_phys_\d+_eng_\d+)(?:_|$)',re.I)


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


def network_rates(previous,current,elapsed):
    if previous is None or elapsed<=0:return None
    pairs=[(previous[k],v) for k,v in current.items() if k in previous
           and v[0]>=previous[k][0] and v[1]>=previous[k][1]]
    if not pairs:return None
    return tuple(sum(end[i]-start[i] for start,end in pairs)/elapsed for i in (0,1))


def link_speed(row):
    return max((v for v in (row.rx_speed,row.tx_speed) if 0<v<2**63),default=0)


class Sampler:
    def __init__(self,metrics,traffic_path=None):
        self.metrics=frozenset();self.last_cpu=None;self.last_net=None;self.net_time=0
        self.traffic_path=traffic_path;self.traffic=None
        self.kernel=C.WinDLL('kernel32');self.ip=None;self.ranking=None;self.pdh=None
        self.device_status=None;self.adapter=None
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
        if metrics & NET_KEYS and not self.ip:
            self.ip=C.WinDLL('iphlpapi')
            self.ip.GetIfTable2.argtypes=[C.POINTER(C.POINTER(IfTable))]
            self.ip.FreeMibTable.argtypes=[C.c_void_p];self.ip.FreeMibTable.restype=None
        if not metrics & NET_KEYS:self.ip=self.last_net=None;self.net_time=0
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

    def network(self,now):
        self.adapter=None
        table=C.POINTER(IfTable)()
        if self.ip.GetIfTable2(C.byref(table)) or not table:
            self.last_net=None
            if self.traffic:self.traffic.observe(None)
            return None
        try:
            count=table.contents.count
            if count>65536:return None
            rows=(IfRow*count).from_address(C.addressof(table.contents)+IfTable.rows.offset)
            eligible=[r for r in rows if r.oper==1 and r.type not in (24,131)]
            rows_to_count=[r for r in eligible if r.flags&1] or eligible
            readings={r.luid:(r.received,r.sent) for r in rows_to_count}
            if 'system_status' in self.metrics or 'connection' in self.metrics:
                def adapter_priority(row):
                    previous=(self.last_net or {}).get(row.luid)
                    activity=max(0,row.received-previous[0])+max(0,row.sent-previous[1]) if previous else 0
                    return (-activity,-link_speed(row),row.index)
                primary=min(rows_to_count,key=adapter_priority,default=None)
                self.adapter=(bytes(primary.guid),primary.alias or primary.description) if primary else (None,'')
        finally:self.ip.FreeMibTable(table)
        result=network_rates(self.last_net,readings,now-self.net_time)
        self.last_net,self.net_time=readings,now
        if 'traffic' in self.metrics:self.traffic.observe(readings)
        return result

    def sample(self,sample_rank=True):
        now=time.monotonic();data={'time':now}
        if 'cpu' in self.metrics:data['cpu']=self.cpu()
        if 'memory' in self.metrics:data['memory']=self.memory()
        if self.metrics & NET_KEYS:
            rates=self.network(now)
            if 'network' in self.metrics:data['network']=rates
            if 'traffic' in self.metrics:data['traffic']=self.traffic.snapshot()
        if self.device_status:
            full='system_status' in self.metrics
            status={}
            if full or 'battery' in self.metrics:
                status['battery']=self.device_status.battery()
            if full or 'volume' in self.metrics:
                status['volume']=self.device_status.volume()
            if full or 'connection' in self.metrics:
                status['connection']=self.device_status.connection_name(*self.adapter,now) if self.adapter is not None else None
            if full:data['system_status']=status
            data.update((key,value) for key,value in status.items() if key in self.metrics)
        ready=self.pdh and self.pdh.collect()
        if 'cpu_cores' in self.metrics:
            instances=self.pdh.read('cores') if ready else {}
            cores={tuple(map(int,name.split(','))):min(100.,max(0.,value))
                   for name,value in instances.items() if re.fullmatch(r'[0-9]+,[0-9]+',name)}
            data['cpu_cores']=[cores[index] for index in sorted(cores)]
        if 'gpu' in self.metrics:
            engines=self.pdh.read('engines',group_engines=True) if ready else {}
            data['gpu']=min(100.,max(engines.values())) if engines else None
        if self.ranking and sample_rank:data['rank']=self.ranking.sample(now)
        return data

    def close(self):
        if self.pdh:self.pdh.close()
        if self.traffic:self.traffic.flush()
        self.ranking=None
