"""Stable action IDs and user-defined ordering for Dock quick settings."""
ACTIONS=[('settings','全部设置','grid'),('taskbar','任务栏效果','position'),('taskbar_text','任务栏文字','text_color'),('manage','应用管理','apps'),
         ('appearance','切换外观','palette'),('size','图标大小','size'),('position','停靠位置','position'),
         ('panels','桌面卡片','panels'),('magnify','图标放大','magnify'),('lite','精简模式','lite'),
         ('notes','便签组件','notes'),('clock','时钟组件','clock'),('calendar','日历组件','calendar'),
         ('reflections','图标倒影','reflection'),('dock_time','Dock 时间','clock'),('color_mode','明暗模式','palette'),
         ('blur','背景模糊','blur'),('panel_auto_hide','卡片收起','panels'),('corners','屏幕圆角','corner'),('add','添加应用','plus'),
         ('search','统一搜索','search'),('undo','撤销整理','undo'),
         ('layouts','布局方案','layouts'),('references','入口修复','repair')]
DEFAULT_ORDER=[key for key,_,_ in ACTIONS]
PRODUCTIVITY_ACTIONS=('search','undo','layouts','references')
MIME='application/x-bigfishdock-quick-action'


def normalize_order(value):
    order=[]
    for key in value if isinstance(value,list) else []:
        if isinstance(key,str) and key in DEFAULT_ORDER and key not in order:order.append(key)
    # The previous default had Add on page one and Taskbar on the last page.
    previous_twenty = [key for key in DEFAULT_ORDER if key not in PRODUCTIVITY_ACTIONS]
    old_default = [key for key in previous_twenty if key != 'taskbar_text']
    previous_default = list(old_default)
    previous_default[1], previous_default[-1] = previous_default[-1], previous_default[1]
    if order in (previous_twenty, old_default, previous_default, previous_default[:-1]):
        return list(DEFAULT_ORDER)
    # Insert the new control beside Taskbar without resetting a saved custom order.
    # Once explicitly arranged, its position is owned by the user.
    order += [key for key in DEFAULT_ORDER if key not in order and key != 'taskbar_text']
    if 'taskbar_text' not in order:order.insert(order.index('taskbar')+1,'taskbar_text')
    return order
