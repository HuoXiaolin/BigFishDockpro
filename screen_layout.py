"""Canonical screen-relative layouts; automatic projection never replaces user anchors."""
import copy


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
    return {'dock':valid_record(value.get('dock')), 'merged':valid_record(value.get('merged')), 'panels':panels}


def screen_records():
    from PyQt5.QtWidgets import QApplication
    app=QApplication.instance();primary=app.primaryScreen()
    ordered=([primary] if primary else [])+[screen for screen in app.screens() if screen is not primary]
    records=[]
    for screen in ordered:
        serial=screen.serialNumber().strip()
        identity=['hardware',screen.manufacturer(),screen.model(),serial] if serial.lower() not in ('','0','-1','unknown') and serial.strip('0') else ['connector',screen.name(),screen.manufacturer(),screen.model()]
        records.append({'screen':'|'.join(identity),'area':list(screen.availableGeometry().getRect())})
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


class DisplayLayout:
    def __init__(self,runtime):
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication
        self.runtime=runtime;self.dock=runtime.dock;self.pending=False;self.applying=False;self.closed=False
        self.bound=[]
        self.timer=QTimer(self.dock);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.apply)
        app=QApplication.instance();self.app=app
        app.screenAdded.connect(self.changed);app.screenRemoved.connect(self.changed);app.primaryScreenChanged.connect(self.changed)
        self.bind_screens()
        self.ensure_profiles()
        self.update_dock()

    def screens(self):return screen_records()

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
        self.pending=True
        self.bind_screens()
        for window in self.runtime.panels.windows.values():
            window.resize_timer.stop();window.fit_timer.stop();window.manual_resize=False
        for window in getattr(getattr(self.runtime,'notes',None),'windows',{}).values():
            window.geometry_timer.stop();window.refresh_timer.stop()
        self.timer.start()

    def record(self,identity):
        state=self.dock.cfg.get('display_layout',{})
        return state.get('merged',{}) if self.runtime.panels.is_merged(identity) else state.get('panels',{}).get(identity,{})

    def panel_bounds(self,identity,fallback):
        screens=self.screens();window=self.runtime.panels.windows.get(identity)
        record=self.record(identity) or capture(list(fallback),screens,getattr(window,'default_ui_factor',1.0))
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

    def panel_update(self,identity,rect):
        state=copy.deepcopy(self.dock.cfg.get('display_layout',{}))
        window=self.runtime.panels.windows.get(identity)
        record=capture(rect,self.screens(),getattr(window,'ui_factor',1.0),self.dock.cfg.get('card_scale',70)/100)
        if self.runtime.panels.is_merged(identity):state['merged']=record
        else:state.setdefault('panels',{})[identity]=record
        return state

    def ensure_profiles(self):
        if self.pending or self.applying:return
        state=copy.deepcopy(self.dock.cfg.get('display_layout',{}));screens=self.screens()
        if not screens:return
        if not state.get('dock'):
            state['dock']=dict(screens[0],rect=list(screens[0]['area']))
        known={model['id'] for model in self.dock.cfg['desktop_panels']}
        state['panels']={key:record for key,record in state.get('panels',{}).items() if key in known}
        panels=state['panels']
        for model in self.dock.cfg['desktop_panels']:
            window=self.runtime.panels.windows.get(model['id'])
            if window and model['id'] not in panels:
                panels[model['id']]=capture(model.get('geometry',window.default_geometry),screens,window.default_ui_factor if not model.get('geometry') else 1.0)
        if self.dock.cfg['merged_panels'] and not state.get('merged'):
            window=self.runtime.panels.windows.get(self.runtime.panels.active_window)
            if window:state['merged']=capture(self.dock.cfg.get('merged_geometry') or window.default_geometry,screens,window.default_ui_factor if not self.dock.cfg.get('merged_geometry') else 1.0)
        if state!=self.dock.cfg.get('display_layout'):
            if self.runtime.api.save_config(dict(self.dock.cfg,display_layout=state)) is not False:self.dock.cfg['display_layout']=state

    def update_dock(self):
        screens=self.screens()
        if not screens:return
        record=self.dock.cfg.get('display_layout',{}).get('dock',{})
        self.dock.display_scale=scale(record,screens[0])
        self.dock.reload()

    def apply(self):
        if self.closed:return
        if not self.screens():
            self.pending=True
            return  # Wait for the next display notification, without polling or saving fallback coordinates.
        self.applying=True
        try:
            self.update_dock()
            self.runtime.panels.reposition()
            if getattr(self.runtime,'notes',None):self.runtime.notes.reposition()
            dialog=getattr(self.runtime.tray,'settings_dialog',None)
            if dialog and hasattr(dialog,'adapt_interface'):dialog.adapt_interface()
            self.runtime.refresh_corners()
        finally:self.applying=False;self.pending=False
        self.ensure_profiles()

    def close(self):
        if self.closed:return
        self.closed=True;self.timer.stop()
        for signal in (self.app.screenAdded,self.app.screenRemoved,self.app.primaryScreenChanged):
            try:signal.disconnect(self.changed)
            except (TypeError,RuntimeError):pass
        for screen in self.bound:
            for name in ('geometryChanged','availableGeometryChanged','logicalDotsPerInchChanged'):
                try:getattr(screen,name).disconnect(self.changed)
                except (TypeError,RuntimeError):pass
        self.bound.clear()
