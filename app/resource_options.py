"""Portable resource display preferences; live measurements are never stored."""
import re
from content_sources import NEWS_FEED_PRESETS, clean_feeds
from screen_layout import valid_record
from spectrum_palettes import SPECTRUM_COLOR_MODES

RUNNER_ANIMALS = {'cat': '小猫', 'dog': '小狗', 'rabbit': '小兔', 'bird':'小鸟', 'penguin':'小企鹅'}
RUNNER_FIXED_RATES = {'fixed_low': ('低', 24), 'fixed_medium': ('中', 48), 'fixed_high': ('高', 96)}
RUNNER_SPEEDS = {'adaptive': '跟随占用率'}
RUNNER_SPEEDS.update({key: f'匀速 · {label}（{fps:g} 帧/秒）' for key, (label, fps) in RUNNER_FIXED_RATES.items()})
LEGACY_RUNNER_SPEEDS = {
    'cpu': 'adaptive', 'low': 'fixed_low', 'medium': 'fixed_low', 'high': 'fixed_medium',
    'fixed_140ms': 'fixed_low', 'fixed_80ms': 'fixed_medium', 'fixed_50ms': 'fixed_high',
}
RUNNER_METRICS = {'cpu': 'CPU', 'gpu': 'GPU', 'memory': '内存', 'disk_activity': '磁盘', 'network_utilization': '网络'}
RUNNER_SLOT = 26

DEVICE_SOURCES = {
    'gpu': ('gpu', 'GPU', '自动 · 最忙 GPU'),
    'disk_activity': ('disk', '磁盘', '自动 · 最忙磁盘'),
    'network_utilization': ('net', '网卡', '自动 · 最忙网卡'),
    'display': ('display', '显示器', '自动 · 内屏亮度优先 / 前台屏桌面帧率'),
}
MONITOR_DEVICES = {'gpu': 'resource_gpu_device', 'network': 'resource_network_device',
                   'disk_activity': 'resource_disk_device', 'display': 'resource_display_device'}
DEVICE_SAMPLE_KEYS = {'gpu': 'gpu_devices', 'disk_activity': 'disk_devices',
                      'network_utilization': 'network_devices', 'network': 'network_devices'}


def valid_device(value, metric):
    source = DEVICE_SOURCES.get(metric)
    return bool(isinstance(value, str) and source and re.fullmatch(source[0] + r':[0-9a-f]{32}', value))


METRICS={'cpu':'CPU','memory':'内存','network':'网速','gpu':'GPU','rank':'高占用进程','bluetooth':'外设电量','system_status':'电脑状态','fps':'帧率 FPS','cpu_temp':'CPU 温度',
         'gpu_temp':'GPU 温度','cpu_power':'CPU 功率','gpu_power':'GPU 功率','traffic':'流量统计','disk_activity':'磁盘活动'}
METRICS.update(cpu_frequency='CPU 频率',cpu_voltage='CPU 电压',cpu_fan='CPU 风扇',cpu_pump='CPU 水泵',
               gpu_frequency='GPU 频率',gpu_fan='GPU 风扇',gpu_memory='显存占用',disk_temp='磁盘温度',
               board_temp='主板温度',case_temp='机箱温度',board_fan='主板风扇')
FAN_METRICS=('cpu_fan','gpu_fan','board_fan')
SENSOR_UNITS={key:unit for unit,keys in [('°C',('cpu_temp','gpu_temp','disk_temp','board_temp','case_temp')),('W',('cpu_power','gpu_power')),
                                      ('MHz',('cpu_frequency','gpu_frequency')),('V',('cpu_voltage',)),('RPM',(*FAN_METRICS,'cpu_pump')),('%',('gpu_memory',))] for key in keys}
