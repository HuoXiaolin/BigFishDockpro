"""One theme vocabulary; rendering adapters retain each component's units."""
MATERIALS = [('液态玻璃','liquid'), ('高光玻璃','gloss'), ('亚克力','acrylic'), ('云母','mica'), ('通透','clear'), ('纯色','solid')]
COLOR_MODES = [('跟随系统','auto'), ('浅色','light'), ('深色','dark')]
PRESET_IDS = ('liquid', 'mist', 'gloss', 'mica', 'transparent')
PANEL_PRESETS = [
    ('轻透液态', dict(opacity=0, blur=6, highlight=36, material='liquid', theme='light', color='#b8d9ef')),
    ('柔雾玻璃', dict(opacity=64, blur=16, highlight=35, material='acrylic', theme='light', color='#ced9e5')),
    ('高光玻璃', dict(opacity=45, blur=8, highlight=75, material='gloss', theme='light', color='#b7ddeb')),
    ('沉静云母', dict(opacity=86, blur=12, highlight=25, material='mica', theme='dark', color='#71869b')),
    ('全透明', dict(opacity=0, blur=2, highlight=0, material='clear', theme='auto', color='')),
]
DOCK_PRESETS = [(name, dict(theme=v['theme'], transparency=100-v['opacity'],
    blur_px=max(3,v['blur']), dock_highlight=v['highlight'], theme_color=v['color'],
    glass=v['material']!='clear', clear_background=v['material']=='clear', dock_material=v['material']))
    for name,v in PANEL_PRESETS]

NOTE_DEFAULTS = dict(material='liquid',theme='light',opacity=41,blur=8,highlight=45)

def normalize_note_appearance(value):
    result=dict(NOTE_DEFAULTS)
    if not isinstance(value,dict):return result
    for key,allowed in [('material',{v for _,v in MATERIALS}),('theme',{'auto','light','dark'})]:
        if isinstance(value.get(key),str) and value[key] in allowed:result[key]=value[key]
    for key,low,high in [('opacity',0,100),('blur',2,30),('highlight',0,100)]:
        if type(value.get(key)) is int:result[key]=max(low,min(high,value[key]))
    return result
