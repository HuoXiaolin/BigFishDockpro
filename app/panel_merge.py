"""Independent merged-card groups; the default group retains legacy layout keys."""
import copy
DEFAULT_GROUP='default'
FIELDS=('active','geometry','collapsed','compact')


def normalize(cfg):
    groups=[];seen=set()
    raw=cfg.get('merge_groups')
    for value in raw[:64] if isinstance(raw,list) else []:
        if not isinstance(value,dict):continue
        key=str(value.get('id') or '')[:80]
        if not key or key=='independent' or key in seen:continue
        seen.add(key);row={'id':key,'name':str(value.get('name') or '合并组')[:40]}
        row['active']=str(value.get('active') or '')[:80]
        geo=value.get('geometry');row['geometry']=list(geo) if isinstance(geo,list) and len(geo)==4 and all(type(n) is int and abs(n)<=1000000 for n in geo) and 0<geo[2]<=8192 and 0<geo[3]<=8192 else []
        for field,default in [('collapsed',False),('compact',True)]:row[field]=value.get(field) if type(value.get(field)) is bool else default
        if isinstance(value.get('fold'),dict):
            from fold_options import normalize as normalize_fold
            row['fold']=normalize_fold(value['fold'])
        groups.append(row)
    if DEFAULT_GROUP not in seen:groups.insert(0,{'id':DEFAULT_GROUP,'name':'合并组 1','active':'','geometry':[],'collapsed':False,'compact':True})
    groups=groups[:64]
    cfg['merge_groups']=groups
    valid={g['id'] for g in groups}
    for panel in cfg['desktop_panels']:
        key=panel.get('merge_group',DEFAULT_GROUP)
        panel['merge_group']=key if key in valid else DEFAULT_GROUP
    if cfg.get('merged_panels'):cfg['merge_initialized']=True
    return cfg


def group_id(cfg,identity):
    row=next(model for model in cfg['desktop_panels'] if model['id']==identity)
    return row.get('merge_group',DEFAULT_GROUP)


def value(cfg,group,field):
    if group==DEFAULT_GROUP:return cfg.get('merged_'+field,{'active':'','geometry':[],'collapsed':False,'compact':True}[field])
    return next(row for row in cfg['merge_groups'] if row['id']==group)[field]


def changes(cfg,group,**values):
    if group==DEFAULT_GROUP:return {'merged_'+key:copy.deepcopy(value) for key,value in values.items()}
    rows=copy.deepcopy(cfg['merge_groups']);row=next(row for row in rows if row['id']==group);row.update(copy.deepcopy(values))
    return {'merge_groups':rows}
