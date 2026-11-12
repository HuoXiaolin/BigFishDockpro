"""Canonical screen-relative layouts; automatic projection never replaces user anchors."""
import copy
import ctypes
from ctypes import wintypes

from PyQt5.QtCore import QAbstractNativeEventFilter


def valid_record(value):
    if not isinstance(value,dict): return {}
    result={}
    for field in ('area','rect'):
        raw=value.get(field)
        if not isinstance(raw,list) or len(raw)!=4 or not all(type(n) is int and abs(n)<=1000000 for n in raw) or not 0<raw[2]<=131072 or not 0<raw[3]<=131072:return {}
        result[field]=list(raw)
    result['screen']=str(value.get('screen',''))[:240]
    ui=value.get('ui_scale')
    if type(ui) in (int,float) and 0.125<=ui<=8:result['ui_scale']=float(ui)
    density=value.get('density')
    if type(density) in (int,float) and .25<=density<=2:result['density']=float(density)
    return result


def normalize_layout(value):
    if not isinstance(value,dict):return {}
    panels=value.get('panels',{})
    panels={str(key)[:80]:record for key,raw in list(panels.items())[:256] if (record:=valid_record(raw))} if isinstance(panels,dict) else {}
    groups=value.get('merge_groups',{})
    groups={str(key)[:80]:record for key,raw in list(groups.items())[:64] if (record:=valid_record(raw))} if isinstance(groups,dict) else {}
    return {'dock':valid_record(value.get('dock')), 'merged':valid_record(value.get('merged')), 'panels':panels,'merge_groups':groups}


def primary_work_area(screen):
    # Windows reports the primary work area in physical pixels, even while
    # Qt still has the previous session's screen geometry.
    work = wintypes.RECT()
    query = ctypes.windll.user32.SystemParametersInfoW
    query.argtypes = (wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT)
    if not query(0x0030, 0, ctypes.byref(work), 0):  # SPI_GETWORKAREA
        return None
    ratio = screen.devicePixelRatio()
    left, top, right, bottom = (round(edge / ratio) for edge in (work.left, work.top, work.right, work.bottom))
    if right > left and bottom > top:
        return [left, top, right - left, bottom - top]
    return None


def screen_records():
    from PyQt5.QtWidgets import QApplication
    app=QApplication.instance();primary=app.primaryScreen()
    ordered=([primary] if primary else [])+[screen for screen in app.screens() if screen is not primary]
    records=[]
    for screen in ordered:
        serial=screen.serialNumber().strip()
        identity=['hardware',screen.manufacturer(),screen.model(),serial] if serial.lower() not in ('','0','-1','unknown') and serial.strip('0') else ['connector',screen.name(),screen.manufacturer(),screen.model()]
        area=list(screen.availableGeometry().getRect())
        if screen is primary and app.platformName() == 'windows':
            area=primary_work_area(screen) or area
        if area[2]<=0 or area[3]<=0:continue
        records.append({'screen':'|'.join(identity),'area':area})
    return records


def initial_card_factor(area):
    return max(1.0,min(2.5,min(area[2]/1536,area[3]/816)))


def choose_screen(record,screens):
    return next((screen for screen in screens if screen['screen']==record.get('screen')),screens[0]) if screens else None


def capture(rect,screens,ui_scale=1.0,density=1.0):
    if not screens:return {}
    cx,cy=rect[0]+rect[2]/2,rect[1]+rect[3]/2
    def distance(screen):
        x,y,w,h=screen['area']
        return max(x-cx,0,cx-x-w)**2+max(y-cy,0,cy-y-h)**2
    screen=min(screens,key=distance)
    result=dict(screen=screen['screen'],area=list(screen['area']),rect=list(rect))
    if ui_scale!=1.0:result['ui_scale']=float(ui_scale)
    if density!=1.0:result['density']=float(density)
    return result


def scale(record,target):
    return min(target['area'][2]/record['area'][2],target['area'][3]/record['area'][3]) if record and target else 1.0


def project(record,screens,minimum=None,density=1.0):
    target=choose_screen(record,screens)
    if not record or not target:return None
    bx,by,bw,bh=record['area'];x,y,w,h=record['rect'];tx,ty,tw,th=target['area']
    density_ratio=density/record.get('density',1.0)
    if minimum is None:
        from dpi_support import minimum as minimum_size
        minimum=minimum_size(scale(record,target)*density_ratio*record.get('ui_scale',1.0))
    factor=min(max(scale(record,target)*density_ratio,minimum[0]/w,minimum[1]/h),tw/w,th/h)
    nw=max(1,round(w*factor));nh=max(1,round(h*factor))
    # Preserve edge/centre anchoring within the available travel area.
    ax=max(0,min(1,(x-bx)/max(1,bw-w)));ay=max(0,min(1,(y-by)/max(1,bh-h)))
    return [tx+round(ax*(tw-nw)),ty+round(ay*(th-nh)),nw,nh]


