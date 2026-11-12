"""Dock into verified free space. Explorer remains the owner of the actual taskbar."""
import ctypes as C
from ctypes import wintypes as W
import json
import time
from PyQt5.QtCore import QObject,QTimer,QProcess,Qt,QRect,QPoint,pyqtSignal
from PyQt5.QtWidgets import QApplication
from platform_services import fullscreen_window, same_monitor
from resource_probes import binary


def free_slot(rect,blocks,ratio,wanted=288,minimum=82):
    vertical=rect.height()>rect.width()
    span=rect.height() if vertical else rect.width()
    thick=rect.width() if vertical else rect.height()
    if thick<14 or span<minimum:return None
    start=rect.top() if vertical else rect.left()
    intervals=[]
    for block in blocks:
        inter=rect.intersected(block)
        if inter.isEmpty():continue
        lo=(inter.top() if vertical else inter.left())-start-4
        hi=(inter.bottom() if vertical else inter.right())-start+5
        intervals.append((max(0,lo),min(span,hi)))
    gaps=[];left=4
    for lo,hi in sorted(intervals)+[(span-4,span)]:
        if lo-left>=minimum:gaps.append((left,lo))
        left=max(left,hi)
    center=ratio*span;candidates=[]
    for lo,hi in gaps:
        width=min(wanted,hi-lo);x=max(lo,min(round(center-width/2),hi-width))
        candidates.append((abs(x+width/2-center),x,width))
    if not candidates:return None
    _,offset,width=min(candidates)
    return QRect(rect.x()+2,rect.y()+offset,rect.width()-4,width) if vertical else QRect(rect.x()+offset,rect.y()+2,width,rect.height()-4)


class MonitorInfo(C.Structure):
    _fields_=[('size',W.DWORD),('monitor',W.RECT),('work',W.RECT),('flags',W.DWORD),('device',W.WCHAR*32)]


def taskbars():
    user=C.windll.user32
    user.FindWindowW.argtypes=[W.LPCWSTR,W.LPCWSTR];user.FindWindowW.restype=W.HWND
    user.FindWindowExW.argtypes=[W.HWND,W.HWND,W.LPCWSTR,W.LPCWSTR];user.FindWindowExW.restype=W.HWND
    user.MonitorFromWindow.argtypes=[W.HWND,W.DWORD];user.MonitorFromWindow.restype=W.HANDLE
    user.GetMonitorInfoW.argtypes=[W.HANDLE,C.c_void_p];user.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
    user.IsWindowVisible.argtypes=[W.HWND]
    screens=QApplication.screens();handles=[user.FindWindowW('Shell_TrayWnd',None)]
    previous=0
    for _ in range(len(screens)+1):
        previous=user.FindWindowExW(None,previous,'Shell_SecondaryTrayWnd',None)
        if not previous:break
        handles.append(previous)
    result=[]
    for hwnd in handles:
        if not hwnd or not user.IsWindowVisible(hwnd):continue
        info=MonitorInfo();info.size=C.sizeof(info);native=W.RECT()
        if not user.GetMonitorInfoW(user.MonitorFromWindow(hwnd,2),C.byref(info)) or not user.GetWindowRect(hwnd,C.byref(native)):continue
        screen=next((s for s in screens if s.name().casefold()==info.device.casefold()),None)
        if screen is None:continue
        base=screen.geometry();m=info.monitor
        mapping=(m.left,m.top,base.x(),base.y(),base.width()/max(1,m.right-m.left),base.height()/max(1,m.bottom-m.top))
        rect=logical([native.left,native.top,native.right,native.bottom],mapping).intersected(base)
        if min(rect.width(),rect.height())<14:continue
        result.append(dict(hwnd=int(hwnd),screen=screen.name(),rect=rect,map=mapping))
    return result


def logical(bounds,mapping):
    ox,oy,x,y,sx,sy=mapping;l,t,r,b=bounds
    return QRect(round(x+(l-ox)*sx),round(y+(t-oy)*sy),round((r-l)*sx),round((b-t)*sy))


