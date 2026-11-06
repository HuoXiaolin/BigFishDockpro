"""Bounded appearance snapshots, deliberately excluding user content and geometry."""
import copy
import re
from appearance_presets import DOCK_PRESETS, PANEL_PRESETS, PRESET_IDS, NEW_PRESET_IDS, DEFAULT_PRESET_ID, DEFAULT_DOCK_STYLE, normalize_note_appearance
from clock_appearance import DEFAULTS as CLOCK_DEFAULTS, normalize as normalize_clock

TOP_DEFAULTS = dict(DEFAULT_DOCK_STYLE, card_design=DEFAULT_PRESET_ID, note_style='glass', clock_style='digital', clock_flipped=False)
TOP_KEYS = tuple(TOP_DEFAULTS) + tuple('panel_'+key for key in PANEL_PRESETS[0][1])
CLOCK_KEYS = tuple(key for key in CLOCK_DEFAULTS if key != 'work')
NOTE_KEYS = ('style','color','font_size','font_scale','body_font_size','body_font_scale','appearance')
MODES = [('自定义','custom'),('默认样式','default')] + [(name,key) for key,(name,_) in zip(PRESET_IDS,PANEL_PRESETS)]

def snapshot(cfg):
    from card_metrics import normalize_profile
    sizing=normalize_profile(cfg.get('card_sizing'))
    return dict(values={key:copy.deepcopy(cfg[key]) for key in TOP_KEYS if key in cfg},
        clock={key:copy.deepcopy(cfg['clock_appearance'][key]) for key in CLOCK_KEYS},
        calendar={key:copy.deepcopy(cfg['calendar_appearance'][key]) for key in CLOCK_KEYS},
        typography={key:sizing[key] for key in ('font_size','font_density')},
        note_default=normalize_note_appearance(cfg.get('note_appearance')),
        notes={row['id']:{key:copy.deepcopy(row.get(key)) for key in NOTE_KEYS} for row in cfg.get('sticky_notes',[])})

