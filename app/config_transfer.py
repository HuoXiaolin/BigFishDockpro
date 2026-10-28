"""Validated, atomic configuration transfer. Application files remain path references."""
import copy
from clock_appearance import STYLES
import datetime
import json
import os
from pathlib import Path
import tempfile

MAX_BYTES=8*1024*1024


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('配置中有重复字段：'+key)
        result[key]=value
    return result


def normalize(data,api):
    if not isinstance(data,dict):raise ValueError('配置内容必须是 JSON 对象。')
    if not {'items','icon_size','position'}<=set(data):raise ValueError('不是完整的 BigFishDockpro 配置。')
    cfg=copy.deepcopy(api.DEFAULT_CONFIG)
    for key,default in api.DEFAULT_CONFIG.items():
        if key not in data:continue
        value=data[key]
        if isinstance(default,bool):valid=type(value) is bool
        elif isinstance(default,int):valid=type(value) is int
        else:valid=isinstance(value,type(default))
        if not valid:raise ValueError('配置字段类型不正确：'+key)
        cfg[key]=copy.deepcopy(value)
    from work_schedule import normalize as normalize_work
    for appearance in ('clock_appearance','calendar_appearance'):
        if isinstance(cfg.get(appearance),dict) and 'work' in cfg[appearance]:normalize_work(cfg[appearance]['work'],strict=True)
    for key,low,high in [('icon_size',20,256),('transparency',0,100),('bottom_margin',0,200),('custom_bottom',0,2000)]:
        if not low<=cfg[key]<=high:raise ValueError('配置数值超出范围：'+key)
    for key,allowed in [('position',{'top','bottom','custom'}),('layer',{'top','bottom'}),
                        ('theme',{'auto','light','dark','fog','gloss'}),('blur_mode',{'smart','fast','normal','slow','off'}),
                        ('clock_style',{value for _,value in STYLES}),('settings_size',{'auto','small','medium','large','custom'}),('note_style',{'glass','paper','plain'}),('desktop_icon_mode',{'both','collected','hide_all'}),('lang',{'zh','en'}),('bump_level',{'low','mid','high'})]:
        if cfg[key] not in allowed:raise ValueError('配置选项不受支持：'+key)
    if not 50<=cfg['card_scale']<=150 or not 50<=cfg['settings_custom_density']<=150:raise ValueError('界面缩放比例无效。')
    from card_metrics import normalize_profile
    if cfg.get('card_sizing'):cfg['card_sizing']=normalize_profile(cfg['card_sizing'],strict=True)
    manual=cfg['settings_manual_size']
    if manual and (len(manual)!=2 or not all(type(v) is int and 200<=v<=10000 for v in manual)):raise ValueError('设置窗口尺寸无效。')
    for key,limit in [('merge_groups',64),('items',4096),('desktop_panels',256),('desktop_entries',20000),('groups',256)]:
        if len(cfg[key])>limit:raise ValueError('配置条目过多：'+key)
    from sticky_notes_store import normalize_notes
    cfg['sticky_notes']=normalize_notes(cfg['sticky_notes'],strict=True)
    cfg['notes_trash']=normalize_notes(cfg['notes_trash'],strict=True,limit=32)
    if len(json.dumps([cfg['sticky_notes'],cfg['notes_trash']],ensure_ascii=False).encode('utf-8'))>4*1024*1024:raise ValueError('便签总内容超过4 MiB。')
    items=[]
    for item in cfg['items']:
        if not isinstance(item,dict):raise ValueError('应用条目格式不正确。')
        if item.get('sep') is True:items.append({'sep':True});continue
        path=item.get('path')
        if not isinstance(path,str) or not path.strip() or '\x00' in path or len(path)>32768:raise ValueError('应用路径格式不正确。')
        row={'path':path,'name':item.get('name') or Path(path).stem,'group':item.get('group') or '未分类'}
        for key in ('name','group','icon'):
            if key in item and not isinstance(item[key],str):raise ValueError('应用文字或图标字段格式不正确。')
        if any('\x00' in item.get(key,'') or len(item.get(key,''))>32768 for key in ('icon','name','group')):raise ValueError('应用字段包含无效字符或内容过长。')
        if item.get('icon'):row['icon']=item['icon']
        items.append(row)
    cfg['items']=items
    for entry in cfg['desktop_entries']:
        if not isinstance(entry,dict) or not isinstance(entry.get('path'),str) or '\x00' in entry['path'] or len(entry['path'])>32768:raise ValueError('桌面收纳路径格式不正确。')
    if any(not isinstance(panel,dict) for panel in cfg['desktop_panels']):raise ValueError('卡片条目格式不正确。')
    if any(not isinstance(group,str) for group in cfg['groups']):raise ValueError('应用分组格式不正确。')
    return api.normalize_features(cfg)


def read_configuration(path,api):
    file=Path(path)
    if file.stat().st_size>MAX_BYTES:raise ValueError('配置文件超过 8 MiB，无法导入。')
    def invalid(value):raise ValueError('配置包含非有限数值：'+value)
    data=json.loads(file.read_text(encoding='utf-8-sig'),object_pairs_hook=_pairs,parse_constant=invalid)
    if isinstance(data,dict) and ('format_version' in data or 'project_id' in data or 'configuration' in data):
        if data.get('project_id')!='BigFishDockpro':raise ValueError('不是 BigFishDockpro 的配置文件。')
        if type(data.get('format_version')) is not int or data['format_version']!=1:raise ValueError('不支持此配置文件格式版本。')
        data=data.get('configuration')
    return normalize(data,api)


def _write(path,data):
    target=Path(path);temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix=target.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def export_configuration(path,cfg,api):
    if os.path.normcase(str(Path(path).resolve()))==os.path.normcase(str(Path(api.CONFIG_PATH).resolve())):raise ValueError('请导出到其他文件，不能覆盖正在使用的 config.json。')
    from app_version import VERSION
    document={'project_id':'BigFishDockpro','format_version':1,'software_version':VERSION,
              'exported_at':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'configuration':normalize(cfg,api)}
    payload=json.dumps(document,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    if len(payload)>MAX_BYTES:raise ValueError('导出配置超过 8 MiB。')
    _write(path,payload)


def backup_before_import(api,cfg,source):
    target=Path(api.CONFIG_DIR)/'config.before-import.json'
    if os.path.normcase(str(target.resolve()))==os.path.normcase(str(Path(source).resolve())):
        target=Path(api.CONFIG_DIR)/'config.before-restore.json'
    current=Path(api.CONFIG_PATH)
    payload=current.read_bytes() if current.exists() else json.dumps(cfg,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    target.parent.mkdir(parents=True,exist_ok=True);_write(target,payload)
    return target
