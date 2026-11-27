"""Effective pointer policy for desktop widgets and its recovery menu."""
from weakref import WeakKeyDictionary
from PyQt5.QtCore import QObject,QEvent,QTimer,Qt,pyqtSignal
from PyQt5.QtWidgets import QActionGroup,QApplication,QWidget

MODES=(('全部穿透','all'),('全部可交互','none'),('自定义','custom'))
COMPONENTS=(('dock','Dock'),('resource','灵动胶囊'),('taskbar','任务栏监控'),('flash','闪念胶囊'),
            ('clock','桌面时钟'),('calendar','桌面日历'),('spectrum','桌面频谱'),('picture','每日图片'))
LEGACY={'resource':'resource_click_through','taskbar':'resource_taskbar_click_through'}
CHOICES=(('可交互',False),('始终穿透',True),('置顶时穿透应用窗口','apps'))


def individual(cfg,key):
    if key in LEGACY and cfg.get(LEGACY[key]):return True
    return cfg.get('component_passthrough',{}).get(key,False)


def pointer_mode(cfg,key):
    mode=cfg.get('passthrough_mode','custom')
    if mode=='custom':return individual(cfg,key)
    return mode=='all'


def selection_changes(cfg,modes):
    selected=dict(cfg['component_passthrough'])
    changes={'component_passthrough':selected,'passthrough_mode':'custom'}
    for key,value in modes.items():
        if key in LEGACY:changes[LEGACY[key]]=value is True
        if value=='apps' or (value is True and key not in LEGACY):selected[key]=value
        else:selected.pop(key,None)
    return changes


def set_component(runtime,key,value):
    from settings_effects import save_changes
    return save_changes(runtime.tray,runtime.api,selection_changes(runtime.dock.cfg,{key:value}))


def set_mode(runtime,mode):
    from settings_effects import save_changes
    return save_changes(runtime.tray,runtime.api,{'passthrough_mode':mode})


class ClickThroughPolicy(QObject):
    input_restored = pyqtSignal(object)

    def __init__(self,runtime):
        super().__init__(runtime.dock);self.runtime=runtime;self.app=QApplication.instance();self.applying=False
        # Visible windows that need cursor hit-testing or a global Alt sample.
        # Each value records (conditional hit-test, currently unlocked by Alt).
        self.watched = WeakKeyDictionary()
        self.closed = False
        self.pointer_timer=QTimer(self)
        self.pointer_timer.setInterval(24)
        self.pointer_timer.timeout.connect(self.update_pointer)
        self.app.installEventFilter(self)

    def sync_timer(self):
        if self.watched:
            if not self.pointer_timer.isActive():self.pointer_timer.start()
        else:self.pointer_timer.stop()

    def apply(self,window,point=None,alt_down=None):
        key=window.property('clickThroughKey')
        if not key or self.applying or self.closed:return
        from window_layers import alt_pressed,application_under,click_through,cursor_position,is_topmost
        mode=pointer_mode(self.runtime.dock.cfg,key)
        edge=getattr(window,'edge_reveal',None)
        if edge or self.runtime.dock.cfg.get('resource_edge_hide') or self.runtime.dock.cfg.get('card_edge_hide'):
            from desktop_edge_reveal import EdgeReveal,option
            setting=option(key)
            enabled=bool(setting and self.runtime.dock.cfg.get(setting) and window.isWindow())
            if enabled and edge is None:
                window.edge_reveal=edge=EdgeReveal(window,self.runtime,key=='resource')
            if edge:
                edge.configure(enabled)
                if edge.fraction<1.:mode=False
        self.applying=True
        try:
            visible = window.isVisible()
            conditional = mode == 'apps' and visible and is_topmost(int(window.winId()))
            can_unlock = visible and (mode is True or conditional) and self.runtime.dock.cfg['passthrough_alt_unlock']
            unlocked = can_unlock and (alt_pressed() if alt_down is None else alt_down)
            if conditional or can_unlock:
                self.watched[window] = (conditional, unlocked)
            else:
                self.watched.pop(window, None)
            self.sync_timer()
            passthrough = mode is True and not unlocked
            if conditional and not unlocked:
                passthrough = application_under(int(window.winId()), point if point is not None else cursor_position())
            restored = not passthrough and window.testAttribute(Qt.WA_TransparentForMouseEvents)
            click_through(window,passthrough)
            if restored and visible:
                self.input_restored.emit(window)
        finally:self.applying=False

    def accepts_input(self, window):
        # An enter or key event can arrive before the next Alt/underlay poll.
        if window in self.watched:
            self.apply(window)
        return not window.testAttribute(Qt.WA_TransparentForMouseEvents)

    def update_pointer(self):
        from window_layers import alt_pressed, cursor_position
        watched = tuple(self.watched.items())
        held = bool(watched) and self.runtime.dock.cfg['passthrough_alt_unlock'] and alt_pressed()
        point = None
        for window, (conditional, unlocked) in watched:
            if held == unlocked and (held or not conditional):
                continue
            if conditional and not held and point is None:
                point = cursor_position()
            try:self.apply(window, point, held)
            except RuntimeError:self.watched.pop(window, None)
        self.sync_timer()

    def eventFilter(self,window,event):
        kind=event.type()
        if kind in (QEvent.Show,QEvent.Hide,QEvent.Enter,QEvent.WindowStateChange) and isinstance(window,QWidget) and window.isWindow():
            if kind==QEvent.Hide:
                if window in self.watched:
                    self.watched.pop(window)
                    self.sync_timer()
            else:self.apply(window)
        return False

    def refresh(self):
        for window in self.app.topLevelWidgets():
            if window.isVisible():self.apply(window)

    def close(self):
        self.closed = True
        self.pointer_timer.stop()
        self.watched.clear()
        self.app.removeEventFilter(self)


