"""Stable action IDs and user-defined ordering for Dock quick settings."""
from idle_fade_options import MODES as FADE_MODES
SHELL_ACTIONS = ('shell_start', 'shell_notifications')
SYSTEM_ACTIONS = (*SHELL_ACTIONS, 'cursor_styles')
ACTIONS=[('settings','全部设置','grid'),('taskbar','任务栏效果','position'),('taskbar_text','任务栏文字','text_color'),
         ('shell_start','开始菜单','start_menu'),('shell_notifications','通知面板','bell'),
         ('cursor_styles','鼠标样式','cursor'),('manage','应用管理','apps'),
         ('appearance','切换外观','palette'),('size','图标大小','size'),('position','停靠位置','position'),
         ('panels','桌面卡片','panels'),('magnify','图标放大','magnify'),
         ('notes','便签组件','notes'),('clock','时钟组件','clock'),('calendar','日历组件','calendar'),
         ('watermark','桌面水印','watermark'),
         ('reflections','图标倒影','reflection'),('dock_time','Dock 时间','clock'),('color_mode','明暗模式','palette'),
         ('blur','背景模糊','blur'),('panel_auto_hide','卡片收起','panels'),('corners','屏幕圆角','corner'),('add','添加入口','plus'),
         ('search','统一搜索','search'),('undo','撤销整理','undo'),
         ('layouts','布局方案','layouts'),('references','入口修复','repair'),('flash','闪念胶囊','flash'),('resources','灵动胶囊','monitor'),('taskbar_monitor','任务栏监控','monitor')]
PREVIOUS_ORDER = [key for key, _, _ in ACTIONS if key not in SYSTEM_ACTIONS]
OLD_PRIORITY_ORDER = [
    'flash', 'resources', 'taskbar_monitor', 'notes', 'clock', 'reflections', 'dock_time', 'calendar',
    'settings', 'taskbar', 'taskbar_text', 'manage', 'appearance', 'panels',
]
FIRST_PAGE_SETTINGS = ['settings', 'taskbar', 'taskbar_text', *SYSTEM_ACTIONS, 'manage', 'appearance', 'panels']
PRIORITY_ORDER = FIRST_PAGE_SETTINGS + [key for key in OLD_PRIORITY_ORDER if key not in FIRST_PAGE_SETTINGS]
PRIORITY_ORDER.insert(PRIORITY_ORDER.index('calendar')+1, 'watermark')
LEGACY_BASE = PRIORITY_ORDER + [key for key in PREVIOUS_ORDER if key not in PRIORITY_ORDER]
PREVIOUS_DEFAULT = [key for key in LEGACY_BASE if key != 'cursor_styles']
WIDGET_SWITCHES = {
    'almanac_alert': ('节气提醒','leaf','resource_alert_almanac','calendar','在收起胶囊中轮换显示节气、农历节日和公历节日'),
    'daily_picture': ('每日图片','picture','daily_picture_enabled','watermark','显示每日图片组件'),
    'card_snap': ('卡片吸附','snap_cards','card_snap',None,'拖动桌面卡片时吸附屏幕边缘和相邻卡片'),
    'card_lock': ('卡片锁定','card_lock','panel_locked',None,'锁定桌面收纳卡片的位置和大小'),
}
STYLE_ACTIONS = {
    'capsule_pet': ('胶囊小动物','paw'), 'tray_pet': ('托盘小动物','tray_paw'),
    'desktop_spectrum': ('桌面频谱','spectrum'), 'capsule_halo': ('胶囊光环','halo'),
}
GLOBAL_CYCLES = {
    'idle_fade': ('空闲淡化', 'fade', 'desktop_idle_fade_mode', FADE_MODES),
    'global_layer': ('全局层级', 'layers', 'desktop_layer_mode',
                     (('custom','自定义'), ('top','置顶'), ('bottom','置底'))),
    'global_passthrough': ('全局穿透', 'pointer_pass', 'passthrough_mode',
                           (('custom','自定义'), ('all','穿透'), ('none','不穿透'))),
}
ACTIONS.extend((key, spec[0], spec[1]) for options in (WIDGET_SWITCHES, GLOBAL_CYCLES, STYLE_ACTIONS)
               for key, spec in options.items())

