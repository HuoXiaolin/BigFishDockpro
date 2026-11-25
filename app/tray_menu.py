"""Shared, task-grouped commands for tray and Dock context menus."""
import ctypes
import os
from ctypes import wintypes

from PyQt5.QtCore import QEvent, QTimer
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication, QMenu
from ui_style import AlignedMenu


class TrayContextMenu(AlignedMenu):
    """Dismiss a Windows tray popup when input goes outside its menu tree."""
    def __init__(self):
        super().__init__()
        self.user=ctypes.windll.user32
        self.user.GetForegroundWindow.restype=wintypes.HWND
        self.user.SetForegroundWindow.argtypes=[wintypes.HWND]
        self.user.GetAsyncKeyState.restype=ctypes.c_short
        self.watcher=QTimer(self)
        self.watcher.setInterval(32)
        self.watcher.timeout.connect(self.poll_outside)
        self.foreground=None
        self.buttons=set()

    def surfaces(self):
        return [menu for menu in (self,*self.findChildren(QMenu)) if menu.isVisible()]

    def outside(self,point):
        return not any(menu.frameGeometry().contains(point) for menu in self.surfaces())

    def mouse_buttons(self):
        return {key for key in (1,2,4) if self.user.GetAsyncKeyState(key)&0x8000}

    def showEvent(self,event):
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)
        self.buttons=self.mouse_buttons()
        self.foreground=self.user.GetForegroundWindow()
        QTimer.singleShot(0,self.take_focus)
        self.watcher.start()

    def take_focus(self):
        if self.isVisible() and not os.environ.get('FISHDOCK_TEST_DESKTOP'):
            self.user.SetForegroundWindow(int(self.winId()))
            self.foreground=self.user.GetForegroundWindow()

    def hideEvent(self,event):
        self.watcher.stop()
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)
        # Qt hides the menu before dispatching the chosen action.
        QTimer.singleShot(0, self.release_if_hidden)

    def clear_actions(self):
        owned_menus = {submenu for action in self.actions()
                       if (submenu := action.menu()) is not None and submenu.parent() is self}
        self.clear()
        # QMenu.clear() removes submenu actions without deleting their menus.
        for submenu in owned_menus:
            submenu.deleteLater()

    def release_if_hidden(self):
        if not self.isVisible():
            self.clear_actions()

    def eventFilter(self,watched,event):
        if self.isVisible() and event.type()==QEvent.MouseButtonPress and self.outside(event.globalPos()):
            self.close()
        return super().eventFilter(watched,event)

    def poll_outside(self):
        foreground=self.user.GetForegroundWindow()
        buttons=self.mouse_buttons()
        clicked=bool(buttons-self.buttons)
        self.buttons=buttons
        if foreground and foreground!=self.foreground:
            if foreground not in {int(menu.winId()) for menu in self.surfaces()}:
                self.close()
                return
            self.foreground=foreground
        if clicked and self.outside(QCursor.pos()):self.close()


def separator_actions(menu,tray,insert_at=None):
    menu.addAction('添加分隔符').triggered.connect(lambda checked=False:tray.add_separator(insert_at))
    snapshot=[dict(item) for item in tray.cfg['items']]
    positions=[i for i,item in enumerate(snapshot) if item.get('sep')]
    remove=menu.addMenu('移除分隔符');remove.menuAction().setEnabled(bool(positions))
    for number,index in enumerate(positions,1):
        left=next((str(item.get('name') or '应用')[:10] for item in reversed(snapshot[:index]) if not item.get('sep')),'开头')
        right=next((str(item.get('name') or '应用')[:10] for item in snapshot[index+1:] if not item.get('sep')),'末尾')
        remove.addAction(str(number)+' · '+left+' / '+right).triggered.connect(lambda checked=False,i=index,s=snapshot:tray.remove_separator(i,s))
    if positions:
        remove.addSeparator();remove.addAction('移除全部分隔符').triggered.connect(lambda checked=False:tray.remove_separator(None,snapshot))


