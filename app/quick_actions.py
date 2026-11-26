"""Stable action IDs and user-defined ordering for Dock quick settings."""
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
DEFAULT_ORDER = PRIORITY_ORDER + [key for key in PREVIOUS_ORDER if key not in PRIORITY_ORDER]
PREVIOUS_DEFAULT = [key for key in DEFAULT_ORDER if key != 'cursor_styles']
WIDGET_SWITCHES = {
    'capsule_pet': ('胶囊小动物','paw','resource_runner_enabled','resources','收起胶囊时显示小动物'),
    'tray_pet': ('托盘小动物','tray_paw','resource_tray_runner_enabled','taskbar_monitor','在系统托盘显示小动物'),
    'almanac_alert': ('节气提醒','leaf','resource_alert_almanac','calendar','在灵动胶囊显示农历节气与节日提醒'),
    'daily_picture': ('每日图片','picture','daily_picture_enabled','watermark','显示每日图片组件'),
}
for key,(title,icon,field,anchor,tip) in WIDGET_SWITCHES.items():
    ACTIONS.append((key,title,icon))
    DEFAULT_ORDER.insert(DEFAULT_ORDER.index(anchor)+1,key)
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
    old_orders = (PREVIOUS_ORDER, PREVIOUS_DEFAULT, previous_twenty, old_default, previous_default, previous_default[:-1], old_priority)
    if not order or order in old_orders or any(order == [key for key in layout if key != 'watermark'] for layout in old_orders):
        return list(DEFAULT_ORDER)
    # Add missing system controls in functional order, leaving saved positions intact.
    order += [key for key in PREVIOUS_ORDER if key not in order and key not in ('taskbar_text','watermark')]
    if 'watermark' not in order:
        order.insert(order.index('calendar')+1, 'watermark')
    anchor = 'taskbar'
    for key in ('taskbar_text', *SYSTEM_ACTIONS):
        if key not in order:
            order.insert(order.index(anchor) + 1, key)
        anchor = key
    order.extend(key for key in WIDGET_SWITCHES if key not in order)
    return order
