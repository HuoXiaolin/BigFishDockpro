"""Settings navigation and searchable field definitions without Qt widgets."""

PAGES = ('外观设置', '桌面收纳', '应用管理', '启动与运行', '更新设置', '使用统计', '关于与数据')


def field_catalog(api, cfg):
    from appearance_presets import COLOR_MODES, MATERIALS, material_choices
    from card_design import DESIGNS
    from flash_data import COLORS, PALETTES
    from settings_layout import MODES as SIZE_MODES
    from sticky_notes_store import STYLES
    from taskbar_appearance import MODES
    from taskbar_text import MODES as TEXT_MODES
    from feature_config import SPECTRUM_STYLES

    return {
        'dock_material': (0, '材质', 'combo', material_choices(cfg['dock_material'])),
        'theme': (0, '明暗模式', 'combo', COLOR_MODES),
        'theme_color': (0, '主题色', 'color', None),
        'dock_highlight': (0, '高光（%）', 'number', (0, 100)),
        'transparency': (0, '不透明度（%）', 'number', (0, 100)),
        'blur_px': (0, '模糊强度', 'number', (3, 30)),
        'icon_size': (0, '图标大小（像素）', 'number', (20, 256)),
        'glass': (0, '背景模糊', 'check', None),
        'clear_background': (0, '背景全透明', 'check', None),
        'blur_mode': (0, '壁纸取样刷新', 'combo', api.BLUR_MODES),
        'magnify': (0, '悬停放大图标', 'check', None),
        'motion_enabled': (0, '交互柔光动效', 'check', None),
        'bump_level': (0, '拉伸鼓包', 'combo', [(title, key) for key, title, _ in api.BUMP_LEVELS]),
        'position': (0, '停靠位置', 'combo', api.POSITIONS),
        'custom_bottom': (0, '自定义距底部（像素）', 'number', (0, 2000)),
        'bottom_margin': (0, '边缘距离（像素）', 'number', (0, 200)),
        'layer': (0, '窗口层级', 'combo', api.LAYERS),
        'show_name': (0, '悬停时显示应用名称', 'check', None),
        'sep_split': (0, '分隔符切开玻璃背景', 'check', None),
        'lang': (0, '原 Dock 菜单语言', 'combo', [(name, key) for name, key in api.LANGS]),
        'screen_corners': (0, '启用屏幕圆角', 'check', None),
        'corner_radius': (0, '屏幕圆角半径（像素）', 'number', (0, 120)),
        'taskbar_mode': (0, '任务栏效果', 'combo', MODES),
        'taskbar_text_mode': (0, '任务栏文字与系统图标', 'combo', TEXT_MODES),
        'taskbar_color': (0, '任务栏颜色', 'color', None),
        'taskbar_opacity': (0, '任务栏不透明度（%）', 'number', (0, 100)),
        'taskbar_blur': (0, '任务栏模糊强度', 'number', (0, 50)),
        'panel_enabled': (1, '显示桌面卡片', 'check', None),
        'desktop_auto_sort': (1, '按文件类型自动分类', 'check', None),
        'card_design': (1, '装饰样式', 'combo', DESIGNS),
        'panel_material': (1, '材质', 'combo', material_choices(cfg['panel_material'])),
        'panel_theme': (1, '明暗模式', 'combo', COLOR_MODES),
        'panel_color': (1, '主题色', 'color', None),
        'panel_highlight': (1, '高光（%）', 'number', (0, 100)),
        'panel_opacity': (1, '不透明度（%）', 'number', (0, 100)),
        'panel_blur': (1, '模糊强度', 'number', (2, 30)),
        'panel_locked': (1, '锁定卡片位置与大小', 'check', None),
        'card_snap': (1, '卡片吸附（屏幕边缘与相邻卡片）', 'check', None),
        'card_snap_distance': (1, '吸附距离（像素）', 'number', (2, 64)),
        'panel_auto_hide': (1, '鼠标离开后自动收起', 'check', None),
        'panel_expand_mode': (1, '展开方式', 'combo', [('鼠标移入', 'hover'), ('点击展开', 'click')]),
        'panel_face': (1, '显示小表情（展开与收起均保留）', 'check', None),
        'panel_face_interactive': (1, '表情跟随鼠标与按压互动（精简模式保留）', 'check', None),
        'panel_face_mood': (1, '表情样式', 'combo', [('随机变化', 'random'), ('默认', 'default'), ('开心', 'happy'), ('眨眼', 'wink'), ('爱心', 'love'), ('星星眼', 'star'), ('害羞', 'shy'), ('嘟嘴', 'pout'), ('眯眼', 'squint')]),
        'panel_face_scale': (1, '表情大小（%）', 'number', (60, 130)),
        'panel_collapse_style': (1, '收起形状', 'combo', [('胶囊', 'capsule'), ('圆球', 'ball'), ('方条', 'bar')]),
        'panel_capsule_ratio': (1, '胶囊宽度比例（%）', 'number', (30, 100)),
        'desktop_icon_mode': (1, '桌面图标显示', 'combo', [('桌面与卡片同时显示', 'both'), ('隐藏全部桌面图标', 'hide_all')]),
        'desktop_middle_toggle': (1, '鼠标中键切换桌面图标', 'check', None),
        'clock_enabled': (1, '桌面时钟', 'check', None),
        'calendar_enabled': (1, '桌面日历', 'check', None),
        'spectrum_enabled': (1, '桌面音乐频谱', 'check', None),
        'spectrum_style': (1, '频谱样式', 'combo', SPECTRUM_STYLES),
        'spectrum_color_mode': (1, '频谱配色', 'combo', [('炫彩','colorful'),('单色','mono')]),
        'spectrum_mono_color': (1, '频谱单色', 'color', None),
        'daily_picture_enabled': (1, '桌面每日图片', 'check', None),
        'daily_picture_material': (1, '每日图片外框材质', 'combo', [('跟随应用','follow'), *MATERIALS]),
        'daily_picture_color': (1, '每日图片外框颜色', 'color', None),
        'daily_picture_source': (1, '每日图片来源', 'combo', [('必应每日图片','bing'),('本地图片轮播','local')]),
        'daily_picture_interval': (1, '本地轮播间隔（秒）', 'number', (5,3600)),
        'notes_enabled': (1, '便签卡片', 'check', None),
        'note_style': (1, '新便签装饰样式', 'combo', STYLES),
        'flash_enabled': (1, '显示贴边胶囊', 'check', None),
        'flash_palette': (1, '胶囊配色', 'combo', PALETTES),
        'flash_color': (1, '新闪念颜色', 'combo', [(name, key) for key, (name, _) in COLORS.items()]),
        'flash_side': (1, '停靠边缘', 'combo', [('右侧', 'right'), ('左侧', 'left')]),
        'flash_edge_hide': (1, '贴边隐藏入口，悬停时滑出', 'check', None),
        'flash_drop': (1, '拖入选中文字生成闪念', 'check', None),
        'flash_auto_hide': (1, '鼠标离开后自动收起', 'check', None),
        'flash_delay': (1, '收起延迟（秒）', 'number', (1, 30)),
        'resource_enabled': (1, '显示资源胶囊', 'check', None),
        'resource_taskbar': (1, '显示任务栏监控', 'check', None),
        'resource_bt_tray': (1, '蓝牙电量托盘图标', 'check', None),
        'resource_ai_tray': (1, 'AI 用量托盘图标', 'check', None),
        'reorder': (2, '允许拖动 Dock 图标排序', 'check', None),
        'running_dots': (2, '显示 Dock 应用的运行标记', 'check', None),
        'lite_enabled': (3, '关闭设置 1 分钟后自动精简', 'check', None),
        'hide_tray': (3, '隐藏托盘图标', 'check', None),
        'autostart': (3, '开机自动启动', 'check', None),
        'startup_priority': (3, '进程优先级', 'combo', [('低（节省后台竞争）', 'low'), ('普通', 'normal'), ('较高（非实时）', 'high')]),
        'startup_delay': (3, '登录后延迟（秒）', 'number', (0, 300)),
        'game_mode': (3, '游戏模式', 'check', None),
        'fullscreen_detection': (3, '全屏时自动隐藏 Dock 和卡片', 'check', None),
        'check_updates_on_start': (4, '启动时检查更新', 'check', None),
        'update_use_proxy': (4, '使用系统 / 环境代理', 'check', None),
        'update_source': (4, '安装包发布 / 更新地址', 'text', None),
        'dock_reflections': (0, '图标倒影', 'check', None),
        'dock_clock': (0, '时间', 'check', None),
        'dock_quick_settings': (0, '九宫格', 'check', None),
        'dock_add_button': (0, '＋ 添加', 'check', None),
        'card_scale': (1, '卡片整体缩放（%）', 'number', (50,150)),
        'settings_size': (-1, '设置窗口大小', 'combo', SIZE_MODES),
    }


def targets(catalog):
    result = []
    for key, (page, title, kind, options) in catalog.items():
        if key == 'card_design':
            continue
        result.append(dict(key=key, title=title, page=PAGES[page] if page >= 0 else '设置',
                           options=' '.join(name for name, _ in options) if kind == 'combo' else ''))
    for key, title in (('@clock', '时钟字体与布局'), ('@calendar', '日历设计与节假日'),
                       ('@notes', '便签管理与搜索'), ('@groups', '卡片分组与合并'),
                       ('@layouts', '桌面布局方案'), ('@references', '失效入口检查')):
        result.append(dict(key=key, title=title, page='组件与整理', options=''))
    return result