def common_actions(menu,tray,dock_context=False,insert_at=None):
    runtime=getattr(tray,'runtime',None)
    open_settings=lambda:runtime.show_settings() if runtime else tray.show_settings()
    dock_actions=menu
    if not dock_context:
        from settings_design import navigation_icon
        primary=menu.addAction('设置…',open_settings)
        primary.setIcon(navigation_icon('settings',menu.palette()))
        action=menu.addAction('显示 / 隐藏 Dock');action.setCheckable(True);action.setChecked(tray.dock.isVisible())
        action.triggered.connect(lambda:runtime.toggle_dock() if runtime else None)
        menu.addSeparator()
        dock_actions=menu.addMenu('Dock 与应用')
        dock_actions.setIcon(navigation_icon('apps',menu.palette()))
    dock_actions.addAction('应用批量管理…').triggered.connect(lambda:runtime.show_batch() if runtime else tray.importer.show())
    if not dock_context and runtime and hasattr(runtime,'productivity'):
        tools=dock_actions.addMenu('查找与整理')
        tools.addAction('统一搜索…').triggered.connect(runtime.productivity.open_search)
        undo=tools.addAction('撤销上次整理');undo.setEnabled(bool(runtime.productivity.history.entries));undo.triggered.connect(runtime.productivity.undo)
        tools.aboutToShow.connect(lambda:undo.setEnabled(bool(runtime.productivity.history.entries)))
        tools.addAction('桌面布局方案…').triggered.connect(runtime.productivity.open_layouts)
        tools.addAction('失效入口检查…').triggered.connect(runtime.productivity.open_references)

    layout=dock_actions.addMenu('Dock 布局');separator_actions(layout,tray,insert_at)
    if getattr(tray.dock,'page_count',1)>1:
        layout.addSeparator();layout.addAction('上一页').triggered.connect(lambda:tray.dock.change_page(-1));layout.addAction('下一页').triggered.connect(lambda:tray.dock.change_page(1))
    if dock_context:
        menu.addSeparator();menu.addAction('设置…',open_settings)
    else:
        groups=[]
        for title,symbol in (('桌面组件','panels'),('胶囊与监控','wave'),('系统外观','palette')):
            group=menu.addMenu(title)
            group.setIcon(navigation_icon(symbol,menu.palette()))
            groups.append(group)
        component_actions(*groups,tray,runtime)
        menu.addSeparator()
        help_actions(menu,tray,runtime)
    menu.addSeparator()
    if dock_context:
        menu.addAction('隐藏 Dock').triggered.connect(lambda:runtime.set_dock_visible(False) if runtime else tray.dock.hide())
    menu.addAction('退出').triggered.connect(lambda:runtime.request_exit() if runtime else QApplication.instance().quit())


