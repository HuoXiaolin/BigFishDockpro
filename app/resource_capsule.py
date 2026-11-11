"""Demand-driven GPU/CPU sampling, Bluetooth sharing, window and settings ownership."""
from collections import deque
import time
import threading
from PyQt5.QtCore import QObject,pyqtSignal,Qt
from background_worker import BackgroundWorker
from resource_options import (CAPSULE_PAGES,COMPACT_DEVICE,RESOURCE_PAGES,component_available,
                              component_location,resource_page_active)
from resource_status import BATTERY_WARNING_LEVEL


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
            previous_keys=frozenset()
            previous_signature=None
            next_full=next_rank=0.
            while not self.cancelled.is_set():
                with self.lock:
                    self.wake.clear()
                    keys,interval=self.signature
                now=time.monotonic()
                if (keys,interval)!=previous_signature:
                    reader.configure(keys)
                    next_full=now
                    if 'rank' in keys-previous_keys:next_rank=now
                    previous_keys=keys
                    previous_signature=(keys,interval)
                rank_due='rank' in keys and now>=next_rank
                warming=rank_due and not reader.ranking.previous
                value=None
                if now>=next_full:
                    value=reader.sample(sample_rank=rank_due)
                    next_full=now+interval
                elif rank_due:
                    value={'time':now,'rank':reader.ranking.sample(now),'rank_only':True}
                if rank_due:
                    next_rank=now+(.30 if warming else 1.0)
                if value is not None and not self.cancelled.is_set():
                    self.sample_ready.emit(value)
                deadline=min(next_full,next_rank) if 'rank' in keys else next_full
                self.wake.wait(max(0.,deadline-time.monotonic()))
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
        self.extras=None;self.pomodoro=None;self.agenda=None;self.battery_warned=False
        self.reminder_audio=None
        self.calendar_sync=None;self.calendar_checked=False
        self.desktop_cards={}
        self.dependency_prompts=None
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
        if 'resource_component_order' in changes:
            changes['resource_component_order']=list(dict.fromkeys([*changes['resource_component_order'],*CAPSULE_PAGES]))
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
    def settings(self,page=None):
        from contextlib import nullcontext
        from resource_settings import ResourceOptions
        from ui_style import exec_dialog
        main = getattr(self.runtime.tray, 'settings_dialog', None)
        scope = main.suspend_page() if main is not None and main.isVisible() else nullcontext()
        self.settings_depth += 1
        self.settings_focus_changed()
        try:
            with scope:
                options=ResourceOptions(self)
                if type(page) is int and 0<=page<options.tabs.count():options.tabs.setCurrentIndex(page)
                exec_dialog(options)
        finally:
            self.settings_depth -= 1
            self.settings_focus_changed()

    def detached(self,key):
        return self.desktop_cards.get(key)

    def component_order_at(self, key, before):
        order = [item for item in self.cfg['resource_component_order'] if item != key]
        if before is not None:
            order.insert(order.index(before), key)
        else:
            last = max((i for i,item in enumerate(order) if self.window.page_enabled(item)), default=-1)
            order.insert(last + 1, key)
        return order

    def detach_component_at(self, key, point):
        from card_snap import drop_rect
        from screen_layout import capture, screen_records, valid_record
        if not self.window or not self.window.page_enabled(key):
            return False
        if key=='notes' and not self.runtime.notes.flush():
            return False
        locations = dict(self.cfg['resource_component_locations'], **{key: 'desktop'})
        changes = {'resource_component_locations': locations}
        if key in RESOURCE_PAGES:
            from resource_desktop_card import INITIAL_SIZES
            layouts = dict(self.cfg['resource_card_layouts'])
            saved = valid_record(layouts.get(key))
            size = saved['rect'][2:] if saved else INITIAL_SIZES[key]
            bounds = drop_rect(point, *size)
            if bounds is None:
                return False
            layouts[key] = capture(bounds, screen_records())
            changes['resource_card_layouts'] = layouts
        return self.set_options(**changes)

    def preview_component_at(self, key, point=None):
        window = self.window
        if window and window.isVisible() and component_location(self.cfg,key)=='desktop':
            if point is None:window.clear_tab_drop()
            else:window.preview_tab_drop(key,point,incoming=True)

    def return_component_at(self, key, point, identity=None):
        window = self.window
        if window is None:
            return False
        window.clear_tab_drop()
        if (not window.isVisible() or not window.geometry().contains(point)
                or component_location(self.cfg,key)!='desktop' or not component_available(self.cfg,key)):
            return False
        if key=='notes' and not self.runtime.notes.flush():
            return False
        locations = dict(self.cfg['resource_component_locations'], **{key: 'capsule'})
        changes = {'resource_component_locations': locations}
        slot = window.tab_drop_slot(key, point)
        if slot is not None:
            changes['resource_component_order'] = self.component_order_at(key,slot[0])
        if not self.set_options(**changes):
            return False
        if self.compact:
            self.fold(False)
        if not self.compact and window.page_enabled(key):
            window.select_page(key)
            if key=='custom' and identity:window.view(key).select(identity)
        return True

    def feature_visible(self,key):
        if self.runtime.game_active or not component_available(self.cfg,key):return False
        if component_location(self.cfg,key)=='desktop':return key in self.desktop_cards
        return bool(self.window and self.window.isVisible())

    def sync_desktop_cards(self):
        wanted=[key for key in RESOURCE_PAGES if not self.runtime.game_active and
                component_location(self.cfg,key)=='desktop' and component_available(self.cfg,key)]
        for key in self.desktop_cards.keys()-set(wanted):self.desktop_cards.pop(key).dispose()
        for key in wanted:
            if key not in self.desktop_cards:
                from resource_desktop_card import ResourceDesktopCard
                self.desktop_cards[key]=ResourceDesktopCard(self,key)
            self.desktop_cards[key].sync_window()

    def hosted_component(self,key,identity=None):
        window=self.window
        if not window or self.compact or window.page_key!=key or not window.page_enabled(key):return None
        view=getattr(window,'_'+key+'_view',None)
        if view and view.active and (identity is None or view.selected==identity):return view.host
        return None

    def components_changed(self):
        if self.window and not self.closed:self.window.refresh()

    def open_component(self,key,identity=None):
        card=self.detached(key)
        if card:
            card.show();card.raise_()
            return
        self.open()
        if self.window and self.window.page_enabled(key):
            self.window.select_page(key)
            if identity:self.window.view(key).select(identity)

    def get_pomodoro(self):
        if self.pomodoro is None:
            from resource_pomodoro import Pomodoro
            self.pomodoro=Pomodoro(self)
            self.pomodoro.changed.connect(self.reminders_changed)
            self.pomodoro.sync()
        return self.pomodoro

    def get_agenda(self):
        if self.agenda is None:
            from resource_agenda import Agenda
            self.agenda=Agenda(self)
            self.agenda.changed.connect(self.agenda_changed)
            self.agenda.sync()
        return self.agenda

    def get_calendar_sync(self):
        if self.calendar_sync is None:
            from resource_calendar_sync import CalendarSync
            self.calendar_sync=CalendarSync(self)
            self.calendar_checked=True
            self.calendar_sync.events_changed.connect(self.calendar_changed)
            self.calendar_sync.schedule()
        return self.calendar_sync

    def calendar_changed(self):
        if self.agenda:self.agenda.sync()
        else:self.get_agenda()

    def calendar_entries(self):
        events=self.cfg['resource_agenda_events']
        return self.calendar_sync.events_for(events) if self.calendar_sync else events

    def agenda_changed(self):
        self.reminders_changed()
        calendar=getattr(self.runtime,'calendar',None)
        if calendar and calendar.isVisible():calendar.update()

    def reminders_changed(self):
        if self.window:self.window.refresh_reminders()
        for key in ('pomodoro','agenda'):
            card=self.detached(key)
            if card and card.isVisible():card.refresh()

    def play_reminder_sound(self,kind):
        if self.closed or not self.cfg['resource_reminder_sound'] or self.runtime.dock.preview or self.runtime.game_active:return
        if self.reminder_audio is None:
            from resource_reminder_audio import ReminderAudio
            self.reminder_audio=ReminderAudio(self)
        self.reminder_audio.play(kind)

    def reminders(self):
        badges=[]
        due=self.agenda.due() if self.agenda else ()
        if due:
            title=due[0]['title']
            if len(due)>1:title+=f' · +{len(due)-1}'
            badges.append(('agenda',title))
        level=self.low_battery()
        if level is not None:badges.append(('battery',f'{level}%'))
        if self.pomodoro:badges.extend(self.pomodoro.badges())
        return tuple(badges)

    def low_battery(self):
        if self.cfg['resource_alert_battery'] and self.cfg['resource_enabled']:
            level,state=self.latest.get('battery',(None,'unknown'))
            if level is not None and state=='battery' and level<=BATTERY_WARNING_LEVEL:return level
        return None

    def check_battery_alert(self):
        level,state=self.latest.get('battery',(None,'unknown'))
        if not self.cfg['resource_alert_battery'] or state in ('charging','ac','plugged','full') or level is not None and level>17:
            self.battery_warned=False
        low=self.low_battery()
        if low is not None and not self.battery_warned:
            self.battery_warned=True
            if not (self.runtime.dock.preview or self.runtime.game_active):
                tray=self.runtime.tray;tray.showMessage('电脑电量低',f'剩余 {low}%，请接上电源。',tray.icon(),5000)
                self.play_reminder_sound('battery')

    def needs(self):
        if self.closed:return set()
        desktop=set()
        detailed=self.detached('resources')
        capsule=(self.window and self.window.isVisible() and component_location(self.cfg,'resources')=='capsule')
        if detailed or capsule and not (self.compact and self.cfg['resource_fold']=='ball'):
            from resource_options import METRICS
            desktop={k for k in METRICS if k not in ('traffic','system_status') and self.cfg['resource_'+k]}
            if detailed or not self.compact and self.window.page_key=='resources':
                if 'cpu' in desktop:desktop.add('cpu_cores')
                if self.cfg['resource_system_status']:desktop.add('system_status')
            elif self.compact:
                selected=self.cfg['resource_compact_metrics']
                desktop.intersection_update(selected)
                if self.cfg['resource_system_status']:
                    desktop.update(key for key in COMPACT_DEVICE if key in selected)
            else:desktop.difference_update(('rank','bluetooth'))
        if self.feature_visible('traffic'):desktop.add('traffic')
        if self.window and self.window.isVisible() and self.cfg['resource_alert_battery']:desktop.add('battery')
        if self.strip and self.strip.isVisible():desktop.update(self.cfg['resource_task_metrics'])
        custom=getattr(self.runtime,'custom_cards',None)
        if custom:desktop.update(custom.needs())
        return desktop

    def active_keys(self):
        return self.needs() & {'cpu','cpu_cores','gpu','memory','network','rank','traffic','system_status',
                               'battery','connection','volume'}

    def strip_allowed(self):
        return not self.runtime.game_active or (
            self.runtime.auto_game and not self.cfg['game_mode'] and self.cfg['resource_taskbar_layer']=='top')

    def make_strip(self):
        if self.strip is None:
            from taskbar_readout import TaskbarReadout
            self.strip=TaskbarReadout(self)
        return self.strip

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
        if self.reminder_audio and (self.runtime.game_active or not self.cfg['resource_reminder_sound']):
            self.reminder_audio.stop()
        visible=self.cfg['resource_enabled'] and not self.runtime.game_active
        if not visible:self.auto_compact=None
        if visible:
            if self.window is None:
                from resource_panel import ResourceWindow
                self.window=ResourceWindow(self)
            self.window.sync_window()
        elif self.window is not None:
            window,self.window=self.window,None;window.dispose()
        self.sync_desktop_cards()
        if self.feature_visible('weather'):
            if self.extras is None:
                from resource_extras import ResourceExtras
                self.extras=ResourceExtras(self)
            self.extras.sync()
        elif self.extras:self.extras.close();self.extras=None
        strip_allowed=self.strip_allowed()
        if self.cfg['resource_taskbar'] and (self.cfg['resource_task_metrics'] or self.cfg['resource_task_music']) and strip_allowed:
            fresh=self.strip is None
            strip=self.make_strip()
            if fresh or getattr(strip.placement,'ratio',None)!=strip.placement.configured_ratio():strip.placement.restore()
            strip.reposition();strip.sync_style()
        elif self.strip:
            strip,self.strip=self.strip,None;strip.dispose()
        demand=self.needs()
        want_tray=self.cfg['resource_ai_tray'] and not self.runtime.game_active
        want_music=bool(self.strip and self.strip.music_requested())
        want_ai=self.cfg['resource_ai'] and self.feature_visible('ai') or want_tray
        want_media=self.feature_visible('music') or want_music or bool(getattr(self.runtime,'spectrum',None))
        want_deck=want_ai or want_media
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
        if 'system_status' in demand or 'brightness' in demand:sensors=sensors|{'brightness'}
        self.check_dependencies(want_media or bool(want_ai and self.cfg['resource_ai_providers']))
        if self.sensors:
            if not sensors:self.sensors.close();self.sensors=None
            elif self.sensors.keys!=sensors:self.sensors.reconfigure(sensors)
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
        interval=max(self.cfg['resource_interval'],2 if self.compact and not self.detached('resources') else 1)
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
        if self.pomodoro:
            self.pomodoro.sync()
        elif resource_page_active(self.cfg,'pomodoro'):
            from resource_pomodoro import state_path
            choices=self.cfg['resource_compact_metrics']
            if (self.cfg['resource_water_enabled'] or state_path(self.runtime.api.CONFIG_DIR).is_file()
                    or self.window and self.compact and ('pomodoro' in choices or 'water' in choices)):
                self.get_pomodoro()
        from resource_options import calendar_data_active
        agenda_enabled=calendar_data_active(self.cfg)
        if agenda_enabled and not self.calendar_checked and not self.runtime.dock.preview:
            from pathlib import Path
            from resource_agenda import SYNC_SOURCES
            self.calendar_checked=True
            directory=Path(self.runtime.api.CONFIG_DIR)
            if any((directory/f'resource-calendar-{source}.dat').is_file() for source in SYNC_SOURCES):
                self.get_calendar_sync()
        if self.calendar_sync:self.calendar_sync.schedule()
        if self.agenda:self.agenda.sync()
        elif agenda_enabled and (self.cfg['resource_agenda_events'] or self.calendar_sync and self.calendar_sync.states):
            self.get_agenda()
        self.check_battery_alert()
        self.display()

    def check_dependencies(self,deck_needed):
        if self.runtime.dock.preview:return
        cfg=self.cfg
        cpu_sensors={'cpu_temp','cpu_power'}
        taskbar=cfg['resource_taskbar'] and self.strip_allowed()
        dotnet=deck_needed or taskbar and cfg['resource_task_music']
        pawnio=(self.feature_visible('resources') and any(cfg['resource_'+key] for key in cpu_sensors)
                or taskbar and bool(cpu_sensors.intersection(cfg['resource_task_metrics'])))
        if self.dependency_prompts is None and (dotnet or pawnio):
            from dependency_prompts import DependencyPrompts
            self.dependency_prompts=DependencyPrompts(self.runtime)
        if self.dependency_prompts:self.dependency_prompts.request(dotnet,pawnio)

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
        if data.get('rank_only'):
            if 'rank' in keys and data.get('rank') is not None:
                self.latest['rank']=data['rank']
                self.observed['rank']=now
                if self.window and self.window.dashboard is not None and self.window.page_key=='resources' and not self.compact:
                    self.window.show_ranking()
                card=self.detached('resources')
                if card and card.dashboard is not None:card.show_ranking()
            return
        for key in keys:
            value=data.get(key)
            if value is not None and (key!='cpu_cores' or value):
                self.latest[key]=value;self.observed[key]=now
            elif now-self.observed.get(key,float('-inf'))>max(4,2*interval+1):
                self.latest.pop(key,None)
        if 'battery' in keys:self.check_battery_alert()

        while self.history and now-self.history[0]['time']>60:self.history.popleft()
        record={k:data[k] for k in ('cpu','memory','network','gpu') if k in keys and data.get(k) is not None}
        self.history.append(dict(record,time=now));self.display()

    def display(self):
        if self.window:self.window.refresh()
        for card in self.desktop_cards.values():card.refresh()
        if self.strip:self.strip.refresh()
        if self.ai_tray:self.ai_tray.refresh()
        custom=getattr(self.runtime,'custom_cards',None)
        if custom:custom.redraw(metrics_only=True)
    def reposition(self):
        if self.window:
            self.window.sync_taskbar();self.window.reposition()
        for card in self.desktop_cards.values():card.reposition()
        if self.strip:self.strip.placement.restore();self.strip.reposition()
    def close(self):
        self.closed=True;self.signature=None;self.history=None;self.latest.clear();self.observed.clear()
        if self.reminder_audio:self.reminder_audio.stop()
        if self.pomodoro:self.pomodoro.timer.stop()
        if self.agenda:self.agenda.timer.stop()
        if self.calendar_sync:self.calendar_sync.close()
        if self.dependency_prompts:self.dependency_prompts.close()
        if self.job:
            self.job.requestInterruption();self.job.deleteLater();self.job=None
        if self.bluetooth:self.bluetooth.close();self.bluetooth=None
        if self.sensors:self.sensors.close();self.sensors=None
        if self.fps:self.fps.close();self.fps=None
        if self.window:self.window.dispose();self.window=None
        for card in self.desktop_cards.values():card.dispose()
        self.desktop_cards.clear()
        if self.strip:self.strip.dispose();self.strip=None
        if self.deck:self.deck.close();self.deck=None
        if self.ai_tray:self.ai_tray.close();self.ai_tray=None
        if self.extras:self.extras.close();self.extras=None
