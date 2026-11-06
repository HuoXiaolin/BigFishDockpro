"""Read per-PID CPU times, parent IDs and private resident bytes in one Windows snapshot."""
from collections import namedtuple
import ctypes as C
from ctypes import wintypes as W
from heapq import nlargest
import os
import sys

Process = namedtuple('Process','pid parent born name ticks memory')
OWNED_IMAGES = {'bigfishdockpro','desktopresourceprobe','presentmon','translucenttb'}


class UnicodeName(C.Structure):
    _fields_ = [('length',W.USHORT),('maximum',W.USHORT),('address',C.c_void_p)]


class ProcessHeader(C.Structure):
    # SYSTEM_PROCESS_INFORMATION prefix, including the aligned UNICODE_STRING on x64.
    _fields_ = [('next',W.ULONG),('threads',W.ULONG),('private_ws',C.c_int64),
                ('faults',W.ULONG),('peak_threads',W.ULONG),('cycles',C.c_uint64),
                ('created',C.c_int64),('user',C.c_int64),('kernel',C.c_int64),
                ('image',UnicodeName),('priority',W.LONG),('pid',C.c_size_t),('parent',C.c_size_t)]


def executable_path(pid):
    kernel=C.windll.kernel32
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
    kernel.CloseHandle.argtypes=[W.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return ''
    try:
        length=W.DWORD(2048);path=C.create_unicode_buffer(length.value)
        return path.value if kernel.QueryFullProcessImageNameW(handle,0,path,C.byref(length)) else ''
    finally:kernel.CloseHandle(handle)


def group_members(records,main_pid,launcher):
    main=records.get(main_pid)
    if not main:return set()
    members={main_pid}
    parent=records.get(main.parent)
    if launcher and parent and parent.pid==launcher and parent.name.casefold()==main.name.casefold() and parent.born<=main.born:
        members.add(parent.pid)
    for row in records.values():
        if row.name.casefold() not in OWNED_IMAGES:continue
        item=row
        for _ in range(8):
            if item.pid in members:
                members.add(row.pid)
                break
            parent=records.get(item.parent)
            if not parent or parent.born>item.born or parent.name.casefold() not in OWNED_IMAGES:break
            item=parent
    return members


class ProcessRanking:
    def __init__(self):
        self.read=C.windll.ntdll.NtQuerySystemInformation
        self.read.argtypes=[W.ULONG,C.c_void_p,W.ULONG,C.POINTER(W.ULONG)];self.read.restype=W.LONG
        self.previous={};self.at=0.;self.capacity=256*1024;self.icons={}
        self.main=os.getpid() if getattr(sys,'frozen',False) else 0
        self.launcher=0
        if self.main and os.path.normcase(executable_path(os.getppid()))==os.path.normcase(sys.executable):self.launcher=os.getppid()

    def snapshot(self):
        size=self.capacity
        while size<=32*1024*1024:
            block=C.create_string_buffer(size);used=W.ULONG()
            status=self.read(5,block,size,C.byref(used)) & 0xffffffff
            if status==0:break
            if status not in (0xc0000004,0xc0000023):return {}
            size=max(size*2,used.value+65536)
        else:return {}
        length=min(used.value,size)
        self.capacity=max(65536,length+65536)
        start=C.addressof(block);offset=0;rows={};prefix=C.sizeof(ProcessHeader)
        while offset+prefix<=length:
            row=ProcessHeader.from_buffer(block,offset)
            addr=row.image.address;n=row.image.length
            if row.pid and addr and not n%2 and start<=addr and addr+n<=start+length:
                name=C.wstring_at(addr,n//2)
                if name.casefold().endswith('.exe'):name=name[:-4]
                rows[row.pid]=Process(row.pid,row.parent,row.created,name,row.user+row.kernel,max(0,row.private_ws))
            if row.next<prefix:break
            offset+=row.next
        return rows

    def sample(self,now):
        records=self.snapshot()
        if not records:return None
        divisor=(now-self.at)*100000*(os.cpu_count() or 1)
        members=group_members(records,self.main,self.launcher)
        entries=[];detail=[]
        for row in records.values():
            old=self.previous.get(row.pid)
            cpu=min(100.,(row.ticks-old[1])/divisor) if old and old[0]==row.born and row.ticks>=old[1] and divisor>0 else None
            entry=(row.name,row.pid,cpu,row.memory)
            if row.pid in members:detail.append(entry)
            else:entries.append(entry)
        self.previous={r.pid:(r.born,r.ticks) for r in records.values()};self.at=now
        if detail:
            rates=[r[2] for r in detail if r[2] is not None]
            title='大肥鱼Dock' if len(detail)==1 else f'大肥鱼Dock ({len(detail)})'
            entries.append((title,self.main,min(100.,sum(rates)) if rates else None,sum(r[3] for r in detail)))
        groups={key:nlargest(5,(r for r in entries if r[col] is not None),key=lambda r:r[col])
                for key,col in [('cpu',2),('memory',3)]}
        visible={r[1] for rows in groups.values() for r in rows}
        icons={}
        for pid in visible:
            key=(pid,records[pid].born)
            icons[key]=self.icons[key] if key in self.icons else executable_path(pid)
        self.icons=icons
        groups['paths']={pid:path for (pid,_),path in icons.items() if path}
        groups['members']={self.main:sorted(detail,key=lambda r:r[3],reverse=True)} if detail else {}
        return groups