TASK_METRICS=('cpu_temp','gpu_temp','memory','network','cpu_power','gpu_power','fps','cpu','gpu','traffic')
TASK_DEFAULT=list(TASK_METRICS[:7])
TASK_METRICS+=tuple(k for k in SENSOR_UNITS if k not in TASK_METRICS)+('disk_activity',)
TASK_COLUMN_NAMES = {
    'cpu_temp': 'CPU 温度 / 功耗', 'gpu_temp': 'GPU 温度 / 功耗',
    'memory': '内存 / 帧率', 'network': '上下行网速',
    'cpu': 'CPU / GPU 使用率', 'traffic': '日 / 月 / 年流量',
    'sensors': '其他传感器',
}
COMPACT_METRICS=tuple(k for k in METRICS if k not in ('rank','system_status'))
COMPACT_DEVICE={'battery':'电池电量','connection':'网卡名称','volume':'系统音量','brightness':'屏幕亮度'}
COMPACT_STATUS=(*COMPACT_DEVICE,'bluetooth')
COMPACT_ROUTINES={'pomodoro':'番茄钟','water':'喝水进度','agenda':'下一项日程'}
COMPACT_ITEMS={**{key:METRICS[key] for key in COMPACT_METRICS},**COMPACT_DEVICE,**COMPACT_ROUTINES}
COMPACT_CONTENT={'ai':'resource_compact_ai','music':'resource_compact_music','weather':'resource_weather_compact'}
PINNABLE={**{key:title for key,title in COMPACT_ITEMS.items() if key not in COMPACT_STATUS},
          'ai':'AI 额度','music':'音乐','weather':'天气'}
COMPACT_CLOCK_FORMATS={
    'time':('时:分',('%H:%M',)), 'seconds':('时:分:秒',('%H:%M:%S',)),
    'date':('年-月-日',('%Y-%m-%d',)),
    'date_time':('年-月-日 / 时:分',('%Y-%m-%d','%H:%M')),
    'date_seconds':('年-月-日 / 时:分:秒',('%Y-%m-%d','%H:%M:%S')),
}
WEATHER_THRESHOLDS=(0,16,26,30)
RESOURCE_PAGES={'resources':'资源','ai':'AI','music':'音乐','traffic':'流量','weather':'天气',
                'pomodoro':'番茄钟','agenda':'日程','news':'新闻','mail':'邮件'}
DESKTOP_COMPONENTS={'notes':'便签','picture':'每日图片','custom':'原生卡片','clock':'时钟','calendar':'日历'}
PLACED_COMPONENTS={**RESOURCE_PAGES,**DESKTOP_COMPONENTS}
CAPSULE_PAGES=PLACED_COMPONENTS
OPEN_PAGES={'last':'上次查看的页面',**CAPSULE_PAGES}
CONTENT_COLUMN_BREAKPOINT=360
TASKBAR_LAYERS={'bottom':'置底','top':'置顶'}
CAPSULE_TASKBAR_POSITIONS={'left':'靠左','center':'居中','right':'靠右','custom':'记住拖放位置'}
HALO_SPEEDS={'slow':('慢速',12), 'medium':('中速',8), 'fast':('快速',4)}
HALO_COLOR_MODES = (('原版彩虹', 'rainbow'), *SPECTRUM_COLOR_MODES)
TASK_MEDIA_PARTS={'cover':'封面图标','title':'曲名','controls':'播放按钮','wave':'声音律动 / 频谱','progress':'进度细线'}
AI_PROVIDERS=('Claude','Codex','Cursor','Antigravity','ZCode','Dsh','Kimi','OpenCode','Pi','GrokBot')
AI_PROVIDER_NAMES={'Dsh':'DeepSeek Harness','GrokBot':'Grok Bot'}
TINTS={'cpu':'#288bee','memory':'#22bba9','network':'#27b8c4','gpu':'#ec79a6'}
TIMER_RANGES={
    'resource_focus_minutes':(1,120), 'resource_break_minutes':(1,60),
    'resource_water_interval':(5,240), 'resource_water_amount':(50,1000),
    'resource_water_goal':(250,5000),
}
DEVICE_ALERTS = {
    'caps_lock': '大小写锁定', 'input_mode': '中英文输入', 'num_lock': '数字小键盘',
    'microphone': '麦克风静音状态', 'touchpad': '触控板开关',
    'bluetooth_link': '蓝牙设备连接', 'network_link': '网络连接',
}
REMINDER_OPTIONS={
    'resource_alert_agenda':'日程到提醒时间', 'resource_alert_focus':'番茄钟倒计时与完成',
    'resource_alert_water':'喝水时间到', 'resource_alert_battery':'电脑电量低于或等于 15%',
    'resource_alert_almanac':'农历节气与节日',
    'resource_alert_mail_code':'收起时显示邮箱验证码',
    'resource_alert_weather':'雨、雪、雾和雷雨',
}
REMINDER_OPTIONS.update({'resource_alert_'+key: title for key,title in DEVICE_ALERTS.items()})
COMPACT_BADGE_HEIGHT_RANGE=(16,40)
MAIL_INTERVAL_RANGE=(10,900)
FACE_SWITCH_RANGE = (1, 1440)
FACE_SWITCH_DEFAULT = 10


