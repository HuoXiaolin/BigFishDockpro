"""Failure/recovery checks using temporary files, fake requests and fake processes."""
import copy
import json
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PyQt5.QtCore import QObject, QProcess, pyqtSignal


def check_config_store():
    from config_store import ConfigStore, _atomic
    with tempfile.TemporaryDirectory(prefix='bfp-config-recovery-') as folder:
        path = Path(folder)/'config.json'
        log = Mock()
        original = {'items': [{'path': 'C:/Demo/App.exe'}], 'icon_size': 52}
        store = ConfigStore(path, log)
        assert store.load(original) == original
        assert store.save(original)
        broken = b'{broken-json-original'
        path.write_bytes(broken)
        store = ConfigStore(path, log)
        assert store.load({'items': [], 'icon_size': 42}) == original
        assert not store.blocked and store.damaged.read_bytes() == broken
        assert store.save(original) and json.loads(path.read_text(encoding='utf-8')) == original
        assert store.damaged.read_bytes() == broken
        assert len(list(Path(folder).iterdir())) == 3
        # Without a usable backup, defaults must never silently replace the source.
        store.backup.unlink()
        path.write_bytes(broken)
        store = ConfigStore(path, log)
        assert store.load({'items': []}) == {'items': []}
        assert store.blocked and not store.save({'items': []})
        assert path.read_bytes() == broken
        assert store.save({'items': []}, explicit_recovery=True)
        assert not store.blocked and store.damaged.read_bytes() == broken
        # If preserving the damaged original fails, even a reset is refused.
        path.write_bytes(b'[{bad-new-data')
        store = ConfigStore(path, log)
        def protected_write(target, payload):
            if Path(target) == store.damaged:
                raise OSError('simulated archive permission denied')
            return _atomic(target, payload)
        with patch('config_store._atomic', side_effect=protected_write):
            store.load({'items': []})
            assert store.blocked and not store.save({'items': []}, explicit_recovery=True)
        assert path.read_bytes() == b'[{bad-new-data'
        # A read failure remains protected even when a valid recovery copy exists.
        actual_read = Path.read_bytes
        def failed_read(target):
            if target == path:
                raise PermissionError('simulated sharing violation')
            return actual_read(target)
        store = ConfigStore(path, log)
        with patch('config_store.Path.read_bytes', new=failed_read):
            store.load({'items': []})
            assert store.blocked and not store.save({'items': []}, explicit_recovery=True)
        assert path.read_bytes() == b'[{bad-new-data'
        # Failed atomic replacement leaves the current valid file and backup intact.
        assert store.save(original, explicit_recovery=True)
        before = path.read_bytes()
        import os
        replace = os.replace
        def fail_replace(source, target):
            if Path(target) == path:
                raise OSError('simulated replace failure')
            return replace(source, target)
        with patch('config_store.os.replace', side_effect=fail_replace):
            assert not store.save({'items': []})
        assert path.read_bytes() == before and not list(Path(folder).glob('*.tmp'))
        with patch('config_store._atomic') as write:
            assert store.save(original) and not write.called


def check_update_generation(app):
    from update_service import UpdateService
    class FakeWorker(QObject):
        ready = pyqtSignal(object)
        failed = pyqtSignal(str)
        finished = pyqtSignal()
        def __init__(self, source, proxy):
            super().__init__()
            self.source, self.proxy = source, proxy
            self.cancelled = threading.Event()
            self.running = True
        def start(self): pass
        def isRunning(self): return self.running
        def wait(self, milliseconds): pass
    cfg = {'update_source': 'https://old.example/version.json', 'update_use_proxy': True}
    runtime = SimpleNamespace(dock=SimpleNamespace(cfg=cfg), tray=SimpleNamespace(showMessage=Mock(), icon=lambda: None), api=SimpleNamespace(log=Mock()))
    service = UpdateService(runtime)
    result = {'newer': True, 'version': '9.0.0', 'release_url': 'https://old.example/download'}
    with patch('update_service.UpdateWorker', FakeWorker):
        service.check()
        old = service.worker
        cfg['update_source'] = 'https://new.example/version.json'
        service.settings_changed()
        message = service.message
        old.ready.emit(result)
        old.failed.emit('stale request failure')
        assert service.message == message and not service.release_url
        assert not runtime.tray.showMessage.called
        # Only one request runs at once; a requested recheck follows worker completion.
        service.check()
        assert service.worker is old and service.restart_requested
        old.running = False
        old.finished.emit()
        app.processEvents()
        current = service.worker
        assert current is not None and current is not old and current.source == cfg['update_source']
        current.ready.emit(dict(result, release_url='https://new.example/download'))
        assert service.release_url == 'https://new.example/download'
        before = service.message
        service.close()
        current.ready.emit(result)
        assert service.release_url == 'https://new.example/download' and service.message == before


