"""Persisted options and validation shared by startup, settings and panels."""
import re
from update_sources import DEFAULT_SOURCE
from quick_actions import DEFAULT_ORDER,normalize_order

SPECTRUM_STYLES = (
    ('线条', 'line'), ('柱形', 'bars'), ('圆环', 'ring'), ('镜像', 'mirror'), ('点阵', 'dots'),
)
RING_HEIGHT_MAX = 140

DEFAULTS = {
    'flash_enabled':False, 'flash_palette':'theme', 'flash_side':'right', 'flash_color':'blue',
    'flash_auto_hide':True, 'flash_edge_hide':True, 'flash_delay':2, 'flash_drop':True, 'flash_layout':{}, 'flash_entries':[], 'flash_draft':{},
    'taskbar_text_mode':'system', 'layout_profiles':[], 'motion_enabled':True,
    'card_design':'aurora',
    'card_snap': True, 'card_snap_distance': 12,
    'passthrough_mode':'custom','component_passthrough':{},
    'appearance_mode':'custom','appearance_custom':{},'appearance_applied':{},'note_appearance':{},
    'dock_quick_order':list(DEFAULT_ORDER),'dock_quick_custom':{},
    'dock_reflections':True,'dock_clock':True,'dock_quick_settings':True,'dock_add_button':True,
    'card_sizing': {}, 'display_layout': {}, 'card_scale':70, 'settings_size':'medium', 'settings_manual_size':[], 'settings_custom_density':100,
    'calendar_enabled':False,'calendar_locked':False,'calendar_layout':{},'calendar_appearance':{},
    'clock_enabled': False, 'clock_flipped':False, 'clock_locked': False, 'clock_style': 'digital', 'clock_layout': {}, 'clock_appearance': {},
    'spectrum_enabled': False, 'spectrum_style': 'bars', 'spectrum_color_mode': 'colorful', 'spectrum_mono_color': '',
    'spectrum_locked': False, 'spectrum_layout': {}, 'spectrum_manual_size': False,
    'spectrum_ring_height': 100,
    'daily_picture_enabled': False, 'daily_picture_locked': False, 'daily_picture_layout': {},
    'daily_picture_material': 'follow', 'daily_picture_color': '', 'daily_picture_source': 'bing',
    'daily_picture_local_paths': [], 'daily_picture_interval': 30,
    'custom_cards': [],
    'notes_enabled': False, 'notes_visible': True, 'notes_active': '', 'note_style': 'glass', 'sticky_notes': [], 'notes_trash': [],
    'dock_visible': True, 'panels_visible': True, 'runtime_lite': False, 'hide_tray': False,
    'merge_groups': [], 'merge_initialized': False,
    'dock_page': 0, 'merged_panels': True, 'merged_active': '', 'merged_geometry': [],
    'merged_collapsed': True, 'merged_compact': True, 'disabled_categories': [], 'lite_restore': {},
    'screen_corners': True, 'corner_radius': 16,
    'lite_enabled': True,
    'desktop_middle_toggle': True, 'desktop_icons_override': False,
    'desktop_icon_mode': 'hide_all', 'panel_enabled': True, 'panel_opacity': 38, 'panel_blur': 8,
    'panel_highlight': 45, 'panel_material': 'liquid', 'panel_locked': False,
    'panel_auto_hide': True, 'panel_geometry': [], 'panel_page_size': 24,
    'panel_face':True, 'panel_face_interactive':True, 'panel_face_mood':'random',
    'panel_face_scale':100, 'panel_expand_mode':'hover',
    'panel_collapse_style': 'ball', 'panel_capsule_ratio': 70, 'desktop_auto_sort': True,
    'panel_theme': 'auto', 'panel_color': '', 'theme_color': '', 'dock_highlight': 45,
    'dock_material': 'liquid',
    'clear_background': False,
    'desktop_panels': [], 'desktop_entries': [], 'desktop_excluded': [],
    'groups': ['未分类', '办公', '开发', '网络', '影音', '游戏', '文件夹'],
    'startup_priority': 'normal', 'startup_delay': 0,
    'game_mode': False, 'fullscreen_detection': False,
    'check_updates_on_start': False, 'update_use_proxy': True, 'update_source': DEFAULT_SOURCE,
}

from resource_options import DEFAULTS as RESOURCE_DEFAULTS
DEFAULTS.update(RESOURCE_DEFAULTS)

# Missing style fields in existing configurations retain pre-1.1.3 defaults.
LEGACY_STYLE_DEFAULTS={key:DEFAULTS[key] for key in ('card_design','appearance_mode','appearance_custom','appearance_applied','note_appearance','clock_appearance','calendar_appearance','panel_opacity','panel_blur','panel_highlight','panel_material','panel_theme','panel_color','theme_color','dock_highlight','dock_material','clear_background')}
LEGACY_STYLE_DEFAULTS.update(transparency=40,theme='auto',glass=True,blur_px=6)

