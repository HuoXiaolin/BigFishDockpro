"""One theme vocabulary; rendering adapters retain each component's units."""
MATERIALS = [('液态玻璃','liquid'), ('高光玻璃','gloss'), ('亚克力','acrylic'), ('云母','mica'), ('全透明','clear'), ('纯色','solid'), ('清透水晶','crystal'), ('柔光流彩','flowing'), ('浅色纸玻璃','paper_glass')]
COLOR_MODES = [('跟随系统','auto'), ('浅色','light'), ('深色','dark')]
VIVID_BLUE, VIVID_GREEN, VIVID_RED = '#5b8def', '#5fd97b', '#ff5d5d'
LIQUID_TINT = '#d3e4f8'
FLOWING_TINT = '#d3b6ee'
PRESET_IDS = ('crystal', 'liquid', 'flowing', 'vivid', 'paper_glass', 'transparent')
DEFAULT_PRESET_ID = 'crystal'
NEW_PRESET_IDS = ('crystal', 'flowing', 'paper_glass')
LIGHT_GLASS_INK = '#1b2c3c'
THEME_INKS = dict.fromkeys(('liquid','crystal','flowing','paper_glass','vivid'),LIGHT_GLASS_INK)
THEME_ACCENTS = {'liquid':'#5678bc','crystal':'#2874ac','flowing':'#8659b0',
                 'paper_glass':'#ab7332','vivid':'#2e8de1','clear':'#15809c'}
THEME_GRADIENTS = {
    'liquid':('#64e8de','#8a64eb'),
    'crystal':('#6ee2f5','#3499ff'),
    'flowing':('#ddb0f3','#8e60e1'),
    'vivid':('#b65eba','#2e8de1'),
    'paper_glass':('#f8d279','#e6a352'),
    'clear':('#00ffed','#0088ba'),
}
PROGRESS_COLORS = (THEME_GRADIENTS['liquid'],('#f3cf80','#dc9c44'),('#72d5b5','#37a98c'))
PANEL_PRESETS = [
    ('清透水晶', dict(opacity=22, blur=6, highlight=38, material='crystal', theme='light', color='#deedf9')),
    ('液态玻璃', dict(opacity=0, blur=6, highlight=36, material='liquid', theme='light', color=LIQUID_TINT)),
    ('柔光流彩', dict(opacity=36, blur=10, highlight=30, material='flowing', theme='light', color=FLOWING_TINT)),
    ('活力原色', dict(opacity=30, blur=7, highlight=34, material='liquid', theme='light', color=VIVID_BLUE)),
    ('浅色纸玻璃', dict(opacity=84, blur=14, highlight=18, material='paper_glass', theme='light', color='#f5e8d2')),
    ('全透明', dict(opacity=0, blur=2, highlight=0, material='clear', theme='auto', color='')),
]
MATERIAL_CHOICES = [('清透玻璃','crystal'), ('液态玻璃','liquid'), ('柔光玻璃','flowing'), ('纸感玻璃','paper_glass'), ('纯色','solid'), ('全透明','clear')]

def preset_design(key):
    return key if key in NEW_PRESET_IDS or key=='vivid' else 'aurora'


def material_choices(current=None):
    choices=list(MATERIAL_CHOICES)
    if current in {value for _,value in MATERIALS} and current not in {value for _,value in choices}:
        choices.append(('自定义材质',current))
    return choices

def material_design(material,previous='aurora'):
    return {'liquid':'aurora','crystal':'crystal','flowing':'flowing','paper_glass':'paper_glass','clear':'aurora','solid':'minimal'}.get(material,previous)

def select_material(field,value):
    # Importing/restoring an older custom appearance must not select another material.
    if field.findData(value)<0 and value in {v for _,v in MATERIALS}:field.addItem('自定义材质',value)
    field.setCurrentIndex(max(0,field.findData(value)))

DOCK_PRESETS = [(name, dict(theme=v['theme'], transparency=100-v['opacity'],
    blur_px=max(3,v['blur']), dock_highlight=v['highlight'], theme_color=v['color'],
    glass=v['material']!='clear', clear_background=v['material']=='clear', dock_material=v['material']))
    for name,v in PANEL_PRESETS]

DEFAULT_PANEL_STYLE = dict(PANEL_PRESETS[PRESET_IDS.index(DEFAULT_PRESET_ID)][1])
DEFAULT_DOCK_STYLE = dict(DOCK_PRESETS[PRESET_IDS.index(DEFAULT_PRESET_ID)][1])
DEFAULT_NOTE_APPEARANCE = {key:DEFAULT_PANEL_STYLE[key] for key in ('material','theme','opacity','blur','highlight')}

NOTE_DEFAULTS = dict(material='liquid',theme='light',opacity=41,blur=8,highlight=45)

def normalize_note_appearance(value):
    result=dict(NOTE_DEFAULTS)
    if not isinstance(value,dict):return result
    for key,allowed in [('material',{v for _,v in MATERIALS}),('theme',{'auto','light','dark'})]:
        if isinstance(value.get(key),str) and value[key] in allowed:result[key]=value[key]
    for key,low,high in [('opacity',0,100),('blur',2,30),('highlight',0,100)]:
        if type(value.get(key)) is int:result[key]=max(low,min(high,value[key]))
    return result