def check_taskbar_retries():
    from taskbar_appearance import TaskbarAppearance
    from taskbar_xaml import XamlTaskbar, effect_key
    class FakeDock(QObject):
        def __init__(self):
            super().__init__()
            self.cfg = {'taskbar_mode': 'clear', 'taskbar_color': '#85c6ed', 'taskbar_opacity': 32, 'taskbar_blur': 12}
    dock = FakeDock()
    component = TaskbarAppearance.__new__(TaskbarAppearance)
    component.dock = dock
    component.text = Mock()
    component.error = ''
    backend = XamlTaskbar(dock, Path(tempfile.gettempdir())/'bfp-fake-taskbar', Mock(), component.xaml_completed)
    component.xaml = component.backend = backend
    state = [QProcess.NotRunning]
    def start():
        state[0] = QProcess.Running
        backend.process.started.emit()
    def terminate():
        state[0] = QProcess.NotRunning
        backend.process.finished.emit(0, QProcess.NormalExit)
    try:
        with patch.object(backend, 'write', side_effect=[OSError('simulated write denied'), None, None]) as write, \
             patch.object(backend.process, 'state', side_effect=lambda: state[0]), \
             patch.object(backend.process, 'start', side_effect=start) as starts, \
             patch.object(backend.process, 'terminate', side_effect=terminate):
            assert not component.sync() and component.error and component._effect is None
            assert write.call_count == 1 and starts.call_count == 0
            assert component.retry() and not component.error
            assert write.call_count == 2 and starts.call_count == 1
            assert component._effect == effect_key(dock.cfg)
            # Text-only changes do not restart the successfully applied background.
            dock.cfg['taskbar_text_mode'] = 'light'
            component.sync()
            assert starts.call_count == 1
            # Unexpected exit invalidates the cache and can be retried unchanged.
            state[0] = QProcess.NotRunning
            backend.process.finished.emit(1, QProcess.CrashExit)
            assert component.error and component._effect is None
            component.retry()
            assert starts.call_count == 2 and not component.error
            state[0] = QProcess.NotRunning
    finally:
        backend.close()
        backend.process.deleteLater()
        backend.stop_timer.deleteLater()


