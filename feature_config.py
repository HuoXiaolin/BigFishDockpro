"""Persisted options and validation shared by startup, settings and panels."""
import re
DEFAULTS = {
    'card_sizing': {}, 'display_layout': {}, 'card_scale':70, 'settings_size':'auto', 'settings_manual_size':[], 'settings_custom_density':100,
    'notes_enabled': False, 'notes_visible': True, 'note_style': 'glass', 'sticky_notes': [], 'notes_trash': [],
    'dock_visible': True, 'panels_visible': True, 'runtime_lite': False, 'hide_tray': False,
    'dock_page': 0, 'merged_panels': False, 'merged_active': '', 'merged_geometry': [],
    'merged_collapsed': False, 'merged_compact': True, 'disabled_categories': [], 'lite_restore': {},
    'screen_corners': False, 'corner_radius': 28,
    'lite_enabled': True,
    'desktop_icon_mode': 'hide_all', 'panel_enabled': False, 'panel_opacity': 38, 'panel_blur': 8,
    'panel_highlight': 45, 'panel_material': 'liquid', 'panel_locked': False,
    'panel_auto_hide': True, 'panel_geometry': [], 'panel_page_size': 24,
    'panel_collapse_style': 'capsule', 'panel_capsule_ratio': 70, 'desktop_auto_sort': True,
    'panel_theme': 'auto', 'panel_color': '', 'theme_color': '', 'dock_highlight': 45,
    'dock_material': 'liquid',
    'clear_background': False,
    'desktop_panels': [], 'desktop_entries': [], 'desktop_excluded': [],
    'groups': ['未分类', '办公', '开发', '网络', '影音', '游戏', '文件夹'],
    'startup_priority': 'normal', 'startup_delay': 0,
    'game_mode': False, 'fullscreen_detection': False,
    'check_updates_on_start': False, 'update_use_proxy': True, 'update_source': '',
}


def normalize(cfg):
    result = dict(cfg)
    for theme, material in [('theme','dock_material'), ('panel_theme','panel_material')]:
        if result.get(theme) in ('gloss','fog'):
            result[theme], result[material] = 'light', 'gloss'
        if result.get(theme) == 'follow': result[theme] = 'auto'
    for key, value in DEFAULTS.items():
        result.setdefault(key, value.copy() if isinstance(value,(list,dict)) else value)
    for key, lower, upper in [('corner_radius', 0, 120), ('panel_opacity', 0, 100),
                              ('panel_blur', 2, 30), ('panel_highlight', 0, 100), ('dock_highlight', 0, 100),
                              ('panel_page_size', 6, 96), ('panel_capsule_ratio', 30, 100), ('startup_delay', 0, 300)]:
        try:
            result[key] = max(lower, min(upper, int(result[key])))
        except (TypeError, ValueError):
            result[key] = DEFAULTS[key]
    from appearance_presets import MATERIALS
    for key, allowed in [('panel_material', tuple(value for _,value in MATERIALS)),
                         ('dock_material', tuple(value for _,value in MATERIALS)),
                         ('panel_collapse_style', ('bar', 'capsule')),
                         ('panel_theme', ('auto', 'light', 'dark')),
                         ('desktop_icon_mode', ('both', 'collected', 'hide_all')),
                         ('note_style', ('glass', 'paper', 'plain')),
                         ('settings_size',('auto','small','medium','large','custom')),
                           ('startup_priority', ('low', 'normal', 'high'))]:
        if result[key] not in allowed:
            result[key] = DEFAULTS[key]
    for key, value in DEFAULTS.items():
        if isinstance(value, bool):
            result[key] = result[key] if isinstance(result[key], bool) else value
    result['disabled_categories'] = [str(value) for value in result.get('disabled_categories', [])] if isinstance(result.get('disabled_categories'), list) else []
    result['lite_restore'] = {str(key): value for key,value in result.get('lite_restore', {}).items() if isinstance(value,bool)} if isinstance(result.get('lite_restore'),dict) else {}
    result['merged_active'] = str(result.get('merged_active') or '')[:80]
    geo = result.get('merged_geometry')
    result['merged_geometry'] = geo if isinstance(geo,list) and len(geo)==4 and all(type(n) is int for n in geo) else []
    try: result['dock_page'] = max(0,int(result['dock_page']))
    except (TypeError,ValueError): result['dock_page'] = 0
    groups = result.get('groups')
    result['groups'] = list(dict.fromkeys(['未分类'] + [str(g)[:40] for g in groups if str(g).strip()])) if isinstance(groups, list) else list(DEFAULTS['groups'])
    geometry = result.get('panel_geometry')
    if not isinstance(geometry, list) or len(geometry) != 4 or not all(isinstance(n, int) for n in geometry):
        result['panel_geometry'] = []
    result['update_source'] = str(result.get('update_source') or '').strip()
    for key in ('theme_color', 'panel_color'):
        color = str(result.get(key) or '').strip()
        result[key] = color.lower() if re.fullmatch(r'#[0-9a-fA-F]{6}', color) else ''
    for key,default,low,high in [('card_scale',70,50,150),('settings_custom_density',100,50,150)]:
        value=result.get(key);result[key]=max(low,min(high,value)) if type(value) is int else default
    size=result.get('settings_manual_size')
    result['settings_manual_size']=list(size) if isinstance(size,list) and len(size)==2 and all(type(v) is int and 200<=v<=10000 for v in size) else []
    from card_metrics import normalize_profile
    result['card_sizing']=normalize_profile(result.get('card_sizing'))
    from sticky_notes_store import normalize_notes
    result['sticky_notes']=normalize_notes(result.get('sticky_notes',[]))
    result['notes_trash']=normalize_notes(result.get('notes_trash',[]),limit=32)
    from screen_layout import normalize_layout
    result['display_layout']=normalize_layout(result.get('display_layout'))
    from desktop_catalog import normalize_desktop
    result.update(normalize_desktop(result))
    return result
