"""Persistent custom slots for settings that cycle between presets."""
import copy,re
from appearance_presets import DOCK_PRESETS,MATERIALS

SIZES=(32,42,54,64)
APPEARANCE_FIELDS=tuple(DOCK_PRESETS[0][1])


def normalize_custom(value):
    if not isinstance(value,dict):return {}
    result={};appearance=value.get('appearance')
    if isinstance(appearance,dict) and all(key in appearance for key in APPEARANCE_FIELDS):
        candidate={key:appearance[key] for key in APPEARANCE_FIELDS}
        valid=(candidate['theme'] in ('auto','light','dark') and isinstance(candidate['dock_material'],str) and candidate['dock_material'] in {key for _,key in MATERIALS}
               and all(type(candidate[key]) is bool for key in ('glass','clear_background'))
               and all(type(candidate[key]) is int and low<=candidate[key]<=high for key,low,high in [('transparency',0,100),('blur_px',3,30),('dock_highlight',0,100)])
               and isinstance(candidate['theme_color'],str) and (not candidate['theme_color'] or bool(re.fullmatch(r'#[0-9a-fA-F]{6}',candidate['theme_color']))))
        if valid:result['appearance']=candidate
    size=value.get('size')
    if isinstance(size,dict) and type(size.get('icon_size')) is int and 20<=size['icon_size']<=256:result['size']={'icon_size':size['icon_size']}
    position=value.get('position')
    if isinstance(position,dict) and type(position.get('custom_bottom')) is int and 0<=position['custom_bottom']<=2000:result['position']={'position':'custom','custom_bottom':position['custom_bottom']}
    return result


def matches(cfg,values):return all(cfg.get(key)==value for key,value in values.items())


def next_cycle(cfg,key):
    saved=copy.deepcopy(normalize_custom(cfg.get('dock_quick_custom')))
    if key=='appearance':
        choices=[dict(values) for _,values in DOCK_PRESETS]
        if not any(matches(cfg,values) for values in choices):saved[key]={field:cfg[field] for field in APPEARANCE_FIELDS}
    elif key=='size':
        choices=[{'icon_size':size} for size in SIZES]
        if cfg['icon_size'] not in SIZES:saved[key]={'icon_size':cfg['icon_size']}
    elif key=='position':
        # Bottom/top do not erase the free-position offset; main-page edits to
        # that custom-only field become the latest value, even while docked.
        saved[key]={'position':'custom','custom_bottom':cfg['custom_bottom']}
        choices=[{'position':'bottom'},{'position':'top'}]
    else:raise ValueError('Unsupported quick-settings cycle')
    custom=saved.get(key)
    if custom and not any(matches(custom,values) for values in choices):choices.append(custom)
    index=next((index for index,values in enumerate(choices) if matches(cfg,values)),-1)
    change=dict(choices[(index+1)%len(choices)]);change['dock_quick_custom']=saved
    return change
