"""Compact, task-ordered tray menu. Detailed options live in Settings."""
from PyQt5.QtWidgets import QApplication


def rebuild(tray):
    menu = tray.menu
    menu.clear()
    runtime = getattr(tray, 'runtime', None)
    action = menu.addAction('显示 / 隐藏 Dock')
    action.setCheckable(True)
    action.setChecked(tray.dock.isVisible())
    action.triggered.connect(lambda: runtime.toggle_dock() if runtime else None)
    menu.addAction('显示 / 隐藏桌面面板').triggered.connect(lambda: runtime.toggle_panels() if runtime else None)
    menu.addAction('应用批量管理…').triggered.connect(lambda: runtime.show_batch() if runtime else tray.importer.show())
    menu.addSeparator()
    menu.addAction('设置…').triggered.connect(lambda: runtime.show_settings() if runtime else tray.show_settings())
    modes = menu.addMenu('运行模式')
    lite = modes.addAction('精简模式')
    lite.setCheckable(True)
    lite.setChecked(bool(runtime and runtime.lite))
    lite.triggered.connect(lambda checked: runtime.set_lite(checked) if runtime else None)
    game = modes.addAction('游戏模式')
    game.setCheckable(True)
    game.setChecked(tray.cfg.get('game_mode', False))
    game.triggered.connect(lambda checked: runtime.toggle_game(checked) if runtime else None)
    tools = menu.addMenu('更多工具')
    tools.addAction('分组与分页管理…').triggered.connect(lambda: runtime.panels.manage_groups() if runtime else None)
    tools.addAction('新建桌面面板…').triggered.connect(lambda: runtime.panels.new_panel() if runtime else None)
    notes=tools.addMenu('便签卡片')
    notes.addAction('新建便签').triggered.connect(lambda: runtime.notes.new() if runtime else None)
    notes.addAction('便签管理与搜索…').triggered.connect(lambda: runtime.notes.manage() if runtime else None)
    notes.addAction('显示 / 隐藏全部便签').triggered.connect(lambda: runtime.notes.toggle() if runtime else None)
    tools.addAction('重新整理桌面').triggered.connect(lambda: runtime.panels.scan() if runtime else None)
    tools.addAction('添加分隔符').triggered.connect(tray.add_separator)
    if getattr(tray.dock, 'page_count', 1) > 1:
        tools.addAction('Dock 上一页').triggered.connect(lambda: tray.dock.change_page(-1))
        tools.addAction('Dock 下一页').triggered.connect(lambda: tray.dock.change_page(1))
    def refresh_glass():
        tray.refresh_now()
        if runtime:
            for window in runtime.panels.windows.values(): window.refresh_timer.start(50)
    tools.addAction('刷新玻璃背景').triggered.connect(refresh_glass)
    tools.addAction('检查更新').triggered.connect(lambda: runtime.updater.check() if runtime else None)
    tools.addAction('使用说明').triggered.connect(tray.open_readme)
    menu.addSeparator()
    menu.addAction('退出').triggered.connect(lambda: runtime.request_exit() if runtime else QApplication.instance().quit())