def content_columns(window_width):
    return 1 if window_width <= CONTENT_COLUMN_BREAKPOINT else 2


DEFAULTS=dict(resource_enabled=False,resource_layer='bottom',resource_click_through=False,resource_auto_hide=True,resource_air_source='auto',
              resource_fold='pill',resource_collapsed=True,resource_layout={},resource_delay=3,
              resource_capsule_taskbar=False,resource_capsule_taskbar_position='custom',resource_capsule_taskbar_anchor={},
              resource_interval=2,resource_taskbar=False,resource_taskbar_position='right',resource_taskbar_layer='bottom',
              resource_taskbar_anchor={},resource_taskbar_click_through=False,resource_task_metrics=TASK_DEFAULT,resource_background='global',resource_backdrop_mode='dynamic',resource_appearance={},resource_palette='theme',resource_tints={},resource_bt_tray=False)
DEFAULTS.update({'resource_'+key:key in ('cpu','memory','network','gpu','rank',*FAN_METRICS) for key in METRICS})
DEFAULTS.update(resource_system_status=True,resource_peripheral_profiles=[],resource_pomodoro=True,resource_focus_minutes=25,resource_break_minutes=5,
                resource_water_enabled=False,resource_water_interval=45,resource_water_amount=250,resource_water_goal=2000)
DEFAULTS.update(resource_agenda=True,resource_agenda_events=[],resource_alert_agenda=True,resource_alert_focus=True,
                resource_alert_water=True,resource_alert_battery=False,resource_alert_almanac=True,resource_reminder_sound=True)
DEFAULTS.update(resource_runner_enabled=False, resource_runner_animal='cat', resource_runner_speed='adaptive', resource_runner_metric='cpu',
                resource_tray_runner_enabled=False, resource_tray_runner_animal='cat', resource_tray_runner_speed='adaptive', resource_tray_runner_metric='cpu')
