"""Per-foreground-process application Present rate; no overlay injection or frame recording."""
import csv
import ctypes as C
from ctypes import wintypes as W
from collections import deque
import math
import os
import subprocess
import time
import uuid
from PyQt5.QtCore import QObject,QTimer,Qt,pyqtSignal
from background_worker import BackgroundWorker
from resource_probes import binary


def foreground():
    user=C.windll.user32;user.GetForegroundWindow.restype=W.HWND
    window=user.GetForegroundWindow()
    if not window:return 0
    pid=W.DWORD();user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    user.GetWindowThreadProcessId(window,C.byref(pid))
    if pid.value==os.getpid():return -1
    name=C.create_unicode_buffer(64);user.GetClassNameW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
    user.GetClassNameW(window,name,len(name))
    return 0 if name.value in ('WorkerW','Progman','Shell_TrayWnd','Shell_SecondaryTrayWnd') else pid.value


class TraceProperties(C.Structure):
    _fields_=[('wnode',C.c_byte*48)]+[(key,W.DWORD) for key in ('buffer','minb','maxb','file_size','mode','flush',
        'enable','age','buffers','free','events_lost','written','log_lost','realtime_lost')]+[
        ('thread',W.HANDLE),('file_offset',W.DWORD),('name_offset',W.DWORD)]


def stop_trace(name):
    # Stop only this run's private session, including after an interrupted child.
    size=C.sizeof(TraceProperties);buf=C.create_string_buffer(size+4096)
    C.cast(buf,C.POINTER(W.DWORD))[0]=len(buf)
    props=TraceProperties.from_buffer(buf);props.name_offset=size;props.file_offset=size+2048
    fn=C.windll.advapi32.ControlTraceW
    fn.argtypes=[C.c_uint64,W.LPCWSTR,C.c_void_p,W.DWORD];fn.restype=W.DWORD
    fn(0,name,buf,1)


class FrameRates:
    def __init__(self):
        self.chains={}
    def add(self,chain,interval,now):
        if not math.isfinite(interval) or not 0<interval<=5000:return
        if chain not in self.chains and len(self.chains)>=32:
            oldest=min(self.chains,key=lambda k:self.chains[k][-1][0]);del self.chains[oldest]
        queue=self.chains.setdefault(chain,deque(maxlen=512));queue.append((now,interval))
    def rate(self,now):
        valid=[]
        for chain in list(self.chains):
            queue=self.chains[chain]
            while queue and now-queue[0][0]>2.5:queue.popleft()
            if not queue:del self.chains[chain]
            elif len(queue)>=2:valid.append(queue)
        if not valid:return None
        main=max(valid,key=len)
        return len(main)*1000/sum(ms for _,ms in main)


class FrameSources:
    """Bound traces to recent swap chains, then select one renderer, never sum programs."""
    def __init__(self):
        self.streams={}

    def add(self,pid,name,chain,interval,now):
        if name.casefold() in ('presentmon.exe','bigfishdockpro.exe') or not math.isfinite(interval) or not 0<interval<=5000:return
        key=(pid,chain)
        if key not in self.streams:
            if len(self.streams)>=32:
                oldest=min(self.streams,key=lambda k:self.streams[k][1][-1][0])
                del self.streams[oldest]
            self.streams[key]=(name,deque(maxlen=180))
        self.streams[key][1].append((now,interval))

    def pick(self,pid,now):
        candidates=[]
        for key,(name,frames) in list(self.streams.items()):
            while frames and now-frames[0][0]>2.5:frames.popleft()
            if not frames:
                del self.streams[key];continue
            if len(frames)<2 or now-frames[-1][0]>1.5:continue
            fps=len(frames)*1000/sum(delta for _,delta in frames)
            desktop=name.casefold()=='dwm.exe'
            priority=3 if key[0]==pid else 2 if pid<=0 and desktop else 0 if desktop else 1
            candidates.append((priority,len(frames),fps,name,desktop))
        if not candidates:return (None,'等待画面更新',now)
        priority,count,fps,name,desktop=max(candidates)
        source='桌面合成 · DWM' if desktop else ('前台 · ' if priority==3 else '活动渲染 · ')+name
        return fps,source,now


class Capture(BackgroundWorker):
    updated=pyqtSignal(object)
    def __init__(self,pid):
        super().__init__();self.pid=pid;self.session='BigFishDockpro-'+str(os.getpid())+'-'+uuid.uuid4().hex[:12]
    def run(self):
        process=None
        try:
            # DWM and composed windows need display tracking to produce frame rows.
            args=[str(binary('PresentMon.exe')),'--session_name',self.session,
                  '--v1_metrics','--output_stdout','--no_console_stats','--no_track_gpu',
                  '--no_track_input']
            if self.pid:args+=['--process_id',str(self.pid),'--terminate_on_proc_exit']
            process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,
                                     creationflags=subprocess.DETACHED_PROCESS)
            self.own_process(process);sources=FrameSources();header=None;last=0
            for raw in process.stdout:
                if self.cancelled.is_set():break
                row=next(csv.reader([raw.decode('utf-8-sig',errors='replace')]),[])
                if row and row[0].casefold()=='application':
                    columns={name.strip().casefold():i for i,name in enumerate(row)}
                    required=('processid','swapchainaddress','msbetweenpresents','application')
                    header=columns if all(key in columns for key in required) else None
                    continue
                if header is None:continue
                try:
                    pid=int(row[header['processid']])
                    if self.pid and pid!=self.pid:continue
                    now=time.monotonic()
                    sources.add(pid,row[header['application']],row[header['swapchainaddress']],float(row[header['msbetweenpresents']]),now)
                    if now-last>=.5:
                        self.updated.emit(sources.pick(self.pid or foreground(),now));last=now
                except (ValueError,IndexError):continue
            code=process.wait(timeout=2)
            if code and not self.cancelled.is_set():self.updated.emit((None,'采集未就绪，请检查性能跟踪权限',time.monotonic()))
        except (OSError,subprocess.TimeoutExpired):
            if not self.cancelled.is_set():self.updated.emit((None,'当前无法启动帧率采集',time.monotonic()))
        finally:
            if process:
                if process.poll() is None:process.kill()
                process.stdout.close();self.release_process(process)
            stop_trace(self.session)


class FrameMonitor(QObject):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.job=None;self.closed=False;self.retry_at=0
        self.value=None;self.name='等待画面更新';self.at=0
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.tick)
        if not owner.runtime.dock.preview:self.timer.start();self.tick()

    def tick(self):
        now=time.monotonic()
        if self.job is None and now>=self.retry_at:
            self.job=Capture(0);self.job.updated.connect(self.update_value,Qt.QueuedConnection)
            self.job.finished.connect(self.finished,Qt.QueuedConnection);self.job.start()
        if self.value is not None and now-self.at>3:
            self.value=None;self.name='等待画面更新';self.owner.display()

    def update_value(self,info):
        if not self.closed and self.sender() is self.job:
            self.value,self.name,self.at=info;self.owner.display()

    def finished(self):
        job=self.sender()
        if job is not self.job:return
        self.job=None;job.deleteLater();self.retry_at=time.monotonic()+30

    def close(self):
        self.closed=True;self.timer.stop()
        if self.job:
            job=self.job;job.requestInterruption();job.deleteLater()
            stop_trace(job.session)
        self.job=None;self.deleteLater()
