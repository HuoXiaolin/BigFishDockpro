"""Packaged preferences captured from the default Dock setup."""
import copy
import json
from pathlib import Path
import sys


LOCAL_DATA = {
    'items', 'desktop_entries', 'desktop_excluded', 'sticky_notes', 'notes_trash',
    'flash_entries', 'flash_draft', 'layout_profiles', 'groups', 'lite_restore',
    'runtime_lite', 'dock_page',
}


def load():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    data = json.loads((root / 'assets' / 'default_settings.json').read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('默认设置格式无效。')
    return {key: value for key, value in data.items() if key not in LOCAL_DATA}


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
    return dict(current, **preset)