DEFAULTS.update(dict.fromkeys((*MONITOR_DEVICES.values(), 'resource_runner_device', 'resource_tray_runner_device'), ''))
DEFAULTS.update(resource_traffic=True,resource_app_traffic=False,resource_task_font=11,resource_task_threshold=False,resource_threshold=True,resource_halo=True,resource_halo_speed='medium',
                resource_halo_color_mode='rainbow',resource_halo_mono_color='',
                resource_liquid=True,resource_edge_snap=True,resource_peer_snap=True,resource_edge='free',resource_face=True,
                resource_expand_mode='hover',resource_open_page='last',resource_face_interactive=True,resource_face_mood='random',resource_face_role='',resource_face_scale=100,
                resource_face_auto_switch=False,resource_face_switch_minutes=FACE_SWITCH_DEFAULT,
                resource_weather=False,resource_alert_weather=True,resource_weather_location=True,resource_weather_alert_sound=False,
                resource_weather_cities=[],resource_weather_compact=True,resource_weather_days=3,
                resource_weather_thresholds=list(WEATHER_THRESHOLDS),
                 resource_news=False,resource_news_feeds=[url for _,url in NEWS_FEED_PRESETS],resource_news_disabled_feeds=[],
                resource_task_music=True,resource_task_music_colorful=False,resource_task_media_parts=list(TASK_MEDIA_PARTS),
                resource_hide_unavailable=True,resource_limits={},resource_task_order=list(TASK_COLUMN_NAMES),
                resource_compact_width=500,resource_compact_height=35,resource_compact_badge_height=20,resource_compact_metrics=list(COMPACT_METRICS),
                resource_compact_auto_width=True,resource_compact_pinned=['cpu','memory','gpu','network'],resource_compact_order=[],
                resource_compact_ai=True,resource_compact_music=True,
                resource_compact_density='dense',
                resource_expanded_width=500,resource_expanded_height=280,
                resource_compact_rings=True,resource_clock=True,resource_clock_format='time',resource_compact_rotate=True,
                resource_ai=False,resource_ai_tray=False,resource_ai_providers=['Claude','Codex','Cursor','Antigravity'],
                resource_ai_tray_mode='auto',resource_ai_tray_provider='',resource_ai_tray_metric='',
                resource_music=False,resource_music_text='wave',resource_lyrics=True,resource_equalizer='flow',
                resource_quota_alert=True)
DEFAULTS.update(resource_component_locations={},resource_component_order=list(CAPSULE_PAGES),resource_card_layouts={},
                resource_card_transparency=20)
DEFAULTS.update(resource_mail=False, resource_mail_accounts=[], resource_mail_notifications=True,
                resource_alert_mail_code=True, resource_mail_icon=False, resource_mail_interval=30)
DEFAULTS.update(dict.fromkeys(('resource_alert_'+key for key in DEVICE_ALERTS), False))
DEFAULTS.update(resource_edge_hide=False, resource_alert_stopwatch=True, resource_alert_alarm=True)


def component_location(cfg,key):
    default='desktop' if key in DESKTOP_COMPONENTS else 'capsule'
    return cfg.get('resource_component_locations',{}).get(key,default)


def component_available(cfg,key):
    if key=='resources':return True
    if key=='notes':
        return cfg['notes_enabled'] and cfg['notes_visible'] and any(row['visible'] for row in cfg['sticky_notes'])
    if key=='custom':return any(row['visible'] for row in cfg['custom_cards'])
    if key=='picture':return cfg['daily_picture_enabled']
    if key in ('clock','calendar'):return cfg[key+'_enabled']
    if key=='ai':return cfg['resource_ai'] or cfg['resource_ai_tray']
    return cfg['resource_'+key]


def resource_page_active(cfg,key):
    return component_available(cfg,key) and (cfg['resource_enabled'] or component_location(cfg,key)=='desktop')


def calendar_data_active(cfg):
    return resource_page_active(cfg,'agenda') or bool(cfg.get('calendar_enabled') and cfg['resource_agenda'])


def migrate_runner_placement(cfg):
    placement = cfg.pop('resource_runner_placement')
    cfg['resource_runner_enabled'] = placement == 'capsule'
    cfg['resource_tray_runner_enabled'] = placement == 'tray'
    if placement == 'tray':
        for field in ('animal', 'speed'):
            key = 'resource_runner_' + field
            cfg['resource_tray_runner_' + field] = cfg.get(key, DEFAULTS[key])


