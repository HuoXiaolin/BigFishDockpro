"""Effective pointer policy for desktop widgets and its recovery menu."""
from PyQt5.QtCore import QObject,QEvent
from PyQt5.QtWidgets import QActionGroup,QApplication,QWidget

MODES=(('全部穿透','all'),('全部可交互','none'),('自定义','custom'))
COMPONENTS=(('dock','Dock'),('resource','资源胶囊'),('taskbar','任务栏监控'),('flash','闪念胶囊'),
            ('clock','桌面时钟'),('calendar','桌面日历'),('spectrum','桌面频谱'),('picture','每日图片'))
LEGACY={'resource':'resource_click_through','taskbar':'resource_taskbar_click_through'}


def individual(cfg,key):
    if key in LEGACY:return bool(cfg.get(LEGACY[key]))
    return bool(cfg.get('component_passthrough',{}).get(key))


def enabled(cfg,key):
    mode=cfg.get('passthrough_mode','custom')
    return mode=='all' or mode=='custom' and individual(cfg,key)


def set_component(runtime,key,value):
    from settings_effects import save_changes
    cfg=runtime.dock.cfg
    if key in LEGACY:changes={LEGACY[key]:value}
    else:
        selected=dict(cfg['component_passthrough'])
        if value:selected[key]=True
        else:selected.pop(key,None)
        changes={'component_passthrough':selected}
    return save_changes(runtime.tray,runtime.api,dict(changes,passthrough_mode='custom'))


def set_mode(runtime,mode):
    from settings_effects import save_changes
    return save_changes(runtime.tray,runtime.api,{'passthrough_mode':mode})


class ClickThroughPolicy(QObject):
    def __init__(self,runtime):
        super().__init__(runtime.dock);self.runtime=runtime;self.app=QApplication.instance();self.applying=False
        self.app.installEventFilter(self)

    def apply(self,window):
        key=window.property('clickThroughKey')
        if not key or self.applying:return
        from window_layers import click_through
        self.applying=True
        try:click_through(window,enabled(self.runtime.dock.cfg,key))
        finally:self.applying=False

    def eventFilter(self,window,event):
        if event.type()==QEvent.Show and isinstance(window,QWidget) and window.isWindow():self.apply(window)
        return False

    def refresh(self):
        for window in self.app.topLevelWidgets():
            if window.isVisible():self.apply(window)

    def close(self):
        self.app.removeEventFilter(self)


def add_menu(menu,runtime):
    cfg=runtime.dock.cfg
    group=QActionGroup(menu);group.setExclusive(True)
    for title,value in MODES:
        action=menu.addAction(title);action.setCheckable(True);action.setChecked(cfg['passthrough_mode']==value)
        group.addAction(action);action.triggered.connect(lambda _,mode=value:set_mode(runtime,mode))
    menu.addSeparator()

    def add(parent,key,title):
        action=parent.addAction(title.replace('&','&&'));action.setCheckable(True);action.setChecked(individual(cfg,key))
        action.triggered.connect(lambda on:set_component(runtime,key,on))

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
