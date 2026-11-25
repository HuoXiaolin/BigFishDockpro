"""Direct links from the main settings window to the actual component editors."""
from functools import partial

from component_preferences import COMPONENTS, open_preferences
from ui_style import AlignedMenu


def shortcut_menu(dialog):
    menu = AlignedMenu(dialog)

    def populate():
        # Rebuild instance lists when opened, including changes made while settings is open.
        for action in menu.actions():
            if action.menu():
                action.menu().deleteLater()
        menu.clear()
        runtime = dialog.tray.runtime

        def link(parent, title, callback):
            parent.addAction(title, lambda checked=False: dialog.open_secondary(callback))

        def pages(parent, titles, open_page):
            for index, title in enumerate(titles):
                link(parent, title, partial(open_page, index))

        cards = menu.addMenu('桌面卡片')
        link(cards, '所有卡片的共享设置', partial(dialog.focus_setting, 'panel_material'))
        windows = list(runtime.panels.windows.values())
        for window in windows:
            card = cards.addMenu(window.model['name'])
            pages(card, ('材质与配色','显示与交互','展开与收起','表情与角色'), window.edit_options)
        cards.addSeparator()
        link(cards, '分组与合并管理…', runtime.panels.manage_groups)
        link(cards, '默认尺寸…', runtime.open_card_sizing)
        link(cards, '标题文字…', partial(runtime.open_card_sizing, page=1))
        notes = menu.addMenu('便签')
        link(notes, '新便签默认外观…', partial(open_preferences, runtime, 'note'))
        for window in runtime.notes.windows.values():
            note = notes.addMenu(window.row()['title'] or '未命名便签')
            pages(note, ('材质与配色', '文字与交互'), window.open_settings)
        link(notes, '管理与搜索…', runtime.notes.manage)
        for name, widget, last in [('桌面时钟',runtime.clock,'工作时间'), ('桌面日历',runtime.calendar,'农历与节假日')]:
            sub = menu.addMenu(name)
            pages(sub, ('样式布局','文字配色','材质',last), widget.open_settings)
            if widget is runtime.clock:
                link(sub, '时光进度与倒计时…', widget.open_progress)
        from resource_settings import NAV_GROUPS, PAGE_NAMES
        resources = menu.addMenu('灵动胶囊')
        for pos, (_, indices) in enumerate(NAV_GROUPS):
            if pos: resources.addSeparator()
            for index in indices:
                link(resources, PAGE_NAMES[index], partial(runtime.resources.settings, index))
        for key in ('flash', 'spectrum', 'daily_picture', 'watermark'):
            name, definitions = COMPONENTS[key]
            sub = menu.addMenu(name)
            pages(sub, [item[0] for item in definitions], partial(open_preferences, runtime, key))
        pages(menu.addMenu('原生卡片'), ('内容', '排版与配图', '工具与接口'), runtime.open_custom_cards)

    menu.aboutToShow.connect(populate)
    return menu