def check_taskbar_shell_recovery(checks):
    from taskbar_xaml import XamlTaskbar
    with tempfile.TemporaryDirectory(prefix='bfp-taskbar-boot-') as directory:
        dock=QObject()
        dock.cfg={'taskbar_mode':'clear','taskbar_color':'#85c6ed','taskbar_opacity':32,'taskbar_blur':12}
        complete = Mock()
        backend=XamlTaskbar(dock,Path(directory),Mock(),complete)
        backend.monitor_shell=True
        state=[QProcess.NotRunning]
        def start():
            state[0]=QProcess.Running
            backend.started()
        with patch('taskbar_xaml.shell_snapshot',return_value=None) as shell, \
             patch('taskbar_xaml.monotonic',return_value=10) as clock, \
             patch('taskbar_xaml.allowed',return_value=True) as allowed, \
             patch('taskbar_xaml.request_refresh',side_effect=[False,True,True,True,True,True]) as refresh, \
             patch('taskbar_xaml.resident_program',return_value=None), \
             patch.object(backend.process,'state',side_effect=lambda:state[0]), \
             patch.object(backend.process,'processId',return_value=901), \
             patch.object(backend.process,'start',side_effect=start) as starts:
            def stop():
                state[0] = QProcess.NotRunning
                backend.finished()
            def apply():
                backend.apply_timer.stop()
                backend.apply_desired()
            def connect():
                backend.refresh_timer.stop()
                backend.refresh_backend()
            try:
                backend.sync()
                assert backend.shell_timer.isActive() and not starts.called
                shell.return_value=(10, 50, ())
                backend.shell_changed()
                clock.return_value=18
                backend.shell_changed()
                assert not backend.apply_timer.isActive()
                apply()
                assert not starts.called and not complete.called
                # The same outer taskbar gets its XAML children later.
                shell.return_value=(10, 50, (101,))
                backend.shell_changed()
                assert backend.apply_timer.isActive() and not starts.called
                with patch.object(backend.process, 'start') as slow_start:
                    apply()
                    slow_start.assert_called_once()
                backend.failed(QProcess.FailedToStart)
                assert backend.apply_timer.isActive() and backend.retries==1
                apply()
                assert starts.call_count==1 and backend.configuration_matches(dock.cfg)
                assert backend.refresh_timer.isActive() and not complete.call_args.args[1]
                connect()
                assert backend.refresh_timer.isActive() and not complete.call_args.args[1]
                connect()
                refresh.assert_called_with(backend.program, 901)
                assert complete.call_args.args[1] and not backend.refresh_timer.isActive()
                # Reload and refresh the same process after the visual tree is replaced.
                shell.return_value=(10, 50, (102,))
                backend.shell_changed()
                assert backend.apply_timer.isActive()
                apply()
                connect()
                assert refresh.call_count==3 and starts.call_count==1
                # Saving another mode during recovery uses the most recent config.
                state[0]=QProcess.NotRunning;backend.finished(1,QProcess.CrashExit)
                assert backend.apply_timer.isActive()
                dock.cfg['taskbar_mode']='acrylic'
                backend.sync()
                apply()
                assert starts.call_count==2
                assert backend.configuration_matches(dock.cfg)
                # Logout blocks an already queued callback; cancellation resumes recovery.
                allowed.return_value=False
                backend.suspend_session()
                connect()
                apply()
                assert refresh.call_count==3 and starts.call_count==2
                assert not backend.shell_timer.isActive() and not backend.refresh_timer.isActive()
                allowed.return_value=True
                backend.sync(force=True)
                connect()
                assert backend.shell_timer.isActive() and refresh.call_count==4
                # Reused HWND with a different Explorer PID is a new shell.
                shell.return_value=(10, 51, (102,))
                backend.shell_changed()
                assert backend.apply_timer.isActive()
                apply()
                connect()
                assert refresh.call_count==5 and starts.call_count==2
                dock.cfg['taskbar_mode']='system'
                with patch.object(backend.process,'terminate',side_effect=stop):
                    backend.sync()
                assert not backend.desired and not backend.shell_timer.isActive()
                assert not backend.apply_timer.isActive() and not backend.refresh_timer.isActive()
                # Classic (or replaced) taskbars on Win11 may never have an island.
                dock.cfg['taskbar_mode']='clear'
                shell.return_value=(15, 52, ())
                backend.sync()
                assert not backend.apply_timer.isActive()
                clock.return_value=45
                backend.shell_changed()
                assert backend.apply_timer.isActive()
                apply()
                connect()
                assert starts.call_count==3 and complete.call_args.args[1]
            finally:
                state[0]=QProcess.NotRunning
                backend.close()
    checks.append('Taskbar: late XAML on the same HWND, classic fallback, late worker, failed launch, pid/child rebuilding, latest mode and cancelled Windows logoff use bounded recovery without a second live backend.')


