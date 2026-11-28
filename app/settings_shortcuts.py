"""Component destinations shared by the settings menu and unified search."""
from functools import partial
from typing import NamedTuple

from component_preferences import COMPONENTS, open_preferences
from settings_sections import CAPSULE_SECTIONS, CLOCK_ORDER, CUSTOM_TABS, NOTE_TABS, PANEL_ORDER, PANEL_TABS, clock_tabs
from ui_style import AlignedMenu, menu_heading


class Shortcut(NamedTuple):
    key: str
    group: str
    parents: tuple
    title: str
    action: object
    keywords: str = ''

    def search_row(self):
        path = ' › '.join(title for _, title in self.parents)
        return dict(key=self.key, title=self.title.rstrip('…'), page=path, options=self.keywords)


def component_links(runtime, catalog):
    group = '胶囊与收纳'
    def link(owner, parents, key, title, action, words=''):
        return Shortcut(f'@editor/{owner}/{key}', group, parents, title, action, words)

    def pages(owner, parents, titles, open_page, words, order=None):
        for index in range(len(titles)) if order is None else order:
            yield link(owner, parents, index, titles[index], partial(open_page,index), words[index])

    def preferences(key):
        name, definitions = COMPONENTS[key]
        parent = ((key, name),)
        for index, (title, _, suffixes) in enumerate(definitions):
            words=' '.join(catalog.get(key+'_'+suffix, (None,'锁定位置与大小'))[1] for suffix in suffixes)
            yield link(key,parent,index,title,partial(open_preferences,runtime,key,index),words)

    for heading, rows in CAPSULE_SECTIONS:
        parent=(('resource','灵动胶囊'), (heading,heading))
        for index, title, _, words in rows:
            yield link('resource',parent,index,title,partial(runtime.resources.settings,index),words)
    yield from preferences('flash')

    cards=(('cards','桌面卡片'),)
    yield link('cards',cards,'shared','所有卡片的共享设置',lambda:runtime.tray.settings_dialog.focus_setting('panel_material'))
    yield link('cards',cards,'groups','分组与合并管理…',runtime.panels.manage_groups)
    yield link('cards',cards,'size','默认尺寸…',runtime.open_card_sizing)
    yield link('cards',cards,'title','标题文字…',partial(runtime.open_card_sizing,page=1))
    for identity,window in runtime.panels.windows.items():
        parent=cards+((identity,window.model['name']),)
        yield from pages('panel/'+identity,parent,PANEL_TABS,window.edit_options,
                         ('配色 字号 玻璃','分组 图标对齐 锁定 穿透 置顶 淡化','形状 圆球 胶囊 自动收起','小表情 鼠标跟随'),PANEL_ORDER)

    group='时间与记录'
    for name, key, widget in (('桌面时钟','clock',runtime.clock),('桌面日历','calendar',runtime.calendar)):
        parent=((key,name),)
        yield from pages(key,parent,clock_tabs(key=='calendar'),widget.open_settings,
                         ('样式布局 格式 宽高','文字配色 字号 字体','透明度 材质 配色','日历工作周 班次 节日'),CLOCK_ORDER)
        if key=='clock':
            yield link(key,parent,'progress','时光进度与倒计时…',widget.open_progress,'生日 发薪日 纪念日')
    notes=(('notes','便签'),)
    yield link('notes',notes,'manage','管理与搜索…',runtime.notes.manage)
    yield link('notes',notes,'default','新便签默认外观…',partial(open_preferences,runtime,'note'))
    for identity,window in runtime.notes.windows.items():
        parent=notes+((identity,window.row()['title'] or '未命名便签'),)
        yield from pages('note/'+identity,parent,NOTE_TABS,window.open_settings,
                         ('外观 正文字号 字体 主题 配色','鼠标离开 自动收起 锁定 置顶 淡化'))
    yield from pages('custom',(('custom','原生卡片'),),CUSTOM_TABS,runtime.open_custom_cards,
                     ('名称 内容 模板','布局 图片 字体','工具 参数 接口'))

    group='图片、声音与水印'
    for key in ('daily_picture','spectrum','watermark'):
        yield from preferences(key)


def shortcut_menu(dialog):
    menu=AlignedMenu(dialog)

    def populate():
        for action in menu.actions():
            if action.menu():action.menu().deleteLater()
        menu.clear()
        parents={():menu}
        current_group=None
        for entry in component_links(dialog.tray.runtime,dialog.catalog):
            if current_group!=entry.group:
                menu_heading(menu,entry.group)
                current_group=entry.group
            path=()
            for key,title in entry.parents:
                parent=parents[path]
                path=(*path,key)
                if path not in parents:parents[path]=parent.addMenu(title)
            parents[path].addAction(entry.title,lambda checked=False,callback=entry.action: dialog.open_secondary(callback))

    menu.aboutToShow.connect(populate)
    return menu
