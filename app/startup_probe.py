"""Verify the actual application entry point without touching personal data."""
import json
import os
import time
from pathlib import Path


class StartupProbe:
    def __init__(self, args, api):
        from run_isolated_test import assert_isolated
        self.desktop = assert_isolated()
        self.output = Path(args[args.index('--startup-test')+1]).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.autostart = '--autostart' in args
        self.fresh = '--fresh-profile' in args
        self.visibility = '--visibility-profile' in args
        self.resume = '--resume-profile' in args
        self.started = time.monotonic()
        api.CONFIG_DIR = str(self.output/'test-config')
        api.CONFIG_PATH = str(self.output/'test-config/config.json')
        api.LOG_PATH = str(self.output/'test-config/dock.log')
        api.RUN_KEY = r'Software\BigFishDockpro_Test_'+self.desktop
        if self.visibility:
            self.api=api
            if self.resume:
                self.expected=api.load_config();return
            cfg=api.normalize_features(dict(api.DEFAULT_CONFIG,items=[],autostart=False,glass=False,running_dots=False,startup_delay=0,
                screen_corners=False,check_updates_on_start=False,fullscreen_detection=False,game_mode=False,lite_enabled=False,runtime_lite=False,
                dock_visible=True,panel_enabled=True,panels_visible=True,notes_enabled=True,notes_visible=True,clock_enabled=True,desktop_auto_sort=False,panel_auto_hide=False,
                desktop_panels=[{'id':'images','name':'恢复测试','geometry':[70,90,340,220]}]))
            assert api.save_config(cfg);self.expected=cfg
            (self.output/'visibility-phase.json').write_text('0',encoding='utf-8');return
        if self.fresh:
            (self.output/'test-config').mkdir(parents=True,exist_ok=True)
            Path(api.CONFIG_PATH).unlink(missing_ok=True)
            return
        cfg = dict(api.DEFAULT_CONFIG, card_scale=100,settings_size='small', items=[], autostart=False, glass=False, running_dots=False,
                   startup_delay=1, screen_corners=False, check_updates_on_start=False,
                   dock_visible=self.autostart, panels_visible=self.autostart, hide_tray=self.autostart,
                   runtime_lite=self.autostart, panel_enabled=True, panel_auto_hide=False, desktop_auto_sort=False,
                   desktop_panels=[{'id':'images','name':'图片','geometry':[70,90,340,220],'collapsed':True}],
                   merged_panels=self.autostart, merged_active='images', merged_geometry=[88,96,360,240],
                   merged_collapsed=True, lite_restore={'images':False,'__merged__':False} if self.autostart else {})
        if not api.save_config(cfg):
            raise RuntimeError('Cannot prepare isolated startup configuration')

    def complete(self, state):
        from PyQt5.QtWidgets import QApplication
        import traceback
        if self.visibility:return self.complete_visibility(state)
        try:
            dock, tray, runtime = state['dock'], state['tray'], state['runtime']
            from dpi_support import awareness
            assert awareness()==2 and awareness(int(dock.winId()))==2 and dock.ui_mult==1.0
            if self.fresh:
                assert dock.isVisible() and not dock.cfg['panel_enabled']
                assert not runtime.panels.windows and not runtime.lite and tray.isVisible()
                assert '托盘' not in __import__('sys').modules[dock.__module__].EMPTY_DOCK_HINT
                dock.grab().save(str(self.output/'fresh-dock.png'))
            else:
                assert dock.isVisible() is self.autostart
                assert runtime.panels.shown is self.autostart
                assert runtime.lite is self.autostart
                assert tray.isVisible() is not self.autostart
                panel = runtime.panels.windows['images']
                assert panel.collapsed
                if self.autostart:
                    assert runtime.panels.active_window=='images' and panel.width()<=360 and panel.height()<240
                    assert panel.bounds()[2:]==[360,240]
                    assert runtime.dock.cfg['merged_geometry']==[88,96,360,240]
            elapsed = time.monotonic()-self.started
            if self.autostart:
                assert elapsed >= .9
            runtime.set_lite(True)
            runtime.show_settings()
            assert not runtime.lite and runtime.settings_open
            if self.autostart and not self.fresh: assert not panel.collapsed
            assert not runtime.lite_timer.isActive()
            tray.settings_dialog.reject()
            assert not runtime.settings_open and runtime.lite_timer.isActive()
            assert runtime.lite_timer.interval() == 60000
            result = {'passed':True, 'checks':['actual application initialization on '+self.desktop,
                      'fresh profile: visible Dock, cards disabled, tray visible, modern drag/context guidance' if self.fresh else 'login start restores visible Dock, hidden tray, lite mode and merged panel geometry/page/collapse after delay' if self.autostart else 'manual start restores hidden Dock and panels without delay',
                      'actual settings-open wake and finished-signal starts 60-second timer'],
                      'elapsed_seconds':round(elapsed,2)}
            fixture=os.environ.get('FISHDOCK_EXIT_LAUNCH_FIXTURE')
            if fixture:
                from external_launch import launch
                from desktop_panel_tests import wait_for
                import sys
                process=launch(fixture)
                report=Path(fixture+'.library.txt')
                wait_for(QApplication.instance(),lambda:report.exists() and report.stat().st_size>0,6)
                library=report.read_text(encoding='utf-8')
                assert not Path(library).resolve().is_relative_to(Path(sys._MEIPASS).resolve()),library
                assert process.poll() is None
                result['exit_cleanup']={'directory':sys._MEIPASS,'child_pid':process.pid,'library':library,'fixture':fixture}
                result['checks'].append('external native child remains alive using runtime outside this onefile payload before actual GUI quit')
                identity=runtime.notes.new()
                assert identity
                runtime.notes.windows[identity].editor.insertPlainText('退出前待保存的演示便签')
                assert runtime.notes.pending
                result['exit_note']={'id':identity,'configuration':str(self.output/'test-config/config.json'),'text':'退出前待保存的演示便签'}
        except Exception:
            result = {'passed':False, 'error':traceback.format_exc()}
        (self.output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2),encoding='utf-8')
        QApplication.instance().quit()

    def complete_visibility(self,state):
        from PyQt5.QtWidgets import QApplication
        import traceback
        try:
            api=self.api;dock=state['dock'];runtime=state['runtime'];cfg=dock.cfg
            expected=self.expected;phase=int((self.output/'visibility-phase.json').read_text(encoding='utf-8'))
            assert dock.isVisible()==expected['dock_visible']
            assert runtime.panels.windows['images'].isVisible()==expected['panels_visible']
            assert runtime.clock.isVisible()==expected['clock_enabled']
            if runtime.notes.windows:assert all(w.isVisible()==expected['notes_visible'] for w in runtime.notes.windows.values())
            if phase==0:
                assert runtime.notes.new()
                runtime.set_dock_visible(False);runtime.panels.toggle();runtime.notes.toggle();runtime.clock.set_enabled(False)
            elif phase==1:
                runtime.set_dock_visible(True);runtime.panels.reveal();runtime.notes.toggle();runtime.clock.set_enabled(True)
            assert runtime.checkpoint_session()
            # Simulate native hiding after the save. aboutToQuit must retain intent.
            dock.hide()
            for window in runtime.panels.windows.values():window.hide()
            for window in runtime.notes.windows.values():window.hide()
            runtime.clock.hide()
            result={'passed':True,'scope':'actual-process-visibility-restart','phase':phase,'checks':['actual app entry restores saved Dock/card/note/clock visibility','explicit toggles persisted before native shutdown hides','aboutToQuit persistence checked by the next cold process'],
                    'expected_on_entry':{key:expected[key] for key in ('dock_visible','panels_visible','notes_visible','clock_enabled')}}
            (self.output/'visibility-phase.json').write_text(str(phase+1),encoding='utf-8')
        except Exception:result={'passed':False,'error':traceback.format_exc()}
        (self.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        QApplication.instance().quit()