class Placement(QObject):
    layout_changed=pyqtSignal()
    def __init__(self,window,*,capsule=False):
        super().__init__(window);self.window=window;self.slot=None;self.slot_bar=None;self.target=None;self.proposal=False
        self.capsule=capsule
        self.key='resource_capsule_taskbar' if capsule else 'resource_taskbar'
        self.layer_key='resource_layer' if capsule else 'resource_taskbar_layer'
        self.closed=False;self.process=None;self.waiting=None;self.checked=False;self.retry_at=0.;self.hook=None;self.callback=None;self.deferred=None
        self.request=None
        self.shell_missing=False;self.fullscreen=False
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(600)
        self.debounce.timeout.connect(self.check);self.layout_changed.connect(self.schedule_check,Qt.QueuedConnection)
        self.shell_timer=QTimer(self);self.shell_timer.setInterval(2500);self.shell_timer.timeout.connect(self.shell_changed)
    def offer(self,bar,point):
        axis=(point.y()-bar['rect'].y())/bar['rect'].height() if bar['rect'].height()>bar['rect'].width() else (point.x()-bar['rect'].x())/bar['rect'].width()
        if not self.proposal:
            self.previous=(self.target,self.slot,self.slot_bar,self.configured_ratio(),self.checked,
                           self.shell_missing,self.fullscreen)
        self.deferred=None
        self.proposal=True;self.target=bar;self.ratio=max(0.,min(1.,axis))
        self.query(bar,self.ratio)
    @property
    def anchor(self):
        return self.window.service.cfg[self.key+'_anchor']
    @property
    def layer(self):
        return self.window.service.cfg[self.layer_key]
    def configured_ratio(self):
        position=self.window.service.cfg[self.key+'_position']
        return self.anchor.get('ratio',.5) if position=='custom' else {'left':0.,'center':.5,'right':1.}[position]
    def restore(self):
        if self.closed or self.proposal:return
        anchor=self.anchor
        previous=getattr(self,'ratio',None);self.ratio=self.configured_ratio()
        bars=self.bars()
        current=next((r for r in bars if r['screen']==anchor.get('screen')),bars[0] if bars else None)
        self.shell_missing=current is None
        self.fullscreen=bool(current and same_monitor(fullscreen_window(),current['hwnd']))
        if current and (not self.target or current!=self.target or not self.checked or previous!=self.ratio):
            self.target=current;self.query(current,self.ratio)
        if not self.shell_timer.isActive():self.shell_timer.start()
    def bars(self):
        return [] if self.window.service.runtime.dock.preview else taskbars()
    def suppressed(self):
        if self.layer=='bottom':
            return self.shell_missing or self.fullscreen
        if self.shell_missing and self.slot_bar and self.slot:
            return not any(s.name()==self.slot_bar['screen'] and s.geometry().contains(self.slot)
                           for s in QApplication.screens())
        return False
    def shell_changed(self):
        if self.closed or self.proposal:return
        hidden=self.suppressed()
        anchor=self.anchor
        bars=self.bars()
        screen=anchor.get('screen') or (self.slot_bar or {}).get('screen')
        bar=next((b for b in bars if b['screen']==screen),None)
        if bar is None:
            # A fullscreen app can slide its taskbar offscreen. Keep the top
            # readout in the last checked slot on that display while it returns.
            retain=(self.layer=='top' and self.slot_bar
                    and self.slot_bar['screen']==screen and any(s.name()==screen for s in QApplication.screens()))
            if not retain:bar=bars[0] if bars else None
        cover=fullscreen_window()
        self.shell_missing=bar is None
        self.fullscreen=bool(bar and same_monitor(cover,bar['hwnd']))
        if hidden!=self.suppressed():
            self.window.placement_changed()
            if self.closed:return
        if bar and not self.suppressed() and (self.target!=bar or not self.checked or (self.slot is None and time.monotonic()>=self.retry_at)):
            changed = self.target != bar
            self.target=bar;self.query(bar,self.ratio)
            if changed:self.window.reposition()
        self.window.restore_input_layer(cover)
    def schedule_check(self):
        if not self.closed:
            self.window.restore_input_layer()
            if not self.debounce.isActive():self.debounce.start()
    def check(self):
        if self.target and not self.proposal and not self.shell_missing and not self.suppressed():self.query(self.target,self.ratio)
    def query(self,bar,ratio):
        from probe_lifecycle import allowed, start as start_probe
        if self.closed or not allowed():return
        request=(bar,ratio)
        if self.process is not None:
            self.waiting=request if request != self.request else None
            return
        self.request=request
        process=QProcess(self);self.process=process
        deadline=QTimer(process);deadline.setSingleShot(True);deadline.setInterval(4000);deadline.timeout.connect(process.kill)
        def finish(ok):
            if process is not self.process:return
            self.process=None;deadline.stop()
            try:
                raw=bytes(process.readAllStandardOutput())
                data=json.loads(raw.decode('utf-8-sig')) if ok and len(raw)<131072 else None
            except (TypeError,ValueError):data=None
            process.deleteLater()
            if self.closed or not allowed():return
            if self.waiting is not None:
                latest=self.waiting;self.waiting=None;self.query(*latest);return
            if self.target!=bar:return
            self.accept_probe(bar,ratio,data)
        process.errorOccurred.connect(lambda error:finish(False) if error==QProcess.FailedToStart else None)
        process.finished.connect(lambda code,status:finish(code==0 and status==QProcess.NormalExit))
        deadline.start()
        if not start_probe(process,binary('DesktopResourceProbe.exe'),['--taskbar',str(bar['hwnd'])]):
            self.process=None;deadline.stop();process.deleteLater()
    def accept_probe(self, bar, ratio, data):
        try:
            if not isinstance(data, dict) or data.get('ok') is not True:
                raise ValueError('Taskbar controls unavailable')
            blocks = [logical(bounds, bar['map']) for bounds in data['blocks']]
        except (KeyError, TypeError, ValueError, OverflowError):
            if self.proposal:
                self.accept(bar, ratio, None)
            else:
                # A missed UI Automation read does not invalidate a slot on the same taskbar.
                self.checked = False
            return
        service=self.window.service
        if self.capsule:
            peer=getattr(getattr(service,'strip',None),'placement',None)
        else:
            peer=getattr(getattr(service,'window',None),'taskbar_placement',None)
        if peer and peer.slot is not None and peer.slot_bar==bar:
            blocks.append(peer.slot)
        wanted = self.window.taskbar_width(bar) if self.capsule else self.window.preferred_width()
        self.accept(bar, ratio, free_slot(bar['rect'], blocks, ratio, wanted, min(82, wanted)))
    def accept(self,bar,ratio,slot):
        if self.window.press is not None:
            self.deferred=(bar,ratio,slot);return
        proposal=self.proposal;self.proposal=False;self.slot=slot;self.slot_bar=bar if slot is not None else None
        self.checked=True
        if proposal and slot is not None:
            self.shell_missing=False;self.fullscreen=bool(same_monitor(fullscreen_window(),bar['hwnd']))
            # Only the capsule can be dragged. Its placement is independent of the readout.
            if not self.window.service.set_options(resource_capsule_taskbar=True,resource_collapsed=True,
                    resource_capsule_taskbar_position='custom',resource_capsule_taskbar_anchor={'screen':bar['screen'],'ratio':ratio}):
                self.slot=None
        if self.closed:return
        if proposal and self.slot is None:
            self.target,self.slot,self.slot_bar,self.ratio,self.checked,self.shell_missing,self.fullscreen=self.previous
            self.window.placement_changed();return
        self.retry_at=time.monotonic()+20
        self.watch(bar['hwnd'])
        if not self.shell_timer.isActive():self.shell_timer.start()
        self.window.placement_changed()
    def resume(self):
        pending,self.deferred=self.deferred,None
        if pending and not self.closed and pending[:2]==(self.target,self.ratio):self.accept(*pending)
    def watch(self,hwnd):
        if self.window.service.runtime.dock.preview:return
        if self.hook and self.hooked==hwnd:return
        self.unwatch();self.hooked=hwnd
        user=C.windll.user32;pid=W.DWORD()
        user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)];user.GetWindowThreadProcessId(hwnd,C.byref(pid))
        proto=C.WINFUNCTYPE(None,W.HANDLE,W.DWORD,W.HWND,W.LONG,W.LONG,W.DWORD,W.DWORD)
        user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
        def changed(hook,event,win,obj,child,thread,stamp):
            if not self.closed and win and event in (0x8000,0x8001,0x8002,0x8003,0x8004,0x800b) and user.GetAncestor(win,2)==hwnd:
                self.layout_changed.emit()
        self.callback=proto(changed)
        user.SetWinEventHook.argtypes=[W.DWORD,W.DWORD,W.HMODULE,proto,W.DWORD,W.DWORD,W.DWORD];user.SetWinEventHook.restype=W.HANDLE
        if pid.value:self.hook=user.SetWinEventHook(0x8000,0x800b,None,self.callback,pid.value,0,2)
    def unwatch(self):
        if self.hook:
            user=C.windll.user32;user.UnhookWinEvent.argtypes=[W.HANDLE];user.UnhookWinEvent(self.hook)
        self.hook=None;self.callback=None
    def close(self):
        self.closed=True;self.unwatch();self.debounce.stop();self.shell_timer.stop();self.waiting=None
        process,self.process=self.process,None
        if process:
            if process.state()!=QProcess.NotRunning:
                process.setParent(QApplication.instance());process.finished.connect(process.deleteLater);process.kill()
            else:process.deleteLater()
        self.deleteLater()
