"""Visible settings categories in reading order, independent of stacked-page IDs."""

# Existing page IDs are also used by component context menus.
FACE, SIZE, STATUS, MUSIC, MAIL, NEWS = range(10, 16)
CAPSULE_SECTIONS = (
    ('胶囊与桌面', (
        (0, '显示与展开', 'startup', '胶囊行为 置顶 置底 穿透 淡化 展开方式 默认页面 收起形态 任务栏固定'),
        (6, '位置与吸附', 'corner', '表情与吸附 拖动 锁定位置和大小 液态拉伸 贴边隐藏 应用窗口前收起 光条 圆球'),
        (4, '材质与光环', 'palette', '材质与配色 主题 透明度 徽标底色强度 小方块 图表颜色 光环流动速度'),
        (FACE, '表情与小动物', 'paw', '表情角色 跟随鼠标 定时切换 跑步小动物 企鹅 小鸟 动物形象 奔跑速度 监测指标'),
    )),
    ('显示内容', (
        (2, '收起内容与顺序', 'size', '收起显示 显示顺序 左中右 靠左 靠右 居中 排序 日期与时间 秒数 农历 资源读数'),
        (SIZE, '尺寸与翻页', 'size', '宽度 高度 色块高度 徽标高度 内容密度 自动翻页 读数轮换间隔 区域翻页'),
        (8, '栏目与独立卡片', 'panels', '组件布局 栏目顺序 拆出到桌面 独立卡片 空闲淡化'),
        (STATUS, '设备状态提醒', 'monitor', '键盘 大小写 中英文 小键盘 麦克风 触摸板 触控板 蓝牙 网络连接 系统音量 屏幕亮度 低电量 天气预警'),
    )),
    ('监控与媒体', (
        (5, '资源与硬件', 'monitor', '资源与阈值 CPU GPU 内存 网速 温度 电压 风扇 功率 采样 外设电量 电池 蓝牙'),
        (1, '任务栏监控', 'position', '任务栏读数 监控列 排序 字号 歌词 音乐封面'),
        (3, 'AI 用量与额度', 'wave', 'AI 与音乐 用量接口 余额 Token 托盘额度环 Codex 限额 提醒'),
        (MUSIC, '音乐与歌词', 'wave', '音乐预览 播放控制 歌词 频谱 媒体'),
    )),
    ('日历与订阅', (
        (9, '日程与计时', 'calendar', '日程与提醒 日历账号 农历节日 节气 番茄钟 喝水 正计时 闹钟 声音'),
        (7, '天气与空气质量', 'calendar', '天气与订阅 城市 位置 温度颜色 预报 空气质量 AQI'),
        (MAIL, '邮箱与通知', 'notes', '邮件通知 邮箱账号 收起邮箱图标 验证码 收件 来信 刷新周期'),
        (NEWS, '新闻订阅', 'notes', '订阅源 新闻 RSS Atom 编辑链接'),
    )),
)

PANEL_TABS = ('材质与文字', '布局与交互', '展开与收起', '表情与角色')
NOTE_TABS = ('材质与文字', '收起与交互')
CUSTOM_TABS = ('卡片内容', '排版与配图', '工具与接口')
PANEL_ORDER = (0, 2, 1, 3)
CLOCK_ORDER = (0, 3, 1, 2)


def clock_tabs(calendar=False):
    return ('样式与尺寸', '字体与配色', '背景材质', '农历与节假日' if calendar else '工作时间')
