"""Stable action IDs and user-defined ordering for Dock quick settings."""
ACTIONS=[('settings','全部设置','grid'),('add','添加应用','plus'),('manage','应用管理','apps'),
         ('appearance','切换外观','palette'),('size','图标大小','size'),('position','停靠位置','position'),
         ('panels','桌面卡片','panels'),('magnify','图标放大','magnify'),('lite','精简模式','lite'),
         ('notes','便签组件','notes'),('clock','时钟组件','clock'),('calendar','日历组件','calendar'),
         ('reflections','图标倒影','reflection'),('dock_time','Dock 时间','clock'),('color_mode','明暗模式','palette'),
         ('blur','背景模糊','blur'),('panel_auto_hide','卡片收起','panels'),('corners','屏幕圆角','corner')]
DEFAULT_ORDER=[key for key,_,_ in ACTIONS]
MIME='application/x-bigfishdock-quick-action'


def normalize_order(value):
    order=[]
    for key in value if isinstance(value,list) else []:
        if isinstance(key,str) and key in DEFAULT_ORDER and key not in order:order.append(key)
    return order+[key for key in DEFAULT_ORDER if key not in order]
