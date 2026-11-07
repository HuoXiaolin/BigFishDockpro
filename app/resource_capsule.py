"""Demand-driven GPU/CPU sampling, Bluetooth sharing, window and settings ownership."""
from collections import deque
import time
import threading
from PyQt5.QtCore import QObject,pyqtSignal,Qt
from background_worker import BackgroundWorker


class MonitorJob(BackgroundWorker):
    sample_ready=pyqtSignal(object)
    def __init__(self,keys,seconds,traffic_path=None):
        super().__init__()
        self.traffic_path=traffic_path
        self.signature=(frozenset(keys),seconds)
        self.lock=threading.Lock();self.wake=threading.Event()

    def reconfigure(self,signature):
        with self.lock:self.signature=signature;self.wake.set()

    def requestInterruption(self):
        super().requestInterruption();self.wake.set()

    def run(self):
        from resource_metrics import Sampler
        reader=None
        try:
            reader=Sampler(set(),self.traffic_path)
            while not self.cancelled.is_set():
                with self.lock:
                    self.wake.clear();keys,interval=self.signature
                reader.configure(keys)
                value=reader.sample()
                if not self.cancelled.is_set():self.sample_ready.emit(value)
                self.wake.wait(interval)
        except (OSError,ValueError,AttributeError):
            if not self.cancelled.is_set():self.sample_ready.emit({'time':time.monotonic(),'error':True})
        finally:
            if reader:reader.close()


