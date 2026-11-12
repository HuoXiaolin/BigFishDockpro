"""Packaged preferences captured from the default Dock setup."""
import copy
import json
from pathlib import Path
import sys


LOCAL_DATA = {
    'items', 'desktop_entries', 'desktop_excluded', 'sticky_notes', 'notes_trash',
    'flash_entries', 'flash_draft', 'layout_profiles', 'groups', 'dock_page',
    'custom_cards', 'resource_news_feeds', 'resource_news_disabled_feeds', 'resource_agenda_events',
}
LEGACY_LAYOUT_FIELDS = {
    'display_layout', 'desktop_panels', 'panel_geometry', 'merge_groups', 'merge_initialized',
    'merged_panels', 'merged_active', 'merged_geometry', 'merged_collapsed', 'merged_compact',
}


def load():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    data = json.loads((root / 'assets' / 'default_settings.json').read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('默认设置格式无效。')
    return {key: value for key, value in data.items() if key not in LOCAL_DATA}


def upgrade_defaults(preset):
    """Fill absent preferences while allowing legacy appearance and layout to migrate."""
    from feature_config import LEGACY_STYLE_DEFAULTS

    missing = {key: value for key, value in preset.items() if key not in LEGACY_LAYOUT_FIELDS}
    return dict(missing, **LEGACY_STYLE_DEFAULTS)


def apply(current, preset):
    """Apply preferences to the latest state, keeping local content and custom groups."""
    preset = copy.deepcopy(preset)
    panels = {row['id']: row for row in current['desktop_panels']}
    styled = []
    for style in preset['desktop_panels']:
        original = panels.pop(style['id'], None)
        if original is not None:
            preferences = {key: value for key, value in style.items()
                           if key not in ('name', 'merge_group', 'excluded', 'pinned_paths')}
            style = dict(original, **preferences)
        styled.append(style)
    preset['desktop_panels'] = styled + list(panels.values())

    groups = {row['id']: row for row in current['merge_groups']}
    for style in preset['merge_groups']:
        original = groups.get(style['id'])
        groups[style['id']] = dict(style, name=original['name']) if original else style
    preset['merge_groups'] = list(groups.values())

    layout = preset['display_layout']
    for key in ('panels', 'merge_groups'):
        layout[key] = dict(current['display_layout'].get(key, {}), **layout[key])
    for key in ('clock_appearance', 'calendar_appearance'):
        work = current[key].get('work', {})
        if work.get('calendars'):
            preset[key]['work']['calendars'] = copy.deepcopy(work['calendars'])
        if current[key].get('progress'):
            preset[key]['progress'] = copy.deepcopy(current[key]['progress'])
    return dict(current, **preset)