class DisplayEvents(QAbstractNativeEventFilter):
    """Guard saved anchors before Qt processes Windows' temporary DPI rectangles."""
    def __init__(self, layout):
        super().__init__()
        self.layout = layout
        self.session_hwnd = 0
        self.wts = None
        if layout.app.platformName() == 'windows':
            self.wts = ctypes.WinDLL('wtsapi32', use_last_error=True)
            self.wts.WTSRegisterSessionNotification.argtypes = (wintypes.HWND, wintypes.DWORD)
            self.wts.WTSUnRegisterSessionNotification.argtypes = (wintypes.HWND,)

    def watch_session(self):
        if self.layout.closed or self.wts is None:
            return
        hwnd = int(self.layout.dock.winId())
        if hwnd == self.session_hwnd:
            return
        self.unwatch_session()
        if self.wts.WTSRegisterSessionNotification(hwnd, 0):  # NOTIFY_FOR_THIS_SESSION
            self.session_hwnd = hwnd

    def unwatch_session(self):
        if self.session_hwnd:
            self.wts.WTSUnRegisterSessionNotification(self.session_hwnd)
            self.session_hwnd = 0

    def nativeEventFilter(self,event_type,message):
        if self.layout.closed or event_type not in (b'windows_generic_MSG',b'windows_dispatcher_MSG'):return False,0
        msg=wintypes.MSG.from_address(int(message))
        if ((msg.message==0x0219 and msg.wParam==7) or
                (msg.message==0x0218 and msg.wParam==18)):  # DBT_DEVNODES_CHANGED / PBT_APMRESUMEAUTOMATIC
            resources=getattr(self.layout.runtime,'resources',None)
            monitor=getattr(resources,'peripherals',None)
            if monitor:monitor.device_changed()
        if msg.message==0x0016:self.layout.runtime.session_ending=bool(msg.wParam)  # WM_ENDSESSION, including cancellation.
        elif msg.message==0x001a and msg.wParam==20:  # SPI_SETDESKWALLPAPER
            if msg.hWnd==int(self.layout.dock.winId()):
                from wallpaper_source import invalidate_source
                invalidate_source()
                resources=self.layout.runtime.resources.window
                if resources:resources.glass.clear();resources.update()
                flash=self.layout.runtime.flash.panel
                if flash:
                    for bar in (flash.toolbar,flash.filters_bar,flash.launch_shell,flash.composer):
                        bar.material.clear();bar.update()
        elif msg.message==0x001a and msg.wParam==0x002f:self.layout.changed()  # SPI_SETWORKAREA
        elif msg.message==0x007e:self.layout.changed()  # WM_DISPLAYCHANGE
        elif msg.message==0x02b1 and msg.hWnd==self.session_hwnd:  # WM_WTSSESSION_CHANGE
            # Console/remote connect or disconnect, unlock, remote control or desktop ready.
            if msg.wParam in (1, 2, 3, 4, 8, 9, 15):
                self.layout.session_changed()
        elif msg.message==0x02e0:  # WM_DPICHANGED: let Qt remain the DPI owner.
            windows=[self.layout.dock,self.layout.runtime.clock,self.layout.runtime.calendar,*self.layout.runtime.panels.windows.values(),*self.layout.runtime.notes.windows.values()]
            for window in windows:
                try:handle=window.windowHandle()
                except RuntimeError:continue
                if handle is not None and int(handle.winId())==int(msg.hWnd or 0):
                    dragging=getattr(window,'drag_origin',None) is not None or getattr(window,'drag',None) is not None
                    if not dragging or self.layout.pending:self.layout.changed()
                    break
        return False,0