def component_actions(menu,capsules,system,tray,runtime):
    panels=menu.addMenu('桌面卡片');panels.menuAction().setEnabled(runtime is not None)
    if runtime:
        windows=list(runtime.panels.windows.values())
        if len(windows)==1:
            panels.addAction('卡片外观设置…',windows[0].edit_options)
        elif windows:
            appearances=panels.addMenu('卡片外观设置')
            for window in windows:appearances.addAction(window.model['name'],window.edit_options)
    visible=panels.addAction('显示 / 隐藏桌面卡片');visible.setCheckable(True)
    visible.setChecked(bool(runtime and any(window.isVisible() for window in runtime.panels.windows.values())))
    visible.triggered.connect(lambda:runtime.toggle_panels() if runtime else None)
    panels.addSeparator();panels.addAction('新建面板…').triggered.connect(lambda:runtime.panels.new_panel() if runtime else None)
    panels.addAction('分组与合并管理…').triggered.connect(lambda:runtime.panels.manage_groups() if runtime else None)
    panels.addAction('尺寸与文字…').triggered.connect(lambda:runtime.open_card_sizing() if runtime else None)
    panels.addAction('重新整理桌面').triggered.connect(lambda:runtime.panels.scan() if runtime else None)
    notes=menu.addMenu('便签');notes.menuAction().setEnabled(runtime is not None)
    if runtime:
        from component_preferences import open_preferences
        notes.addAction('新便签默认外观…',lambda:open_preferences(runtime,'note'))
    notes.addAction('新建便签').triggered.connect(lambda:runtime.notes.new() if runtime else None)
    notes.addAction('管理与搜索…').triggered.connect(lambda:runtime.notes.manage() if runtime else None)
    action=notes.addAction('显示 / 隐藏便签');action.setCheckable(True)
    action.setChecked(bool(runtime and any(window.isVisible() for window in runtime.notes.windows.values())))
    action.triggered.connect(lambda:runtime.notes.toggle() if runtime else None)
    if runtime and hasattr(runtime,'flash'):
        from component_preferences import open_preferences
        flash=capsules.addMenu('闪念胶囊')
        flash.addAction('闪念设置…',lambda:open_preferences(runtime,'flash'))
        flash.addAction('记一条闪念…').triggered.connect(lambda:runtime.flash.open(compose=True))
        flash.addAction('查看闪念…').triggered.connect(lambda:runtime.flash.open())
        edge=flash.addAction('显示贴边胶囊');edge.setCheckable(True);edge.setChecked(tray.cfg['flash_enabled'])
        edge.triggered.connect(runtime.flash.set_enabled)
    if runtime and hasattr(runtime,'resources'):
        monitor=capsules.addMenu('灵动胶囊')
        monitor.addAction('打开资源详情…').triggered.connect(runtime.resources.open)
        monitor.addAction('显示与采样设置…').triggered.connect(runtime.resources.settings)
        show=monitor.addAction('显示桌面灵动胶囊');show.setCheckable(True);show.setChecked(tray.cfg['resource_enabled'])
        show.triggered.connect(lambda on:runtime.resources.set_options(resource_enabled=on))
        bt=monitor.addAction('显示外设电量托盘图标');bt.setCheckable(True);bt.setChecked(tray.cfg['resource_bt_tray'])
        bt.triggered.connect(lambda on:runtime.resources.set_options(resource_bt_tray=on))
        from taskbar_menu import add_menu as taskbar_actions
        taskbar_actions(system.addMenu('任务栏'),runtime)
        from shell_menu import add_menu as shell_actions
        shell_actions(system.addMenu('开始菜单'),runtime,'start')
        shell_actions(system.addMenu('通知与快捷面板'),runtime,'notifications')
        from cursor_style_ui import add_tray_menu as cursor_actions
        cursor_actions(system.addMenu('鼠标样式'), runtime)
        from component_passthrough import add_menu as passthrough_actions
        passthrough_actions(system.addMenu('鼠标穿透'),runtime)
    clock_menu=menu.addMenu('桌面时钟');clock_menu.menuAction().setEnabled(runtime is not None)
    clock=clock_menu.addAction('显示 / 隐藏时钟');clock.setCheckable(True);clock.setChecked(bool(runtime and tray.cfg['clock_enabled']))
    clock.triggered.connect(lambda checked:runtime.clock.set_enabled(checked) if runtime else None)
    clock_menu.addAction('时钟设置…').triggered.connect(lambda:runtime.clock.open_settings() if runtime else None)
    clock_menu.addAction('时光进度与倒计时…').triggered.connect(lambda:runtime.clock.open_progress() if runtime else None)
    calendar_menu=menu.addMenu('桌面日历');calendar_menu.menuAction().setEnabled(runtime is not None)
    calendar=calendar_menu.addAction('显示 / 隐藏日历');calendar.setCheckable(True);calendar.setChecked(bool(runtime and tray.cfg['calendar_enabled']))
    calendar.triggered.connect(lambda checked:runtime.calendar.set_enabled(checked) if runtime else None)
    calendar_menu.addAction('日历设置…').triggered.connect(lambda:runtime.calendar.open_settings() if runtime else None)
    if runtime:
        from settings_effects import save_changes
        from component_preferences import open_preferences
        marking=menu.addMenu('桌面文字水印')
        marking.addAction('水印设置…',lambda:open_preferences(runtime,'watermark'))
        watermark = marking.addAction('显示桌面文字水印')
        watermark.setCheckable(True)
        watermark.setChecked(tray.cfg['watermark_enabled'])
        def toggle_watermark(checked):
            if not save_changes(tray, runtime.api, {'watermark_enabled':checked}):
                watermark.setChecked(tray.cfg['watermark_enabled'])
        watermark.triggered.connect(toggle_watermark)
        from desktop_spectrum import add_menu_actions
        add_menu_actions(menu.addMenu('桌面音乐频谱'), runtime)
        from daily_picture_card import add_menu_actions as picture_actions
        picture_actions(menu.addMenu('每日图片'),runtime)
        menu.addAction('原生卡片编辑器…').triggered.connect(runtime.open_custom_cards)
    pause=menu.addMenu('组件暂停');pause.menuAction().setEnabled(runtime is not None)
    for title,key,callback in [('暂停桌面组件','game_mode',lambda on:runtime.set_desktop_paused(on) if runtime else None),
                               ('全屏自动暂停','fullscreen_detection',lambda on:runtime.set_fullscreen_pause(on) if runtime else None)]:
        action=pause.addAction(title);action.setCheckable(True);action.setChecked(tray.cfg[key]);action.triggered.connect(callback)


def help_actions(menu,tray,runtime):
    help_menu=menu.addMenu('帮助与更新')
    def refresh():
        tray.refresh_now()
        if runtime:
            runtime.clock.refresh_timer.start(50);runtime.calendar.refresh_timer.start(50)
            for manager in (runtime.panels,runtime.notes):
                for window in manager.windows.values():window.refresh_timer.start(50)
    help_menu.addAction('刷新玻璃背景').triggered.connect(refresh)
    help_menu.addAction('检查更新').triggered.connect(lambda:runtime.updater.check() if runtime else None)
    help_menu.addAction('使用说明').triggered.connect(tray.open_readme)


def rebuild(tray):
    tray.menu.clear_actions()
    common_actions(tray.menu, tray)