# Fresh installations use the agreed crystal composition; saved values still win.
from appearance_presets import DEFAULT_DOCK_STYLE,DEFAULT_PANEL_STYLE,DEFAULT_NOTE_APPEARANCE
from clock_appearance import DEFAULT_STYLE
DEFAULTS.update(DEFAULT_DOCK_STYLE)
DEFAULTS.update({'panel_'+key:value for key,value in DEFAULT_PANEL_STYLE.items()})
DEFAULTS.update(card_design='crystal',note_appearance=dict(DEFAULT_NOTE_APPEARANCE),
                clock_appearance=dict(DEFAULT_STYLE),calendar_appearance=dict(DEFAULT_STYLE),appearance_mode='crystal')


def normalize(cfg):
    result = dict(cfg)
    if 'resource_taskbar_position' not in result:
        anchor=result.get('resource_taskbar_anchor')
        ratio=anchor.get('ratio') if isinstance(anchor,dict) else None
        if type(ratio) in (int,float):result['resource_taskbar_position']='left' if ratio<.25 else 'right' if ratio>.75 else 'center'
    # Previous default compact height was designed for two text rows. Preserve
    # deliberate sizes, while adopting the single-row layout on its first load.
    if 'resource_compact_pinned' not in result and result.get('resource_compact_height')==54:result['resource_compact_height']=44
    for theme, material in [('theme','dock_material'), ('panel_theme','panel_material')]:
        if result.get(theme) in ('gloss','fog'):
            result[theme], result[material] = 'light', 'gloss'
        if result.get(theme) == 'follow': result[theme] = 'auto'
    for key, value in DEFAULTS.items():
        result.setdefault(key, value.copy() if isinstance(value,(list,dict)) else value)
    from layout_profiles import normalize_profiles
    result['layout_profiles']=normalize_profiles(result.get('layout_profiles'))
    result['dock_quick_order']=normalize_order(result.get('dock_quick_order'))
    from quick_cycles import normalize_custom
    result['dock_quick_custom']=normalize_custom(result.get('dock_quick_custom'))
    # Retired live-glass state must not survive old profiles or configuration imports.
    result.pop('realtime_glass',None)
    # Retired selective hiding is migrated to the safe co-display mode.
    if result.get('desktop_icon_mode')=='collected':result['desktop_icon_mode']='both'
    for key, lower, upper in [('corner_radius', 0, 120), ('card_snap_distance', 2, 64), ('panel_opacity', 0, 100),
                              ('panel_blur', 2, 30), ('panel_highlight', 0, 100), ('dock_highlight', 0, 100),
                              ('panel_face_scale',60,130), ('panel_page_size', 6, 96), ('panel_capsule_ratio', 30, 100), ('startup_delay', 0, 300)]:
        try:
            result[key] = max(lower, min(upper, int(result[key])))
        except (TypeError, ValueError):
            result[key] = DEFAULTS[key]
    from appearance_presets import MATERIALS
    for key, allowed in [('panel_material', tuple(value for _,value in MATERIALS)),
                         ('taskbar_text_mode', ('system','light','dark')),
                         ('dock_material', tuple(value for _,value in MATERIALS)),
                         ('panel_collapse_style', ('bar', 'capsule', 'ball')),
                         ('panel_expand_mode', ('hover','click')),
                         ('panel_face_mood', ('random','default','happy','wink','love','star','shy','pout','squint')),
                         ('panel_theme', ('auto', 'light', 'dark')),
                         ('desktop_icon_mode', ('both', 'hide_all')),
                         ('note_style', ('glass', 'paper', 'plain')),
                         ('settings_size',('auto','small','medium','custom')),
                           ('startup_priority', ('low', 'normal', 'high'))]:
        if result[key] not in allowed:
            result[key] = DEFAULTS[key]
    from card_design import DESIGNS
    if result.get('card_design') not in {value for _,value in DESIGNS}:result['card_design']='aurora'
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
    result['update_source'] = str(result.get('update_source') or '').strip() or DEFAULT_SOURCE
    for key in ('theme_color', 'panel_color', 'daily_picture_color', 'spectrum_mono_color'):
        color = str(result.get(key) or '').strip()
        result[key] = color.lower() if re.fullmatch(r'#[0-9a-fA-F]{6}', color) else ''
    for key,default,low,high in [('card_scale',70,50,150),('settings_custom_density',100,50,150)]:
        value=result.get(key);result[key]=max(low,min(high,value)) if type(value) is int else default
    size=result.get('settings_manual_size')
    result['settings_manual_size']=list(size) if isinstance(size,list) and len(size)==2 and all(type(v) is int and 200<=v<=10000 for v in size) else []
    from clock_appearance import STYLES
    if result['clock_style'] not in {value for _,value in STYLES}: result['clock_style']='digital'
    from clock_appearance import normalize as normalize_clock
    result['clock_appearance']=normalize_clock(result.get('clock_appearance'),result)
    calendar_options=result.get('calendar_appearance')
    result['calendar_appearance']=normalize_clock(calendar_options,result)
    if not calendar_options:result['calendar_appearance'].update(theme='light',color='')
    from screen_layout import valid_record
    result['clock_layout']=valid_record(result.get('clock_layout'))
    result['calendar_layout']=valid_record(result.get('calendar_layout'))
    result['spectrum_layout']=valid_record(result.get('spectrum_layout'))
    result['daily_picture_layout']=valid_record(result.get('daily_picture_layout'))
    from appearance_presets import MATERIALS
    if result['daily_picture_material'] not in ('follow', *(value for _,value in MATERIALS)):
        result['daily_picture_material']='follow'
    if result['daily_picture_source'] not in ('bing','local'):result['daily_picture_source']='bing'
    paths=result['daily_picture_local_paths']
    result['daily_picture_local_paths']=list(dict.fromkeys(p for p in paths[:64] if isinstance(p,str) and 0<len(p)<=2048 and '\0' not in p)) if isinstance(paths,list) else []
    interval=result['daily_picture_interval']
    result['daily_picture_interval']=max(5,min(3600,interval)) if type(interval) is int else 30
    if result['passthrough_mode'] not in ('all','none','custom'):result['passthrough_mode']='custom'
    selection=result['component_passthrough']
    result['component_passthrough']={k:True for k,v in selection.items() if isinstance(k,str) and 0<len(k)<=104 and v is True} if isinstance(selection,dict) else {}
    if result['spectrum_style'] not in tuple(value for _, value in SPECTRUM_STYLES):
        result['spectrum_style'] = 'bars'
    if result['spectrum_color_mode'] not in ('colorful','mono'):
        result['spectrum_color_mode']='colorful'
    height=result['spectrum_ring_height']
    result['spectrum_ring_height']=max(0,min(RING_HEIGHT_MAX,height)) if type(height) is int else 100
    for key in ('spectrum_enabled', 'spectrum_locked', 'spectrum_manual_size', 'daily_picture_enabled', 'daily_picture_locked'):
        if type(result[key]) is not bool:
            result[key] = DEFAULTS[key]
    if result['custom_cards']:
        from custom_card_data import normalize_cards
        result['custom_cards']=normalize_cards(result['custom_cards'])
    from flash_data import COLORS, PALETTES, normalize_entries, normalize_draft
    from resource_options import normalize as normalize_resources
    normalize_resources(result)
    result['flash_layout']=valid_record(result.get('flash_layout'))
    result['flash_entries']=normalize_entries(result.get('flash_entries'))
    result['flash_draft']=normalize_draft(result.get('flash_draft'))
    for key,options in [('flash_color',tuple(COLORS)),('flash_palette',tuple(v for _,v in PALETTES)),('flash_side',('left','right'))]:
        if result[key] not in options: result[key]=DEFAULTS[key]
    delay=result['flash_delay']
    result['flash_delay']=max(1,min(30,delay)) if type(delay) is int else DEFAULTS['flash_delay']
    from card_metrics import normalize_profile
    result['card_sizing']=normalize_profile(result.get('card_sizing'))
    from sticky_notes_store import normalize_notes
    result['sticky_notes']=normalize_notes(result.get('sticky_notes',[]))
    if not any(row['id']==result['notes_active'] for row in result['sticky_notes']):result['notes_active']=''
    result['notes_trash']=normalize_notes(result.get('notes_trash',[]),limit=32)
    from screen_layout import normalize_layout
    result['display_layout']=normalize_layout(result.get('display_layout'))
    from desktop_catalog import normalize_desktop
    result.update(normalize_desktop(result))
    from panel_preferences import without_overrides
    result['desktop_panels']=without_overrides(result['desktop_panels'])
    from panel_merge import normalize as normalize_merge_groups
    normalize_merge_groups(result)
    from appearance_presets import normalize_note_appearance
    result['note_appearance']=normalize_note_appearance(result.get('note_appearance'))
    from appearance_profiles import MODES,clean_snapshot
    if result.get('appearance_mode') not in {value for _,value in MODES}:result['appearance_mode']='custom'
    for key in ('appearance_custom','appearance_applied'):result[key]=clean_snapshot(result.get(key))
    if result['appearance_mode']=='crystal' and not result['appearance_applied']:
        from appearance_profiles import snapshot
        result['appearance_applied']=snapshot(result)
    return result
