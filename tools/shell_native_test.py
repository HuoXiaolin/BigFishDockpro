"""Validate the shipped native engines on a private desktop, with synthetic XAML."""
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'app'), str(ROOT / 'tools')]


def check_probe(executable, library, case, report_name, timeout, timeout_retries):
    report = case / report_name
    for attempt in range(2):
        report.unlink(missing_ok=True)
        try:
            result = subprocess.run([str(executable), str(library), str(case)],
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
        except subprocess.TimeoutExpired:
            if attempt:
                raise
            timeout_retries.append(case.name)
            continue
        data = json.loads(report.read_text()) if report.exists() else {}
        if result.returncode or not data.get('passed'):
            raise AssertionError(f'{case.name}: exit={result.returncode}, result={data}')
        return


def main(output):
    from run_isolated_test import assert_isolated
    from shell_appearance_model import START_MENU_SIZE, settings, encode_ini, normalize
    output = Path(output).resolve()
    checks = []
    timeout_retries = []
    try:
        desktop = assert_isolated()
        executable = ROOT / 'artifacts/shell-build/BigFishShellProbe.exe'
        payload = ROOT / 'artifacts/shell-appearance'
        build = json.loads((payload / 'manifest.json').read_text(encoding='utf-8'))['build']
        cases = [(material, 'light', 72, 'auto') for material in ('crystal', 'acrylic', 'solid', 'clear', 'flowing', 'paper_glass')]
        cases += [(material, 'dark', 0, 'auto') for material in ('crystal', 'acrylic', 'clear')]
        cases += [('liquid', 'light', opacity, 'auto') for opacity in (0, 25, 50, 100)]
        cases += [('liquid', 'light', 25, 'white'), ('liquid', 'dark', 25, 'black')]
        focused = os.environ.get('FISHDOCK_SHELL_TEST_PROFILE') == 'layout'
        if focused:
            cases = [('crystal', 'light', 72, 'auto'), ('crystal', 'dark', 0, 'auto'), ('liquid', 'light', 0, 'auto')]
        for kind, filename, inspected in (
                ('start', 'BigFishStartStyle.dll', 'complete native columns, hitboxes, nested footer, stable Search viewport and popup placement'),
                ('notifications', 'BigFishNotificationStyle.dll', 'surface and inherited quick-settings theme with native restoration')):
            for material, theme, opacity, text_mode in cases:
                if focused and kind == 'notifications' and (material, theme, opacity) != ('crystal', 'light', 72):
                    continue
                case = output / f'{kind}-{material}-{theme}-{opacity}-{text_mode}'
                case.mkdir(parents=True, exist_ok=True)
                cfg = normalize({f'shell_{kind}_enabled': True,
                                 f'shell_{kind}_text_mode': text_mode,
                                 'dock_material': material, 'theme': theme, 'transparency': 100 - opacity})
                if material == 'liquid':
                    cfg.update({f'shell_{kind}_source': 'custom', f'shell_{kind}_material': material,
                                f'shell_{kind}_theme': theme, f'shell_{kind}_opacity': opacity})
                expected = 0 if material == 'clear' else opacity
                alpha = round(expected * 255 / 100)
                if cfg[f'shell_{kind}_source'] == 'app':
                    from liquid_glass import dock_theme_colors, dock_tint_layers, material_alpha
                    from appearance_presets import DEFAULT_DOCK_STYLE
                    colors = dock_theme_colors({**DEFAULT_DOCK_STYLE, **cfg}, True)
                    tint, layer = dock_tint_layers(colors, 100 - opacity)
                    alpha = 0 if material == 'clear' else round(material_alpha(tint, material) * layer)
                data = settings(cfg, kind, os.getpid())
                data.update(probe_tint_percent=str(expected), probe_tint_alpha=str(alpha))
                if kind == 'start':
                    data['probe_core_apps'] = '1' if material == 'crystal' and theme == 'dark' else '0'
                    if (material, theme, opacity, text_mode) == ('liquid', 'light', 0, 'auto'):
                        data['bigfish_footer_surface'] = '#209ff0'
                    data['probe_footer_hit_test'] = '1' if (material, theme, opacity, text_mode) in (
                        ('crystal', 'light', 72, 'auto'), ('crystal', 'dark', 0, 'auto'), ('liquid', 'light', 0, 'auto')) else '0'
                    data['trace_menu_input'] = data['probe_footer_hit_test']
                    assert 'StartDocked.StartSizingFrame' in data.values()
                    assert 'Cortana.UI.Views.TaskbarSearchPage' in data.values()
                    # Recreate these private classes with real Grid layout in the fixture.
                    for key, value in tuple(data.items()):
                        if key.endswith('.target'):
                            data[key] = value.replace('StartDocked.StartSizingFrame', 'Grid#StartSizingFrame').replace(
                                'Cortana.UI.Views.TaskbarSearchPage', 'Grid#TaskbarSearchPage').replace(
                                'StartDocked.AllAppsGridListView#AppsList', 'ListView#AppsList').replace(
                                'StartDocked.AllAppsGridListViewItem', 'ListViewItem').replace(
                                'StartMenu.ExpandedFolderList', 'ContentControl#ExpandedFolderList').replace(
                                'StartMenu.PinnedList', 'ContentControl#StartMenuPinnedList')
                    data.update(probe_start_width=str(START_MENU_SIZE[0]), probe_start_height=str(START_MENU_SIZE[1]))
                else:
                    for key, value in tuple(data.items()):
                        if key.endswith('.target'):
                            data[key] = value.replace('ControlCenter.PaginatedToggleButton',
                                                      'Windows.UI.Xaml.Controls.Primitives.ToggleButton')
                (case / f'{kind}.{build}.ini').write_bytes(encode_ini(data))
                check_probe(executable, payload / filename, case, kind + '-probe.json', 12, timeout_retries)
                checks.append(case.name + ': verified tint and ' + inspected)
                if kind == 'start' and material == 'crystal' and theme == 'light':
                    data = settings(cfg, kind, os.getpid())
                    # Reuse the private-type mappings from the standard fixture.
                    for key, value in tuple(data.items()):
                        if key.endswith('.target'):
                            data[key] = value.replace('StartDocked.StartSizingFrame', 'Grid#StartSizingFrame').replace(
                                'Cortana.UI.Views.TaskbarSearchPage', 'Grid#TaskbarSearchPage').replace(
                                'StartDocked.AllAppsGridListView#AppsList', 'ListView#AppsList').replace(
                                'StartDocked.AllAppsGridListViewItem', 'ListViewItem').replace(
                                'StartMenu.ExpandedFolderList', 'ContentControl#ExpandedFolderList').replace(
                                'StartMenu.PinnedList', 'ContentControl#StartMenuPinnedList')
                    data['probe_observer_layout'] = '1'
                    data['probe_outer_inset'] = '1'
                    observed = output / 'start-observer-layout'
                    observed.mkdir(parents=True, exist_ok=True)
                    (observed / f'{kind}.{build}.ini').write_bytes(encode_ini(data))
                    check_probe(executable, payload / filename, observed, 'start-layout.json', 15, timeout_retries)
                    checks.append('start-observer-layout: complete layout through real TAP, refresh and production teardown')
                    for header in ('unnamed', 'named'):
                        modern = output / f'start-redesigned-{header}-header'
                        modern.mkdir(parents=True, exist_ok=True)
                        config = settings(cfg, kind, os.getpid())
                        for key, value in tuple(config.items()):
                            if key.endswith('.target'):
                                config[key] = value.replace('StartMenu.PinnedList >', 'ContentControl#StartMenuPinnedList >')
                        config['probe_redesigned_start'] = header
                        (modern / f'{kind}.{build}.ini').write_bytes(encode_ini(config))
                        check_probe(executable, payload / filename, modern, 'start-redesigned.json', 15, timeout_retries)
                        checks.append(f'{modern.name}: deferred discovery, full rows, four pins, footer and complete native restore')
        result = {'passed': True, 'scope': 'native-xaml-isolated', 'desktop': desktop, 'checks': checks,
                  'profile': 'layout' if focused else 'full',
                  'limits': ['Synthetic native XAML; no injection into the user shell or live Windows start/notification interaction.']}
    except Exception:
        result = {'passed': False, 'checks': checks, 'error': traceback.format_exc()}
    result['timeout_retries'] = timeout_retries
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[-1]))