def check_taskbar_effect_status(runtime, checks):
    from taskbar_appearance import TaskbarAppearance
    from taskbar_xaml import XamlTaskbar, effect_key
    from dock_extras import DockQuickSettings

    dock = runtime.dock
    original = {k:dock.cfg[k] for k in ('taskbar_mode','taskbar_color','taskbar_opacity','taskbar_blur',
                'shell_notifications_enabled','shell_notifications_tray_overflow','shell_notifications_source',
                'shell_notifications_material','shell_notifications_theme','shell_notifications_color',
                'shell_notifications_opacity','shell_notifications_blur')}
    saved_component = runtime.taskbar
    component = TaskbarAppearance(dock, Mock())  # The private desktop disables native effects.
    runtime.taskbar = component
    with tempfile.TemporaryDirectory(prefix='bfp-taskbar-status-') as directory:
        backend = XamlTaskbar(dock, Path(directory), component.log, component.xaml_completed)
        component.xaml = component.backend = backend
        state = QProcess.NotRunning
        def start():
            nonlocal state
            state = QProcess.Running
            backend.process.started.emit()
        def finish(code=0, status=QProcess.NormalExit):
            nonlocal state
            state = QProcess.NotRunning
            backend.process.finished.emit(code, status)
        popup = DockQuickSettings(dock.extras)
        try:
            with patch('taskbar_xaml.resident_program', return_value=None) as resident, \
                 patch.object(backend.process,'state',side_effect=lambda:state), \
                 patch.object(backend.process,'start',side_effect=start) as starts, \
                 patch.object(backend.process,'terminate') as stops:
                dock.cfg['taskbar_mode'] = 'clear'
                assert component.sync()
                popup.refresh()
                for mode in ('color','acrylic','glass','clear'):
                    dock.cfg['taskbar_mode'] = mode
                    assert component.sync() and backend.configuration_matches(dock.cfg)
                assert starts.call_count == 1 and not stops.called

                backend.process.errorOccurred.emit(QProcess.ReadError)
                assert not component.error and popup.tiles['taskbar'].value == '全透明'
                resident.return_value = backend.program
                component.set_status('旧状态','旧错误')
                assert popup.tiles['taskbar'].value == '应用失败'
                popup.show()
                assert popup.tiles['taskbar'].value == '全透明' and not component.error
                assert '失败' not in popup.status.text() and not popup.status.toolTip()

                dock.cfg['taskbar_mode'] = 'color'
                with patch.object(backend, 'write', side_effect=PermissionError('denied')):
                    assert not component.sync()
                component.reconcile_status()
                assert component.error and popup.tiles['taskbar'].value == '应用失败'
                assert component.retry() and popup.tiles['taskbar'].value == '自定义颜色'
                # An old request cannot overwrite a newer selection.
                component.xaml_completed(effect_key(dict(dock.cfg,taskbar_mode='clear')),False,'old')
                assert not component.error

                # A -> system -> A while the owned process is stopping.
                resident.return_value = None
                dock.cfg['taskbar_mode'] = 'system'
                component.sync()
                dock.cfg['taskbar_mode'] = 'color'
                component.sync()
                assert stops.call_count == 1 and popup.tiles['taskbar'].value == '正在应用…'
                finish()
                assert starts.call_count == 2 and not backend.stop_timer.isActive()
                assert popup.tiles['taskbar'].value == '自定义颜色'
                # A normal handoff is valid only with the exact resident and matching JSON.
                resident.return_value = backend.program
                finish()
                assert backend.shared and not component.error
                dock.cfg['taskbar_mode'] = 'glass'
                assert component.sync() and starts.call_count == 2
                resident.return_value = Path(directory).parent/'other'/'TranslucentTB.exe'
                component.reconcile_status()
                assert component.error and popup.tiles['taskbar'].value == '应用失败'
                finish()
                assert component.error
                component.reconcile_status()
                assert popup.tiles['taskbar'].value == '应用失败'
                resident.return_value = None
                assert component.retry()
                finish(1,QProcess.CrashExit)
                assert component.error and '退出码 1' in component.error
                with patch.object(backend.process, 'start', side_effect=lambda:backend.process.errorOccurred.emit(QProcess.FailedToStart)):
                    assert not component.retry()
                    assert '未能启动' in component.error
                assert component.retry() and not component.error
                dock.cfg['taskbar_mode'] = 'system'
                component.sync()
                finish()
                assert popup.tiles['taskbar'].value == '跟随系统' and not component.error
                with patch('shell_appearance.system_appearance',return_value=(True,True)):
                    dock.cfg.update(shell_notifications_enabled=True,shell_notifications_tray_overflow=True,
                                    shell_notifications_source='custom',shell_notifications_material='liquid',
                                    shell_notifications_theme='light',shell_notifications_color='#4d92bf',
                                    shell_notifications_opacity=33,shell_notifications_blur=16)
                    started = starts.call_count
                    component.sync()
                    path = Path(directory) / 'tray-overflow.ini'
                    assert starts.call_count == started + 1 and state == QProcess.Running
                    assert 'Brush=3\nTint=544d92bf\nAmount=1600\n' in path.read_text(encoding='ascii')
                    from json import loads
                    data = loads((Path(directory) / 'settings.json').read_text(encoding='utf-8'))
                    assert data['desktop_appearance']['accent']=='normal' and data['desktop_appearance']['show_line']
                    assert not data['copy_dlls']
                    dock.cfg['shell_notifications_opacity']=51
                    component.sync()
                    assert 'Tint=824d92bf' in path.read_text(encoding='ascii') and starts.call_count==started+1
                    dock.cfg['shell_notifications_tray_overflow']=False
                    component.sync()
                    finish()
                    assert path.read_text(encoding='ascii')=='[Appearance]\nBrush=0\n'
            checks.append('Taskbar: live config reload reuses one simulated process; channel errors, stale notifications, rapid reversal and verified same-path handoff keep the mode label. Disk mismatch, foreign instance, start failure and crash remain visible; Quick Settings reopens and recovers from stale failure. No desktop taskbar modified.')
            checks.append('Tray overflow takes the notification tint and blur. It starts the shared worker with the taskbar in system mode, reloads opacity without a second worker, and restores the overflow settings when disabled.')
        finally:
            state = QProcess.NotRunning
            popup.close()
            popup.deleteLater()
            component.close()
            runtime.taskbar = saved_component
            dock.cfg.update(original)


