"""Portable resource display preferences; live measurements are never stored."""
import re
from screen_layout import valid_record

METRICS={'cpu':'CPU','memory':'内存','network':'网速','gpu':'GPU','rank':'高占用进程','bluetooth':'蓝牙电量','fps':'帧率 FPS','cpu_temp':'CPU 温度',
         'gpu_temp':'GPU 温度','cpu_power':'CPU 功率','gpu_power':'GPU 功率','traffic':'流量统计'}
METRICS.update(cpu_frequency='CPU 频率',cpu_voltage='CPU 电压',cpu_fan='CPU 风扇',cpu_pump='CPU 水泵',
               gpu_frequency='GPU 频率',gpu_fan='GPU 风扇',gpu_memory='显存占用',disk_temp='磁盘温度',board_temp='主板温度',case_temp='机箱温度')
SENSOR_UNITS={key:unit for unit,keys in [('°C',('cpu_temp','gpu_temp','disk_temp','board_temp','case_temp')),('W',('cpu_power','gpu_power')),
                                      ('MHz',('cpu_frequency','gpu_frequency')),('V',('cpu_voltage',)),('RPM',('cpu_fan','cpu_pump','gpu_fan')),('%',('gpu_memory',))] for key in keys}
TASK_METRICS=('cpu_temp','gpu_temp','memory','network','cpu_power','gpu_power','fps','cpu','gpu','traffic')
TASK_DEFAULT=list(TASK_METRICS[:7])
TASK_METRICS+=tuple(k for k in SENSOR_UNITS if k not in TASK_METRICS)
TASK_COLUMN_NAMES = {
    'cpu_temp': 'CPU 温度 / 功耗', 'gpu_temp': 'GPU 温度 / 功耗',
    'memory': '内存 / 帧率', 'network': '上下行网速',
    'cpu': 'CPU / GPU 使用率', 'traffic': '日 / 月 / 年流量',
    'sensors': '其他传感器',
}
COMPACT_METRICS=tuple(k for k in METRICS if k!='rank')
PINNABLE={**{k:METRICS[k] for k in COMPACT_METRICS if k!='bluetooth'},'ai':'AI 额度','music':'音乐','weather':'天气'}
OPEN_PAGES={'last':'上次查看的页面','resources':'资源','ai':'AI','music':'音乐','traffic':'流量','weather':'天气'}
TASK_MEDIA_PARTS={'cover':'封面图标','title':'曲名','controls':'播放按钮','wave':'声音律动 / 频谱','progress':'进度细线'}
AI_PROVIDERS=('Claude','Codex','Cursor','Antigravity','ZCode','Dsh','Kimi','OpenCode','Pi','GrokBot')
TINTS={'cpu':'#288bee','memory':'#22bba9','network':'#27b8c4','gpu':'#ec79a6'}
DEFAULTS=dict(resource_enabled=False,resource_layer='bottom',resource_auto_hide=True,
              resource_fold='pill',resource_collapsed=True,resource_layout={},resource_delay=3,
              resource_interval=2,resource_taskbar=False,resource_taskbar_position='right',resource_taskbar_anchor={},resource_task_metrics=TASK_DEFAULT,resource_background='global',resource_appearance={},resource_palette='theme',resource_tints={},resource_bt_tray=False)
DEFAULTS.update({'resource_'+key:key in ('cpu','memory','network','gpu','rank') for key in METRICS})
DEFAULTS.update(resource_traffic=True,resource_task_font=11,resource_task_threshold=False,resource_threshold=True,resource_halo=True,
                resource_liquid=True,resource_edge_snap=True,resource_edge='free',resource_face=False,resource_live_glass=False,
                resource_expand_mode='hover',resource_open_page='last',resource_face_interactive=True,resource_face_mood='random',resource_face_scale=100,
                resource_weather=False,resource_weather_cities=['天津','乌鲁木齐','沈阳'],resource_weather_compact=True,resource_weather_days=3,
                resource_task_music=True,resource_task_music_colorful=False,resource_task_media_parts=list(TASK_MEDIA_PARTS),
                resource_hide_unavailable=True,resource_limits={},resource_task_order=list(TASK_COLUMN_NAMES),
                resource_compact_width=560,resource_compact_height=44,resource_compact_metrics=list(COMPACT_METRICS),
                resource_compact_auto_width=True,resource_compact_pinned=['cpu','memory','gpu','network'],resource_compact_order=[],
                resource_compact_density='auto',
                resource_expanded_width=560,resource_expanded_height=300,
                resource_compact_rings=True,resource_clock=True,resource_compact_rotate=True,
                resource_ai=False,resource_ai_tray=False,resource_ai_providers=['Claude','Codex','Cursor','Antigravity'],
                resource_music=False,resource_music_text='wave',resource_lyrics=True,resource_equalizer='flow',
                resource_ring_letters=True,resource_quota_alert=True)


def migrate_docked(data):
    if data.get('resource_taskbar') is not True or 'resource_task_metrics' in data:return data
    # In 1.1.5, docking moved the only resource window to the taskbar.
    return dict(data,resource_enabled=False,resource_taskbar=data.get('resource_enabled') is True,
                resource_task_metrics=[k for k in TASK_METRICS if data.get('resource_'+k,DEFAULTS['resource_'+k])])


