"""Verify the actual application entry point without touching personal data."""
import json
import time
from pathlib import Path


class StartupProbe:
    def __init__(self, args, api):
        from run_isolated_test import assert_isolated
        self.desktop = assert_isolated()
        self.output = Path(args[args.index('--startup-test')+1]).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.autostart = '--autostart' in args
        self.started = time.monotonic()
        api.CONFIG_DIR = str(self.output/'test-config')
        api.CONFIG_PATH = str(self.output/'test-config/config.json')
        api.LOG_PATH = str(self.output/'test-config/dock.log')
        api.RUN_KEY = r'Software\BigFishDockpro_Test_'+self.desktop
        cfg = dict(api.DEFAULT_CONFIG, items=[], autostart=False, glass=False, running_dots=False,
                   startup_delay=1, screen_corners=False, check_updates_on_start=False)
        if not api.save_config(cfg):
            raise RuntimeError('Cannot prepare isolated startup configuration')

    def complete(self, state):
        from PyQt5.QtWidgets import QApplication
        import traceback
        try:
            dock, tray, runtime = state['dock'], state['tray'], state['runtime']
            assert dock.isVisible() is not self.autostart
            elapsed = time.monotonic()-self.started
            if self.autostart:
                assert elapsed >= .9
            runtime.set_lite(True)
            runtime.show_settings()
            assert not runtime.lite and runtime.settings_open
            assert not runtime.lite_timer.isActive()
            tray.settings_dialog.reject()
            assert not runtime.settings_open and runtime.lite_timer.isActive()
            assert runtime.lite_timer.interval() == 60000
            result = {'passed':True, 'checks':['actual application initialization on '+self.desktop,
                      'autostart delay and silent tray' if self.autostart else 'manual start shows Dock without delay',
                      'actual settings-open wake and finished-signal starts 60-second timer'],
                      'elapsed_seconds':round(elapsed,2)}
        except Exception:
            result = {'passed':False, 'error':traceback.format_exc()}
        (self.output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2),encoding='utf-8')
        QApplication.instance().quit()