def run(api, runtime, main, app, output, checks):
    from config_store import ConfigStore
    from feature_config import LEGACY_STYLE_DEFAULTS
    from appearance_profiles import selected_mode
    with tempfile.TemporaryDirectory(prefix='config-migration-') as folder:
        target=Path(folder)/'config.json';store=ConfigStore(target,lambda message:None)
        fresh=api.normalize_features(store.load(api.DEFAULT_CONFIG,LEGACY_STYLE_DEFAULTS))
        assert fresh['dock_material']=='crystal' and selected_mode(fresh)=='crystal'
        legacy={'items':[],'icon_size':52,'transparency':17,'theme_color':'#edb080'}
        target.write_text(json.dumps(legacy),encoding='utf-8');raw=target.read_bytes()
        loaded=api.normalize_features(store.load(api.DEFAULT_CONFIG,LEGACY_STYLE_DEFAULTS))
        assert loaded['dock_material']=='liquid' and loaded['card_design']=='aurora' and selected_mode(loaded)=='custom'
        assert loaded['transparency']==17 and loaded['theme_color']=='#edb080' and target.read_bytes()==raw
        target.write_text(json.dumps(fresh),encoding='utf-8')
        assert store.load(api.DEFAULT_CONFIG,LEGACY_STYLE_DEFAULTS)['dock_material']=='crystal'
    checks.append('style migration: missing file uses crystal; sparse existing config keeps legacy defaults and saved values without rewriting; explicit crystal remains unchanged')

    from config_transfer import read_configuration
    with tempfile.TemporaryDirectory(prefix='legacy-feature-defaults-') as folder:
        path = Path(folder)/'config.json'
        legacy = dict(items=[{'sep': True}], icon_size=48, position='bottom', theme='dark', autostart=False,
                      panel_geometry=[20, 30, 480, 280])
        off_by_default = ('panel_enabled', 'resource_taskbar', 'resource_ai_tray', 'flash_enabled',
                          'resource_face_auto_switch', 'panel_face_auto_switch')
        enabled = ('resource_enabled', 'resource_face', 'resource_face_interactive', 'resource_weather',
                   'resource_ai', 'resource_music', 'resource_bt_tray', 'clock_enabled', 'notes_enabled',
                   'panel_face', 'panel_face_interactive')
        saved = dict(resource_face=False, resource_ai=False, resource_music=False,
                     resource_weather=False, clock_enabled=False, flash_enabled=True,
                     panel_face=False, panel_face_interactive=False, resource_face_interactive=False,
                     resource_face_auto_switch=True, resource_face_switch_minutes=17,
                     panel_face_auto_switch=True, panel_face_switch_minutes=20)
        with patch.object(api, 'CONFIG_PATH', str(path)), patch.object(api, '_config_store', None):
            for additions in ({}, saved):
                previous = dict(legacy, **additions)
                payload = json.dumps(previous).encode('utf-8')
                path.write_bytes(payload)
                for config in (api.load_config(), read_configuration(path, api)):
                    assert all(config[key] == value for key, value in previous.items())
                    assert all(config[key] is True for key in enabled if key not in additions)
                    assert all(config[key] is False for key in off_by_default if key not in additions)
                    assert config['resource_face_switch_minutes'] == additions.get('resource_face_switch_minutes', 10)
                    assert config['panel_face_switch_minutes'] == additions.get('panel_face_switch_minutes', 10)
                    assert config['resource_expand_mode'] == 'click' and not config['display_layout'].get('panels')
                assert path.read_bytes() == payload
    checks.append('Legacy profiles and imports fill missing features from bundled defaults, including the capsule face, while saved values and legacy layout remain intact.')

    check_config_store()
    check_update_generation(app)
    check_taskbar_retries()
    check_taskbar_shell_recovery(checks)
    check_taskbar_effect_status(runtime, checks)
    checks.append('configuration recovery: bounded last-good/damaged copies, corrupted/unreadable source protection, explicit recovery and atomic failure; update source generations discard stale success/error and serialize rechecks; taskbar write failure/exit retry and text-only cache via fake process; no system settings or network changed')