def migrate_docked(data):
    if 'resource_weather_location' not in data and data.get('resource_weather_cities')==['天津','乌鲁木齐','沈阳']:
        data=dict(data,resource_weather_cities=[])
    if 'resource_runner_placement' in data:
        data = dict(data)
        migrate_runner_placement(data)
    # The previous capsule switch applied to both screen edges and peer cards.
    if 'resource_peer_snap' not in data and data.get('resource_edge_snap') is False:
        data = dict(data, resource_peer_snap=False)
    if data.get('resource_layout') and 'resource_edge' not in data:
        data = dict(data, resource_edge='free')
    if data.get('resource_taskbar') is not True or 'resource_task_metrics' in data:return data
    # In 1.1.5, docking moved the only resource window to the taskbar.
    return dict(data,resource_enabled=False,resource_taskbar=data.get('resource_enabled') is True,
                resource_task_metrics=[k for k in TASK_METRICS if data.get('resource_'+k,DEFAULTS['resource_'+k])])


def background(cfg):
    from appearance_presets import dock_appearance, panel_appearance
    if cfg.get('resource_background') == 'app':
        return dock_appearance(cfg)
    if cfg.get('resource_background')=='custom' and cfg.get('resource_appearance'):
        return dict(cfg['resource_appearance'])
    return panel_appearance(cfg)


def clean_background(raw,strict=False):
    from appearance_presets import MATERIALS,COLOR_MODES
    if raw=={}:return {}
    ranges={'opacity':(0,100),'blur':(0,30),'highlight':(0,100)}
    valid=(isinstance(raw,dict) and isinstance(raw.get('material'),str) and isinstance(raw.get('theme'),str) and raw.get('material') in {v for _,v in MATERIALS}
           and raw.get('theme') in {v for _,v in COLOR_MODES}
           and isinstance(raw.get('color'),str) and (not raw['color'] or re.fullmatch(r'#[0-9a-fA-F]{6}',raw['color']))
           and all(type(raw.get(k)) is int and lo<=raw[k]<=hi for k,(lo,hi) in ranges.items()))
    if not valid:
        if strict:raise ValueError('灵动胶囊背景参数无效。')
        return {}
    return {k:(raw[k].lower() if k=='color' else raw[k]) for k in ('material','theme','color',*ranges)}


def clean_weather_thresholds(raw,strict=False):
    if (isinstance(raw,list) and len(raw)==4 and all(type(value) is int and -80<=value<=80 for value in raw)
            and all(left<right for left,right in zip(raw,raw[1:]))):
        return list(raw)
    if strict:raise ValueError('天气温度的四个分界值须按从低到高排列。')
    return list(WEATHER_THRESHOLDS)


def clean_halo_color(value, strict=False):
    if isinstance(value, str) and (not value or re.fullmatch(r'#[0-9a-fA-F]{6}', value)):
        return value.lower()
    if strict:
        raise ValueError('光环单色请输入 #RRGGBB，或点击「默认」。')
    return ''