class ResourceCapsule(QObject):
    def __init__(self,runtime):
        super().__init__(runtime.dock)
        self.runtime=runtime;self.window=self.strip=self.job=self.bluetooth=None
        self.history=None;self.latest={};self.observed={};self.signature=None;self.closed=False
        self.sensors=self.fps=None;self.auto_compact=None;self.deck=None;self.ai_tray=None
        self.extras=None
        self.main_settings = False
        self.settings_depth = 0
        self.preview_detail = False

    @property
    def cfg(self):return self.runtime.dock.cfg

    @property
    def compact(self):
        if self.editing and not self.preview_detail:
            return True
        return self.cfg['resource_collapsed'] if self.auto_compact is None else self.auto_compact

    @property
    def editing(self):
        return self.main_settings or self.settings_depth > 0

    def set_main_settings(self, open_):
        if self.main_settings == open_:
            return
        self.main_settings = open_
        self.settings_focus_changed()

    def settings_focus_changed(self):
        if not self.editing:
            self.preview_detail = False
        self.sync()
        if self.editing and self.window is not None:
            self.window.release_inactive_views()

    def set_options(self,**changes):
        from settings_effects import save_changes
        old=self.auto_compact
        if 'resource_collapsed' in changes or 'resource_auto_hide' in changes:self.auto_compact=None
        ok=save_changes(self.runtime.tray,self.runtime.api,changes)
        if not ok:self.auto_compact=old
        elif old is not None and self.auto_compact is None:self.sync()
        return ok

    def open(self):
        if self.runtime.game_active:return
        self.preview_detail = self.editing
        self.set_options(resource_enabled=True,resource_collapsed=False)
        if self.window:
            self.window.sync_window()
            self.window.raise_if_top()

    def fold(self,compact,automatic=False):
        if self.editing and not compact and not self.preview_detail:
            if automatic:
                return True
            self.preview_detail = True
            if self.cfg['resource_collapsed'] is False:
                self.auto_compact = None
                self.sync()
                return True
        if automatic:
            if self.compact!=bool(compact):
                self.auto_compact=bool(compact);self.sync()
            return True
        return self.set_options(resource_collapsed=bool(compact))
    def settings(self):
        from contextlib import nullcontext
        from resource_panel import ResourceOptions
        from ui_style import exec_dialog
        main = getattr(self.runtime.tray, 'settings_dialog', None)
        scope = main.suspend_page() if main is not None and main.isVisible() else nullcontext()
        self.settings_depth += 1
        self.settings_focus_changed()
        try:
            with scope:
                exec_dialog(ResourceOptions(self))
        finally:
            self.settings_depth -= 1
            self.settings_focus_changed()

    def needs(self):
        if self.closed or self.runtime.game_active:return set()
        desktop=set()
        if self.window and self.window.isVisible() and not (self.compact and self.cfg['resource_fold']=='ball'):
            from resource_options import METRICS
            desktop={k for k in METRICS if self.cfg['resource_'+k]}
            if self.compact:desktop.intersection_update(self.cfg['resource_compact_metrics'])
            elif self.window.page_key=='resources':
                if 'cpu' in desktop:desktop.add('cpu_cores')
            else:desktop.discard('rank')
        if self.window and self.window.isVisible() and self.cfg['resource_traffic']:desktop.add('traffic')
        if self.strip and self.strip.isVisible():desktop.update(self.cfg['resource_task_metrics'])
        return desktop

    def active_keys(self):
        return self.needs() & {'cpu','cpu_cores','gpu','memory','network','rank','traffic'}

    def make_strip(self):
        if self.strip is None:
            from taskbar_readout import TaskbarReadout
            self.strip=TaskbarReadout(self)
        return self.strip

    def offer_taskbar(self,bar,point):
        self.make_strip().placement.offer(bar,point)

    def return_from_taskbar(self,point):
        changes={'resource_taskbar':False,'resource_enabled':True}
        if point is not None:
            from screen_layout import screen_records,capture
            from PyQt5.QtCore import QRect
            from PyQt5.QtWidgets import QApplication
            display=QApplication.screenAt(point) or QApplication.primaryScreen()
            area=display.availableGeometry()
            rect=self.window.desktop_rect() if self.window else QRect(0,0,min(680,area.width()),min(220,area.height()))
            rect.moveLeft(max(area.left(),min(point.x()-rect.width()//2,area.right()-rect.width()+1)))
            rect.moveTop(max(area.top(),min(point.y()-15,area.bottom()-rect.height()+1)))
            changes['resource_layout']=capture(list(rect.getRect()),screen_records())
        self.set_options(**changes)

    def sync(self):
        if self.closed:return
        visible=self.cfg['resource_enabled'] and not self.runtime.game_active
        if not visible:self.auto_compact=None
        if visible:
            if self.window is None:
                from resource_panel import ResourceWindow
                self.window=ResourceWindow(self)
            self.window.sync_window()
        elif self.window is not None:
            window,self.window=self.window,None;window.dispose()
        if visible and self.cfg['resource_weather']:
            if self.extras is None:
                from resource_extras import ResourceExtras
                self.extras=ResourceExtras(self)
            self.extras.sync()
        elif self.extras:self.extras.close();self.extras=None
        if self.cfg['resource_taskbar'] and (self.cfg['resource_task_metrics'] or self.cfg['resource_task_music']) and not self.runtime.game_active:
            fresh=self.strip is None
            strip=self.make_strip()
            if fresh or getattr(strip.placement,'ratio',None)!=strip.placement.configured_ratio():strip.placement.restore()
            strip.reposition();strip.sync_style()
        elif self.strip and (self.runtime.game_active or not self.strip.placement.proposal):
            strip,self.strip=self.strip,None;strip.dispose()
        demand=self.needs()
        want_tray=self.cfg['resource_ai_tray'] and not self.runtime.game_active
        want_music=bool(self.strip and self.strip.music_requested())
        want_deck=visible and (self.cfg['resource_ai'] or self.cfg['resource_music']) or want_tray or want_music
        if want_deck:
            if self.deck is None:
                from resource_deck import DeckBridge
                self.deck=DeckBridge(self)
            self.deck.configure()
        elif self.deck:self.deck.close();self.deck=None
        if want_tray and self.ai_tray is None:
            from resource_ai_tray import AiTray
            self.ai_tray=AiTray(self)
        elif not want_tray and self.ai_tray:self.ai_tray.close();self.ai_tray=None
        bt_visible='bluetooth' in demand
        use_bt=bt_visible or self.cfg['resource_bt_tray']
        if use_bt and self.bluetooth is None:
            from bluetooth_gauge import BluetoothGauge
            self.bluetooth=BluetoothGauge(self);self.bluetooth.set_tray(self.cfg['resource_bt_tray']);self.bluetooth.refresh()
        elif use_bt:
            self.bluetooth.set_tray(self.cfg['resource_bt_tray'])
        elif self.bluetooth is not None:
            bt,self.bluetooth=self.bluetooth,None;bt.close()
        from resource_options import SENSOR_UNITS
        sensors=frozenset(demand & SENSOR_UNITS.keys())
        if self.sensors and self.sensors.keys!=sensors:
            self.sensors.close();self.sensors=None
        if sensors and not self.sensors:
            from resource_probes import SensorRead
            self.sensors=SensorRead(self,sensors)
        want_fps='fps' in demand
        if want_fps and not self.fps:
            from resource_fps import FrameMonitor
            self.fps=FrameMonitor(self)
        elif not want_fps and self.fps:
            self.fps.close();self.fps=None
        keys=self.active_keys()
        interval=max(self.cfg['resource_interval'],5 if self.runtime.lite else 2 if self.compact else 1)
        signature=(frozenset(keys),interval) if keys else None
        if signature!=self.signature:
            self.signature=signature
            now=time.monotonic()
            # A quick fold may suspend detailed counters. Keep their last small snapshot
            # only while this visible desktop component still has the metric enabled.
            keep=set(keys)
            if self.window and self.window.isVisible():
                keep.update(k for k in self.latest if self.cfg.get('resource_'+('cpu' if k=='cpu_cores' else k)) and
                            now-self.observed.get(k,float('-inf'))<=max(4,2*interval+1))
            self.latest={k:v for k,v in self.latest.items() if k in keep and
                         now-self.observed.get(k,float('-inf'))<=max(4,2*interval+1)}
            if signature is None:self.history=None
            elif self.history is None:self.history=deque(maxlen=65)
            else:
                self.history=deque(({k:v for k,v in row.items() if k=='time' or k in keys} for row in self.history),maxlen=65)
            self.observed={k:v for k,v in self.observed.items() if k in self.latest}
            if self.job and signature and not self.job.cancelled.is_set():self.job.reconfigure(signature)
            elif self.job:self.job.requestInterruption()
            else:self.start_job()
        self.display()

    def start_job(self):
        if self.closed or not self.signature or self.runtime.dock.preview:return
        from pathlib import Path
        self.job=MonitorJob(*self.signature,traffic_path=Path(self.runtime.api.CONFIG_DIR)/'network-traffic.json')
        self.job.sample_ready.connect(self.receive,Qt.QueuedConnection)
        self.job.finished.connect(self.job_finished,Qt.QueuedConnection);self.job.start()

    def job_finished(self):
        job=self.sender()
        if job is not self.job:return
        self.job=None;job.deleteLater()
        if job.cancelled.is_set():self.start_job()

    def receive(self,data):
        if self.sender() is not self.job or not self.job or self.job.cancelled.is_set():return
        self.accept_sample(data)

    def accept_sample(self,data):
        if not self.signature or self.history is None:return
        keys,interval=self.signature
        now=data['time']
        for key in keys:
            value=data.get(key)
            if value is not None and (key!='cpu_cores' or value):
                self.latest[key]=value;self.observed[key]=now
            elif now-self.observed.get(key,float('-inf'))>max(4,2*interval+1):
                self.latest.pop(key,None)

        while self.history and now-self.history[0]['time']>60:self.history.popleft()
        record={k:data[k] for k in ('cpu','memory','network','gpu') if k in keys and data.get(k) is not None}
        self.history.append(dict(record,time=now));self.display()

    def display(self):
        if self.window:self.window.refresh()
        if self.strip:self.strip.refresh()
        if self.ai_tray:self.ai_tray.refresh()
    def reposition(self):
        if self.window:self.window.reposition()
        if self.strip:self.strip.placement.restore();self.strip.reposition()
    def close(self):
        self.closed=True;self.signature=None;self.history=None;self.latest.clear();self.observed.clear()
        if self.job:
            self.job.requestInterruption();self.job.deleteLater();self.job=None
        if self.bluetooth:self.bluetooth.close();self.bluetooth=None
        if self.sensors:self.sensors.close();self.sensors=None
        if self.fps:self.fps.close();self.fps=None
        if self.window:self.window.dispose();self.window=None
        if self.strip:self.strip.dispose();self.strip=None
        if self.deck:self.deck.close();self.deck=None
        if self.ai_tray:self.ai_tray.close();self.ai_tray=None
        if self.extras:self.extras.close();self.extras=None
