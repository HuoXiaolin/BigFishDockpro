"""Verify the two import features against an isolated temporary configuration."""
import json
import os
from pathlib import Path
import tempfile
import traceback
import faulthandler

_fault_logs = []


def run(output):
    if not __debug__:
        raise RuntimeError('Self-tests require assertions enabled; rebuild with optimize=0.')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    fault_log = (output/'native-fault.log').open('w', encoding='utf-8')
    _fault_logs.append(fault_log)
    faulthandler.enable(file=fault_log, all_threads=True)
    checks = []
    importer = None
    app = tray = None
    original_discovery = None
    test_run_key = None
    try:
        from run_isolated_test import assert_isolated
        desktop = assert_isolated()
        checks.append('verified separate desktop: ' + desktop)
        import dock as api
        from app_catalog import discover_apps, merge_items
        from batch_import import BatchImporter
        from ui_style import apply_theme
        from PyQt5.QtCore import Qt, QMimeData, QUrl, QPoint, QPointF
        from PyQt5.QtGui import QDragEnterEvent, QDropEvent
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(['BigFishDockpro test'])
        app.setQuitOnLastWindowClosed(False)
        apply_theme(app, True)
        from dpi_support import awareness
        assert awareness()==2
        checks.append('DPI startup: GUI thread is per-monitor aware before native windows, Qt high-DPI attributes and fractional scaling configured')
        with tempfile.TemporaryDirectory(prefix='fishdock-test-') as root:
            api.CONFIG_DIR = root
            api.CONFIG_PATH = os.path.join(root, 'config.json')
            api.LOG_PATH = os.path.join(root, 'dock.log')
            import uuid
            api.RUN_KEY = test_run_key = r'Software\BigFishDockpro_Test_'+uuid.uuid4().hex
            files = []
            for name in ['中文 应用.url', 'editor.url', 'notes.url']:
                path = Path(root, name)
                path.write_text('[InternetShortcut]\nURL=https://example.com/'+name+'\n', encoding='utf-8')
                files.append(str(path))
            cfg = dict(api.DEFAULT_CONFIG, items=[])
            dock = api.Dock(cfg, preview=True)
            assert awareness(int(dock.winId()))==2
            tray = api.DockTray(dock)
            dock.tray = tray
            importer = tray.importer = BatchImporter(dock, tray, api.save_config)
            found = discover_apps([root], include_store=False)
            import batch_import
            original_discovery = batch_import.discover_apps
            batch_import.discover_apps = lambda **options: discover_apps([root], include_store=False, **options)
            assert len(found) == 3
            checks.append('discovery: Unicode paths and launchable extensions')
            _, added, duplicates, invalid = merge_items([], [{'path': files[0]}, {'path': files[0].upper()}, {'path': root+'\\missing.exe'}])
            assert (added, duplicates, invalid) == (1, 1, 1)
            checks.append('batch: case-insensitive duplicates and missing paths')
            importer.show()
            batch = importer.dialog
            batch.worker.wait(27000)
            app.processEvents()
            batch.discovered(found)
            batch.select_visible()
            batch.query.setText('editor')
            assert len(batch.selected[0]) == 3 and batch.list.count() == 1
            batch.perform()
            assert len(cfg['items']) == 0 and len(batch.pending_add) == 1
            assert len(batch.selected[0]) == 2
            batch.reject()
            assert cfg['items'] == [] and not batch.pending_add
            batch.reveal()
            batch.query.clear()
            batch.select_visible()
            batch.perform()
            assert cfg['items'] == [] and len(batch.pending_add) == 3
            batch.commit()
            assert len(cfg['items']) == 3
            assert batch.isVisible() and not batch.pending_add and '已保存' in batch.pending.text()
            assert api.load_config()['items'] == cfg['items']
            checks.append('batch add: hidden selection excluded, staged changes cancel safely, save persists')
            batch.reveal()
            batch.tabs.setCurrentIndex(1)
            batch.select_visible()
            batch.query.setText('editor')
            batch.perform()
            assert len(batch.pending_remove) == 1 and len(cfg['items']) == 3
            batch.reject()
            assert len(cfg['items']) == 3
            batch.reveal()
            batch.query.clear()
            batch.select_visible()
            batch.clear_selection()
            assert len(batch.selected[1]) == 0
            batch.select_visible()
            batch.perform()
            assert len(batch.pending_remove) == 3
            batch.commit()
            assert cfg['items'] == [] and api.load_config()['items'] == []
            assert all(Path(f).exists() for f in files)
            checks.append('batch remove: current filter only, cancel selection, cancel edits, remove preserves files')
            batch.reveal()
            batch.tabs.setCurrentIndex(0)
            batch.query.clear()
            batch.select_visible()
            batch.perform()
            original_save = importer.save
            importer.save = lambda _: False
            batch.commit()
            assert cfg['items'] == [] and len(batch.pending_add) == 3
            importer.save = original_save
            batch.commit()
            checks.append('save failure: no in-memory mutation, staged edits retained for retry')
            batch.reveal()
            batch.tabs.setCurrentIndex(1)
            batch.select_visible()
            for theme in ('light', 'dark'):
                apply_theme(app, theme == 'light')
                app.processEvents()
                batch.grab().save(str(output/('batch-'+theme+'.png')))
            batch.reject()
            checks.append('native batch dialog rendered in light and dark themes')
            from interaction_tests import run as check_interactions
            check_interactions(api, dock, importer, root, output, checks)
            from settings_dialog import SettingsDialog
            from types import SimpleNamespace
            display_api = SimpleNamespace(**dict(api.__dict__, CONFIG_DIR=r'C:\Users\Demo\AppData\Roaming\BigFishDock'))
            settings = SettingsDialog(tray, display_api)
            before = dict(cfg)
            settings.reveal()
            settings.fields['icon_size'].setValue(62)
            settings.reject()
            assert cfg == before
            settings.reveal()
            settings.fields['icon_size'].setValue(62)
            settings.commit()
            assert cfg['icon_size'] == 62 and api.load_config()['icon_size'] == 62
            assert settings.isVisible() and '已保存' in settings.status.text()
            checks.append('settings: cancel leaves configuration unchanged; save and reload match')
            for theme in ('light', 'dark'):
                apply_theme(app, theme == 'light')
                settings.reveal()
                for tab in range(3):
                    settings.tabs.setCurrentIndex(tab)
                    app.processEvents()
                    settings.grab().save(str(output/('settings-%s-%d.png' % (theme, tab))))
                settings.resize(560, 440)
                settings.tabs.setCurrentIndex(1)
                app.processEvents()
                settings.grab().save(str(output/('settings-small-'+theme+'.png')))
                settings.resize(740, 600)
                settings.reject()
            checks.append('native settings rendered: all tabs, light/dark, minimum size')
            cfg['items'] = []
            dock.reload()
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(f) for f in files[:2]])
            enter = QDragEnterEvent(QPoint(40, 40), Qt.CopyAction | Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
            dock.dragEnterEvent(enter)
            assert enter.isAccepted() and enter.dropAction() == Qt.CopyAction
            drop = QDropEvent(QPointF(40, 40), Qt.CopyAction | Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
            dock.dropEvent(drop)
            assert drop.isAccepted() and len(cfg['items']) == 2
            assert all(Path(f).exists() for f in files)
            dock.dropEvent(drop)
            assert len(cfg['items']) == 2
            remote = QMimeData()
            remote.setUrls([QUrl('https://example.com')])
            blocked = QDragEnterEvent(QPoint(40, 40), Qt.CopyAction, remote, Qt.LeftButton, Qt.NoModifier)
            dock.dragEnterEvent(blocked)
            assert not blocked.isAccepted()
            checks.append('drop: multi-file CopyAction, originals preserved, duplicates skipped, non-local URLs rejected')
            assert api.load_config()['items'] == cfg['items']
            checks.append('drop: persisted paths survive configuration reload')
            assert cfg.keys() == api.DEFAULT_CONFIG.keys()
            tray.rebuild()
            labels = [a.text() for a in tray.menu.actions()]
            assert '应用批量管理…' in labels and '设置…' in labels
            assert not any(any(extra in title for extra in ['启动器', '小组件', '快捷设置', '状态栏']) for title in labels)
            checks.append('original batch management and settings remain compatible')
            dock.grab().save(str(output/'dock.png'))
            from feature_tests import run as run_features
            run_features(api, dock, tray, root, output, checks)
            importer.close()
            app.aboutToQuit.disconnect(importer.close)
            importer = None
            dock.hide()
            tray.hide()
        (output/'result.json').write_text(json.dumps({'passed': True, 'checks': checks}, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0
    except Exception:
        (output/'result.json').write_text(json.dumps({'passed': False, 'checks': checks, 'error': traceback.format_exc()}, ensure_ascii=False, indent=2), encoding='utf-8')
        if importer:
            importer.close()
        return 1
    finally:
        if test_run_key:
            import winreg
            try: winreg.DeleteKey(winreg.HKEY_CURRENT_USER, test_run_key)
            except FileNotFoundError: pass
        if original_discovery is not None:
            batch_import.discover_apps = original_discovery
        if app is not None:
            runtime = getattr(tray, 'runtime', None) if tray is not None else None
            if runtime is not None: runtime.close()
            from ui_style import shutdown_ui
            shutdown_ui(app)
            assert not app.topLevelWidgets(), 'GUI resources remain after explicit shutdown'