# Keep related controls on one page even when the final two pages have empty cells.
QUICK_PAGES = (
    ('全局与外观', ('settings','global_layer','global_passthrough', 'appearance','color_mode','blur',
                 'idle_fade','corners','cursor_styles')),
    ('Dock 与系统面板', ('position','size','magnify', 'reflections','dock_time','taskbar',
                      'taskbar_text','shell_start','shell_notifications')),
    ('桌面卡片', ('panels','card_lock','card_snap', 'panel_auto_hide','notes','clock',
               'calendar','daily_picture','watermark')),
    ('胶囊与监控', ('resources','capsule_halo','capsule_pet', 'flash','almanac_alert','desktop_spectrum',
                 'taskbar_monitor','tray_pet')),
    ('入口与整理', ('add','manage','search', 'layouts','undo','references')),
)
DEFAULT_ORDER = [key for _, keys in QUICK_PAGES for key in keys]
PAGE_STARTS = tuple(DEFAULT_ORDER.index(keys[0]) for _, keys in QUICK_PAGES)


def page_for(index):
    return next(page for page in reversed(range(len(PAGE_STARTS))) if index >= PAGE_STARTS[page])
PRODUCTIVITY_ACTIONS=('search','undo','layouts','references','flash','resources','taskbar_monitor')
MIME='application/x-bigfishdock-quick-action'

# Stable IDs keep each function's colour when a tile is moved to another page.
TILE_TINTS = {
    'settings':'#6987ab', 'taskbar':'#398ccc', 'taskbar_text':'#8271c5',
    'shell_start':'#417fc4', 'shell_notifications':'#cc9043', 'cursor_styles':'#9974bc',
    'manage':'#398e88', 'appearance':'#bf7097', 'panels':'#358baf',
    'flash':'#c88643', 'resources':'#388e76', 'taskbar_monitor':'#4483a3',
    'notes':'#c59c45', 'clock':'#548bb7', 'calendar':'#bb746b',
    'watermark':'#7286a8', 'daily_picture':'#629775', 'capsule_pet':'#b7845c',
    'tray_pet':'#be8b65', 'almanac_alert':'#809c56', 'size':'#547fa8',
    'position':'#5d8b93', 'magnify':'#488f9e', 'reflections':'#6c87af',
    'dock_time':'#648cb9', 'color_mode':'#947db8', 'blur':'#5b9caa',
    'panel_auto_hide':'#678e7e', 'corners':'#8d80a6', 'add':'#57976d',
    'search':'#479899', 'undo':'#ab8464', 'layouts':'#758ab6', 'references':'#a37e55',
    'global_layer':'#647db5','idle_fade':'#58968c','global_passthrough':'#9272b3',
    'card_snap':'#668fbe','card_lock':'#ac8550',
    'desktop_spectrum':'#a16fa8','capsule_halo':'#578e9e',
}


def normalize_order(value):
    order=[]
    for key in value if isinstance(value,list) else []:
        if isinstance(key,str) and key in DEFAULT_ORDER and key not in order:order.append(key)
    # The previous default had Add on page one and Taskbar on the last page.
    previous_twenty = [key for key in PREVIOUS_ORDER if key not in PRODUCTIVITY_ACTIONS]
    old_default = [key for key in previous_twenty if key != 'taskbar_text']
    previous_default = list(old_default)
    previous_default[1], previous_default[-1] = previous_default[-1], previous_default[1]
    old_priority = OLD_PRIORITY_ORDER + [key for key in PREVIOUS_ORDER if key not in OLD_PRIORITY_ORDER]
    anchored = list(LEGACY_BASE)
    for key, anchor in (('capsule_pet','resources'), ('tray_pet','taskbar_monitor')):
        anchored.insert(anchored.index(anchor) + 1, key)
    for key, (_, _, _, anchor, _) in WIDGET_SWITCHES.items():
        if anchor:
            anchored.insert(anchored.index(anchor) + 1, key)
    old_orders = (PREVIOUS_ORDER, PREVIOUS_DEFAULT, previous_twenty, old_default, previous_default,
                  previous_default[:-1], old_priority, LEGACY_BASE, anchored)
    saved = set(order)
    optional = {*SYSTEM_ACTIONS,'taskbar_text','watermark','capsule_pet','tray_pet','almanac_alert','daily_picture'}
    if not order or any(set(layout)-saved <= optional and order == [key for key in layout if key in saved]
                        for layout in old_orders):
        return list(DEFAULT_ORDER)
    # Intermediate releases appended extra switches in several combinations.
    if order == anchored + ['card_snap','card_lock','desktop_spectrum','capsule_halo']:
        return list(DEFAULT_ORDER)
    if len(order) >= len(LEGACY_BASE) and order == [key for key in DEFAULT_ORDER if key in order]:
        return list(DEFAULT_ORDER)
    # Preserve a personal ordering. Introduce missing siblings next to the closest
    # preceding member of their own group; an entirely new group starts at the end.
    for _, group in QUICK_PAGES:
        anchor = None
        for key in group:
            if key not in order:
                if anchor is None:
                    order.append(key)
                else:
                    order.insert(order.index(anchor) + 1, key)
            anchor = key
    return order