class DisplayLayout:
    SESSION_SETTLE_MS = 2600

    def __init__(self,runtime):
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication
        self.runtime=runtime;self.dock=runtime.dock;self.pending=False;self.applying=False;self.closed=False
        self.session_transition = False
        self.bound=[];self.revision=0
        self.timer=QTimer(self.dock);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.apply_pending)
        self.settle_timer=QTimer(self.dock);self.settle_timer.setSingleShot(True);self.settle_timer.setInterval(450);self.settle_timer.timeout.connect(self.finish)
        app=QApplication.instance();self.app=app
        app.screenAdded.connect(self.changed);app.screenRemoved.connect(self.changed);app.primaryScreenChanged.connect(self.changed)
        self.native_filter=DisplayEvents(self);app.installNativeEventFilter(self.native_filter)
        self.native_filter.watch_session()
        if not self.native_filter.session_hwnd and self.native_filter.wts is not None:
            # The Windows session service may still be starting at logon.
            QTimer.singleShot(3500, self.native_filter.watch_session)
        self.bind_screens()
        self.ensure_profiles()
        self.update_dock()

    def screens(self):return screen_records()

    def check_work_area(self):
        # Also catch remote viewers which change the Windows work area without
        # a Qt screen notification. Reuse the Dock's existing position check.
        if self.pending or self.closed:
            return
        screens = self.screens()
        if screens and screens[0]['area'] != list(self.dock.available_area().getRect()):
            self.changed()

    def session_changed(self):
        self.session_transition = True
        self.changed()

    def bind_screens(self):
        current=self.app.screens()
        self.bound=[old for old in self.bound if any(old is screen for screen in current)]
        for screen in current:
            if any(old is screen for old in self.bound):continue
            self.bound.append(screen)
            for name in ('geometryChanged','availableGeometryChanged','logicalDotsPerInchChanged'):
                getattr(screen,name).connect(self.changed)

    def changed(self,*args):
        if self.closed:return
        self.pending=True;self.revision+=1
        self.settle_timer.stop()
        self.bind_screens()
        for window in self.runtime.panels.windows.values():
            window.resize_timer.stop();window.fit_timer.stop();window.expand_timer.stop();window.collapse_timer.stop();window.manual_resize=False
        for window in getattr(getattr(self.runtime,'notes',None),'windows',{}).values():
            window.geometry_timer.stop();window.refresh_timer.stop();window.collapse_timer.stop();window.expand_timer.stop()
        for name in ('clock','calendar'):
            clock=getattr(self.runtime,name,None)
            if clock:clock.geometry_timer.stop();clock.refresh_timer.stop()
        self.timer.start()

    def record(self,identity):
        state=self.dock.cfg.get('display_layout',{})
        if self.runtime.panels.is_merged(identity):
            group=self.runtime.panels.group_id(identity)
            return state.get('merged',{}) if group=='default' else state.get('merge_groups',{}).get(group,{})
        return state.get('panels',{}).get(identity,{})

    def panel_bounds(self,identity,fallback):
        screens=self.screens();window=self.runtime.panels.windows.get(identity)
        record=self.record(identity) or capture(list(fallback),screens,getattr(window,'default_ui_factor',1.0),self.dock.cfg.get('card_scale',70)/100 if not self.runtime.panels.model(identity).get('geometry') else 1.0)
        from card_metrics import metrics
        bounds=project(record,screens,density=self.dock.cfg.get('card_scale',70)/100) or list(fallback)
        return metrics(self.dock.cfg,bounds,screens,choose_screen(record,screens))[0]

    def panel_scale(self,identity):
        from card_metrics import metrics
        record=self.record(identity);screens=self.screens()
        window=self.runtime.panels.windows.get(identity)
        fallback=getattr(window,'default_geometry',[0,0,320,260])
        bounds=project(record,screens,density=self.dock.cfg.get('card_scale',70)/100) or fallback
        return metrics(self.dock.cfg,bounds,screens,choose_screen(record,screens))[1]

    def panel_update(self,identity,rect,*,group=''):
        state=copy.deepcopy(self.dock.cfg.get('display_layout',{}))
        window=self.runtime.panels.windows.get(identity)
        record=capture(rect,self.screens(),getattr(window,'ui_factor',1.0),self.dock.cfg.get('card_scale',70)/100)
        if group=='':
            manager=self.runtime.panels
            group=manager.group_id(identity) if manager.is_merged(identity) else None
        if group=='default':state['merged']=record
        elif group is not None:state.setdefault('merge_groups',{})[group]=record
        else:state.setdefault('panels',{})[identity]=record
        return state

    def ensure_profiles(self):
        if self.pending or self.applying:return
        from card_metrics import metrics

        state=copy.deepcopy(self.dock.cfg.get('display_layout',{}));screens=self.screens()
        if not screens:return
        if not state.get('dock'):
            state['dock']=dict(screens[0],rect=list(screens[0]['area']))
        known={model['id'] for model in self.dock.cfg['desktop_panels']}
        state['panels']={key:record for key,record in state.get('panels',{}).items() if key in known}
        panels=state['panels']
        manager=self.runtime.panels
        density=self.dock.cfg.get('card_scale',70)/100
        for model in self.dock.cfg['desktop_panels']:
            identity=model['id']
            if identity in panels:continue
            window=manager.windows.get(identity)
            saved=model.get('geometry')
            geometry=saved or (window.default_geometry if window else manager.default_geometries.get(identity))
            if geometry:
                factor=window.ui_factor if window else metrics(self.dock.cfg,geometry,screens)[1]
                panels[identity]=capture(geometry,screens,factor,1.0 if saved else density)
        valid={group['id'] for group in self.dock.cfg.get('merge_groups',[])}
        state['merge_groups']={key:record for key,record in state.get('merge_groups',{}).items() if key in valid}
        for group,identity in getattr(manager,'active_windows',{}).items():
            existing=state.get('merged') if group=='default' else state['merge_groups'].get(group)
            if existing:continue
            window=manager.windows.get(identity)
            saved=manager.group_value(identity,'geometry')
            geometry=saved or (window.default_geometry if window else manager.default_geometries.get(identity))
            if geometry:
                factor=window.ui_factor if window else metrics(self.dock.cfg,geometry,screens)[1]
                record=capture(geometry,screens,factor,1.0 if saved else density)
                if group=='default':state['merged']=record
                else:state['merge_groups'][group]=record
        if state!=self.dock.cfg.get('display_layout'):
            if self.runtime.api.save_config(dict(self.dock.cfg,display_layout=state)) is not False:self.dock.cfg['display_layout']=state

    def update_dock(self, screens=None):
        screens=self.screens() if screens is None else screens
        if not screens:return
        record=self.dock.cfg.get('display_layout',{}).get('dock',{})
        from PyQt5.QtCore import QRect
        self.dock._display_area=QRect(*screens[0]['area'])
        self.dock.display_scale=scale(record,screens[0])
        self.dock.reload()

    def apply_pending(self):
        self.apply(settling=True)
        if self.pending and not self.timer.isActive():
            self.settle_timer.start(self.SESSION_SETTLE_MS if self.session_transition else 450)

    def finish(self):
        self.apply()

    def apply(self,settling=False):
        if self.closed:return
        screens=self.screens()
        if not screens:
            self.pending=True
            return  # Wait for the next display notification, without polling or saving fallback coordinates.
        self.applying=True;revision=self.revision
        try:
            self.update_dock(screens)
            self.runtime.panels.reposition()
            if getattr(self.runtime,'notes',None):self.runtime.notes.reposition()
            for name in ('clock','calendar'):
                component=getattr(self.runtime,name,None)
                if component:component.reposition();component.refresh_timer.start()
            flash=getattr(self.runtime,'flash',None)
            if flash:flash.reposition()
            resources=getattr(self.runtime,'resources',None)
            if resources:resources.reposition()
            spectrum=getattr(self.runtime,'spectrum',None)
            if spectrum:spectrum.reposition()
            daily=getattr(self.runtime,'daily_picture',None)
            if daily:daily.reposition()
            custom=getattr(self.runtime,'custom_cards',None)
            if custom:custom.reposition()
            dialog=getattr(self.runtime.tray,'settings_dialog',None)
            if dialog and hasattr(dialog,'adapt_interface'):dialog.adapt_interface()
            self.runtime.refresh_corners()
        finally:
            self.applying=False;self.pending=bool(settling or revision!=self.revision)
        if revision!=self.revision:
            self.timer.start();return
        if not settling:
            self.timer.stop();self.settle_timer.stop()
            self.ensure_profiles()
            self.native_filter.watch_session()
            if self.session_transition:
                self.session_transition = False
                self.runtime.check_fullscreen()
                if self.dock.isVisible() and self.dock.isMinimized():
                    self.dock.showNormal()
                    self.dock.reposition()
            else:
                self.runtime.apply_visibility()
            if self.dock.isVisible():
                self.dock.apply_layer()

    def close(self):
        if self.closed:return
        self.closed=True;self.timer.stop();self.settle_timer.stop()
        self.native_filter.unwatch_session()
        self.app.removeNativeEventFilter(self.native_filter)
        for signal in (self.app.screenAdded,self.app.screenRemoved,self.app.primaryScreenChanged):
            try:signal.disconnect(self.changed)
            except (TypeError,RuntimeError):pass
        for screen in self.bound:
            for name in ('geometryChanged','availableGeometryChanged','logicalDotsPerInchChanged'):
                try:getattr(screen,name).disconnect(self.changed)
                except (TypeError,RuntimeError):pass
        self.bound.clear()
