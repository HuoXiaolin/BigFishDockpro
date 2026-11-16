"""Meaningful preference, lifecycle, payload and settings regressions."""
import copy
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch


def run(api, runtime, root, app, output, checks):
    from shell_appearance_model import normalize, appearance, background, panel_ink, settings, encode_ini, rules, KINDS
    from shell_appearance import ShellAppearance, verify_payload, stage_payload, payload_root
    from settings_dialog import SettingsDialog
    from settings_catalog import START_MENU, NOTIFICATIONS, TASKBAR
    from PyQt5.QtWidgets import QWidget
    cfg = normalize({'shell_start_source': 'custom', 'shell_start_color': '#123456',
                     'shell_start_material': 'solid', 'shell_start_opacity': 35})
    assert not cfg['shell_start_enabled'] and not cfg['shell_notifications_enabled']
    assert not normalize({'shell_start_enabled': 'yes'})['shell_start_enabled']
    assert normalize({'shell_start_color': '#fff\nowner_pid=7'})['shell_start_color'] == '#deedf9'
    saved = copy.deepcopy(cfg)
    cfg['shell_start_source'] = 'system'
    assert appearance(cfg, 'start', False, False)['material'] == 'solid'
    assert cfg['shell_start_color'] == '#123456'
    cfg['shell_start_source'] = 'custom'
    assert appearance(cfg, 'start') == appearance(saved, 'start')
    cfg.update(shell_notifications_source='custom', shell_notifications_material='clear')
    assert appearance(cfg, 'notifications')['material'] == 'clear'
    assert appearance(cfg, 'start')['material'] == 'solid'
    basic = rules(cfg, 'notifications')
    cfg['shell_notifications_toast'] = False
    assert any('ToastBackground' in target for target, _ in basic)
    assert all('ToastBackground' not in target for target, _ in rules(cfg, 'notifications'))
    # Notifications have no position/size overrides: the native host owns them.
    assert not any(p.startswith(('Margin=', 'Width=', 'Height=', 'RenderTransform')) for _, properties in basic for p in properties)
    try:
        encode_ini({'bad': 'line\nbreak'})
        raise AssertionError('Multiline native configuration accepted')
    except ValueError:
        pass
    checks.append('shell appearance: independent sources persist, bounded settings and unchanged system notification placement')
    dark = settings({'shell_start_source':'custom', 'shell_start_material':'solid', 'shell_start_color':'#102030'}, 'start', 1)
    bright = settings({'shell_start_source':'custom', 'shell_start_material':'solid', 'shell_start_color':'#ffffff'}, 'start', 1)
    assert dark['bigfish_theme']=='Dark' and bright['bigfish_theme']=='Light'
    assert 'Foreground=#ffffff' in dark.values() and 'Foreground=#000000' in bright.values()
    for enabled in (False, True):
        legacy = {'shell_start_enabled': enabled, 'shell_start_layout': 'classic',
                  'shell_start_source': 'custom', 'shell_start_color': '#123456'}
        migrated = api.normalize_features(legacy)
        assert 'shell_start_layout' not in migrated and migrated['shell_start_enabled'] is enabled
        assert migrated['shell_start_source'] == 'custom' and migrated['shell_start_color'] == '#123456'
        assert 'bigfish_layout' not in settings(migrated, 'start', 1)
        assert rules(legacy, 'start') == rules(migrated, 'start')
    from background_contrast import contrast
    from appearance_presets import MATERIALS
    for scheme, ink in (('light', '#000000'), ('dark', '#ffffff')):
        for _, material in MATERIALS:
            cfg = {'theme': scheme, 'dock_material': material, 'theme_color': '#b8d9ef',
                   'transparency': 100, 'blur_px': 9, 'dock_highlight': 27,
                   'shell_start_color': '#123456', 'shell_notifications_color': '#ffeedd'}
            style = appearance(cfg, 'start')
            assert appearance(cfg, 'notifications') == style
            assert (style['material'], style['blur'], style['highlight']) == (material, 9, 0 if material == 'clear' else 27)
            assert appearance(cfg, 'start', transparent=False) == appearance(cfg, 'notifications', transparent=False)
            assert style['opacity'] == 0
            for window_color in ((0, 0, 0), (255, 255, 255)):
                assert contrast(window_color, panel_ink(style, window_color)) >= 4.5
            surface = dict(rules(cfg, 'start'))['Border#AcrylicBorder']
            notified = dict(rules(cfg, 'notifications'))
            for target in ('Grid#NotificationCenterGrid', 'Grid#CalendarCenterGrid', 'Grid#ControlCenterRegion',
                           'Grid#MediaTransportControlsRegion', 'Border#ToastBackgroundBorder, Border#ToastBackgroundBorder2'):
                assert notified[target] == surface
            for kind in KINDS:
                assert settings(cfg, kind, 1)['bigfish_theme'] == scheme.title()
            buttons = [props for target, props in notified.items() if 'PaginatedToggleButton' in target]
            assert len(buttons) == 2 and all(f'Background@Normal:=<SolidColorBrush Color="#18{ink[1:]}"/>' in props for props in buttons)
            assert all(not any(prop.startswith('Background@Checked') for prop in props) for props in buttons)
            cfg['glass'] = False
            for kind, target in (('start', 'Border#AcrylicBorder'), ('notifications', 'Grid#ControlCenterRegion')):
                surface = dict(rules(cfg, kind))[target]
                assert surface[0].startswith('Background:=<SolidColorBrush ')
    checks.append('Start and notification panels share Dock materials, foreground, corner and border settings; sampled contrast leaves tint alpha untouched')

    for kind in KINDS:
        prefix = f'shell_{kind}_'
        for material in ('liquid', 'acrylic', 'paper_glass', 'solid', 'mica'):
            cfg = {prefix + 'source': 'custom', prefix + 'material': material}
            for opacity in (0, 10, 25, 50, 75, 100):
                cfg[prefix + 'opacity'] = opacity
                style = appearance(cfg, kind)
                tint = f'#{round(opacity * 255 / 100):02x}deedf9'
                assert style['opacity'] == opacity
                brush = background(style)
                if opacity == 100 or material in ('solid', 'mica'):
                    assert brush == f'<SolidColorBrush Color="{tint}"/>'
                else:
                    assert f'FallbackColor="{tint}"' in brush
                    if material == 'liquid':
                        assert f'BlurAmount="24" TintColor="{tint}"' in brush
                    else:
                        assert f'TintOpacity="{opacity / 100:.2f}" TintLuminosityOpacity="0"' in brush
            cfg.update({prefix + 'opacity': 0, prefix + 'blur': 0})
            assert background(appearance(cfg, kind)) == '<SolidColorBrush Color="#00deedf9"/>'
            assert background(appearance(cfg, kind, transparent=False)) == '<SolidColorBrush Color="#ffdeedf9"/>'
    checks.append('Custom opacity 0–100% reaches the native brush and its fallback; zero tint can keep blur and zero blur leaves only the selected tint')

    for kind in KINDS:
        key=f'shell_{kind}_text_mode'
        assert normalize({key: 'unsupported'})[key]=='auto'
        backdrop = (240, 240, 240)
        original = settings({}, kind, 1, surface_color=backdrop)
        assert original['bigfish_theme'] == 'Light'
        for mode, system_light, expected in (('white', True, 'Dark'), ('black', False, 'Light'),
                                             ('system', False, 'Dark'), ('system', True, 'Light')):
            styled = settings({key: mode}, kind, 1, surface_color=backdrop, system_text_light=system_light)
            assert styled['bigfish_theme'] == expected
            assert styled['controlStyles[0].styles[0]'] == original['controlStyles[0].styles[0]']
    from quick_cycles import next_cycle, shell_cycle_index
    system_start = {'shell_start_enabled': True, 'shell_start_source': 'system'}
    assert shell_cycle_index(system_start, 'shell_start') is None
    assert next_cycle(system_start, 'shell_start')['shell_start_source'] == 'app'
    checks.append('Shell text color can follow background, Windows shell theme or fixed black/white independently of the background')

    payload = payload_root()
    manifest = verify_payload(payload)
    assert manifest['protocol'] == 1
    exe = payload / 'BigFishShellAppearance.exe'
    assert subprocess.run([str(exe), '--self-test'], creationflags=subprocess.CREATE_NO_WINDOW, timeout=5).returncode == 0
    assert subprocess.run([str(exe), '--attach', str(os.getpid()), 'start'], creationflags=subprocess.CREATE_NO_WINDOW, timeout=5).returncode == 22
    checks.append('packaged native shell backend: manifest hashes, GUI launcher and non-shell process rejection')

    folder = Path(root) / 'shell-lifecycle'
    class Api:
        CONFIG_DIR = str(folder)
        log = staticmethod(lambda text: None)
    dock = QWidget();dock.preview = False
    dock.cfg = normalize({'shell_start_enabled': True, 'shell_notifications_enabled': True})
    controller = ShellAppearance(dock, Api)
    # All OS interactions are mocked even though the test desktop is private.
    controller.disabled = False
    controller.supported = True
    attach = []
    def attached(pid, kind):
        attach.append((pid, kind));controller.attached.add(pid)
    controller.attach = attached
    with patch('shell_appearance.stage_payload', return_value=payload), patch('shell_appearance.shell_hosts', return_value={1234: 'start'}), \
         patch('shell_appearance.system_appearance', return_value=(True, True)), patch('shell_container.context', return_value=None), \
         patch('shell_appearance.signal_host', return_value=True) as signal:
        controller.sync()
        file = folder / 'shell-appearance/start.ini'
        assert file.exists() and 'enabled=1' in file.read_text(encoding='utf-16')
        timestamp = file.stat().st_mtime_ns
        signal.reset_mock();controller.sync()
        assert file.stat().st_mtime_ns == timestamp and not signal.called and attach == [(1234, 'start')]
        dock.cfg.update(theme='dark');controller.sync()
        notification = file.with_name('notifications.ini')
        assert all('bigfish_theme=Dark' in path.read_text(encoding='utf-16') for path in (file, notification))
        for kind in KINDS:
            dock.cfg.update({f'shell_{kind}_source': 'custom', f'shell_{kind}_material': 'liquid',
                             f'shell_{kind}_theme': 'dark', f'shell_{kind}_opacity': 0})
        with patch('shell_appearance.foreground_surface', return_value=('start', (250, 250, 250))) as surface:
            controller.refresh_foreground()
            surface.assert_called_with({1234: 'start'})
            rendered = file.read_text(encoding='utf-16')
            assert 'bigfish_theme=Light' in rendered and 'TintColor="#00313437"' in rendered
            assert 'bigfish_theme=Dark' in notification.read_text(encoding='utf-16')
            timestamp = file.stat().st_mtime_ns
            signal.reset_mock();controller.refresh_foreground()
            assert file.stat().st_mtime_ns == timestamp and not signal.called
            dock.cfg['shell_start_text_mode']='system'
            with patch('taskbar_text.system_mode', return_value=0):controller.sync()
            surface.assert_called_with({})
            assert 'bigfish_theme=Dark' in file.read_text(encoding='utf-16')
        controller.suspend()
        assert not controller.timer.isActive() and 'enabled=0' in file.read_text(encoding='utf-16')
        controller.resume()
        assert controller.timer.isActive() and 'enabled=1' in file.read_text(encoding='utf-16')
        # A working quick-settings host must not hide a failed notification host.
        controller.hosts={1234:'notifications',5678:'notifications'}
        controller.errors[5678]='组件连接失败'
        (controller.root/'1234.json').write_text(json.dumps(dict(protocol=1,pid=1234,owner_pid=os.getpid(),state='applied',matches=9,errors=0)))
        controller.update_status({'notifications'})
        assert '部分已应用' in controller.status and '组件连接失败' in controller.status
        controller.errors.clear()
        controller.update_status({'notifications'})
        assert '其余等待' in controller.status
        controller.hosts={1234:'start'}
        controller.close()
        assert not controller.timer.isActive() and 'enabled=0' in file.read_text(encoding='utf-16')
    dock.deleteLater()
    assert runtime.shell_appearance.disabled and not runtime.shell_appearance.timer.isActive()
    checks.append('shell lifecycle: no duplicate style writes/attach, theme refresh, shutdown cancellation and restore on close; OS calls mocked')

    dialog = SettingsDialog(runtime.tray, api)
    try:
        dialog.tabs.setCurrentIndex(TASKBAR);dialog.show();app.processEvents()
        auto = dialog.fields['taskbar_text_auto'];manual = dialog.fields['taskbar_text_mode']
        auto.setChecked(True);assert not manual.isEnabled()
        dialog.grab().save(str(Path(output)/'shell-settings-taskbar-auto.png'))
        auto.setChecked(False);assert manual.isEnabled()
        for page, kind in ((START_MENU, 'start'), (NOTIFICATIONS, 'notifications')):
            dialog.tabs.setCurrentIndex(page)
            dialog.show();app.processEvents()
            prefix = 'shell_' + kind + '_'
            source = dialog.fields[prefix + 'source']
            assert [source.itemData(i) for i in range(source.count())] == ['app', 'system', 'custom']
            text_mode = dialog.fields[prefix + 'text_mode']
            assert [text_mode.itemData(i) for i in range(text_mode.count())] == ['auto','system','white','black']
            dialog.set_draft_values({prefix + 'text_mode': 'white'})
            assert text_mode.isEnabled() and dialog.draft_values()[prefix + 'text_mode']=='white'
            if kind == 'start':
                style = dialog.fields['shell_start_enabled']
                assert [(style.itemText(i), style.itemData(i)) for i in range(style.count())] == [
                    ('系统默认', False), ('Windows 11 · 玻璃网格', True)]
                assert 'shell_start_layout' not in dialog.fields
            dialog.set_draft_values({prefix+'source': 'custom', prefix+'color': '#dceff9'})
            app.processEvents()
            assert dialog.fields[prefix+'color'].isEnabled()
            dialog.fields[prefix+'source'].setCurrentIndex(dialog.fields[prefix+'source'].findData('app'))
            assert not dialog.fields[prefix+'color'].isEnabled()
            assert dialog.draft_values()[prefix+'color'] == '#dceff9'
            dialog.fields[prefix+'source'].setCurrentIndex(dialog.fields[prefix+'source'].findData('custom'))
            assert dialog.fields[prefix+'color'].text() == '#dceff9'
            with patch('shell_appearance_settings.system_appearance', return_value=(True, True)):
                dialog.set_draft_values({prefix + 'material': 'liquid', prefix + 'opacity': 0})
                opacity = dialog.fields[prefix + 'opacity']
                assert opacity.isEnabled() and dialog.draft_values()[prefix + 'opacity'] == 0
                opacity.setValue(100)
                assert dialog.draft_values()[prefix + 'opacity'] == 100
                dialog.set_draft_values({prefix + 'material': 'clear'})
                assert not opacity.isEnabled() and dialog.draft_values()[prefix + 'opacity'] == 100
                dialog.set_draft_values({prefix + 'material': 'liquid', prefix + 'opacity': 0})
            dialog.grab().save(str(Path(output) / ('shell-settings-' + kind + '.png')))
        assert not runtime.dock.cfg['shell_start_enabled'] and not runtime.dock.cfg['shell_notifications_enabled']
        from tray_menu import common_actions
        from ui_style import AlignedMenu
        from PyQt5.QtCore import QPoint
        menu = AlignedMenu();original = copy.deepcopy(runtime.dock.cfg)
        def saved(tray, _api, values):
            tray.cfg.update(values);return True
        def action(parent, title):return next(a for a in parent.actions() if a.text()==title)
        try:
            with patch('settings_effects.save_changes',side_effect=saved), patch('taskbar_menu.auto_hide',return_value=False), \
                 patch.object(runtime,'show_settings') as opened, patch.object(runtime.tray,'settings_dialog',dialog,create=True):
                common_actions(menu,runtime.tray)
                start=action(menu,'开始菜单').menu();notifications=action(menu,'通知与快捷面板').menu();taskbar=action(menu,'任务栏').menu()
                assert [item.text() for item in start.actions() if item.isCheckable()] == ['系统默认', 'Windows 11 · 玻璃网格']
                assert action(start, '系统默认').isChecked()
                action(start, 'Windows 11 · 玻璃网格').trigger()
                assert runtime.dock.cfg['shell_start_enabled']
                assert action(start, 'Windows 11 · 玻璃网格').isChecked() and not action(start, '系统默认').isChecked()
                action(start, '系统默认').trigger()
                assert not runtime.dock.cfg['shell_start_enabled']
                action(start, 'Windows 11 · 玻璃网格').trigger()
                action(action(start,'外观来源').menu(),'跟随系统').trigger()
                action(notifications,'启用通知与快捷面板美化').trigger()
                action(action(notifications,'美化范围').menu(),'通知弹窗').trigger()
                assert runtime.dock.cfg['shell_start_enabled'] and 'shell_start_layout' not in runtime.dock.cfg
                assert runtime.dock.cfg['shell_start_source']=='system' and runtime.dock.cfg['shell_notifications_enabled']
                assert runtime.dock.cfg['shell_notifications_toast'] is False
                action(taskbar,'文字随背景自动切换黑白色').trigger()
                assert runtime.dock.cfg['taskbar_text_auto']
                action(action(taskbar,'任务栏文字').menu(),'深色文字（黑字）').trigger()
                assert runtime.dock.cfg['taskbar_text_auto'] is False and runtime.dock.cfg['taskbar_text_mode']=='dark'
                for submenu, label, page in ((start,'开始菜单',START_MENU),(notifications,'通知与快捷面板',NOTIFICATIONS),(taskbar,'任务栏外观',TASKBAR)):
                    action(submenu,label+'设置…').trigger()
                    assert dialog.tabs.currentIndex()==page and opened.called
                for popup,name in ((menu,'root'),(start,'start'),(notifications,'notifications'),(taskbar,'taskbar')):
                    popup.popup(QPoint(40,40));app.processEvents()
                    popup.grab().save(str(Path(output)/('shell-context-'+name+'.png')));popup.hide();app.processEvents()
        finally:
            runtime.dock.cfg.clear();runtime.dock.cfg.update(original);menu.deleteLater()
        checks.append('Dock/tray context menus: two Start choices, notification scope and appearance sources, taskbar auto/manual selection, settings-page navigation and persistence routing with native effects mocked')

        from dock_extras import DockQuickSettings
        from shell_menu import add_menu
        from quick_actions import SHELL_ACTIONS
        quick = DockQuickSettings(runtime.dock.extras)
        menu = AlignedMenu(quick)
        shell = runtime.shell_appearance
        cycles = {
            'shell_start': ('shell_start_source', [('app', '跟随本应用'), ('custom', '自定义'), (None, '系统默认')]),
            'shell_notifications': ('shell_notifications_source', [('app', '跟随本应用'), ('system', '跟随系统'),
                                                                  ('custom', '自定义'), (None, '系统默认')]),
        }
        try:
            with patch.object(shell, 'supported', True), patch.object(shell, 'sync', wraps=shell.sync) as sync, \
                 patch.object(runtime.tray, 'settings_dialog', dialog, create=True):
                quick.refresh()
                quick.show();app.processEvents()
                start_index = quick.order().index('taskbar_text') + 1
                assert tuple(quick.order()[start_index:start_index + 2]) == SHELL_ACTIONS
                original_draft = dialog.draft_values()['shell_start_color']
                for key in SHELL_ACTIONS:
                    tile = quick.tiles[key]
                    assert tile.isVisible() and tile.value == '系统默认'
                    tile.click()
                quick.grab().save(str(Path(output) / 'dock-quick-shell.png'))
                with patch.object(api, 'save_config', return_value=False):
                    quick.tiles['shell_start'].click()
                assert quick.tiles['shell_start'].value == '跟随本应用' and '保存失败' in quick.status.text()
                for key, (option, modes) in cycles.items():
                    tile = quick.tiles[key]
                    enabled = key + '_enabled'
                    for index, (mode, label) in enumerate(modes):
                        if index:
                            tile.click()
                        saved = api.load_config()
                        assert tile.value == label and not tile.active
                        assert saved[enabled] == dialog.draft_values()[enabled] == (mode is not None)
                        if option:
                            assert saved[option] == dialog.fields[option].currentData() == (mode or modes[index-1][0])
                        menu.clear()
                        add_menu(menu, runtime, key.removeprefix('shell_'))
                        selected = ('Windows 11 · 玻璃网格' if mode else '系统默认') if key == 'shell_start' else '启用通知与快捷面板美化'
                        assert action(menu, selected).isChecked() == (key == 'shell_start' or saved[enabled])
                assert sync.call_count == 7 and dialog.draft_values()['shell_start_color'] == original_draft
                assert api.load_config()['shell_notifications_color'] == original['shell_notifications_color']
            with patch.object(shell, 'supported', False):
                quick.refresh()
                assert all(not quick.tiles[key].isEnabled() for key in SHELL_ACTIONS)
                quick.toggle_edit()
                assert all(quick.tiles[key].isEnabled() for key in SHELL_ACTIONS)
        finally:
            quick.close();quick.deleteLater()
            runtime.dock.cfg.clear();runtime.dock.cfg.update(original);api.save_config(original)
        checks.append('Dock quick settings: Start app appearance → custom → native default, notification sources cycle, and all entries share saved choices')
    finally:
        dialog.reject();dialog.deleteLater();app.processEvents()
    checks.append('shell settings: two native pages render and preserve independent drafts; isolated UI never changes the user shell')
