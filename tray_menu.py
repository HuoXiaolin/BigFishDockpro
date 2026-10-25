"""Shared, task-grouped commands for tray and Dock context menus."""
from PyQt5.QtWidgets import QApplication


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
    if not dock_context:
        action=menu.addAction('显示 / 隐藏 Dock');action.setCheckable(True);action.setChecked(tray.dock.isVisible())
        action.triggered.connect(lambda:runtime.toggle_dock() if runtime else None)
    menu.addAction('应用批量管理…').triggered.connect(lambda:runtime.show_batch() if runtime else tray.importer.show())
    layout=menu.addMenu('Dock 布局');separator_actions(layout,tray,insert_at)
    if getattr(tray.dock,'page_count',1)>1:
        layout.addSeparator();layout.addAction('上一页').triggered.connect(lambda:tray.dock.change_page(-1));layout.addAction('下一页').triggered.connect(lambda:tray.dock.change_page(1))
    panels=menu.addMenu('桌面卡片');panels.menuAction().setEnabled(runtime is not None)
    visible=panels.addAction('显示 / 隐藏桌面卡片');visible.setCheckable(True)
    visible.setChecked(bool(runtime and any(window.isVisible() for window in runtime.panels.windows.values())))
    visible.triggered.connect(lambda:runtime.toggle_panels() if runtime else None)
    panels.addSeparator();panels.addAction('新建面板…').triggered.connect(lambda:runtime.panels.new_panel() if runtime else None)
    panels.addAction('分组与合并管理…').triggered.connect(lambda:runtime.panels.manage_groups() if runtime else None)
    panels.addAction('尺寸与文字…').triggered.connect(lambda:runtime.open_card_sizing() if runtime else None)
    panels.addAction('重新整理桌面').triggered.connect(lambda:runtime.panels.scan() if runtime else None)
    notes=menu.addMenu('便签');notes.menuAction().setEnabled(runtime is not None)
    notes.addAction('新建便签').triggered.connect(lambda:runtime.notes.new() if runtime else None)
    notes.addAction('管理与搜索…').triggered.connect(lambda:runtime.notes.manage() if runtime else None)
    action=notes.addAction('显示 / 隐藏便签');action.setCheckable(True)
    action.setChecked(bool(runtime and any(window.isVisible() for window in runtime.notes.windows.values())))
    action.triggered.connect(lambda:runtime.notes.toggle() if runtime else None)
    modes=menu.addMenu('运行模式');modes.menuAction().setEnabled(runtime is not None)
    for title,state,callback in [('精简模式',bool(runtime and runtime.lite),lambda checked:runtime.set_lite(checked) if runtime else None),('游戏模式',tray.cfg.get('game_mode',False),lambda checked:runtime.toggle_game(checked) if runtime else None)]:
        action=modes.addAction(title);action.setCheckable(True);action.setChecked(state);action.triggered.connect(callback)
    menu.addSeparator();menu.addAction('设置…').triggered.connect(lambda:runtime.show_settings() if runtime else tray.show_settings())
    help_menu=menu.addMenu('帮助与更新')
    def refresh():
        tray.refresh_now()
        if runtime:
            for manager in (runtime.panels,runtime.notes):
                for window in manager.windows.values():window.refresh_timer.start(50)
    help_menu.addAction('刷新玻璃背景').triggered.connect(refresh)
    help_menu.addAction('检查更新').triggered.connect(lambda:runtime.updater.check() if runtime else None)
    help_menu.addAction('使用说明').triggered.connect(tray.open_readme)
    menu.addSeparator()
    if dock_context:menu.addAction('隐藏 Dock').triggered.connect(lambda:runtime.set_dock_visible(False) if runtime else tray.dock.hide())
    menu.addAction('退出').triggered.connect(lambda:runtime.request_exit() if runtime else QApplication.instance().quit())


def rebuild(tray):
    tray.menu.clear();common_actions(tray.menu,tray)
