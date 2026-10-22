"""Persisted options and validation shared by startup, settings and panels."""
import re
DEFAULTS = {
    'screen_corners': False, 'corner_radius': 28,
    'lite_enabled': True,
    'panel_enabled': True, 'panel_opacity': 38, 'panel_blur': 8,
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
        result.setdefault(key, list(value) if isinstance(value, list) else value)
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
                         ('startup_priority', ('low', 'normal', 'high'))]:
        if result[key] not in allowed:
            result[key] = DEFAULTS[key]
    for key, value in DEFAULTS.items():
        if isinstance(value, bool):
            result[key] = result[key] if isinstance(result[key], bool) else value
    groups = result.get('groups')
    result['groups'] = list(dict.fromkeys(['未分类'] + [str(g)[:40] for g in groups if str(g).strip()])) if isinstance(groups, list) else list(DEFAULTS['groups'])
    geometry = result.get('panel_geometry')
    if not isinstance(geometry, list) or len(geometry) != 4 or not all(isinstance(n, int) for n in geometry):
        result['panel_geometry'] = []
    result['update_source'] = str(result.get('update_source') or '').strip()
    for key in ('theme_color', 'panel_color'):
        color = str(result.get(key) or '').strip()
        result[key] = color.lower() if re.fullmatch(r'#[0-9a-fA-F]{6}', color) else ''
    from desktop_catalog import normalize_desktop
    result.update(normalize_desktop(result))
    return result