def component_actions(menu,runtime,key):
    group=QActionGroup(menu);group.setExclusive(True)
    current=individual(runtime.dock.cfg,key)
    for title,value in CHOICES:
        action=menu.addAction(title);action.setCheckable(True);action.setChecked(current==value)
        group.addAction(action)
        action.triggered.connect(lambda _,choice=value:set_component(runtime,key,choice))


def add_menu(menu,runtime):
    cfg=runtime.dock.cfg
    group=QActionGroup(menu);group.setExclusive(True)
    for title,value in MODES:
        action=menu.addAction(title);action.setCheckable(True);action.setChecked(cfg['passthrough_mode']==value)
        group.addAction(action);action.triggered.connect(lambda _,mode=value:set_mode(runtime,mode))
    menu.addSeparator()
    from settings_catalog import ALT_PASSTHROUGH_LABEL
    unlock = menu.addAction(ALT_PASSTHROUGH_LABEL)
    unlock.setCheckable(True);unlock.setChecked(cfg['passthrough_alt_unlock'])
    def set_unlock(checked):
        from settings_effects import save_changes
        if not save_changes(runtime.tray,runtime.api,{'passthrough_alt_unlock':checked}):
            unlock.setChecked(cfg['passthrough_alt_unlock'])
    unlock.triggered.connect(set_unlock)
    menu.addSeparator()

    def add(parent,key,title):
        component_actions(parent.addMenu(title.replace('&','&&')),runtime,key)

    for key,title in COMPONENTS:add(menu,key,title)
    if runtime.resources.desktop_cards:
        from resource_options import RESOURCE_PAGES
        items=menu.addMenu('独立资源卡片')
        for key in runtime.resources.desktop_cards:add(items,'resource:'+key,RESOURCE_PAGES[key])
    panel_groups=[*cfg.get('desktop_panels',[]),*cfg.get('merge_groups',[])]
    if 'merged' in runtime.panels.windows and not any(row.get('id')=='merged' for row in panel_groups):
        panel_groups.append(dict(id='merged',name='桌面收纳'))
    for window_id in runtime.panels.windows:
        if not any(row.get('id')==window_id for row in panel_groups):
            panel_groups.append(dict(id=window_id,name=runtime.panels.windows[window_id].windowTitle().split(' · ')[0]))
    for prefix,title,rows in (('panel','桌面卡片',panel_groups),('note','便签',cfg['sticky_notes']),('custom','自定义卡片',cfg['custom_cards'])):
        if not rows:continue
        items=menu.addMenu(title)
        for row in rows:
            if row.get('id'):add(items,prefix+':'+row['id'],row.get('name') or row.get('title') or title)
