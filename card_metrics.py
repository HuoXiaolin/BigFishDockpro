"""One shared size/font profile for all collection cards and notes."""
from screen_layout import capture

DEFAULT_PROFILE={'width':320,'height':260,'font_size':13,'area':[1536,816],'density':1.0,'ui_scale':1.0}


def normalize_profile(value,strict=False):
    import copy
    valid=isinstance(value,dict)
    if valid:
        valid=all(type(value.get(k)) is int and low<=value[k]<=high for k,low,high in [('width',160,8192),('height',96,8192),('font_size',8,48)])
        area=value.get('area');valid=valid and isinstance(area,list) and len(area)==2 and all(type(v) is int and 1<=v<=131072 for v in area)
        valid=valid and all(type(value.get(k)) in (int,float) and low<=value[k]<=high for k,low,high in [('density',.25,2),('ui_scale',.125,8)])
    if not valid:
        if strict:raise ValueError('统一卡片尺寸与文字配置无效。')
        return copy.deepcopy(DEFAULT_PROFILE)
    return {key:copy.deepcopy(value[key]) for key in DEFAULT_PROFILE}


def metrics(cfg,geometry,screens,target=None):
    profile=normalize_profile(cfg.get('card_sizing'))
    if not target:
        record=capture(list(geometry),screens)
        target=next((s for s in screens if s['screen']==record.get('screen')),None)
    if not target:return list(geometry),profile['ui_scale'],profile['font_size']
    x,y,w,h=target['area']
    ratio=min(w/profile['area'][0],h/profile['area'][1])*cfg.get('card_scale',70)/100/profile['density']
    ratio=min(ratio,w/profile['width'],h/profile['height'])
    width=max(1,min(w,round(profile['width']*ratio)));height=max(1,min(h,round(profile['height']*ratio)))
    rect=[max(x,min(geometry[0],x+w-width)),max(y,min(geometry[1],y+h-height)),width,height]
    return rect,profile['ui_scale']*ratio,max(8,min(72,round(profile['font_size']*ratio)))


def font_pixels(cfg,ui_factor):
    profile=normalize_profile(cfg.get('card_sizing'))
    return max(8,min(72,round(profile['font_size']*ui_factor/profile['ui_scale'])))