def clean_snapshot(value):
    """Imported snapshots may contain only valid style values, at most 64 notes."""
    if not isinstance(value,dict) or not isinstance(value.get('values'),dict):return {}
    from quick_cycles import normalize_custom
    dock=normalize_custom({'appearance':value['values']}).get('appearance')
    if not dock:return {}
    values=dict(dock)
    from card_design import DESIGNS
    from clock_appearance import STYLES
    choices={'card_design':{v for _,v in DESIGNS},'note_style':{'glass','paper','plain'},'clock_style':{v for _,v in STYLES}}
    raw=value['values']
    for key,options in choices.items():
        if not isinstance(raw.get(key),str) or raw[key] not in options:return {}
        values[key]=raw[key]
    values['clock_flipped']=raw.get('clock_flipped') is True
    panel=normalize_note_appearance({key[6:]:v for key,v in raw.items() if isinstance(key,str) and key.startswith('panel_')})
    values.update({'panel_'+key:v for key,v in panel.items()})
    color=raw.get('panel_color','')
    values['panel_color']=color.lower() if isinstance(color,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',color) else ''
    result={'values':values}
    for name in ('clock','calendar'):
        normalized=normalize_clock(value.get(name))
        result[name]={key:normalized[key] for key in CLOCK_KEYS}
    typography=value.get('typography',{})
    if not isinstance(typography,dict):typography={}
    from card_metrics import DEFAULT_PROFILE
    size=typography.get('font_size')
    result['typography']={'font_size':size if type(size) is int and 8<=size<=48 else DEFAULT_PROFILE['font_size']}
    density=typography.get('font_density')
    if type(density) in (int,float) and .25<=density<=2:result['typography']['font_density']=density
    result['note_default']=normalize_note_appearance(value.get('note_default'))
    result['notes']={}
    from sticky_notes_store import normalize_notes
    rows=value.get('notes',{})
    if isinstance(rows,dict):
        for identity,style in list(rows.items())[:64]:
            if not isinstance(identity,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',identity) or not isinstance(style,dict):continue
            if not isinstance(style.get('style'),str) or style['style'] not in {'glass','paper','plain'}:continue
            record=normalize_notes([dict({key:v for key,v in style.items() if key in NOTE_KEYS and v is not None},id=identity)])[0]
            result['notes'][identity]={key:copy.deepcopy(record.get(key)) for key in NOTE_KEYS}
    return result

def apply_snapshot(cfg, saved):
    result=copy.deepcopy(cfg)
    if not saved:return result
    result.update(copy.deepcopy(saved['values']))
    for component in ('clock','calendar'):
        result[component+'_appearance'].update(copy.deepcopy(saved[component]))
    result['card_sizing'].update({key:copy.deepcopy(value) for key,value in saved['typography'].items() if key in ('font_size','font_density')})
    result['note_appearance']=copy.deepcopy(saved['note_default'])
    for row in result.get('sticky_notes',[]):
        for key,value in saved['notes'].get(row['id'],{}).items():
            if value is None:row.pop(key,None)
            else:row[key]=copy.deepcopy(value)
    return result

def apply_profile(cfg, mode, defaults):
    if mode == 'custom':
        saved = clean_snapshot(cfg.get('appearance_custom'))
        result = apply_snapshot(cfg, saved)
        if saved:
            from sticky_notes_store import default_note_style
            for row in result.get('sticky_notes', []):
                if row['id'] not in saved['notes']:
                    row.update(default_note_style(result))
        return result
    result=copy.deepcopy(cfg)
    if mode=='default':
        for key in TOP_KEYS:result[key]=copy.deepcopy(defaults[key])
        for component in ('clock','calendar'):
            work=result[component+'_appearance']['work']
            result[component+'_appearance']=copy.deepcopy(defaults[component+'_appearance'])
            result[component+'_appearance']['work']=work
        result=apply_profile(result,DEFAULT_PRESET_ID,defaults)
        from clock_appearance import DEFAULT_STYLE
        for component in ('clock','calendar'):
            work=result[component+'_appearance']['work']
            result[component+'_appearance']=normalize_clock(dict(DEFAULT_STYLE,work=work))
        result.update(clock_style='digital',clock_flipped=False)
        from card_metrics import DEFAULT_PROFILE
        result['card_sizing'].update(font_size=DEFAULT_PROFILE['font_size'],font_density=result['card_sizing']['density'])
        from appearance_presets import DEFAULT_NOTE_APPEARANCE
        result['note_appearance']=dict(DEFAULT_NOTE_APPEARANCE)
        for row in result.get('sticky_notes',[]):
            row.update(style='glass',color=defaults['panel_color'],font_size=12,font_scale=1.0)
            for key in ('body_font_size','body_font_scale','appearance'):row.pop(key,None)
        return result
    if mode not in PRESET_IDS:return result
    index=PRESET_IDS.index(mode);values=PANEL_PRESETS[index][1]
    result.update(DOCK_PRESETS[index][1])
    result.update({'panel_'+key:v for key,v in values.items()})
    result.update(card_design=mode if mode in NEW_PRESET_IDS else 'aurora',note_style='glass',note_appearance=normalize_note_appearance(values))
    from clock_appearance import PRESETS
    for component in ('clock','calendar'):result[component+'_appearance'].update(PRESETS[index][1])
    for row in result.get('sticky_notes',[]):
        row.update(style='glass',color=values['color'] or '#b8d9ef',appearance=normalize_note_appearance(values))
    return result

def selected_mode(cfg):
    mode = cfg.get('appearance_mode', 'custom')
    applied = cfg.get('appearance_applied')
    if mode == 'custom' or not applied or mode not in {value for _, value in MODES}:
        return 'custom'
    current = snapshot(cfg)
    if any(value != applied.get(key) for key, value in current.items() if key != 'notes'):
        return 'custom'
    # Adding or deleting a note while a preset is active must not replace the custom slot.
    from sticky_notes_store import default_note_style
    previous_notes = applied.get('notes', {})
    default_note = dict(default_note_style(cfg), font_size=12, font_scale=1.0,
                        body_font_size=None, body_font_scale=None)
    for identity, style in current['notes'].items():
        if style != previous_notes.get(identity, default_note):
            return 'custom'
    return mode


def switch_profile(cfg, target, current_mode, defaults=None):
    """Select an overall style using the same custom slot from either settings entry."""
    saved = cfg.get('appearance_custom')
    if not saved or (current_mode == 'custom' and target != 'custom'):
        custom = snapshot(cfg)
        # Older quick settings saved only the Dock fields. Pair them with the
        # current components when upgrading from an active Dock preset.
        legacy = cfg.get('dock_quick_custom', {}).get('appearance')
        if not saved and legacy and any(all(cfg.get(k) == v for k, v in preset.items())
                                        for _, preset in DOCK_PRESETS):
            custom['values'].update(legacy)
        saved = custom
    result = apply_profile(dict(cfg, appearance_custom=saved), target, defaults)
    applied = snapshot(result)
    result.update(appearance_mode=target, appearance_applied=applied,
                  appearance_custom=copy.deepcopy(applied if target == 'custom' else saved))
    return result