def normalize(cfg,strict=False):
    cfg.setdefault('resource_halo_color_mode', DEFAULTS['resource_halo_color_mode'])
    cfg['resource_halo_mono_color'] = clean_halo_color(cfg.get('resource_halo_mono_color', ''), strict)
    profiles=cfg.get('resource_peripheral_profiles',[])
    if profiles!=[]:
        from resource_peripherals import normalize_profiles
        profiles=normalize_profiles(profiles,strict=strict)
    cfg['resource_peripheral_profiles']=profiles
    from resource_weather import clean_cities
    role_id=cfg.get('resource_face_role','')
    if role_id or not isinstance(role_id,str):
        from face_roles import clean_role_id
        role_id=clean_role_id(role_id,strict)
    cfg['resource_face_role']=role_id
    cfg.pop('resource_notifications', None)
    cfg.pop('resource_live_glass', None)
    locations=cfg.get('resource_component_locations',{})
    if not isinstance(locations,dict) or any(key not in PLACED_COMPONENTS or value not in ('capsule','desktop') for key,value in locations.items()):
        if strict:raise ValueError('组件位置设置无效。')
        locations={}
    cfg['resource_component_locations']=dict(locations)
    order=cfg.get('resource_component_order',[])
    if not isinstance(order,list) or any(not isinstance(key,str) or key not in CAPSULE_PAGES for key in order):
        if strict:raise ValueError('组件排序设置无效。')
        order=[]
    cfg['resource_component_order']=list(dict.fromkeys([*order,*CAPSULE_PAGES]))
    layouts=cfg.get('resource_card_layouts',{})
    clean={key:record for key,value in layouts.items() if key in RESOURCE_PAGES and (record:=valid_record(value))} if isinstance(layouts,dict) else {}
    if strict and clean!=layouts:raise ValueError('桌面资源卡片位置无效。')
    cfg['resource_card_layouts']=clean
    cfg['resource_weather_cities']=clean_cities(cfg.get('resource_weather_cities',DEFAULTS['resource_weather_cities']),strict)
    cfg['resource_weather_thresholds']=clean_weather_thresholds(cfg.get('resource_weather_thresholds',list(WEATHER_THRESHOLDS)),strict)
    if cfg.get('resource_air_source','auto') not in ('auto','cams','qweather'):
        if strict:raise ValueError('空气质量来源无效。')
        cfg['resource_air_source']='auto'
    else:cfg.setdefault('resource_air_source','auto')
    cfg['resource_news_feeds']=clean_feeds(cfg.get('resource_news_feeds',DEFAULTS['resource_news_feeds']),strict)
    disabled_feeds=clean_feeds(cfg.get('resource_news_disabled_feeds',[]),strict)
    cfg['resource_news_disabled_feeds']=[url for url in cfg['resource_news_feeds'] if url in disabled_feeds]
    accounts = cfg.get('resource_mail_accounts', [])
    if accounts != []:
        from mail_accounts import clean_accounts
        accounts = clean_accounts(accounts, strict)
    cfg['resource_mail_accounts'] = accounts
    mail_interval = cfg.get('resource_mail_interval', DEFAULTS['resource_mail_interval'])
    if type(mail_interval) is not int or not MAIL_INTERVAL_RANGE[0] <= mail_interval <= MAIL_INTERVAL_RANGE[1]:
        if strict:
            raise ValueError('邮箱刷新周期须为 10 至 900 秒。')
        mail_interval = DEFAULTS['resource_mail_interval']
    cfg['resource_mail_interval'] = mail_interval
    if type(cfg.get('resource_news')) is not bool:
        if strict:raise ValueError('灵动胶囊设置无效：resource_news')
        cfg['resource_news']=False
    for key, limit in (('resource_ai_tray_provider', 96), ('resource_ai_tray_metric', 512)):
        value = cfg.get(key, '')
        if not isinstance(value, str) or len(value) > limit or (value and not value.isprintable()):
            if strict:
                raise ValueError('AI 托盘固定项无效。')
            value = ''
        cfg[key] = value
    cfg.setdefault('resource_ai_tray_mode', 'auto')
    if 'resource_runner_placement' in cfg:
        migrate_runner_placement(cfg)
    cfg.pop('resource_runner_color', None)
    for prefix in ('resource_runner_', 'resource_tray_runner_'):
        cfg.setdefault(prefix + 'animal', 'cat')
        cfg.setdefault(prefix + 'metric', 'cpu')
        device = cfg.get(prefix + 'device', '')
        metric = cfg[prefix + 'metric']
        cfg[prefix + 'device'] = device if isinstance(metric, str) and valid_device(device, metric) else ''
        speed = cfg.setdefault(prefix + 'speed', 'adaptive')
        if isinstance(speed, str):
            cfg[prefix + 'speed'] = LEGACY_RUNNER_SPEEDS.get(speed, speed)
    for metric, key in MONITOR_DEVICES.items():
        device = cfg.get(key, '')
        cfg[key] = device if valid_device(device, 'network_utilization' if metric == 'network' else metric) else ''
    from appearance_presets import BACKDROP_MODES
    options={'resource_background':('global','app','custom'),'resource_backdrop_mode':tuple(value for _,value in BACKDROP_MODES),
             'resource_layer':('top','bottom'),'resource_fold':('pill','ball','bar'),
             'resource_palette':('theme','vivid','custom'),'resource_interval':(1,2,5),
             'resource_music_text':('wave','title','lyrics'),'resource_equalizer':('flow','spectrum'),
             'resource_ai_tray_mode':('auto','fixed'),
             'resource_runner_animal':tuple(RUNNER_ANIMALS),'resource_tray_runner_animal':tuple(RUNNER_ANIMALS),
             'resource_runner_speed':tuple(RUNNER_SPEEDS),'resource_tray_runner_speed':tuple(RUNNER_SPEEDS),
             'resource_runner_metric':tuple(RUNNER_METRICS),'resource_tray_runner_metric':tuple(RUNNER_METRICS),
             'resource_expand_mode':('hover','click'),'resource_open_page':tuple(OPEN_PAGES),
             'resource_face_mood':('random','default','happy','wink','love','star','shy','pout','squint'),
             'resource_compact_density':('auto','dense'),
             'resource_clock_format':tuple(COMPACT_CLOCK_FORMATS),
             'resource_capsule_taskbar_position':tuple(CAPSULE_TASKBAR_POSITIONS),
             'resource_taskbar_position':('left','center','right'),
             'resource_taskbar_layer':tuple(TASKBAR_LAYERS), 'resource_halo_speed':tuple(HALO_SPEEDS),
             'resource_halo_color_mode':tuple(value for _, value in HALO_COLOR_MODES),
             'resource_edge':('free','top','bottom','left','right')}
    for key,allowed in options.items():
        if cfg.get(key) not in allowed:
            if strict:raise ValueError('灵动胶囊设置无效：'+key)
            cfg[key]=DEFAULTS[key]
    for key in ('resource_edge_hide','resource_alert_stopwatch','resource_alert_alarm','resource_edge_snap','resource_peer_snap','resource_system_status','resource_pomodoro','resource_capsule_taskbar','resource_app_traffic',
                'resource_agenda','resource_water_enabled','resource_compact_ai','resource_compact_music','resource_reminder_sound',
                'resource_face_auto_switch','resource_runner_enabled','resource_tray_runner_enabled',
                'resource_mail','resource_mail_notifications','resource_mail_icon','resource_weather_location',
                'resource_weather_alert_sound',*REMINDER_OPTIONS):
        if type(cfg.get(key,DEFAULTS[key])) is not bool:
            if strict:raise ValueError('灵动胶囊设置无效：'+key)
            cfg[key]=DEFAULTS[key]
        else:cfg.setdefault(key,DEFAULTS[key])
    face_minutes = cfg.get('resource_face_switch_minutes', FACE_SWITCH_DEFAULT)
    if type(face_minutes) is not int or not FACE_SWITCH_RANGE[0] <= face_minutes <= FACE_SWITCH_RANGE[1]:
        if strict:
            raise ValueError('表情切换间隔须为 1 至 1440 分钟。')
        face_minutes = FACE_SWITCH_DEFAULT
    cfg['resource_face_switch_minutes'] = face_minutes
    for key,(low,high) in TIMER_RANGES.items():
        value=cfg.get(key,DEFAULTS[key])
        if type(value) is not int or not low<=value<=high:
            if strict:raise ValueError('番茄钟设置超出范围。')
            value=DEFAULTS[key]
        cfg[key]=value
    agenda=cfg.get('resource_agenda_events',[])
    if agenda!=[]:
        from resource_agenda import normalize_events
        agenda=normalize_events(agenda,strict)
    cfg['resource_agenda_events']=agenda
    cfg['resource_appearance']=clean_background(cfg.get('resource_appearance',{}),strict)
    transparency=cfg.get('resource_card_transparency',DEFAULTS['resource_card_transparency'])
    if type(transparency) is not int or not 0<=transparency<=100:
        if strict:raise ValueError('卡底透底须为 0 至 100 的整数。')
        transparency=DEFAULTS['resource_card_transparency']
    cfg['resource_card_transparency']=transparency
    limits=cfg.get('resource_limits',{})
    valid=isinstance(limits,dict) and all(k in METRICS and type(v) is int and 0<=v<=100000 for k,v in limits.items())
    if not valid:
        if strict:raise ValueError('资源阈值上限无效。')
        limits={}
    cfg['resource_limits']=dict(limits)
    items=cfg.get('resource_task_metrics',TASK_DEFAULT)
    if not isinstance(items,list) or any(not isinstance(k,str) or k not in TASK_METRICS for k in items):
        if strict:raise ValueError('任务栏监控项目无效。')
        items=TASK_DEFAULT
    cfg['resource_task_metrics']=[k for k in TASK_METRICS if k in items]
    for key,choices in [('resource_compact_metrics',COMPACT_ITEMS),('resource_compact_pinned',PINNABLE),('resource_ai_providers',AI_PROVIDERS),('resource_task_media_parts',TASK_MEDIA_PARTS),
                        ('resource_task_order',TASK_COLUMN_NAMES),('resource_compact_order',PINNABLE)]:
        value=cfg.get(key,DEFAULTS[key])
        if key in ('resource_compact_pinned', 'resource_compact_order') and isinstance(value, list):
            value = [item for item in value if item not in (*COMPACT_STATUS,'peripherals','notifications')]
        if key=='resource_compact_metrics' and isinstance(value,list):
            value=['bluetooth' if item=='peripherals' else item for item in value]
        if not isinstance(value,list) or any(not isinstance(k,str) or k not in choices for k in value):
            if strict:raise ValueError('灵动胶囊显示项目无效。')
            value=DEFAULTS[key]
        cfg[key]=list(dict.fromkeys(value))[:7] if key=='resource_ai_providers' else list(dict.fromkeys(value))
    cfg['resource_task_order'] = list(dict.fromkeys(cfg['resource_task_order'] + list(TASK_COLUMN_NAMES)))
    for key,low,high in [('resource_task_font',2,24),('resource_weather_days',1,7),('resource_face_scale',60,130),
                         ('resource_compact_width',96,1400),('resource_compact_height',28,100),
                         ('resource_compact_badge_height',*COMPACT_BADGE_HEIGHT_RANGE),
                         ('resource_expanded_width',260,1000),('resource_expanded_height',180,800)]:
        if type(cfg.get(key)) is not int or not low<=cfg[key]<=high:
            if strict:raise ValueError('灵动胶囊尺寸或字号无效。')
            cfg[key]=DEFAULTS[key]
    delay=cfg.get('resource_delay')
    if type(delay) is not int or not 1<=delay<=30:
        if strict:raise ValueError('灵动胶囊收起时间无效。')
        cfg['resource_delay']=3
    raw=cfg.get('resource_tints');raw=raw if isinstance(raw,dict) else {}
    clean={k:v.lower() for k,v in raw.items() if k in TINTS and isinstance(v,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',v)}
    if strict and len(clean)!=len(raw):raise ValueError('资源监控曲线颜色无效。')
    cfg['resource_tints']=clean
    record=valid_record(cfg.get('resource_layout'))
    if strict and cfg.get('resource_layout') and not record:raise ValueError('灵动胶囊位置无效。')
    cfg['resource_layout']=record
    for key in ('resource_taskbar_anchor','resource_capsule_taskbar_anchor'):
        anchor=cfg.get(key,{})
        valid=isinstance(anchor,dict) and isinstance(anchor.get('screen'),str) and type(anchor.get('ratio')) in (int,float) and 0<=anchor['ratio']<=1
        if strict and anchor and not valid:raise ValueError('任务栏停靠位置无效。')
        cfg[key]={'screen':anchor['screen'][:240],'ratio':float(anchor['ratio'])} if valid else {}
