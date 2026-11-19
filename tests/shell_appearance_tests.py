"""Meaningful preference, lifecycle, payload and settings regressions."""
import copy
import json
import os
from pathlib import Path
import subprocess
import time
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
            assert len(buttons) == 2 and all('CornerRadius=30' in props for props in buttons)
            assert all(not any(prop.startswith(('Background', 'Foreground')) for prop in props) for props in buttons)
            cfg['glass'] = False
            for kind, target in (('start', 'Border#AcrylicBorder'), ('notifications', 'Grid#ControlCenterRegion')):
                surface = dict(rules(cfg, kind))[target]
                assert surface[0].startswith('Background:=<SolidColorBrush ')
    checks.append('Start and notification panels share Dock materials, foreground, corner and border settings; sampled contrast leaves tint alpha untouched')

    from appearance_presets import DOCK_PRESETS
    paper = next(preset for _, preset in DOCK_PRESETS if preset['dock_material'] == 'paper_glass')
    for kind in KINDS:
        brush = settings(paper, kind, 1)['controlStyles[0].styles[0]']
        assert brush == 'Background:=<WindhawkBlur BlurAmount="14" TintColor="#cdf6f1eb" FallbackColor="#cdf6f1eb"/>'
        for sample in ((12, 78, 225), (14, 14, 18), (255, 255, 255)):
            assert settings(paper, kind, 1, surface_color=sample)['controlStyles[0].styles[0]'] == brush
    checks.append('Paper glass uses the same Dock tint #f6f1eb and alpha 205 over blue, dark and white backgrounds in both Shell panels.')

    for kind in KINDS:
        prefix = f'shell_{kind}_'
        for material in ('liquid', 'acrylic', 'paper_glass', 'solid', 'mica'):
            cfg = {prefix + 'source': 'custom', prefix + 'material': material, prefix + 'blur': 24}
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
         patch('shell_container.panel_geometry_mapping', return_value=200), patch('shell_container.share_panel_geometry', return_value=201), \
         patch('shell_container.close_panel_geometry'), \
         patch('shell_appearance.signal_host', side_effect=lambda *args, notify=True: notify) as signal:
        controller.sync()
        file = folder / 'shell-appearance' / f'start.{manifest["build"]}.ini'
        assert file.exists() and 'enabled=1' in file.read_text(encoding='utf-16')
        timestamp = file.stat().st_mtime_ns
        signal.reset_mock();controller.sync()
        assert file.stat().st_mtime_ns == timestamp and not signal.called and attach == [(1234, 'start')]
        dock.cfg.update(theme='dark');controller.sync()
        notification = file.with_name(f'notifications.{manifest["build"]}.ini')
        assert all('bigfish_theme=Dark' in path.read_text(encoding='utf-16') for path in (file, notification))
        for kind in KINDS:
            dock.cfg.update({f'shell_{kind}_source': 'custom', f'shell_{kind}_material': 'liquid',
                             f'shell_{kind}_theme': 'dark', f'shell_{kind}_opacity': 0, f'shell_{kind}_blur': 24})
        with patch('shell_appearance.foreground_surface', return_value=('start', (250, 250, 250))) as surface, \
             patch('shell_appearance.foreground_target', return_value=(None, 1, 'start')) as open_panel:
            signal.reset_mock()
            controller.refresh_foreground()
            surface.assert_called_with({1234: 'start'}, controller.start_panel_bounds, ())
            rendered = file.read_text(encoding='utf-16')
            assert 'bigfish_theme=Dark' in rendered and 'bigfish_live_ink=#000000' in rendered and 'bigfish_footer_surface=#fafafa' in rendered and signal.called
            timestamp = file.stat().st_mtime_ns
            signal.reset_mock();controller.refresh_foreground()
            assert file.stat().st_mtime_ns == timestamp and not signal.called
            surface.return_value = ('start', (52, 158, 224))
            controller.refresh_foreground()
            rendered = file.read_text(encoding='utf-16')
            assert 'bigfish_live_ink=#000000' in rendered and 'bigfish_footer_surface=#349ee0' in rendered and signal.called
            signal.reset_mock()
            surface.return_value = ('start', (40, 16, 65))
            controller.refresh_foreground()
            assert 'bigfish_live_ink=#ffffff' in file.read_text(encoding='utf-16') and signal.called
            surface.return_value = ('start', (250, 250, 250))
            controller.refresh_foreground()
            open_panel.return_value = None
            surface.return_value = None
            with patch.object(controller, 'start_window_visible', return_value=True):
                timestamp = file.stat().st_mtime_ns
                signal.reset_mock()
                controller.refresh_foreground()
                assert file.stat().st_mtime_ns == timestamp and not signal.called
                assert 'bigfish_theme=Dark' in file.read_text(encoding='utf-16')
            controller.refresh_foreground()
            rendered = file.read_text(encoding='utf-16')
            assert 'bigfish_theme=Light' in rendered and 'TintColor="#00313437"' in rendered
            assert 'bigfish_theme=Dark' in notification.read_text(encoding='utf-16')
            timestamp = file.stat().st_mtime_ns
            signal.reset_mock();controller.refresh_foreground()
            assert file.stat().st_mtime_ns == timestamp and not signal.called
            dock.cfg['shell_start_text_mode']='system'
            with patch('taskbar_text.system_mode', return_value=0):controller.sync()
            surface.assert_called_with({1234: 'start'}, controller.start_panel_bounds, ())
            rendered = file.read_text(encoding='utf-16')
            assert 'bigfish_theme=Dark' in rendered and 'bigfish_live_ink=' not in rendered
            surface.return_value = ('start', (39, 117, 184))
            with patch('taskbar_text.system_mode', return_value=0):controller.refresh_foreground()
            rendered = file.read_text(encoding='utf-16')
            assert 'bigfish_footer_surface=#2775b8' in rendered and 'bigfish_theme=Dark' in rendered
        with patch('shell_appearance.shell_hosts',return_value={1234:'start',5678:'notifications'}), \
             patch('shell_appearance.foreground_surface',return_value=None) as surface:
            controller.sync()
            controller.window_created(5678,123)
            assert controller.ink_timer.isActive()
            for rgb,wanted in (((250,250,250),'Light'),((22,18,33),'Dark')):
                surface.return_value=('notifications',rgb)
                controller.refresh_foreground()
                assert controller.notification_surface==rgb
                surface.return_value=None;controller.sync()
                assert 'bigfish_theme='+wanted in notification.read_text(encoding='utf-16')
                assert 'bigfish_theme=Dark' in file.read_text(encoding='utf-16')
                surface.assert_called_with({1234:'start',5678:'notifications'},controller.start_panel_bounds,(123,))
        controller.suspend()
        assert not controller.timer.isActive() and 'enabled=0' in file.read_text(encoding='utf-16')
        controller.resume()
        assert controller.timer.isActive() and 'enabled=1' in file.read_text(encoding='utf-16')
        # A working quick-settings host must not hide a failed notification host.
        controller.hosts={1234:'notifications',5678:'notifications'}
        controller.errors[5678]='组件连接失败'
        controller.status_path(1234, manifest['build']).write_text(json.dumps(dict(protocol=1,pid=1234,owner_pid=os.getpid(),state='applied',matches=9,errors=0)))
        controller.update_status({'notifications'})
        assert '部分已应用' in controller.status and '组件连接失败' in controller.status
        controller.errors.clear()
        controller.update_status({'notifications'})
        assert '其余等待' in controller.status
        controller.hosts={1234:'start'}
        controller.close()
        assert not controller.timer.isActive() and 'enabled=0' in file.read_text(encoding='utf-16')

    upgraded = ShellAppearance(dock, Api)
    upgraded.root = folder / 'upgrade'
    upgraded.disabled = False
    upgraded.supported = True
    cache = folder / 'builds'
    stage = cache / manifest['build']
    stage.mkdir(parents=True)
    (stage / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    old_build = '1111111111111111'
    (cache / old_build).mkdir()
    legacy = upgraded.event_name(1234, '')
    previous = upgraded.event_name(1234, old_build)
    upgraded.root.mkdir(parents=True)

    def status(build, state, **extra):
        path = upgraded.status_path(1234, build)
        path.write_text(json.dumps(dict(protocol=1, pid=1234, owner_pid=os.getpid(), state=state,
                                        matches=2, errors=0, **extra)), encoding='utf-8')

    status('', 'applied')
    with patch('shell_appearance.stage_payload', return_value=stage), \
         patch('shell_appearance.shell_hosts', return_value={1234: 'start'}), \
         patch('shell_appearance.system_appearance', return_value=(True, True)), \
         patch('shell_container.context', return_value=None), \
         patch('shell_container.panel_geometry_mapping', return_value=200), patch('shell_container.share_panel_geometry', return_value=201), \
         patch('shell_container.close_panel_geometry'), \
         patch('shell_appearance.signal_host', side_effect=lambda pid, name, notify=True: notify or name in (legacy, previous)), \
         patch.object(upgraded, 'attach') as attach_new:
        upgraded.sync()
        for name in ('start.ini', f'start.{old_build}.ini'):
            assert 'enabled=0' in (upgraded.root / name).read_text(encoding='utf-16')
        assert upgraded.next_attach.isActive() and upgraded.next_attach.interval() <= 100
        assert '正在切换' in upgraded.status
        attach_new.assert_not_called()
        legacy_file = upgraded.status_path(1234, '')
        prior_time = legacy_file.stat().st_mtime_ns
        status('', 'restored')
        os.utime(legacy_file, ns=(prior_time, prior_time))
        upgraded.sync()
        attach_new.assert_not_called()
        status(old_build, 'restored')
        upgraded.sync()
        attach_new.assert_called_once_with(1234, 'start')
        status(manifest['build'], 'applied', search_button=False)
        upgraded.update_status({'start'})
        assert '等待搜索入口' in upgraded.status
        status(manifest['build'], 'applied', search_button=True, start_width=382, start_height=302)
        upgraded.update_status({'start'})
        assert upgraded.status == '开始菜单：已应用'
        upgraded.attached.add(1234)
        upgraded.sync()
        limits = (upgraded.root / f'start.{manifest["build"]}.ini').read_text(encoding='utf-16')
        assert 'Width=563' in limits and 'Height=625' in limits
        assert 'BigFishSearchWidth=382' not in limits and 'panel_geometry_1234=201' in limits
        upgraded.close()
    notice = ShellAppearance(dock, Api)
    notice.root = folder / 'notification-upgrade'
    notice.disabled = False;notice.supported = True
    notice.root.mkdir(parents=True)
    notice_legacy = notice.event_name(4321, '')
    old_status = notice.root / '4321.json'
    old_status.write_text(json.dumps(dict(protocol=1, pid=4321, owner_pid=os.getpid(),
                                           state='applied', matches=2, errors=0)))
    staged_status = old_status.with_name(old_status.name + '.tmp')
    restored_receipt = dict(protocol=1, pid=4321, owner_pid=os.getpid(), state='restored', matches=0, errors=0)
    staged_status.write_text(json.dumps(restored_receipt))
    with patch('shell_appearance.stage_payload', return_value=stage), \
         patch('shell_appearance.shell_hosts', return_value={4321: 'notifications'}), \
         patch('shell_appearance.system_appearance', return_value=(True, True)), \
         patch('shell_container.context', return_value=None), \
         patch('shell_container.panel_geometry_mapping', return_value=200), \
         patch('shell_container.close_panel_geometry'), \
         patch('shell_appearance.signal_host', side_effect=lambda pid, name, notify=True: notify or name==notice_legacy), \
         patch.object(notice, 'attach') as connect_notice:
        notice.sync()
        assert 'enabled=0' in (notice.root/'notifications.ini').read_text(encoding='utf-16')
        assert 'enabled=1' in (notice.root/f'notifications.{manifest["build"]}.ini').read_text(encoding='utf-16')
        connect_notice.assert_not_called()
        pending, _ = notice.start_handoffs[4321]
        notice.start_handoffs[4321] = (pending, time.monotonic() - 1)
        notice.window_created(4321)
        assert notice.start_handoffs[4321][1] > time.monotonic() and notice.next_attach.interval() == 0
        notice.sync()
        connect_notice.assert_not_called()  # Old staged receipt predates this handoff.
        staged_status.write_text(json.dumps(dict(restored_receipt, owner_pid=os.getpid() + 1)))
        notice.sync()
        connect_notice.assert_not_called()
        staged_status.write_text(json.dumps(restored_receipt))
        fresh_stamp = time.time_ns() + 1_000_000_000
        os.utime(staged_status, ns=(fresh_stamp, fresh_stamp))
        notice.sync()
        connect_notice.assert_called_once_with(4321, 'notifications')
        assert notice.status_path(4321, notice.build).name == f'4321.{manifest["build"]}.json'
        notice.close()
    notice.deleteLater()
    recovering = ShellAppearance(dock, Api)
    recovering.root = folder / 'cold-start'
    recovering.disabled = False
    recovering.supported = True
    with patch('shell_appearance.stage_payload', side_effect=[PermissionError('logon directory busy'), payload]), \
         patch('shell_appearance.shell_hosts', return_value={}) as hosts, \
         patch('shell_appearance.system_appearance', return_value=(True, True)), \
         patch('shell_container.context', return_value=None), \
         patch('shell_container.panel_geometry_mapping', return_value=200), \
         patch('shell_container.share_panel_geometry', return_value=201), \
         patch('shell_container.close_panel_geometry'), \
         patch('shell_appearance.signal_host', side_effect=lambda *args, notify=True: notify), \
         patch.object(recovering, 'attach') as attach_recovered:
        recovering.sync()
        assert recovering.timer.isActive() and recovering.sync_failures == 1
        assert dock.cfg['shell_start_enabled']
        recovering.sync()
        assert recovering.sync_failures == 0 and recovering.timer.interval() == 5000
        # The Shell starts later than Dock, then restarts with a different PID.
        hosts.return_value = {1201: 'start'}
        recovering.sync();attach_recovered.assert_called_with(1201, 'start')
        recovering.attached.add(1201)
        hosts.return_value = {1202: 'start'}
        recovering.sync();attach_recovered.assert_called_with(1202, 'start')
        assert 1201 not in recovering.attached and 1201 not in recovering.panel_handles
        # Three temporary failures must not disable this host for the session.
        recovering.attempts[1202] = (3, 200)
        attach_recovered.reset_mock()
        with patch('shell_appearance.time.monotonic', return_value=199):recovering.sync()
        attach_recovered.assert_not_called()
        with patch('shell_appearance.time.monotonic', return_value=201):recovering.sync()
        attach_recovered.assert_called_once_with(1202, 'start')
        # A ready notification host goes before a Start retry, and a finished
        # launcher drains the next host without a five-second discovery delay.
        hosts.return_value = {1202: 'start', 1203: 'notifications', 1204: 'notifications'}
        recovering.attempts[1199] = (1, 100)
        with patch('shell_appearance.time.monotonic', return_value=201):recovering.sync()
        attach_recovered.assert_called_with(1203, 'notifications')
        assert 1199 not in recovering.attempts
        from unittest.mock import Mock
        from PyQt5.QtCore import QProcess
        recovering.active_pid = 1203
        recovering.process = Mock()
        recovering.finished(0, QProcess.NormalExit)
        assert recovering.next_attach.isActive() and recovering.next_attach.interval() == 0
        attach_recovered.reset_mock()
        app.processEvents()
        attach_recovered.assert_called_once_with(1204, 'notifications')
        recovering.next_attach.start(0)
        recovering.close()
        assert not recovering.timer.isActive() and not recovering.next_attach.isActive()
    recovering.deleteLater()
    dock.deleteLater()
    assert runtime.shell_appearance.disabled and not runtime.shell_appearance.timer.isActive()
    checks.append('shell lifecycle: no duplicate style writes/attach, theme refresh, shutdown cancellation and restore on close; OS calls mocked')
    checks.append('Start upgrade waits for legacy and previous-version restore acknowledgements, then attaches once and reports the search button state')
    checks.append('Notification upgrades accept a fresh restore receipt despite an unchanged file time or a delayed rename, reject stale and foreign receipts, and resume the handoff when the date window opens.')
    checks.append('Start keeps its layout during automatic color sampling. Its inner widths cannot override the shared panel dimensions.')
    checks.append('Shell cold start recovers from staging failure, absent/late/restarted hosts and an expired three-attempt backoff; saved choices remain enabled. OS calls mocked.')
    checks.append('Shell attachment drains ready hosts without discovery-delay gaps, prioritizes new hosts over retries and cancels pending work on close; OS calls mocked.')

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
                action(taskbar,'文字随壁纸自动切换黑白色').trigger()
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
