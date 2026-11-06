"""Portable resource display preferences; live measurements are never stored."""
import re
from screen_layout import valid_record

METRICS={'cpu':'CPU','memory':'内存','network':'网速','gpu':'GPU','rank':'高占用进程','bluetooth':'蓝牙电量','fps':'帧率 FPS','cpu_temp':'CPU 温度',
         'gpu_temp':'GPU 温度','cpu_power':'CPU 功率','gpu_power':'GPU 功率'}
TASK_METRICS=('cpu_temp','gpu_temp','memory','network','cpu_power','gpu_power','fps','cpu','gpu')
TASK_DEFAULT=list(TASK_METRICS[:7])
TINTS={'cpu':'#288bee','memory':'#22bba9','network':'#27b8c4','gpu':'#ec79a6'}
DEFAULTS=dict(resource_enabled=False,resource_layer='bottom',resource_auto_hide=True,
              resource_fold='pill',resource_collapsed=True,resource_layout={},resource_delay=3,
              resource_interval=2,resource_taskbar=False,resource_taskbar_anchor={},resource_task_metrics=TASK_DEFAULT,resource_background='global',resource_appearance={},resource_palette='theme',resource_tints={},resource_bt_tray=False)
DEFAULTS.update({'resource_'+key:key in ('cpu','memory','network','gpu','rank') for key in METRICS})


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
    options={'resource_background':('global','custom'),'resource_layer':('top','bottom'),'resource_fold':('pill','ball','bar'),
             'resource_palette':('theme','vivid','custom'),'resource_interval':(1,2,5)}
    for key,allowed in options.items():
        if cfg.get(key) not in allowed:
            if strict:raise ValueError('资源胶囊设置无效：'+key)
            cfg[key]=DEFAULTS[key]
    cfg['resource_appearance']=clean_background(cfg.get('resource_appearance',{}),strict)
    items=cfg.get('resource_task_metrics',TASK_DEFAULT)
    if not isinstance(items,list) or any(not isinstance(k,str) or k not in TASK_METRICS for k in items):
        if strict:raise ValueError('任务栏监控项目无效。')
        items=TASK_DEFAULT
    cfg['resource_task_metrics']=[k for k in TASK_METRICS if k in items]
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
