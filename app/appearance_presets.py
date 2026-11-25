"""One theme vocabulary; rendering adapters retain each component's units."""
MATERIALS = [('液态玻璃','liquid'), ('高光玻璃','gloss'), ('亚克力','acrylic'), ('云母','mica'), ('全透明','clear'), ('纯色','solid'), ('清透水晶','crystal'), ('柔光流彩','flowing'), ('浅色纸玻璃','paper_glass'), ('铜边缎面','obsidian'), ('青瓷釉面','celadon'), ('霞光丝绒','velvet')]
COLOR_MODES = [('跟随系统','auto'), ('浅色','light'), ('深色','dark')]
APPEARANCE_SOURCES = [('跟随本应用', 'app'), ('自定义', 'custom')]
BACKDROP_MODES = [('动态透明', 'dynamic'), ('仅壁纸', 'wallpaper')]
VIVID_BLUE, VIVID_GREEN, VIVID_RED = '#5b8def', '#5fd97b', '#ff5d5d'
LIQUID_TINT = '#d3e4f8'
FLOWING_TINT = '#d3b6ee'
PRESET_IDS = ('crystal', 'liquid', 'flowing', 'vivid', 'paper_glass', 'transparent', 'obsidian', 'celadon', 'velvet')
DEFAULT_PRESET_ID = 'crystal'
NEW_PRESET_IDS = ('crystal', 'flowing', 'paper_glass', 'obsidian', 'celadon', 'velvet')
LIGHT_GLASS_INK = '#1b2c3c'
THEME_INKS = dict.fromkeys(('liquid','crystal','flowing','paper_glass','vivid'),LIGHT_GLASS_INK)
THEME_INKS.update(obsidian='#483124',celadon='#193e34',velvet='#562238')
THEME_ACCENTS = {'liquid':'#5678bc','crystal':'#2874ac','flowing':'#8659b0',
                 'paper_glass':'#ab7332','vivid':'#2e8de1','clear':'#15809c',
                 'obsidian':'#d7a277','celadon':'#277a65','velvet':'#ffc1ad'}
THEME_GRADIENTS = {
    'liquid':('#64e8de','#8a64eb'),
    'crystal':('#6ee2f5','#3499ff'),
    'flowing':('#ddb0f3','#8e60e1'),
    'vivid':('#b65eba','#2e8de1'),
    'paper_glass':('#f8d279','#e6a352'),
    'clear':('#00ffed','#0088ba'),
    'obsidian':('#efd1a0','#ad6b48'),
    'celadon':('#9bd9be','#216e63'),
    'velvet':('#ffc0a3','#d87898'),
}
PROGRESS_COLORS = (THEME_GRADIENTS['liquid'],('#f3cf80','#dc9c44'),('#72d5b5','#37a98c'))
PANEL_PRESETS = [
    ('清透水晶', dict(opacity=0, blur=0, highlight=0, material='crystal', theme='light', color='#deedf9')),
    ('液态玻璃', dict(opacity=0, blur=6, highlight=36, material='liquid', theme='light', color=LIQUID_TINT)),
    ('柔光流彩', dict(opacity=36, blur=10, highlight=30, material='flowing', theme='light', color=FLOWING_TINT)),
    ('活力原色', dict(opacity=30, blur=7, highlight=34, material='liquid', theme='light', color=VIVID_BLUE)),
    ('浅色纸玻璃', dict(opacity=84, blur=14, highlight=18, material='paper_glass', theme='light', color='#f5e8d2')),
    ('全透明', dict(opacity=0, blur=2, highlight=0, material='clear', theme='auto', color='')),
    ('曜石铜边', dict(opacity=92, blur=5, highlight=26, material='obsidian', theme='dark', color='#272c34')),
    ('青瓷釉面', dict(opacity=81, blur=11, highlight=39, material='celadon', theme='light', color='#c1e4d3')),
    ('落霞丝绒', dict(opacity=93, blur=8, highlight=18, material='velvet', theme='dark', color='#80374b')),
]
MATERIAL_CHOICES = [('清透玻璃','crystal'), ('液态玻璃','liquid'), ('柔光玻璃','flowing'), ('纸感玻璃','paper_glass'), ('纯色','solid'), ('全透明','clear'), ('铜边缎面','obsidian'), ('青瓷釉面','celadon'), ('霞光丝绒','velvet')]

def preset_design(key):
    return key if key in NEW_PRESET_IDS or key=='vivid' else 'aurora'


def material_choices(current=None):
    choices=list(MATERIAL_CHOICES)
    if current in {value for _,value in MATERIALS} and current not in {value for _,value in choices}:
        choices.append(('自定义材质',current))
    return choices

def material_design(material,previous='aurora'):
    if material in NEW_PRESET_IDS:return material
    return {'liquid':'aurora','clear':'aurora','solid':'minimal'}.get(material,previous)

def select_material(field,value):
    # Importing/restoring an older custom appearance must not select another material.
    if field.findData(value)<0 and value in {v for _,v in MATERIALS}:field.addItem('自定义材质',value)
    field.setCurrentIndex(max(0,field.findData(value)))

DOCK_PRESETS = [(name, dict(theme=v['theme'], transparency=100-v['opacity'],
    blur_px=max(0,v['blur']), dock_highlight=v['highlight'], theme_color=v['color'],
    glass=v['material']!='clear', clear_background=v['material']=='clear', dock_material=v['material']))
    for name,v in PANEL_PRESETS]

DEFAULT_PANEL_STYLE = dict(PANEL_PRESETS[PRESET_IDS.index(DEFAULT_PRESET_ID)][1])
DEFAULT_DOCK_STYLE = dict(DOCK_PRESETS[PRESET_IDS.index(DEFAULT_PRESET_ID)][1])
DEFAULT_NOTE_APPEARANCE = {key:DEFAULT_PANEL_STYLE[key] for key in ('material','theme','opacity','blur','highlight')}


def dock_appearance(cfg):
    """Resolve the shared Dock appearance without altering component settings."""
    defaults = DEFAULT_DOCK_STYLE
    material = cfg.get('dock_material', defaults['dock_material'])
    clear = cfg.get('clear_background') or material == 'clear'
    return dict(material='clear' if clear else material,
                theme=cfg.get('theme', defaults['theme']),
                color=cfg.get('theme_color', defaults['theme_color']),
                opacity=0 if clear else 100 - cfg.get('transparency', defaults['transparency']),
                blur=cfg.get('blur_px', defaults['blur_px']),
                highlight=0 if clear else cfg.get('dock_highlight', defaults['dock_highlight']),
                blur_enabled=not clear and cfg.get('glass', defaults['glass']))


def panel_appearance(cfg):
    if cfg.get('panel_appearance_source') == 'app':
        return dock_appearance(cfg)
    return {key: cfg.get('panel_' + key, value) for key, value in DEFAULT_PANEL_STYLE.items()}

NOTE_DEFAULTS = dict(material='liquid',theme='light',opacity=41,blur=8,highlight=45)

def normalize_note_appearance(value):
    result=dict(NOTE_DEFAULTS)
    if not isinstance(value,dict):return result
    for key,allowed in [('material',{v for _,v in MATERIALS}),('theme',{'auto','light','dark'})]:
        if isinstance(value.get(key),str) and value[key] in allowed:result[key]=value[key]
    for key,low,high in [('opacity',0,100),('blur',0,30),('highlight',0,100)]:
        if type(value.get(key)) is int:result[key]=max(low,min(high,value[key]))
    return result
