"""Focused private-desktop entry point for the native shell settings pages."""
import json
from pathlib import Path
import sys
import tempfile
import traceback
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / name) for name in ('app', 'tests', 'tools')]


def main(output):
    from run_isolated_test import assert_isolated
    assert_isolated()
    output = Path(output)
    checks = []
    runtime = None
    try:
        from PyQt5.QtWidgets import QApplication
        from ui_style import apply_theme, shutdown_ui
        from runtime_controller import RuntimeController
        import dock as api
        from shell_appearance_tests import run
        app = QApplication([]);app.setQuitOnLastWindowClosed(False);apply_theme(app, True)
        with tempfile.TemporaryDirectory(prefix='fishdock-shell-ui-') as root:
            api.CONFIG_DIR = root;api.CONFIG_PATH = str(Path(root) / 'config.json');api.LOG_PATH = str(Path(root) / 'dock.log')
            cfg = api.normalize_features(dict(api.DEFAULT_CONFIG))
            cfg.update(items=[], resource_enabled=False, resource_taskbar=False, panel_enabled=False, hide_tray=True,
                       check_updates_on_start=False, settings_size='medium')
            dock = api.Dock(cfg, preview=True);tray = api.DockTray(dock);dock.tray = tray
            runtime = tray.runtime = RuntimeController(dock, tray, api)
            run(api, runtime, root, app, output, checks)
            runtime.close();runtime = None;shutdown_ui(app)
        result = {'passed': True, 'checks': checks}
    except Exception:
        result = {'passed': False, 'checks': checks, 'error': traceback.format_exc()}
    finally:
        if runtime:
            runtime.close()
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[-1]))