def background(cfg):
    style={key:cfg['panel_'+key] for key in ('material','theme','color','opacity','blur','highlight')}
    if cfg.get('resource_background')=='custom' and cfg.get('resource_appearance'):
        style.update(cfg['resource_appearance'])
    return style


def clean_background(raw,strict=False):
    from appearance_presets import MATERIALS,COLOR_MODES
    if raw=={}:return {}
    ranges={'opacity':(0,100),'blur':(2,30),'highlight':(0,100)}
    valid=(isinstance(raw,dict) and isinstance(raw.get('material'),str) and isinstance(raw.get('theme'),str) and raw.get('material') in {v for _,v in MATERIALS}
           and raw.get('theme') in {v for _,v in COLOR_MODES}
           and isinstance(raw.get('color'),str) and (not raw['color'] or re.fullmatch(r'#[0-9a-fA-F]{6}',raw['color']))
           and all(type(raw.get(k)) is int and lo<=raw[k]<=hi for k,(lo,hi) in ranges.items()))
    if not valid:
        if strict:raise ValueError('资源胶囊背景参数无效。')
        return {}
    return {k:(raw[k].lower() if k=='color' else raw[k]) for k in ('material','theme','color',*ranges)}


def normalize(cfg,strict=False):
    from resource_weather import clean_cities
    cfg.pop('resource_notifications', None)
    cfg['resource_weather_cities']=clean_cities(cfg.get('resource_weather_cities',DEFAULTS['resource_weather_cities']),strict)
    options={'resource_background':('global','custom'),'resource_layer':('top','bottom'),'resource_fold':('pill','ball','bar'),
             'resource_palette':('theme','vivid','custom'),'resource_interval':(1,2,5),
             'resource_music_text':('wave','title','lyrics'),'resource_equalizer':('flow','spectrum'),
             'resource_expand_mode':('hover','click'),'resource_open_page':tuple(OPEN_PAGES),
             'resource_face_mood':('random','default','happy','wink','love','star','shy','pout','squint'),
             'resource_compact_density':('auto','dense'),
             'resource_taskbar_position':('left','center','right'),
             'resource_edge':('free','top','bottom','left','right')}
    for key,allowed in options.items():
        if cfg.get(key) not in allowed:
            if strict:raise ValueError('资源胶囊设置无效：'+key)
            cfg[key]=DEFAULTS[key]
    cfg['resource_appearance']=clean_background(cfg.get('resource_appearance',{}),strict)
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
    for key,choices in [('resource_compact_metrics',COMPACT_METRICS),('resource_compact_pinned',tuple(PINNABLE)+('bluetooth',)),('resource_ai_providers',AI_PROVIDERS),('resource_task_media_parts',TASK_MEDIA_PARTS),
                        ('resource_task_order',TASK_COLUMN_NAMES),('resource_compact_order',PINNABLE)]:
        value=cfg.get(key,DEFAULTS[key])
        if key in ('resource_compact_pinned', 'resource_compact_order') and isinstance(value, list):
            value = [item for item in value if item != 'notifications']
        if not isinstance(value,list) or any(not isinstance(k,str) or k not in choices for k in value):
            if strict:raise ValueError('资源胶囊显示项目无效。')
            value=DEFAULTS[key]
        cfg[key]=list(dict.fromkeys(value))[:7] if key=='resource_ai_providers' else list(dict.fromkeys(value))
    cfg['resource_task_order'] = list(dict.fromkeys(cfg['resource_task_order'] + list(TASK_COLUMN_NAMES)))
    for key,low,high in [('resource_task_font',2,24),('resource_weather_days',1,7),('resource_face_scale',60,130),('resource_compact_width',96,1400),('resource_compact_height',28,100),('resource_expanded_width',260,1000),('resource_expanded_height',180,800)]:
        if type(cfg.get(key)) is not int or not low<=cfg[key]<=high:
            if strict:raise ValueError('资源胶囊尺寸或字号无效。')
            cfg[key]=DEFAULTS[key]
    delay=cfg.get('resource_delay')
    if type(delay) is not int or not 1<=delay<=30:
        if strict:raise ValueError('资源胶囊收起时间无效。')
        cfg['resource_delay']=3
    raw=cfg.get('resource_tints');raw=raw if isinstance(raw,dict) else {}
    clean={k:v.lower() for k,v in raw.items() if k in TINTS and isinstance(v,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',v)}
    if strict and len(clean)!=len(raw):raise ValueError('资源监控曲线颜色无效。')
    cfg['resource_tints']=clean
    record=valid_record(cfg.get('resource_layout'))
    if strict and cfg.get('resource_layout') and not record:raise ValueError('资源胶囊位置无效。')
    cfg['resource_layout']=record
    anchor=cfg.get('resource_taskbar_anchor',{})
    valid=isinstance(anchor,dict) and isinstance(anchor.get('screen'),str) and type(anchor.get('ratio')) in (int,float) and 0<=anchor['ratio']<=1
    if strict and anchor and not valid:raise ValueError('任务栏停靠位置无效。')
    cfg['resource_taskbar_anchor']={'screen':anchor['screen'][:240],'ratio':float(anchor['ratio'])} if valid else {}
