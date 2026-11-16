"""Native shell appearance shortcuts shared by Dock and tray context menus."""
from PyQt5.QtWidgets import QActionGroup


def open_settings(runtime, page):
    runtime.show_settings()
    dialog = getattr(runtime.tray, 'settings_dialog', None)
    if dialog is not None:dialog.tabs.setCurrentIndex(page)


def add_menu(menu, runtime, kind):
    from settings_catalog import START_MENU, NOTIFICATIONS
    from settings_effects import save_changes
    from shell_appearance_model import START_STYLES, SOURCES
    cfg = runtime.dock.cfg
    supported = runtime.shell_appearance.supported
    prefix = 'shell_' + kind + '_'
    title = '开始菜单' if kind == 'start' else '通知与快捷面板'

    def toggle(parent, label, key):
        action = parent.addAction(label)
        action.setCheckable(True);action.setChecked(bool(cfg.get(key)))
        action.setEnabled(supported)
        action.triggered.connect(lambda enabled: save_changes(runtime.tray, runtime.api, {key: enabled}))
        return action

    def choose(parent, key, choices):
        group = QActionGroup(parent)
        group.setExclusive(True)
        for name, value in choices:
            action = parent.addAction(name)
            action.setCheckable(True)
            action.setChecked(cfg.get(key) == value)
            action.setEnabled(supported)
            group.addAction(action)
            action.triggered.connect(lambda _, value=value: save_changes(runtime.tray, runtime.api, {key: value}))

    if kind == 'start':
        choose(menu, prefix + 'enabled', START_STYLES)
    else:
        toggle(menu, '启用' + title + '美化', prefix + 'enabled')
        parts = menu.addMenu('美化范围')
        for part, name in (('quick','快速设置'),('media','媒体控制'),('toast','通知弹窗'),('calendar','日历')):
            toggle(parts, name, prefix + part)
    source = menu.addMenu('外观来源')
    source.setEnabled(supported)
    choose(source, prefix + 'source', SOURCES)
    menu.addSeparator()
    page = START_MENU if kind == 'start' else NOTIFICATIONS
    menu.addAction(title + '设置…', lambda: open_settings(runtime, page))
    retry = menu.addAction('重新应用外观', runtime.shell_appearance.retry)
    retry.setEnabled(supported and bool(cfg.get(prefix + 'enabled')))
    if not supported:
        item = menu.addAction('系统面板美化需要 Windows 11');item.setEnabled(False)
