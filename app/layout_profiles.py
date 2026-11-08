"""Layout-only scenes: content, themes and application launches are not restored."""
import copy
import uuid
from screen_layout import normalize_layout,valid_record
from fold_options import normalize as normalize_fold
TOP=('dock_visible','panels_visible','panel_enabled','notes_enabled','notes_visible','clock_enabled','calendar_enabled','spectrum_enabled','merged_panels',
     'merged_active','merged_geometry','merged_collapsed','merged_compact','position','custom_bottom','bottom_margin','icon_size','dock_page','disabled_categories')
PANEL=('geometry','enabled','merged','merge_group','collapsed','compact','fold')
NOTE=('geometry','layout','visible','collapsed','fold')


def snapshot(cfg):
    fold={'style':cfg.get('panel_collapse_style','ball'),'ratio':cfg.get('panel_capsule_ratio',70)}
    panels={p['id']:dict(enabled=True,merged=True,merge_group='default',collapsed=False,compact=True) for p in cfg.get('desktop_panels',[])}
    for row in cfg.get('desktop_panels',[]):
        panels[row['id']].update({k:copy.deepcopy(row[k]) for k in PANEL if k in row})
        panels[row['id']]['fold']=normalize_fold(row.get('fold')) or copy.deepcopy(fold)
    notes={p['id']:dict(visible=True,collapsed=False) for p in cfg.get('sticky_notes',[])}
    for row in cfg.get('sticky_notes',[]):
        notes[row['id']].update({k:copy.deepcopy(row[k]) for k in NOTE if k in row})
        notes[row['id']]['fold']=normalize_fold(row.get('fold')) or {'style':'bar','ratio':100}
    groups=copy.deepcopy(cfg.get('merge_groups',[]))
    for group in groups:group['fold']=normalize_fold(group.get('fold')) or copy.deepcopy(fold)
    return {'values':{k:copy.deepcopy(cfg[k]) for k in TOP if k in cfg},
            'display_layout':copy.deepcopy(cfg.get('display_layout',{})),
            'clock_layout':copy.deepcopy(cfg.get('clock_layout',{})), 'calendar_layout':copy.deepcopy(cfg.get('calendar_layout',{})),
            'spectrum_layout':copy.deepcopy(cfg.get('spectrum_layout',{})),
            'panels':panels,
            'groups':groups,
            'panel_order':[p['id'] for p in cfg.get('desktop_panels',[])],
            'notes':notes}


def geometry(v):
    return isinstance(v,list) and len(v)==4 and all(type(n) is int and abs(n)<=1000000 for n in v) and 0<v[2]<=131072 and 0<v[3]<=131072


def clean_snapshot(value):
    if not isinstance(value,dict):return None
    result={'values':{}}
    raw=value.get('values',{})
    if not isinstance(raw,dict):return None
    for k,v in raw.items():
        if k not in TOP:continue
        if k in ('position',):
            if v in ('top','bottom','custom'):result['values'][k]=v
        elif k=='merged_active':result['values'][k]=str(v)[:80]
        elif k=='disabled_categories' and isinstance(v,list):result['values'][k]=list(dict.fromkeys(x for x in v if isinstance(x,str) and 0<len(x)<=80))[:256]
        elif k=='merged_geometry':
            if v==[] or geometry(v):result['values'][k]=list(v)
        elif k in ('custom_bottom','bottom_margin','icon_size','dock_page'):
            lo,hi={'custom_bottom':(0,2000),'bottom_margin':(0,200),'icon_size':(20,256),'dock_page':(0,4096)}[k]
            if type(v) is int and lo<=v<=hi:result['values'][k]=v
        elif type(v) is bool:result['values'][k]=v
    for k in ('clock_layout','calendar_layout','spectrum_layout'):result[k]=valid_record(value.get(k))
    result['display_layout']=normalize_layout(value.get('display_layout'))
    for section,fields,limit in (('panels',PANEL,256),('notes',NOTE,64)):
        result[section]={};rows=value.get(section,{})
        if not isinstance(rows,dict):continue
        for identity,row in list(rows.items())[:limit]:
            if not isinstance(identity,str) or not identity or len(identity)>80 or not isinstance(row,dict):continue
            cleaned={}
            for k in fields:
                v=row.get(k)
                if k=='geometry' and geometry(v):cleaned[k]=list(v)
                elif k=='layout' and valid_record(v):cleaned[k]=valid_record(v)
                elif k=='fold' and isinstance(v,dict):cleaned[k]=normalize_fold(v)
                elif k=='merge_group' and isinstance(v,str):cleaned[k]=v[:80]
                elif k in ('visible','enabled','merged','collapsed','compact') and type(v) is bool:cleaned[k]=v
            result[section][identity]=cleaned
    order=value.get('panel_order',list(result['panels']))
    result['panel_order']=list(dict.fromkeys(x for x in order if isinstance(x,str) and 0<len(x)<=80))[:256] if isinstance(order,list) else list(result['panels'])
    from panel_merge import normalize
    groups=value.get('groups',[])
    result['groups']=normalize({'merge_groups':groups,'desktop_panels':[]})['merge_groups']
    return result


def normalize_profiles(value):
    result=[];seen=set()
    for row in value[:12] if isinstance(value,list) else []:
        if not isinstance(row,dict):continue
        identity=row.get('id');name=row.get('name');data=clean_snapshot(row.get('layout'))
        if not isinstance(identity,str) or not identity or len(identity)>80 or identity in seen or not isinstance(name,str) or not name.strip() or data is None:continue
        seen.add(identity);result.append({'id':identity,'name':name.strip()[:40],'layout':data})
    return result


def create(cfg,name):return {'id':uuid.uuid4().hex,'name':name.strip()[:40],'layout':snapshot(cfg)}


def apply(cfg,profile):
    data=clean_snapshot(profile['layout'])
    if data is None:raise ValueError('布局方案无效')
    result=copy.deepcopy(cfg);result.update(data['values'])
    for k in ('clock_layout','calendar_layout','spectrum_layout'):
        if data[k]:result[k]=copy.deepcopy(data[k])
    layout=copy.deepcopy(result.get('display_layout',{}));saved=data['display_layout']
    for key in ('dock','merged'):
        if saved.get(key):layout[key]=copy.deepcopy(saved[key])
    for key in ('panels','merge_groups'):
        layout.setdefault(key,{}).update(copy.deepcopy(saved.get(key,{})))
    result['display_layout']=layout
    # Existing objects retain their names, rules, file references and note text.
    for section,key in (('panels','desktop_panels'),('notes','sticky_notes')):
        for row in result.get(key,[]):
            row.update(copy.deepcopy(data[section].get(row['id'],{})))
    order={identity:index for index,identity in enumerate(data['panel_order'])}
    result['desktop_panels'].sort(key=lambda row:order.get(row['id'],len(order)))
    current_groups={group['id']:group for group in result.get('merge_groups',[])}
    group_ids={g['id'] for g in data['groups']}
    groups=copy.deepcopy(data['groups'])
    for group in groups:
        if group['id'] in current_groups:group['name']=current_groups[group['id']]['name']
    result['merge_groups']=groups+[g for g in result.get('merge_groups',[]) if g['id'] not in group_ids]
    from panel_merge import normalize
    normalize(result)
    return result
