"""Effective pointer policy for desktop widgets and its recovery menu."""
from weakref import WeakSet
from PyQt5.QtCore import QObject,QEvent,QTimer
from PyQt5.QtWidgets import QActionGroup,QApplication,QWidget

MODES=(('全部穿透','all'),('全部可交互','none'),('自定义','custom'))
COMPONENTS=(('dock','Dock'),('resource','资源胶囊'),('taskbar','任务栏监控'),('flash','闪念胶囊'),
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
    def __init__(self,runtime):
        super().__init__(runtime.dock);self.runtime=runtime;self.app=QApplication.instance();self.applying=False
        self.conditional=WeakSet()
        self.pointer_timer=QTimer(self)
        self.pointer_timer.setInterval(24)
        self.pointer_timer.timeout.connect(self.update_pointer)
        self.app.installEventFilter(self)

    def apply(self,window,point=None):
        key=window.property('clickThroughKey')
        if not key or self.applying:return
        from window_layers import application_under,click_through,cursor_position,is_topmost
        mode=pointer_mode(self.runtime.dock.cfg,key)
        passthrough=mode is True
        self.applying=True
        try:
            if mode=='apps' and window.isVisible() and is_topmost(int(window.winId())):
                self.conditional.add(window)
                if not self.pointer_timer.isActive():self.pointer_timer.start()
                passthrough=application_under(int(window.winId()),point if point is not None else cursor_position())
            else:
                self.conditional.discard(window)
                if not self.conditional:self.pointer_timer.stop()
            click_through(window,passthrough)
        finally:self.applying=False

    def update_pointer(self):
        from window_layers import cursor_position
        point=cursor_position()
        for window in tuple(self.conditional):
            try:self.apply(window,point)
            except RuntimeError:self.conditional.discard(window)
        if not self.conditional:self.pointer_timer.stop()

    def eventFilter(self,window,event):
        kind=event.type()
        if kind in (QEvent.Show,QEvent.Hide,QEvent.Enter,QEvent.WindowStateChange) and isinstance(window,QWidget) and window.isWindow():
            if kind==QEvent.Hide and window in self.conditional:
                self.conditional.discard(window)
                if not self.conditional:self.pointer_timer.stop()
            elif kind!=QEvent.Hide:self.apply(window)
        return False

    def refresh(self):
        for window in self.app.topLevelWidgets():
            if window.isVisible():self.apply(window)

    def close(self):
        self.pointer_timer.stop()
        self.conditional.clear()
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
