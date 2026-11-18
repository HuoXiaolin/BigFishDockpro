"""Persistent custom slots for settings that cycle between presets."""
import copy,re
from appearance_presets import APPEARANCE_SOURCES, DOCK_PRESETS, MATERIALS
from shell_appearance_model import SOURCES

SIZES=(32,42,54,64)
APPEARANCE_FIELDS=tuple(DOCK_PRESETS[0][1])
SHELL_CYCLES = {
    'shell_start': (
        ('系统默认', {'shell_start_enabled': False}),
        *((label, {'shell_start_enabled': True, 'shell_start_source': source})
          for label, source in APPEARANCE_SOURCES),
    ),
    'shell_notifications': (
        ('系统默认', {'shell_notifications_enabled': False}),
        *((label, {'shell_notifications_enabled': True, 'shell_notifications_source': source})
          for label, source in SOURCES),
    ),
}


def normalize_custom(value):
    if not isinstance(value,dict):return {}
    result={};appearance=value.get('appearance')
    if isinstance(appearance,dict) and all(key in appearance for key in APPEARANCE_FIELDS):
        candidate={key:appearance[key] for key in APPEARANCE_FIELDS}
        valid=(candidate['theme'] in ('auto','light','dark') and isinstance(candidate['dock_material'],str) and candidate['dock_material'] in {key for _,key in MATERIALS}
               and all(type(candidate[key]) is bool for key in ('glass','clear_background'))
               and all(type(candidate[key]) is int and low<=candidate[key]<=high for key,low,high in [('transparency',0,100),('blur_px',0,30),('dock_highlight',0,100)])
               and isinstance(candidate['theme_color'],str) and (not candidate['theme_color'] or bool(re.fullmatch(r'#[0-9a-fA-F]{6}',candidate['theme_color']))))
        if valid:result['appearance']=candidate
    size=value.get('size')
    if isinstance(size,dict) and type(size.get('icon_size')) is int and 20<=size['icon_size']<=256:result['size']={'icon_size':size['icon_size']}
    position=value.get('position')
    if isinstance(position,dict) and type(position.get('custom_bottom')) is int and 0<=position['custom_bottom']<=2000:result['position']={'position':'custom','custom_bottom':position['custom_bottom']}
    return result


def matches(cfg,values):return all(cfg.get(key)==value for key,value in values.items())


def shell_cycle_index(cfg, key):
    return next((index for index, (_, values) in enumerate(SHELL_CYCLES[key]) if matches(cfg, values)), None)


def next_cycle(cfg,key):
    if key in SHELL_CYCLES:
        choices = SHELL_CYCLES[key]
        index = shell_cycle_index(cfg, key)
        return dict(choices[(1 if index is None else index + 1) % len(choices)][1])

    if key == 'appearance':
        from appearance_profiles import selected_mode, switch_profile
        from appearance_presets import PRESET_IDS, DEFAULT_PRESET_ID
        current = selected_mode(cfg)
        modes = (*PRESET_IDS, 'custom')
        index = modes.index(DEFAULT_PRESET_ID if current == 'default' else current)
        candidate = switch_profile(cfg, modes[(index + 1) % len(modes)], current)
        changes = {field:value for field, value in candidate.items() if cfg.get(field) != value}
        # A component edit can invalidate a preset while its stored ID is still the same.
        changes['appearance_mode'] = candidate['appearance_mode']
        if 'appearance' in cfg.get('dock_quick_custom', {}):
            changes['dock_quick_custom'] = {k:v for k, v in cfg['dock_quick_custom'].items() if k != 'appearance'}
        return changes

    saved=copy.deepcopy(normalize_custom(cfg.get('dock_quick_custom')))
    if key=='size':
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
